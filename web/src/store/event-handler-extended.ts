/**
 * WebSocket 扩展事件处理器
 *
 * 仅在命中非首屏关键路径事件时按需加载，降低主包体积。
 */

import type {
  WSEvent,
  Message,
  AnalysisStep,
  AnalysisTaskItem,
  AnalysisPlanProgress,
  AnalysisTaskAttemptStatus,
  ArtifactInfo,
  RetrievalItem,
  StreamingMetrics,
} from "./types";
import type { AppStateSubset, GetStateFn, SetStateFn } from "./event-handler";

import {
  isRecord,
  nextId,
  nextAnalysisTaskId,
  makePlanProgressFromSteps,
  applyPlanStepUpdateToProgress,
  updateAnalysisTaskById,
  updateAnalysisTaskWithAttempt,
  findTaskIdByStepAndTurn,
  clampStepIndex,
} from "./utils";
import {
  normalizeAnalysisSteps,
  normalizePlanStepStatus,
  mergePlanStepStatus,
  createDefaultPlanSteps,
} from "./normalizers";
import { upsertAssistantTextMessage } from "./message-normalizer";
import { deriveNextHint } from "./plan-state-machine";

function extractPlanEventOrder(
  evt: WSEvent,
  payload?: Record<string, unknown> | null,
): number {
  const seqBase = 1_000_000_000_000_000;
  const seq = evt.metadata?.seq;
  if (typeof seq === "number" && Number.isFinite(seq)) return seqBase + seq;
  if (payload) {
    const payloadSeq = payload.seq;
    if (typeof payloadSeq === "number" && Number.isFinite(payloadSeq)) {
      return seqBase + payloadSeq;
    }
    const updatedAt = payload.updated_at;
    if (typeof updatedAt === "string" && updatedAt.trim()) {
      const parsed = Date.parse(updatedAt);
      if (!Number.isNaN(parsed)) return parsed;
    }
  }
  return Date.now();
}

function normalizeTaskAttemptStatus(raw: unknown): AnalysisTaskAttemptStatus {
  if (typeof raw !== "string") return "in_progress";
  const normalized = raw.trim().toLowerCase();
  switch (normalized) {
    case "retrying":
      return "retrying";
    case "success":
    case "done":
      return "success";
    case "failed":
    case "error":
      return "failed";
    default:
      return "in_progress";
  }
}

function applyPlanProgressPayload(
  s: AppStateSubset,
  payload: Record<string, unknown>,
): AnalysisPlanProgress | null {
  const totalRaw = payload.total_steps;
  const total =
    typeof totalRaw === "number" && Number.isFinite(totalRaw) && totalRaw > 0
      ? Math.floor(totalRaw)
      : s.analysisPlanProgress?.total_steps || 0;
  if (total <= 0) return s.analysisPlanProgress;

  const currentRaw = payload.current_step_index;
  const currentStepIndex =
    typeof currentRaw === "number" && Number.isFinite(currentRaw)
      ? clampStepIndex(Math.floor(currentRaw), total)
      : s.analysisPlanProgress?.current_step_index
        ? clampStepIndex(s.analysisPlanProgress.current_step_index, total)
        : 1;

  const incomingStatus = normalizePlanStepStatus(payload.step_status);
  const stepTitleRaw = payload.step_title;
  const incomingStepTitle =
    typeof stepTitleRaw === "string" && stepTitleRaw.trim()
      ? stepTitleRaw.trim()
      : s.analysisPlanProgress?.step_title || `步骤 ${currentStepIndex}`;
  const incomingNextHint =
    typeof payload.next_hint === "string" && payload.next_hint.trim()
      ? payload.next_hint.trim()
      : null;
  const blockReason =
    typeof payload.block_reason === "string" && payload.block_reason.trim()
      ? payload.block_reason.trim()
      : null;

  const baseSteps =
    s.analysisPlanProgress && s.analysisPlanProgress.steps.length > 0
      ? [...s.analysisPlanProgress.steps]
      : createDefaultPlanSteps(total);
  const steps = Array.from({ length: total }, (_, idx) => {
    const existingStep = baseSteps[idx];
    const fallbackStep: AnalysisStep = {
      id: idx + 1,
      title: `步骤 ${idx + 1}`,
      tool_hint: null,
      status: "not_started",
    };
    return existingStep ? { ...existingStep, id: idx + 1 } : fallbackStep;
  });

  const targetIdx = currentStepIndex - 1;
  const targetStep = steps[targetIdx];
  const mergedStatus = mergePlanStepStatus(targetStep.status, incomingStatus);
  steps[targetIdx] = {
    ...targetStep,
    title: incomingStepTitle,
    status: mergedStatus,
  };

  return {
    steps,
    current_step_index: currentStepIndex,
    total_steps: total,
    step_title: incomingStepTitle,
    step_status: mergedStatus,
    next_hint:
      incomingNextHint ?? deriveNextHint(steps, currentStepIndex, mergedStatus),
    block_reason: blockReason,
  };
}

import { emitSessionsChanged } from "./session-lifecycle";

export function handleExtendedEvent(
  evt: WSEvent,
  set: SetStateFn,
  get: GetStateFn,
): boolean {
  switch (evt.type) {
    case "analysis_plan": {
      const data = isRecord(evt.data) ? evt.data : null;
      if (!data) return true;
      const steps = normalizeAnalysisSteps(data.steps);
      const rawText = typeof data.raw_text === "string" ? data.raw_text : "";
      if (steps.length === 0) return true;
      const eventOrder = extractPlanEventOrder(evt, data);
      const turnId = evt.turn_id || get()._currentTurnId || undefined;
      const msgId = nextId();
      const msg: Message = {
        id: msgId,
        role: "assistant",
        content: rawText,
        isReasoning: true,
        analysisPlan: { steps, raw_text: rawText },
        turnId,
        timestamp: Date.now(),
      };
      set((s) => {
        if (eventOrder < s._analysisPlanOrder) return {};
        const now = Date.now();
        const currentTurnId = turnId || s._currentTurnId || null;
        const existingTasks = s.analysisTasks;
        const deduplicatedTasks = currentTurnId
          ? existingTasks.filter((t) => t.turn_id !== currentTurnId)
          : existingTasks;
        const newTasks: AnalysisTaskItem[] = steps.map((step) => ({
          id: nextAnalysisTaskId(),
          plan_step_id: step.id,
          action_id: step.action_id ?? null,
          title: step.title,
          tool_hint: step.tool_hint,
          status: step.status,
          raw_status: step.raw_status,
          current_activity: null,
          last_error: null,
          attempts: [],
          created_at: now,
          updated_at: now,
          turn_id: currentTurnId,
          depends_on: step.depends_on,
        }));
        const filteredActionMap = currentTurnId
          ? Object.fromEntries(
              Object.entries(s._planActionTaskMap).filter(([_, taskId]) => {
                const task = existingTasks.find((t) => t.id === taskId);
                return task?.turn_id !== currentTurnId;
              }),
            )
          : { ...s._planActionTaskMap };
        const actionMap = {
          ...filteredActionMap,
          ...Object.fromEntries(
            newTasks
              .filter((task) => typeof task.action_id === "string" && task.action_id)
              .map((task) => [task.action_id as string, task.id]),
          ),
        };
        const filteredActiveIds = currentTurnId
          ? s._activePlanTaskIds.filter((id) => {
              if (!id) return false;
              const task = existingTasks.find((t) => t.id === id);
              return task?.turn_id !== currentTurnId;
            })
          : [...s._activePlanTaskIds];
        return {
          messages: [...s.messages, msg],
          _activePlanMsgId: msgId,
          analysisPlanProgress: makePlanProgressFromSteps(steps, rawText),
          analysisTasks: [...deduplicatedTasks, ...newTasks],
          _activePlanTaskIds: [...filteredActiveIds, ...newTasks.map((task) => task.id)],
          _planActionTaskMap: actionMap,
          workspacePanelOpen: true,
          workspacePanelTab: "tasks",
          previewFileId: null,
          _analysisPlanOrder: eventOrder,
        };
      });
      return true;
    }

    case "plan_step_update": {
      const data = isRecord(evt.data) ? evt.data : null;
      if (!data || typeof data.id !== "number" || typeof data.status !== "string") {
        return true;
      }
      const stepId = data.id as number;
      const stepStatus = data.status;
      const eventOrder = extractPlanEventOrder(evt, data);
      const planMsgId = get()._activePlanMsgId;

      set((s) => {
        if (eventOrder < s._analysisPlanOrder) return {};
        const msgs = [...s.messages];
        let updatedSteps: AnalysisStep[] = [];
        let rawText = "";
        const normalizedStatus = normalizePlanStepStatus(stepStatus);
        if (planMsgId) {
          const idx = msgs.findIndex((m) => m.id === planMsgId);
          if (idx >= 0 && msgs[idx].analysisPlan) {
            const plan = msgs[idx].analysisPlan!;
            rawText = plan.raw_text;
            updatedSteps = plan.steps.map((step) =>
              step.id === stepId
                ? {
                    ...step,
                    status: mergePlanStepStatus(step.status, normalizedStatus),
                    raw_status: stepStatus,
                  }
                : step,
            );
            msgs[idx] = { ...msgs[idx], analysisPlan: { ...plan, steps: updatedSteps } };
          }
        }
        const currentTurnId = s._currentTurnId;
        const taskId = findTaskIdByStepAndTurn(s.analysisTasks, stepId, currentTurnId);
        const currentTask = taskId ? s.analysisTasks.find((task) => task.id === taskId) : undefined;
        const mergedTaskStatus = currentTask
          ? mergePlanStepStatus(currentTask.status, normalizedStatus)
          : normalizedStatus;
        const nextTasks = updateAnalysisTaskById(s.analysisTasks, taskId, {
          status: mergedTaskStatus,
          raw_status: stepStatus,
          current_activity:
            normalizedStatus === "done"
              ? null
              : normalizedStatus === "failed"
                ? "步骤执行失败"
                : normalizedStatus === "blocked"
                  ? "步骤已阻塞"
                  : "步骤执行中",
          last_error:
            normalizedStatus === "failed" && typeof data.error === "string"
              ? data.error
              : normalizedStatus === "done"
                ? null
                : undefined,
        });
        const currentProgress =
          s.analysisPlanProgress ??
          (updatedSteps.length > 0 ? makePlanProgressFromSteps(updatedSteps, rawText) : null);
        return {
          messages: updatedSteps.length > 0 ? msgs : s.messages,
          analysisPlanProgress: applyPlanStepUpdateToProgress(currentProgress, stepId, stepStatus),
          analysisTasks: nextTasks,
          _analysisPlanOrder: eventOrder,
        };
      });
      return true;
    }

    case "plan_progress": {
      const data = isRecord(evt.data) ? evt.data : null;
      if (!data) return true;
      const eventOrder = extractPlanEventOrder(evt, data);
      set((s) => {
        if (eventOrder < s._analysisPlanOrder) return {};
        const nextProgress = applyPlanProgressPayload(s, data);
        if (!nextProgress) return {};
        const stepId = nextProgress.current_step_index;
        const currentTurnId = s._currentTurnId;
        const taskId = findTaskIdByStepAndTurn(s.analysisTasks, stepId, currentTurnId);
        const currentTask = taskId ? s.analysisTasks.find((task) => task.id === taskId) : undefined;
        const mergedTaskStatus = currentTask
          ? mergePlanStepStatus(currentTask.status, nextProgress.step_status)
          : nextProgress.step_status;
        const nextTasks = updateAnalysisTaskById(s.analysisTasks, taskId, {
          title: nextProgress.step_title,
          status: mergedTaskStatus,
          current_activity:
            nextProgress.step_status === "done"
              ? null
              : nextProgress.step_status === "failed"
                ? "步骤执行失败"
                : nextProgress.step_status === "blocked"
                  ? "步骤已阻塞"
                  : nextProgress.step_status === "in_progress"
                    ? "步骤执行中"
                    : "等待执行",
          last_error:
            nextProgress.step_status === "failed"
              ? nextProgress.block_reason || undefined
              : nextProgress.step_status === "done"
                ? null
                : undefined,
        });
        return {
          analysisPlanProgress: nextProgress,
          analysisTasks: nextTasks,
          _analysisPlanOrder: eventOrder,
        };
      });
      return true;
    }

    case "task_attempt": {
      const data = isRecord(evt.data) ? evt.data : null;
      if (!data) return true;
      set((s) => {
        const actionId =
          typeof data.action_id === "string" && data.action_id.trim()
            ? data.action_id.trim()
            : null;
        const stepId =
          typeof data.step_id === "number" && Number.isFinite(data.step_id)
            ? Math.floor(data.step_id)
            : null;
        const toolName =
          typeof data.tool_name === "string" && data.tool_name.trim()
            ? data.tool_name.trim()
            : evt.tool_name || "tool";
        const attempt =
          typeof data.attempt === "number" && Number.isFinite(data.attempt) && data.attempt > 0
            ? Math.floor(data.attempt)
            : 1;
        const maxAttempts =
          typeof data.max_attempts === "number" && Number.isFinite(data.max_attempts) && data.max_attempts > 0
            ? Math.floor(data.max_attempts)
            : Math.max(attempt, 1);
        const attemptStatus = normalizeTaskAttemptStatus(data.status);
        const note =
          typeof data.note === "string" && data.note.trim() ? data.note.trim() : null;
        const error =
          typeof data.error === "string" && data.error.trim() ? data.error.trim() : null;

        let taskId: string | null = null;
        if (actionId && s._planActionTaskMap[actionId]) {
          taskId = s._planActionTaskMap[actionId];
        } else if (stepId) {
          taskId = findTaskIdByStepAndTurn(s.analysisTasks, stepId, s._currentTurnId);
        }
        if (!taskId) return {};

        const nextTasks = updateAnalysisTaskWithAttempt(s.analysisTasks, taskId, {
          action_id: actionId,
          tool_name: toolName,
          attempt,
          max_attempts: maxAttempts,
          status: attemptStatus,
          note,
          error,
        });
        const nextActionMap =
          actionId && actionId !== ""
            ? { ...s._planActionTaskMap, [actionId]: taskId }
            : s._planActionTaskMap;
        return {
          analysisTasks: nextTasks,
          _planActionTaskMap: nextActionMap,
        };
      });
      return true;
    }

    case "retrieval": {
      const data = isRecord(evt.data) ? evt.data : null;
      const query = data && typeof data.query === "string" ? data.query : "检索结果";
      const rawResults = data && Array.isArray(data.results) ? data.results : [];
      const retrievals: RetrievalItem[] = rawResults
        .filter((item): item is Record<string, unknown> => isRecord(item))
        .map((item) => ({
          source: typeof item.source === "string" ? item.source : "unknown",
          score: typeof item.score === "number" ? item.score : undefined,
          hits: typeof item.hits === "number" ? item.hits : undefined,
          snippet: typeof item.snippet === "string" ? item.snippet : "",
        }));
      if (retrievals.length === 0) return true;

      const turnId = evt.turn_id || get()._currentTurnId || undefined;
      const msg: Message = {
        id: nextId(),
        role: "assistant",
        content: `检索上下文：${query}`,
        retrievals,
        turnId,
        timestamp: Date.now(),
      };
      set((s) => ({ messages: [...s.messages, msg] }));
      return true;
    }

    case "chart": {
      const turnId = evt.turn_id || get()._currentTurnId || undefined;
      const messageId = evt.metadata?.message_id as string | undefined;
      set((s) => ({
        messages: upsertAssistantTextMessage(s.messages, {
          content: "图表已生成",
          chartData: evt.data,
          messageId,
          turnId,
          operation: "replace",
          timestamp: Date.now(),
        }),
      }));
      return true;
    }

    case "data": {
      const turnId = evt.turn_id || get()._currentTurnId || undefined;
      const messageId = evt.metadata?.message_id as string | undefined;
      set((s) => ({
        messages: upsertAssistantTextMessage(s.messages, {
          content: "数据预览如下",
          dataPreview: evt.data,
          messageId,
          turnId,
          operation: "replace",
          timestamp: Date.now(),
        }),
      }));
      return true;
    }

    case "artifact": {
      const artifact = evt.data as ArtifactInfo;
      if (artifact && artifact.download_url) {
        const turnId = evt.turn_id || get()._currentTurnId || undefined;
        const messageId = evt.metadata?.message_id as string | undefined;
        set((s) => ({
          messages: upsertAssistantTextMessage(s.messages, {
            content: "产物已生成",
            artifacts: [artifact],
            messageId,
            turnId,
            operation: "replace",
            timestamp: Date.now(),
          }),
        }));
      }
      return true;
    }

    case "image": {
      const imageData = evt.data as { url?: string; urls?: string[] };
      const urls: string[] = [];
      if (imageData.url) urls.push(imageData.url);
      if (imageData.urls) urls.push(...imageData.urls);
      if (urls.length > 0) {
        const turnId = evt.turn_id || get()._currentTurnId || undefined;
        const messageId = evt.metadata?.message_id as string | undefined;
        set((s) => ({
          messages: upsertAssistantTextMessage(s.messages, {
            content: "图片已生成",
            images: urls,
            messageId,
            turnId,
            operation: "replace",
            timestamp: Date.now(),
          }),
        }));
      }
      return true;
    }

    case "session_title": {
      const data = evt.data as { session_id: string; title: string };
      if (data && data.session_id && data.title) {
        set((s) => ({
          sessions: s.sessions.map((sess) =>
            sess.id === data.session_id ? { ...sess, title: data.title } : sess,
          ),
        }));
        emitSessionsChanged({
          reason: "rename",
          sessionId: data.session_id,
          title: data.title,
        });
      }
      return true;
    }

    case "workspace_update":
      get().fetchWorkspaceFiles();
      get().fetchDatasets();
      return true;

    case "code_execution": {
      const execRecord = evt.data as AppStateSubset["codeExecutions"][number];
      if (execRecord && execRecord.id) {
        set((s) => ({
          codeExecutions: [execRecord, ...s.codeExecutions],
        }));
      }
      return true;
    }

    case "context_compressed": {
      const data = isRecord(evt.data) ? evt.data : null;
      const archivedCount =
        typeof data?.archived_count === "number" ? data.archived_count : 0;
      const sysMsg: Message = {
        id: nextId(),
        role: "assistant",
        content: `上下文已自动压缩，归档了 ${archivedCount} 条消息，以保持响应速度。`,
        timestamp: Date.now(),
      };
      set((s) => ({
        messages: [...s.messages, sysMsg],
        contextCompressionTick: s.contextCompressionTick + 1,
      }));
      return true;
    }

    case "token_usage": {
      const data = isRecord(evt.data) ? evt.data : null;
      if (!data) return true;

      const model = typeof data.model === "string" ? data.model : "unknown";
      const inputTokens = typeof data.input_tokens === "number" ? data.input_tokens : 0;
      const outputTokens = typeof data.output_tokens === "number" ? data.output_tokens : 0;
      const totalTokens =
        typeof data.total_tokens === "number" ? data.total_tokens : inputTokens + outputTokens;
      const costUsd = typeof data.cost_usd === "number" ? data.cost_usd : null;
      const sessionTotalTokens =
        typeof data.session_total_tokens === "number" ? data.session_total_tokens : totalTokens;
      const sessionTotalCost =
        typeof data.session_total_cost === "number" ? data.session_total_cost : 0;
      const usageTurnId = evt.turn_id || null;

      set((s) => {
        const currentMetrics = s._streamingMetrics;
        if (usageTurnId && currentMetrics.turnId && currentMetrics.turnId !== usageTurnId) {
          return {};
        }
        const nextStreamingMetrics: StreamingMetrics = {
          ...currentMetrics,
          turnId: currentMetrics.turnId || usageTurnId,
          totalTokens: currentMetrics.totalTokens + totalTokens,
          hasTokenUsage: true,
        };
        const current = s.tokenUsage;
        if (!current) {
          return {
            runtimeModel: {
              provider_id: s.runtimeModel?.provider_id || "",
              provider_name: s.runtimeModel?.provider_name || "",
              model,
              preferred_provider: s.activeModel?.preferred_provider ?? null,
            },
            _streamingMetrics: nextStreamingMetrics,
            tokenUsage: {
              session_id: s.sessionId || "",
              input_tokens: inputTokens,
              output_tokens: outputTokens,
              total_tokens: sessionTotalTokens,
              estimated_cost_usd: sessionTotalCost,
              estimated_cost_cny: sessionTotalCost * 7.2,
              model_breakdown: {
                [model]: {
                  model_id: model,
                  input_tokens: inputTokens,
                  output_tokens: outputTokens,
                  total_tokens: totalTokens,
                  cost_usd: costUsd || 0,
                  cost_cny: (costUsd || 0) * 7.2,
                  call_count: 1,
                },
              },
              updated_at: new Date().toISOString(),
            },
          };
        }
        const modelBreakdown = { ...current.model_breakdown };
        const existing = modelBreakdown[model];
        if (existing) {
          modelBreakdown[model] = {
            ...existing,
            input_tokens: existing.input_tokens + inputTokens,
            output_tokens: existing.output_tokens + outputTokens,
            total_tokens: existing.total_tokens + totalTokens,
            cost_usd: existing.cost_usd + (costUsd || 0),
            cost_cny: existing.cost_cny + (costUsd || 0) * 7.2,
            call_count: existing.call_count + 1,
          };
        } else {
          modelBreakdown[model] = {
            model_id: model,
            input_tokens: inputTokens,
            output_tokens: outputTokens,
            total_tokens: totalTokens,
            cost_usd: costUsd || 0,
            cost_cny: (costUsd || 0) * 7.2,
            call_count: 1,
          };
        }
        return {
          runtimeModel: {
            provider_id: s.runtimeModel?.provider_id || "",
            provider_name: s.runtimeModel?.provider_name || "",
            model,
            preferred_provider: s.activeModel?.preferred_provider ?? null,
          },
          _streamingMetrics: nextStreamingMetrics,
          tokenUsage: {
            ...current,
            input_tokens: current.input_tokens + inputTokens,
            output_tokens: current.output_tokens + outputTokens,
            total_tokens: sessionTotalTokens,
            estimated_cost_usd: sessionTotalCost,
            estimated_cost_cny: sessionTotalCost * 7.2,
            model_breakdown: modelBreakdown,
            updated_at: new Date().toISOString(),
          },
        };
      });
      return true;
    }

    default:
      return false;
  }
}
