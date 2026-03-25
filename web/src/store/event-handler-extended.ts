/**
 * WebSocket 扩展事件处理器
 *
 * 仅在命中非首屏关键路径事件时按需加载，降低主包体积。
 */

import type {
  WSEvent,
  Message,
  ChartDataPayload,
  DataPreviewPayload,
  AnalysisStep,
  AnalysisTaskItem,
  ArtifactInfo,
  RetrievalItem,
  StreamingMetrics,
  DeepTaskState,
} from "./types";
import type { AppStateSubset, GetStateFn, SetStateFn } from "./event-handler";

import {
  isRecord,
  nextId,
  nextAnalysisTaskId,
  makePlanProgressFromSteps,
  applyPlanProgressPayload,
  applyPlanStepUpdateToProgress,
  updateAnalysisTaskById,
  updateAnalysisTaskWithAttempt,
  findTaskIdByStepAndTurn,
} from "./utils";
import {
  normalizeAnalysisSteps,
  normalizeTaskAttemptStatus,
  normalizePlanStepStatus,
  mergePlanStepStatus,
} from "./normalizers";
import { upsertAssistantTextMessage } from "./message-normalizer";
import { updateSessionUiCacheEntry } from "./session-ui-cache";

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

function isActiveSessionEvent(evt: WSEvent, get: GetStateFn): boolean {
  const currentSessionId = get().sessionId;
  return (
    typeof evt.session_id === "string" &&
    evt.session_id.length > 0 &&
    currentSessionId === evt.session_id
  );
}

import { emitSessionsChanged } from "./session-lifecycle";

function normalizeDeepTaskStatus(raw: unknown): DeepTaskState["status"] {
  if (typeof raw !== "string") return "running";
  const normalized = raw.trim().toLowerCase();
  switch (normalized) {
    case "queued":
      return "queued";
    case "retrying":
      return "retrying";
    case "blocked":
      return "blocked";
    case "failed":
      return "failed";
    case "completed":
    case "done":
      return "completed";
    default:
      return "running";
  }
}

function buildDeepTaskStateFromProgress(
  data: Record<string, unknown>,
  nextProgress: NonNullable<AppStateSubset["analysisPlanProgress"]>,
  previousState: DeepTaskState | null | undefined,
): DeepTaskState | null {
  if (typeof data.task_id !== "string" || !data.task_id.trim()) {
    return previousState ?? null;
  }
  return {
    task_id: data.task_id.trim(),
    status: normalizeDeepTaskStatus(nextProgress.step_status),
    current_step_index: nextProgress.current_step_index,
    total_steps: nextProgress.total_steps,
    current_step_title: nextProgress.step_title,
    next_hint: nextProgress.next_hint,
    block_reason: nextProgress.block_reason,
    retry_count: typeof data.retry_count === "number" ? data.retry_count : 0,
  };
}

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
      const backgroundSessionId =
        typeof evt.session_id === "string" && evt.session_id !== get().sessionId
          ? evt.session_id
          : null;
      if (backgroundSessionId) {
        updateSessionUiCacheEntry(backgroundSessionId, (entry) => {
          const now = Date.now();
          const turnId = evt.turn_id || entry.currentTurnId || undefined;
          const msgId = nextId();
          const msg: Message = {
            id: msgId,
            role: "assistant",
            content: rawText,
            isReasoning: true,
            analysisPlan: { steps, raw_text: rawText },
            turnId,
            timestamp: now,
          };
          if (eventOrder < entry.analysisPlanOrder) return entry;
          const currentTurnId = turnId || entry.currentTurnId || null;
          const existingTasks = entry.analysisTasks;
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
                Object.entries(entry.planActionTaskMap).filter(([_, taskId]) => {
                  const task = existingTasks.find((t) => t.id === taskId);
                  return task?.turn_id !== currentTurnId;
                }),
              )
            : { ...entry.planActionTaskMap };
          const actionMap = {
            ...filteredActionMap,
            ...Object.fromEntries(
              newTasks
                .filter((task) => typeof task.action_id === "string" && task.action_id)
                .map((task) => [task.action_id as string, task.id]),
            ),
          };
          const filteredActiveIds = currentTurnId
            ? entry.activePlanTaskIds.filter((id) => {
                if (!id) return false;
                const task = existingTasks.find((t) => t.id === id);
                return task?.turn_id !== currentTurnId;
              })
            : [...entry.activePlanTaskIds];
          return {
            ...entry,
            messages: [...entry.messages, msg],
            analysisPlanProgress: makePlanProgressFromSteps(steps, rawText),
            analysisTasks: [...deduplicatedTasks, ...newTasks],
            activePlanMsgId: msgId,
            activePlanTaskIds: [...filteredActiveIds, ...newTasks.map((task) => task.id)],
            planActionTaskMap: actionMap,
            analysisPlanOrder: eventOrder,
            currentTurnId,
            workspacePanelTab: "tasks",
          };
        });
        return true;
      }
      if (!isActiveSessionEvent(evt, get)) return true;
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
      const backgroundSessionId =
        typeof evt.session_id === "string" && evt.session_id !== get().sessionId
          ? evt.session_id
          : null;
      if (backgroundSessionId) {
        updateSessionUiCacheEntry(backgroundSessionId, (entry) => {
          if (eventOrder < entry.analysisPlanOrder) return entry;
          const msgs = [...entry.messages];
          let updatedSteps: AnalysisStep[] = [];
          let rawText = "";
          const normalizedStatus = normalizePlanStepStatus(stepStatus);
          if (entry.activePlanMsgId) {
            const idx = msgs.findIndex((m) => m.id === entry.activePlanMsgId);
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
          const taskId = findTaskIdByStepAndTurn(
            entry.analysisTasks,
            stepId,
            entry.currentTurnId,
          );
          const currentTask = taskId
            ? entry.analysisTasks.find((task) => task.id === taskId)
            : undefined;
          const mergedTaskStatus = currentTask
            ? mergePlanStepStatus(currentTask.status, normalizedStatus)
            : normalizedStatus;
          const nextTasks = updateAnalysisTaskById(entry.analysisTasks, taskId, {
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
            entry.analysisPlanProgress ??
            (updatedSteps.length > 0 ? makePlanProgressFromSteps(updatedSteps, rawText) : null);
          return {
            ...entry,
            messages: updatedSteps.length > 0 ? msgs : entry.messages,
            analysisPlanProgress: applyPlanStepUpdateToProgress(
              currentProgress,
              stepId,
              stepStatus,
            ),
            analysisTasks: nextTasks,
            analysisPlanOrder: eventOrder,
          };
        });
        return true;
      }
      if (!isActiveSessionEvent(evt, get)) return true;
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
      const backgroundSessionId =
        typeof evt.session_id === "string" && evt.session_id !== get().sessionId
          ? evt.session_id
          : null;
      if (backgroundSessionId) {
        updateSessionUiCacheEntry(backgroundSessionId, (entry) => {
          if (eventOrder < entry.analysisPlanOrder) return entry;
          const nextProgress = applyPlanProgressPayload(entry.analysisPlanProgress, data);
          if (!nextProgress) return entry;
          const stepId = nextProgress.current_step_index;
          const taskId = findTaskIdByStepAndTurn(
            entry.analysisTasks,
            stepId,
            entry.currentTurnId,
          );
          const currentTask = taskId
            ? entry.analysisTasks.find((task) => task.id === taskId)
            : undefined;
          const mergedTaskStatus = currentTask
            ? mergePlanStepStatus(currentTask.status, nextProgress.step_status)
            : nextProgress.step_status;
          return {
            ...entry,
            activeRecipeId:
              typeof data.recipe_id === "string" && data.recipe_id.trim()
                ? data.recipe_id.trim()
                : entry.activeRecipeId,
            deepTaskState: buildDeepTaskStateFromProgress(
              data,
              nextProgress,
              entry.deepTaskState,
            ),
            analysisPlanProgress: nextProgress,
            analysisTasks: updateAnalysisTaskById(entry.analysisTasks, taskId, {
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
            }),
            analysisPlanOrder: eventOrder,
          };
        });
        return true;
      }
      if (!isActiveSessionEvent(evt, get)) return true;
      set((s) => {
        if (eventOrder < s._analysisPlanOrder) return {};
        const nextProgress = applyPlanProgressPayload(s.analysisPlanProgress, data);
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
          activeRecipeId:
            typeof data.recipe_id === "string" && data.recipe_id.trim()
              ? data.recipe_id.trim()
              : s.activeRecipeId,
          deepTaskState: buildDeepTaskStateFromProgress(data, nextProgress, s.deepTaskState),
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
      const backgroundSessionId =
        typeof evt.session_id === "string" && evt.session_id !== get().sessionId
          ? evt.session_id
          : null;
      if (backgroundSessionId) {
        updateSessionUiCacheEntry(backgroundSessionId, (entry) => {
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
            typeof data.max_attempts === "number" &&
            Number.isFinite(data.max_attempts) &&
            data.max_attempts > 0
              ? Math.floor(data.max_attempts)
              : Math.max(attempt, 1);
          const attemptStatus = normalizeTaskAttemptStatus(data.status);
          const note =
            typeof data.note === "string" && data.note.trim() ? data.note.trim() : null;
          const error =
            typeof data.error === "string" && data.error.trim() ? data.error.trim() : null;
          let taskId: string | null = null;
          if (actionId && entry.planActionTaskMap[actionId]) {
            taskId = entry.planActionTaskMap[actionId];
          } else if (stepId) {
            taskId = findTaskIdByStepAndTurn(entry.analysisTasks, stepId, entry.currentTurnId);
          }
          if (!taskId) return entry;
          return {
            ...entry,
            analysisTasks: updateAnalysisTaskWithAttempt(entry.analysisTasks, taskId, {
              action_id: actionId,
              tool_name: toolName,
              attempt,
              max_attempts: maxAttempts,
              status: attemptStatus,
              note,
              error,
            }),
            planActionTaskMap:
              actionId && actionId !== ""
                ? { ...entry.planActionTaskMap, [actionId]: taskId }
                : entry.planActionTaskMap,
          };
        });
        return true;
      }
      if (!isActiveSessionEvent(evt, get)) return true;
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
          sourceId: typeof item.source_id === "string" ? item.source_id : undefined,
          sourceType: typeof item.source_type === "string" ? item.source_type : undefined,
          acquisitionMethod:
            typeof item.acquisition_method === "string"
              ? item.acquisition_method
              : undefined,
          accessedAt: typeof item.accessed_at === "string" ? item.accessed_at : undefined,
          sourceTime: typeof item.source_time === "string" ? item.source_time : undefined,
          stableRef: typeof item.stable_ref === "string" ? item.stable_ref : undefined,
          documentId: typeof item.document_id === "string" ? item.document_id : undefined,
          resourceId: typeof item.resource_id === "string" ? item.resource_id : undefined,
          sourceUrl: typeof item.source_url === "string" ? item.source_url : undefined,
          claimId: typeof item.claim_id === "string" ? item.claim_id : undefined,
          verificationStatus:
            item.verification_status === "verified" ||
            item.verification_status === "pending_verification" ||
            item.verification_status === "conflicted"
              ? item.verification_status
              : undefined,
          reasonSummary:
            typeof item.reason_summary === "string" ? item.reason_summary : undefined,
          conflictSummary:
            typeof item.conflict_summary === "string" ? item.conflict_summary : undefined,
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
      const backgroundSessionId =
        typeof evt.session_id === "string" && evt.session_id !== get().sessionId
          ? evt.session_id
          : null;
      if (backgroundSessionId) {
        updateSessionUiCacheEntry(backgroundSessionId, (entry) => ({
          ...entry,
          messages: [...entry.messages, msg],
        }));
        return true;
      }
      if (!isActiveSessionEvent(evt, get)) return true;
      set((s) => ({ messages: [...s.messages, msg] }));
      return true;
    }

    case "chart": {
      const turnId = evt.turn_id || get()._currentTurnId || undefined;
      const messageId = evt.metadata?.message_id as string | undefined;
      const backgroundSessionId =
        typeof evt.session_id === "string" && evt.session_id !== get().sessionId
          ? evt.session_id
          : null;
      if (backgroundSessionId) {
        updateSessionUiCacheEntry(backgroundSessionId, (entry) => ({
          ...entry,
          messages: upsertAssistantTextMessage(entry.messages, {
            content: "图表已生成",
            chartData: evt.data as ChartDataPayload,
            messageId,
            turnId: evt.turn_id || entry.currentTurnId || undefined,
            operation: "replace",
            timestamp: Date.now(),
          }),
        }));
        return true;
      }
      if (!isActiveSessionEvent(evt, get)) return true;
      set((s) => ({
        messages: upsertAssistantTextMessage(s.messages, {
          content: "图表已生成",
          chartData: evt.data as ChartDataPayload,
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
      const backgroundSessionId =
        typeof evt.session_id === "string" && evt.session_id !== get().sessionId
          ? evt.session_id
          : null;
      if (backgroundSessionId) {
        updateSessionUiCacheEntry(backgroundSessionId, (entry) => ({
          ...entry,
          messages: upsertAssistantTextMessage(entry.messages, {
            content: "数据预览如下",
            dataPreview: evt.data as DataPreviewPayload,
            messageId,
            turnId: evt.turn_id || entry.currentTurnId || undefined,
            operation: "replace",
            timestamp: Date.now(),
          }),
        }));
        return true;
      }
      if (!isActiveSessionEvent(evt, get)) return true;
      set((s) => ({
        messages: upsertAssistantTextMessage(s.messages, {
          content: "数据预览如下",
          dataPreview: evt.data as DataPreviewPayload,
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
        const backgroundSessionId =
          typeof evt.session_id === "string" && evt.session_id !== get().sessionId
            ? evt.session_id
            : null;
        if (backgroundSessionId) {
          updateSessionUiCacheEntry(backgroundSessionId, (entry) => ({
            ...entry,
            messages: upsertAssistantTextMessage(entry.messages, {
              content: "产物已生成",
              artifacts: [artifact],
              messageId,
              turnId: evt.turn_id || entry.currentTurnId || undefined,
              operation: "replace",
              timestamp: Date.now(),
            }),
          }));
          return true;
        }
        if (!isActiveSessionEvent(evt, get)) return true;
        set((s) => {
          return {
            messages: upsertAssistantTextMessage(s.messages, {
              content: "产物已生成",
              artifacts: [artifact],
              messageId,
              turnId,
              operation: "replace",
              timestamp: Date.now(),
            }),
          };
        });
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
        const backgroundSessionId =
          typeof evt.session_id === "string" && evt.session_id !== get().sessionId
            ? evt.session_id
            : null;
        if (backgroundSessionId) {
          updateSessionUiCacheEntry(backgroundSessionId, (entry) => ({
            ...entry,
            messages: upsertAssistantTextMessage(entry.messages, {
              content: "图片已生成",
              images: urls,
              messageId,
              turnId: evt.turn_id || entry.currentTurnId || undefined,
              operation: "replace",
              timestamp: Date.now(),
            }),
          }));
          return true;
        }
        if (!isActiveSessionEvent(evt, get)) return true;
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
      if (!isActiveSessionEvent(evt, get)) return true;
      if (isRecord(evt.data)) {
        const data = evt.data;
        set((s) => ({
          activeRecipeId:
            typeof data.recipe_id === "string" && data.recipe_id.trim()
              ? data.recipe_id.trim()
              : s.activeRecipeId,
          deepTaskState:
            s.deepTaskState && typeof data.task_id === "string" && data.task_id.trim()
              ? { ...s.deepTaskState, task_id: data.task_id.trim() }
              : s.deepTaskState,
        }));
      }
      get().fetchWorkspaceFiles();
      get().fetchDatasets();
      return true;

    case "code_execution": {
      if (!isActiveSessionEvent(evt, get)) return true;
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
      const backgroundSessionId =
        typeof evt.session_id === "string" && evt.session_id !== get().sessionId
          ? evt.session_id
          : null;
      if (backgroundSessionId) {
        updateSessionUiCacheEntry(backgroundSessionId, (entry) => ({
          ...entry,
          messages: [...entry.messages, sysMsg],
        }));
        return true;
      }
      if (!isActiveSessionEvent(evt, get)) return true;
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
      const backgroundSessionId =
        typeof evt.session_id === "string" && evt.session_id !== get().sessionId
          ? evt.session_id
          : null;
      if (backgroundSessionId) {
        updateSessionUiCacheEntry(backgroundSessionId, (entry) => {
          const currentMetrics = entry.streamingMetrics;
          if (usageTurnId && currentMetrics.turnId && currentMetrics.turnId !== usageTurnId) {
            return entry;
          }
          const nextStreamingMetrics: StreamingMetrics = {
            ...currentMetrics,
            turnId: currentMetrics.turnId || usageTurnId,
            totalTokens: currentMetrics.totalTokens + totalTokens,
            hasTokenUsage: true,
          };
          const current = entry.tokenUsage;
          if (!current) {
            return {
              ...entry,
              streamingMetrics: nextStreamingMetrics,
              tokenUsage: {
                session_id: backgroundSessionId,
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
            ...entry,
            streamingMetrics: nextStreamingMetrics,
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
      if (!isActiveSessionEvent(evt, get)) return true;

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
              provider_id: s.runtimeModel?.provider_id || s.activeModel?.provider_id || "",
              provider_name: s.runtimeModel?.provider_name || s.activeModel?.provider_name || "",
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
            provider_id: s.runtimeModel?.provider_id || s.activeModel?.provider_id || "",
            provider_name: s.runtimeModel?.provider_name || s.activeModel?.provider_name || "",
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
