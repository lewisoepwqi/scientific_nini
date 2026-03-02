/**
 * WebSocket 事件处理器
 *
 * 处理 17+ 种 WebSocket 事件类型
 */

import type {
  WSEvent,
  Message,
  AnalysisStep,
  AnalysisTaskItem,
  AnalysisPlanProgress,
  AnalysisTaskAttemptStatus,
  AskUserQuestionItem,
  AskUserQuestionOption,
  ArtifactInfo,
  RetrievalItem,
  CodeExecution,
  ModelTokenUsage,
} from "./types";

import {
  isRecord,
  nextId,
  nextAnalysisTaskId,
  mergeReasoningContent,
  makePlanProgressFromSteps,
  applyPlanStepUpdateToProgress,
  updateAnalysisTaskById,
  updateAnalysisTaskWithAttempt,
  findTaskIdByStepAndTurn,
} from "./utils";

import {
  normalizeAnalysisSteps,
  normalizePlanStepStatus,
  mergePlanStepStatus,
  stripReasoningMarkers,
} from "./normalizers";

import { areAllPlanStepsDone } from "./plan-state-machine";

// ---- 错误处理类型 ----

interface NormalizedWsError {
  message: string;
  detail: string | null;
  hint: string | null;
  code: string | null;
  kind:
    | "quota"
    | "rate_limit"
    | "context_limit"
    | "request"
    | "server"
    | "unknown";
  retryable: boolean;
}

// ---- 辅助函数 ----

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

// eslint-disable-next-line @typescript-eslint/no-unused-vars
// Helper functions now imported from ./api-actions

function normalizeRunCodeIntent(
  name: string,
  toolArgs: Record<string, unknown>,
): Record<string, unknown> {
  if (name !== "run_code") return toolArgs;

  const intent =
    typeof toolArgs.intent === "string" ? toolArgs.intent.trim() : "";
  if (intent) return toolArgs;

  const label = typeof toolArgs.label === "string" ? toolArgs.label.trim() : "";
  if (!label) return toolArgs;

  return { ...toolArgs, intent: label };
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function normalizeToolResult(rawContent: unknown): {
  message: string;
  status: "success" | "error";
} {
  if (typeof rawContent !== "string" || !rawContent.trim()) {
    return { message: "", status: "success" };
  }
  try {
    const parsed = JSON.parse(rawContent);
    if (isRecord(parsed)) {
      if (typeof parsed.error === "string" && parsed.error) {
        return { message: parsed.error, status: "error" };
      }
      if (parsed.success === false) {
        const msg =
          typeof parsed.message === "string" && parsed.message
            ? parsed.message
            : "工具执行失败";
        return { message: msg, status: "error" };
      }
      if (typeof parsed.message === "string" && parsed.message) {
        return { message: parsed.message, status: "success" };
      }
    }
  } catch {
    // 保持原始文本
  }
  return { message: rawContent, status: "success" };
}

function stringifyUnknown(value: unknown): string {
  if (typeof value === "string") return value;
  if (value instanceof Error) return value.message;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function detectErrorCode(text: string): string | null {
  const matches = text.match(
    /(insufficient_quota|rate_limit_exceeded|context_length_exceeded|invalid_request_error|access_terminated_error)/i,
  );
  if (matches && matches[1]) return matches[1].toLowerCase();
  return null;
}

function normalizeWsError(data: unknown): NormalizedWsError {
  let raw = "";
  let explicitCode: string | null = null;
  let explicitMessage: string | null = null;

  if (typeof data === "string") {
    raw = data.trim();
  } else if (isRecord(data)) {
    const topMessage =
      typeof data.message === "string"
        ? data.message
        : typeof data.error === "string"
          ? data.error
          : typeof data.detail === "string"
            ? data.detail
            : null;
    const topCode = typeof data.code === "string" ? data.code : null;
    const nestedError = isRecord(data.error) ? data.error : null;
    const nestedMessage =
      nestedError && typeof nestedError.message === "string"
        ? nestedError.message
        : null;
    const nestedCode =
      nestedError && typeof nestedError.code === "string"
        ? nestedError.code
        : null;

    explicitMessage = nestedMessage || topMessage;
    explicitCode = nestedCode || topCode;
    raw = (explicitMessage || stringifyUnknown(data)).trim();
  } else {
    raw = stringifyUnknown(data).trim();
  }

  const normalizedRaw = raw || "未知错误";
  const lower = normalizedRaw.toLowerCase();
  const code =
    (explicitCode || detectErrorCode(normalizedRaw) || null)?.toLowerCase() ||
    null;

  const isQuota =
    code === "insufficient_quota" ||
    lower.includes("insufficient_quota") ||
    lower.includes("exceeded your current quota") ||
    lower.includes("配额") ||
    lower.includes("quota");
  const isRateLimit =
    lower.includes("429") ||
    lower.includes("too many requests") ||
    lower.includes("rate limit");
  const isContextLimit =
    code === "context_length_exceeded" ||
    lower.includes("context length") ||
    lower.includes("context window");
  const isClientRequestError =
    lower.includes("消息内容不能为空") ||
    lower.includes("消息格式错误") ||
    lower.includes("不支持的消息类型") ||
    lower.includes("没有可重试的用户消息") ||
    lower.includes("当前有进行中的请求");
  const isServerError =
    lower.includes("服务器错误") ||
    lower.includes("server error") ||
    lower.includes("internal error");

  if (isQuota) {
    return {
      message: "模型服务额度不足，请检查配额/账单或切换模型后重试。",
      hint: "检测到配额不足（insufficient_quota）。",
      detail: normalizedRaw,
      code: code || "insufficient_quota",
      kind: "quota",
      retryable: true,
    };
  }

  if (isRateLimit) {
    return {
      message: "模型请求触发限流（HTTP 429），请稍后重试。",
      hint: "请求过于频繁，触发模型限流。",
      detail: normalizedRaw,
      code,
      kind: "rate_limit",
      retryable: true,
    };
  }

  if (isContextLimit) {
    return {
      message: "上下文超出模型限制，请重试或先压缩会话。",
      hint: "可先点击「压缩会话」，再重试上一轮。",
      detail: normalizedRaw,
      code: code || "context_length_exceeded",
      kind: "context_limit",
      retryable: true,
    };
  }

  if (isClientRequestError) {
    return {
      message: explicitMessage?.trim() || normalizedRaw,
      hint: null,
      detail: null,
      code,
      kind: "request",
      retryable: false,
    };
  }

  if (isServerError) {
    return {
      message: "服务端处理失败，请稍后重试。",
      hint: "服务端异常，建议稍后重试。",
      detail: normalizedRaw,
      code,
      kind: "server",
      retryable: true,
    };
  }

  return {
    message: explicitMessage?.trim() || normalizedRaw,
    hint: null,
    detail: null,
    code,
    kind: "unknown",
    retryable: true,
  };
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function buildErrorMeta(content: string): Partial<Message> {
  const normalized = normalizeWsError(content.replace(/^错误[:：]\s*/u, ""));
  return {
    isError: true,
    errorKind: normalized.kind,
    errorCode: normalized.code,
    errorHint: normalized.hint,
    errorDetail: normalized.detail,
    retryable: normalized.retryable,
  };
}

function finalizeReasoningMessages(
  messages: Message[],
  turnId?: string | null,
): Message[] {
  let changed = false;
  const next = messages.map((msg) => {
    if (!msg.isReasoning || !msg.reasoningLive) return msg;
    if (turnId && msg.turnId && msg.turnId !== turnId) return msg;
    changed = true;
    return { ...msg, reasoningLive: false };
  });
  return changed ? next : messages;
}

// ---- 主事件处理器 ----

export type SetStateFn = (
  fn: Partial<AppStateSubset> | ((s: AppStateSubset) => Partial<AppStateSubset>),
) => void;
export type GetStateFn = () => AppStateSubset;

// Store 状态子集（事件处理器所需）
export interface AppStateSubset {
  sessionId: string | null;
  messages: Message[];
  sessions: { id: string; title: string; message_count: number; source: "memory" | "disk" }[];
  _currentTurnId: string | null;
  _streamingText: string;
  _lastHandledSeq: number | undefined;
  _activePlanMsgId: string | null;
  _analysisPlanOrder: number;
  _activePlanTaskIds: Array<string | null>;
  _planActionTaskMap: Record<string, string>;
  analysisPlanProgress: AnalysisPlanProgress | null;
  analysisTasks: AnalysisTaskItem[];
  pendingAskUserQuestion: { toolCallId: string; questions: AskUserQuestionItem[]; createdAt: number } | null;
  isStreaming: boolean;
  tokenUsage: {
    session_id: string;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    estimated_cost_usd: number;
    estimated_cost_cny: number;
    model_breakdown: Record<string, ModelTokenUsage>;
    updated_at?: string;
  } | null;
  contextCompressionTick: number;
  workspacePanelOpen: boolean;
  workspacePanelTab: "files" | "executions" | "tasks";
  previewFileId: string | null;
  codeExecutions: CodeExecution[];
  // 操作函数
  fetchSessions: () => Promise<void>;
  fetchDatasets: () => Promise<void>;
  fetchWorkspaceFiles: () => Promise<void>;
  fetchSkills: () => Promise<void>;
}

export function handleEvent(
  evt: WSEvent,
  set: SetStateFn,
  get: GetStateFn,
) {
  switch (evt.type) {
    case "session": {
      const data = evt.data;
      if (isRecord(data) && typeof data.session_id === "string") {
        set({ sessionId: data.session_id });
        // 新会话创建后刷新会话列表
        get().fetchSessions();
        get().fetchDatasets();
        get().fetchWorkspaceFiles();
        get().fetchSkills();
      }
      break;
    }

    case "iteration_start": {
      // 新迭代开始：重置流式文本累积，记录 turnId，同时重置序列号
      set({ _streamingText: "", _currentTurnId: evt.turn_id || null, _lastHandledSeq: undefined });
      break;
    }

    case "text": {
      const text = stripReasoningMarkers((evt.data as string) || "");
      if (!text) break;

      // 防重复处理：检查事件序列号
      const seq = evt.metadata?.seq as number | undefined;
      if (seq !== undefined) {
        const lastSeq = get()._lastHandledSeq;
        if (lastSeq !== undefined && seq <= lastSeq) {
          // 已处理过此事件，跳过
          break;
        }
      }

      const newStreamText = get()._streamingText + text;
      const turnId = evt.turn_id || get()._currentTurnId || undefined;

      set((s) => {
        // 更新或创建 assistant 消息（同一迭代内）
        const msgs = [...s.messages];
        const last = msgs[msgs.length - 1];

        // 查找当前 turnId 的最后一条 assistant 消息（支持非连续情况）
        let targetIndex = -1;
        if (last &&
            last.role === "assistant" &&
            !last.toolName &&
            !last.retrievals &&
            !last.isReasoning &&
            last.turnId === turnId) {
          targetIndex = msgs.length - 1;
        } else {
          // 向前查找同 turnId 的 assistant 消息
          for (let i = msgs.length - 1; i >= 0; i--) {
            const m = msgs[i];
            if (m.role === "assistant" &&
                !m.toolName &&
                !m.retrievals &&
                !m.isReasoning &&
                m.turnId === turnId) {
              targetIndex = i;
              break;
            }
          }
        }

        if (targetIndex >= 0) {
          // 更新现有消息
          msgs[targetIndex] = { ...msgs[targetIndex], content: newStreamText };
        } else {
          // 检查是否已有相同内容的消息（防重复）
          const isDuplicate = msgs.some(
            (m) =>
              m.role === "assistant" &&
              !m.isReasoning &&
              m.content === newStreamText
          );
          if (!isDuplicate) {
            msgs.push({
              id: nextId(),
              role: "assistant",
              content: newStreamText,
              turnId,
              timestamp: Date.now(),
            });
          }
        }
        return { messages: msgs, _streamingText: newStreamText, _lastHandledSeq: seq };
      });
      break;
    }

    case "analysis_plan": {
      const data = isRecord(evt.data) ? evt.data : null;
      if (!data) break;
      const steps = normalizeAnalysisSteps(data.steps);
      const rawText =
        typeof data.raw_text === "string"
          ? stripReasoningMarkers(data.raw_text)
          : "";
      if (steps.length === 0) break;
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
        const appendedTasks: AnalysisTaskItem[] = steps.map((step) => ({
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
        }));
        const actionMap = {
          ...s._planActionTaskMap,
          ...Object.fromEntries(
            appendedTasks
              .filter(
                (task) => typeof task.action_id === "string" && task.action_id,
              )
              .map((task) => [task.action_id as string, task.id]),
          ),
        };
        return {
          messages: [...s.messages, msg],
          _activePlanMsgId: msgId,
          analysisPlanProgress: makePlanProgressFromSteps(steps, rawText),
          analysisTasks: [...s.analysisTasks, ...appendedTasks],
          // 累加任务ID，保留历史任务引用
          _activePlanTaskIds: [...s._activePlanTaskIds, ...appendedTasks.map((task) => task.id)],
          _planActionTaskMap: actionMap,
          workspacePanelOpen: true,
          workspacePanelTab: "tasks",
          previewFileId: null,
          _analysisPlanOrder: eventOrder,
        };
      });
      break;
    }

    case "plan_step_update": {
      const data = isRecord(evt.data) ? evt.data : null;
      if (
        !data ||
        typeof data.id !== "number" ||
        typeof data.status !== "string"
      )
        break;
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
                    raw_status:
                      typeof stepStatus === "string"
                        ? stepStatus
                        : step.raw_status,
                  }
                : step,
            );
            msgs[idx] = {
              ...msgs[idx],
              analysisPlan: { ...plan, steps: updatedSteps },
            };
          }
        }

        // 使用 turn_id 优先匹配当前回合的任务
        const currentTurnId = s._currentTurnId;
        const taskId = findTaskIdByStepAndTurn(s.analysisTasks, stepId, currentTurnId);
        const currentTask = taskId
          ? s.analysisTasks.find((task) => task.id === taskId)
          : undefined;
        const mergedTaskStatus = currentTask
          ? mergePlanStepStatus(currentTask.status, normalizedStatus)
          : normalizedStatus;
        const nextTasks = updateAnalysisTaskById(s.analysisTasks, taskId, {
          status: mergedTaskStatus,
          raw_status: typeof stepStatus === "string" ? stepStatus : undefined,
          current_activity:
            normalizedStatus === "done"
              ? "步骤已完成"
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
          (updatedSteps.length > 0
            ? makePlanProgressFromSteps(updatedSteps, rawText)
            : null);

        return {
          messages: updatedSteps.length > 0 ? msgs : s.messages,
          analysisPlanProgress: applyPlanStepUpdateToProgress(
            currentProgress,
            stepId,
            stepStatus,
          ),
          analysisTasks: nextTasks,
          _analysisPlanOrder: eventOrder,
        };
      });
      break;
    }

    case "plan_progress": {
      const data = isRecord(evt.data) ? evt.data : null;
      if (!data) break;
      const eventOrder = extractPlanEventOrder(evt, data);
      set((s) => {
        if (eventOrder < s._analysisPlanOrder) return {};
        const nextProgress = applyPlanProgressPayload(s, data);
        if (!nextProgress) return {};
        const stepId = nextProgress.current_step_index;
        // 使用 turn_id 优先匹配当前回合的任务
        const currentTurnId = s._currentTurnId;
        const taskId = findTaskIdByStepAndTurn(s.analysisTasks, stepId, currentTurnId);
        const currentTask = taskId
          ? s.analysisTasks.find((task) => task.id === taskId)
          : undefined;
        const mergedTaskStatus = currentTask
          ? mergePlanStepStatus(currentTask.status, nextProgress.step_status)
          : nextProgress.step_status;
        const nextTasks = updateAnalysisTaskById(s.analysisTasks, taskId, {
          title: nextProgress.step_title,
          status: mergedTaskStatus,
          current_activity:
            nextProgress.step_status === "done"
              ? "步骤已完成"
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
      break;
    }

    case "task_attempt": {
      const data = isRecord(evt.data) ? evt.data : null;
      if (!data) break;
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
          typeof data.attempt === "number" &&
          Number.isFinite(data.attempt) &&
          data.attempt > 0
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
          typeof data.note === "string" && data.note.trim()
            ? data.note.trim()
            : null;
        const error =
          typeof data.error === "string" && data.error.trim()
            ? data.error.trim()
            : null;

        let taskId: string | null = null;
        if (actionId && s._planActionTaskMap[actionId]) {
          taskId = s._planActionTaskMap[actionId];
        } else if (stepId) {
          // 使用 turn_id 优先匹配当前回合的任务
          taskId = findTaskIdByStepAndTurn(s.analysisTasks, stepId, s._currentTurnId);
        }
        if (!taskId) return {};

        const nextTasks = updateAnalysisTaskWithAttempt(
          s.analysisTasks,
          taskId,
          {
            action_id: actionId,
            tool_name: toolName,
            attempt,
            max_attempts: maxAttempts,
            status: attemptStatus,
            note,
            error,
          },
        );
        const nextActionMap =
          actionId && actionId !== ""
            ? { ...s._planActionTaskMap, [actionId]: taskId }
            : s._planActionTaskMap;
        return {
          analysisTasks: nextTasks,
          _planActionTaskMap: nextActionMap,
        };
      });
      break;
    }

    case "ask_user_question": {
      const data = isRecord(evt.data) ? evt.data : null;
      const toolCallId =
        typeof evt.tool_call_id === "string" && evt.tool_call_id.trim()
          ? evt.tool_call_id.trim()
          : "";
      const rawQuestions =
        data && Array.isArray(data.questions) ? data.questions : [];
      if (!toolCallId || rawQuestions.length === 0) break;

      const questions: AskUserQuestionItem[] = rawQuestions
        .filter((item): item is Record<string, unknown> => isRecord(item))
        .map((item) => {
          const rawOptions = Array.isArray(item.options) ? item.options : [];
          const options: AskUserQuestionOption[] = rawOptions
            .filter((opt): opt is Record<string, unknown> => isRecord(opt))
            .map((opt) => ({
              label: typeof opt.label === "string" ? opt.label.trim() : "",
              description:
                typeof opt.description === "string"
                  ? opt.description.trim()
                  : "",
            }))
            .filter((opt) => opt.label && opt.description);

          return {
            question:
              typeof item.question === "string" ? item.question.trim() : "",
            header: typeof item.header === "string" ? item.header.trim() : "",
            options,
            multiSelect: item.multiSelect === true,
            allowTextInput:
              typeof item.allowTextInput === "boolean"
                ? item.allowTextInput
                : true,
          };
        })
        .filter((item) => item.question && item.options.length >= 2);

      if (questions.length === 0) break;
      set({
        pendingAskUserQuestion: {
          toolCallId,
          questions,
          createdAt: Date.now(),
        },
      });
      break;
    }

    case "reasoning": {
      // 如果同一 turnId 已有 analysis_plan 消息，则跳过 reasoning（避免重复）
      const turnId = evt.turn_id || get()._currentTurnId || undefined;
      if (turnId) {
        const hasPlan = get().messages.some(
          (m) => m.turnId === turnId && m.analysisPlan,
        );
        if (hasPlan) break;
      }
      const data = isRecord(evt.data) ? evt.data : null;
      const content =
        data && typeof data.content === "string"
          ? stripReasoningMarkers(data.content)
          : "";
      if (!content) break;

      // 获取 reasoning_id（如果后端提供）
      const reasoningId =
        data && typeof data.reasoning_id === "string"
          ? data.reasoning_id
          : undefined;

      // 获取 reasoningLive 状态（流式中=true，完成=false）
      const isLive =
        data && typeof data.reasoningLive === "boolean"
          ? data.reasoningLive
          : true; // 默认流式中

      set((s) => {
        const msgs = [...s.messages];

        // 如果有 reasoningId，查找具有相同 reasoningId 的消息
        if (reasoningId) {
          const existingIndex = msgs.findIndex(
            (m) => m.isReasoning && m.reasoningId === reasoningId,
          );
          if (existingIndex >= 0) {
            const target = msgs[existingIndex];
            // 传入 isLive 参数：流式中追加，最终事件直接替换
            const merged = mergeReasoningContent(target.content, content, isLive);
            msgs[existingIndex] = {
              ...target,
              content: merged,
              reasoningLive: isLive,
            };
            return { messages: msgs };
          }
          // 没有找到相同 reasoningId 的消息，创建新消息
          // 按时间顺序追加到消息列表末尾（不再强制插入到回答之前）
          const msg: Message = {
            id: nextId(),
            role: "assistant",
            content,
            isReasoning: true,
            reasoningLive: isLive,
            reasoningId,
            turnId,
            timestamp: Date.now(),
          };
          msgs.push(msg);
          return { messages: msgs };
        }

        // 没有 reasoningId（向后兼容）：查找同一 turnId 的最后一个 reasoning 消息
        const lastReasoningIndex = [...msgs]
          .reverse()
          .findIndex(
            (m) =>
              m.isReasoning &&
              !m.analysisPlan &&
              (m.turnId || undefined) === turnId,
          );

        if (lastReasoningIndex >= 0) {
          const idx = msgs.length - 1 - lastReasoningIndex;
          const target = msgs[idx];
          // 传入 isLive 参数：流式中追加，最终事件直接替换
          const merged = mergeReasoningContent(target.content, content, isLive);
          msgs[idx] = {
            ...target,
            content: merged,
            reasoningLive: isLive,
          };
          return { messages: msgs };
        }

        // 创建新的 reasoning 消息
        // 按时间顺序追加到消息列表末尾（不再强制插入到回答之前）
        const msg: Message = {
          id: nextId(),
          role: "assistant",
          content,
          isReasoning: true,
          reasoningLive: isLive,
          turnId,
          timestamp: Date.now(),
        };
        msgs.push(msg);
        return { messages: msgs };
      });
      break;
    }

    case "tool_call": {
      const data = evt.data as { name: string; arguments: string };
      const turnId = evt.turn_id || get()._currentTurnId || undefined;
      let toolArgs: Record<string, unknown> = {};
      try {
        const parsed = JSON.parse(data.arguments);
        toolArgs = isRecord(parsed) ? parsed : { value: parsed };
      } catch {
        toolArgs = { raw: data.arguments };
      }
      toolArgs = normalizeRunCodeIntent(data.name, toolArgs);
      const intent =
        typeof evt.metadata?.intent === "string"
          ? evt.metadata.intent
          : data.name === "run_code" && typeof toolArgs.intent === "string"
            ? toolArgs.intent
            : undefined;
      const msg: Message = {
        id: nextId(),
        role: "tool",
        content:
          data.name === "run_code" && intent
            ? `🔧 ${data.name}: ${intent}`
            : `调用工具: **${data.name}**`,
        toolName: data.name,
        toolCallId: evt.tool_call_id || undefined,
        toolInput: toolArgs,
        toolIntent: intent,
        turnId,
        timestamp: Date.now(),
      };
      set((s) => ({ messages: [...s.messages, msg] }));
      break;
    }

    case "tool_result": {
      const data = evt.data as Record<string, unknown>;
      const status = (data.status as "success" | "error") || "success";
      const resultMessage =
        (data.message as string) ||
        (status === "error" ? "工具执行失败" : "工具执行完成");
      const toolCallId = evt.tool_call_id;
      const turnId = evt.turn_id || get()._currentTurnId || undefined;
      const shouldClearPendingQuestion = evt.tool_name === "ask_user_question";

      set((s) => {
        const msgs = [...s.messages];
        // 查找是否有对应的 tool_call 消息
        const existingIndex = msgs.findIndex(
          (m) =>
            m.role === "tool" && m.toolCallId === toolCallId && !m.toolResult,
        );

        if (existingIndex >= 0) {
          // 合并到现有消息
          msgs[existingIndex] = {
            ...msgs[existingIndex],
            toolResult: resultMessage,
            toolStatus: status,
            toolIntent:
              msgs[existingIndex].toolIntent ||
              (typeof evt.metadata?.intent === "string"
                ? evt.metadata.intent
                : undefined),
          };
        } else {
          // 创建新的结果消息
          msgs.push({
            id: nextId(),
            role: "tool",
            content: resultMessage,
            toolName: evt.tool_name || undefined,
            toolCallId: toolCallId || undefined,
            toolResult: resultMessage,
            toolStatus: status,
            toolIntent:
              typeof evt.metadata?.intent === "string"
                ? evt.metadata.intent
                : undefined,
            turnId,
            timestamp: Date.now(),
          });
        }
        return {
          messages: msgs,
          ...(shouldClearPendingQuestion ? { pendingAskUserQuestion: null } : {}),
        };
      });
      break;
    }

    case "retrieval": {
      const data = isRecord(evt.data) ? evt.data : null;
      const query =
        data && typeof data.query === "string" ? data.query : "检索结果";
      const rawResults =
        data && Array.isArray(data.results) ? data.results : [];
      const retrievals: RetrievalItem[] = rawResults
        .filter((item): item is Record<string, unknown> => isRecord(item))
        .map((item) => ({
          source: typeof item.source === "string" ? item.source : "unknown",
          score: typeof item.score === "number" ? item.score : undefined,
          hits: typeof item.hits === "number" ? item.hits : undefined,
          snippet: typeof item.snippet === "string" ? item.snippet : "",
        }));
      if (retrievals.length === 0) break;

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
      break;
    }

    case "chart": {
      const turnId = evt.turn_id || get()._currentTurnId || undefined;
      const msg: Message = {
        id: nextId(),
        role: "assistant",
        content: "图表已生成",
        chartData: evt.data,
        turnId,
        timestamp: Date.now(),
      };
      set((s) => ({ messages: [...s.messages, msg] }));
      break;
    }

    case "data": {
      const turnId = evt.turn_id || get()._currentTurnId || undefined;
      const msg: Message = {
        id: nextId(),
        role: "assistant",
        content: "数据预览如下",
        dataPreview: evt.data,
        turnId,
        timestamp: Date.now(),
      };
      set((s) => ({ messages: [...s.messages, msg] }));
      break;
    }

    case "artifact": {
      // 将产物附加到最近的 tool/assistant 消息上
      const artifact = evt.data as ArtifactInfo;
      if (artifact && artifact.download_url) {
        set((s) => {
          const msgs = [...s.messages];
          // 找到最近的 tool 或 assistant 消息来附加 artifact
          for (let i = msgs.length - 1; i >= 0; i--) {
            if (msgs[i].role === "tool" || msgs[i].role === "assistant") {
              const existing = msgs[i].artifacts || [];
              msgs[i] = { ...msgs[i], artifacts: [...existing, artifact] };
              break;
            }
          }
          return { messages: msgs };
        });
      }
      break;
    }

    case "image": {
      // 图片事件：将图片 URL 附加到最近的 assistant 消息，或创建新消息
      const imageData = evt.data as { url?: string; urls?: string[] };
      const urls: string[] = [];
      if (imageData.url) urls.push(imageData.url);
      if (imageData.urls) urls.push(...imageData.urls);

      if (urls.length > 0) {
        set((s) => {
          const msgs = [...s.messages];
          // 尝试找到最近的 assistant 消息来附加图片
          for (let i = msgs.length - 1; i >= 0; i--) {
            if (msgs[i].role === "assistant" && !msgs[i].toolName) {
              const existing = msgs[i].images || [];
              msgs[i] = { ...msgs[i], images: [...existing, ...urls] };
              return { messages: msgs };
            }
          }
          // 如果没找到 assistant 消息，创建一个新消息
          msgs.push({
            id: nextId(),
            role: "assistant",
            content: "图片已生成",
            images: urls,
            timestamp: Date.now(),
          });
          return { messages: msgs };
        });
      }
      break;
    }

    case "session_title": {
      const data = evt.data as { session_id: string; title: string };
      if (data && data.session_id && data.title) {
        set((s) => ({
          sessions: s.sessions.map((sess) =>
            sess.id === data.session_id ? { ...sess, title: data.title } : sess,
          ),
        }));
      }
      break;
    }

    case "workspace_update": {
      // 工作区文件变更，刷新文件列表
      get().fetchWorkspaceFiles();
      get().fetchDatasets();
      break;
    }

    case "code_execution": {
      // 新的代码执行记录
      const execRecord = evt.data as CodeExecution;
      if (execRecord && execRecord.id) {
        set((s) => ({
          codeExecutions: [execRecord, ...s.codeExecutions],
        }));
      }
      break;
    }

    case "context_compressed": {
      // 上下文自动压缩通知
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
      break;
    }

    case "token_usage": {
      // Token 使用量实时更新
      const data = isRecord(evt.data) ? evt.data : null;
      if (!data) break;

      const model = typeof data.model === "string" ? data.model : "unknown";
      const inputTokens =
        typeof data.input_tokens === "number" ? data.input_tokens : 0;
      const outputTokens =
        typeof data.output_tokens === "number" ? data.output_tokens : 0;
      const totalTokens =
        typeof data.total_tokens === "number"
          ? data.total_tokens
          : inputTokens + outputTokens;
      const costUsd =
        typeof data.cost_usd === "number" ? data.cost_usd : null;
      const sessionTotalTokens =
        typeof data.session_total_tokens === "number"
          ? data.session_total_tokens
          : totalTokens;
      const sessionTotalCost =
        typeof data.session_total_cost === "number"
          ? data.session_total_cost
          : 0;

      set((s) => {
        const current = s.tokenUsage;
        if (!current) {
          // 如果没有现有数据，创建新的 TokenUsage
          return {
            tokenUsage: {
              session_id: s.sessionId || "",
              input_tokens: inputTokens,
              output_tokens: outputTokens,
              total_tokens: sessionTotalTokens,
              estimated_cost_usd: sessionTotalCost,
              estimated_cost_cny: sessionTotalCost * 7.2, // 近似汇率
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
              } as Record<string, { model_id: string; input_tokens: number; output_tokens: number; total_tokens: number; cost_usd: number; cost_cny: number; call_count: number }>,
              updated_at: new Date().toISOString(),
            },
          };
        }

        // 更新现有数据
        const modelBreakdown = { ...current.model_breakdown };
        const existing = modelBreakdown[model];
        if (existing) {
          modelBreakdown[model] = {
            ...existing,
            input_tokens: (existing as { input_tokens: number }).input_tokens + inputTokens,
            output_tokens: (existing as { output_tokens: number }).output_tokens + outputTokens,
            total_tokens: (existing as { total_tokens: number }).total_tokens + totalTokens,
            cost_usd: (existing as { cost_usd: number }).cost_usd + (costUsd || 0),
            cost_cny: (existing as { cost_cny: number }).cost_cny + (costUsd || 0) * 7.2,
            call_count: (existing as { call_count: number }).call_count + 1,
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
      break;
    }

    case "done":
      set((s) => {
        let progress = s.analysisPlanProgress;
        let tasks = s.analysisTasks;
        const turnId = s._currentTurnId;
        if (progress && progress.step_status === "in_progress") {
          // 使用 turn_id 优先匹配当前回合的任务
          const taskId = findTaskIdByStepAndTurn(
            s.analysisTasks,
            progress.current_step_index,
            turnId,
          );
          const currentTask = taskId
            ? tasks.find((task) => task.id === taskId)
            : undefined;
          const mergedStatus = currentTask
            ? mergePlanStepStatus(currentTask.status, "done")
            : "done";
          tasks = updateAnalysisTaskById(tasks, taskId, {
            status: mergedStatus,
            current_activity: "步骤已完成",
            last_error: null,
          });
          progress = applyPlanStepUpdateToProgress(
            progress,
            progress.current_step_index,
            "done",
          );
        }
        if (progress && areAllPlanStepsDone(progress.steps)) {
          progress = {
            ...progress,
            step_status: "done",
            next_hint: "全部步骤已完成。",
            block_reason: null,
          };
        }
        return {
          messages: finalizeReasoningMessages(s.messages, turnId),
          isStreaming: false,
          pendingAskUserQuestion: null,
          _streamingText: "",
          _currentTurnId: null,
          _activePlanMsgId: null,
          _activePlanTaskIds: [],
          _planActionTaskMap: {},
          analysisPlanProgress: progress,
          analysisTasks: tasks,
        };
      });
      // 对话结束后刷新会话列表（更新消息计数）
      get().fetchSessions();
      break;

    case "stopped":
      set((s) => {
        let progress = s.analysisPlanProgress;
        let tasks = s.analysisTasks;
        const turnId = s._currentTurnId;
        if (progress && progress.step_status === "in_progress") {
          // 使用 turn_id 优先匹配当前回合的任务
          const taskId = findTaskIdByStepAndTurn(
            s.analysisTasks,
            progress.current_step_index,
            turnId,
          );
          const currentTask = taskId
            ? tasks.find((task) => task.id === taskId)
            : undefined;
          const mergedStatus = currentTask
            ? mergePlanStepStatus(currentTask.status, "blocked")
            : "blocked";
          tasks = updateAnalysisTaskById(tasks, taskId, {
            status: mergedStatus,
            current_activity: "步骤已阻塞",
          });
          const idx = progress.current_step_index - 1;
          const steps: AnalysisStep[] = progress.steps.map((step, stepIdx) =>
            stepIdx === idx ? { ...step, status: "blocked" } : step,
          );
          progress = {
            ...progress,
            step_status: "blocked",
            next_hint: "你可以重新发送请求继续当前流程。",
            block_reason: "用户手动停止当前请求",
            steps,
          };
        }
        return {
          messages: finalizeReasoningMessages(s.messages, turnId),
          isStreaming: false,
          pendingAskUserQuestion: null,
          _streamingText: "",
          _currentTurnId: null,
          _activePlanMsgId: null,
          _activePlanTaskIds: [],
          _planActionTaskMap: {},
          analysisPlanProgress: progress,
          analysisTasks: tasks,
        };
      });
      break;

    case "error": {
      const normalizedError = normalizeWsError(evt.data);
      const turnId = get()._currentTurnId || evt.turn_id || undefined;
      const errMsg: Message = {
        id: nextId(),
        role: "assistant",
        content: `错误: ${normalizedError.message}`,
        isError: true,
        errorKind: normalizedError.kind,
        errorCode: normalizedError.code,
        errorHint: normalizedError.hint,
        errorDetail: normalizedError.detail,
        retryable: normalizedError.retryable,
        turnId,
        timestamp: Date.now(),
      };
      set((s) => ({
        messages: [
          ...finalizeReasoningMessages(s.messages, turnId),
          errMsg,
        ],
        isStreaming: false,
        pendingAskUserQuestion: null,
        _streamingText: "",
        _currentTurnId: null,
        _activePlanMsgId: null,
        _activePlanTaskIds: [],
        _planActionTaskMap: {},
        analysisTasks: (() => {
          const progress = s.analysisPlanProgress;
          if (!progress || progress.step_status !== "in_progress") {
            return s.analysisTasks;
          }
          // 使用 turn_id 优先匹配当前回合的任务
          const taskId = findTaskIdByStepAndTurn(
            s.analysisTasks,
            progress.current_step_index,
            s._currentTurnId,
          );
          const currentTask = taskId
            ? s.analysisTasks.find((task) => task.id === taskId)
            : undefined;
          const mergedStatus = currentTask
            ? mergePlanStepStatus(currentTask.status, "failed")
            : "failed";
          return updateAnalysisTaskById(s.analysisTasks, taskId, {
            status: mergedStatus,
            current_activity: "步骤执行失败",
            last_error: normalizedError.detail || normalizedError.message,
          });
        })(),
        analysisPlanProgress: (() => {
          const progress = s.analysisPlanProgress;
          if (!progress || progress.step_status !== "in_progress")
            return progress;
          const failedIndex = progress.current_step_index - 1;
          return {
            ...progress,
            step_status: "failed",
            block_reason: normalizedError.detail || normalizedError.message,
            next_hint: "请检查错误信息后重试。",
            steps: progress.steps.map((step, idx) =>
              idx === failedIndex ? { ...step, status: "failed" } : step,
            ),
          };
        })(),
      }));
      break;
    }
  }
}

// ---- applyPlanProgressPayload 辅助函数 ----

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

// ---- 需要从 normalizers 导入的辅助函数 ----

function normalizeTaskAttemptStatus(
  raw: unknown,
): AnalysisTaskAttemptStatus {
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

function clampStepIndex(index: number, total: number): number {
  if (total <= 0) return 0;
  return Math.max(1, Math.min(index, total));
}

function truncatePlanText(text: string, maxLen = 72): string {
  const normalized = text.trim();
  if (normalized.length <= maxLen) return normalized;
  return `${normalized.slice(0, Math.max(0, maxLen - 1)).trimEnd()}…`;
}

function createDefaultPlanSteps(total: number): AnalysisStep[] {
  const safeTotal = Math.max(0, total);
  return Array.from({ length: safeTotal }, (_, idx) => ({
    id: idx + 1,
    title: `步骤 ${idx + 1}`,
    tool_hint: null,
    status: "not_started" as const,
  }));
}

function deriveNextHint(
  steps: AnalysisStep[],
  currentStepIndex: number,
  currentStatus: import("./types").PlanStepStatus,
): string {
  if (steps.length === 0) return "";
  const safeIndex = clampStepIndex(currentStepIndex, steps.length);
  const nextStep = steps[safeIndex];

  if (currentStatus === "failed" || currentStatus === "blocked") {
    return "可尝试重试当前步骤或补充输入后继续。";
  }
  if (currentStatus === "done" && safeIndex >= steps.length) {
    return "全部步骤已完成。";
  }
  if (currentStatus === "done" && nextStep) {
    return `下一步：${truncatePlanText(nextStep.title)}`;
  }
  if (currentStatus === "in_progress" && nextStep) {
    return `完成后将进入：${truncatePlanText(nextStep.title)}`;
  }
  return `下一步：${truncatePlanText(steps[safeIndex - 1]?.title || "继续执行")}`;
}
