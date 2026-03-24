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
  AskUserQuestionItem,
  AskUserQuestionOption,
  CodeExecution,
  ModelTokenUsage,
  MessageBuffer,
  StreamingMetrics,
  HarnessRunContextState,
  CompletionCheckState,
  HarnessBlockedState,
  AgentInfo,
} from "./types";

import {
  isRecord,
  nextId,
  applyPlanStepUpdateToProgress,
  updateAnalysisTaskById,
  findTaskIdByStepAndTurn,
} from "./utils";

import {
  looksLikeToolCallReasoningPollution,
  mergePlanStepStatus,
  stripReasoningMarkers,
} from "./normalizers";
import {
  upsertAssistantTextMessage,
  upsertReasoningMessage,
  upsertToolCallMessage,
  upsertToolResultMessage,
} from "./message-normalizer";
import { normalizeToolResult } from "./tool-result";
import {
  getSessionUiCacheEntry,
  updateSessionUiCacheEntry,
} from "./session-ui-cache";

import { areAllPlanStepsDone } from "./plan-state-machine";
import { handleAgentEvent } from "./agent-event-handler";
import { handleHypothesisEvent } from "./hypothesis-event-handler";

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
  closeAllWhenTurnMissing: boolean = false,
): Message[] {
  let changed = false;
  const next = messages.map((msg) => {
    if (!msg.isReasoning || !msg.reasoningLive) return msg;
    if (!turnId && closeAllWhenTurnMissing) {
      changed = true;
      return { ...msg, reasoningLive: false };
    }
    // 如果提供了 turnId，只关闭匹配该 turnId 的消息
    if (turnId) {
      if (msg.turnId && msg.turnId !== turnId) return msg;
    } else {
      // 如果没有提供 turnId，只关闭没有 turnId 的消息（避免误关闭其他回合的消息）
      if (msg.turnId) return msg;
    }
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
  _messageBuffer: MessageBuffer;
  _streamingMetrics: StreamingMetrics;
  activeModel?: {
    provider_id: string;
    provider_name: string;
    model: string;
    preferred_provider: string | null;
  } | null;
  runtimeModel?: {
    provider_id: string;
    provider_name: string;
    model: string;
    preferred_provider: string | null;
  } | null;
  modelFallback?: {
    purpose: string;
    attempt: number;
    from_provider_id?: string | null;
    from_provider_name?: string | null;
    from_model?: string | null;
    to_provider_id: string;
    to_provider_name: string;
    to_model: string;
    reason?: string | null;
    fallback_chain?: Array<Record<string, unknown>>;
    occurred_at: number;
  } | null;
  analysisPlanProgress: AnalysisPlanProgress | null;
  analysisTasks: AnalysisTaskItem[];
  harnessRunContext: HarnessRunContextState | null;
  completionCheck: CompletionCheckState | null;
  blockedState: HarnessBlockedState | null;
  pendingAskUserQuestionsBySession: Record<string, {
    sessionId: string;
    sessionTitle: string;
    toolCallId: string;
    questions: AskUserQuestionItem[];
    questionCount: number;
    createdAt: number;
    attentionRequestedAt: number;
  }>;
  pendingAskUserQuestion: {
    sessionId: string;
    sessionTitle: string;
    toolCallId: string;
    questions: AskUserQuestionItem[];
    questionCount: number;
    createdAt: number;
    attentionRequestedAt: number;
  } | null;
  askUserQuestionNotificationPreference: "default" | "enabled" | "denied";
  isStreaming: boolean;
  /** 所有正在运行 Agent 的 session_id 集合（多会话并发） */
  runningSessions: Set<string>;
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
  // 多 Agent 执行状态
  activeAgents: Record<string, AgentInfo>;
  completedAgents: AgentInfo[];
  // 假设驱动范式状态
  hypotheses: import("./types").HypothesisInfo[];
  currentPhase: string;
  iterationCount: number;
  activeAgentId: string | null;
  // 操作函数
  fetchSessions: () => Promise<void>;
  fetchDatasets: () => Promise<void>;
  fetchWorkspaceFiles: () => Promise<void>;
  fetchSkills: () => Promise<void>;
  switchSession?: (sessionId: string) => Promise<void>;
}

function resetStreamingMetrics(): StreamingMetrics {
  return {
    startedAt: null,
    turnId: null,
    totalTokens: 0,
    hasTokenUsage: false,
  };
}

function isActiveSessionEvent(evt: WSEvent, get: GetStateFn): boolean {
  const currentSessionId = get().sessionId;
  return (
    typeof evt.session_id === "string" &&
    evt.session_id.length > 0 &&
    currentSessionId === evt.session_id
  );
}

function getBackgroundSessionId(evt: WSEvent, get: GetStateFn): string | null {
  const sessionId =
    typeof evt.session_id === "string" && evt.session_id.trim()
      ? evt.session_id.trim()
      : null;
  if (!sessionId) return null;
  return sessionId === get().sessionId ? null : sessionId;
}

function resolveSessionTitle(state: AppStateSubset, sessionId: string): string {
  const matched = state.sessions.find((item) => item.id === sessionId);
  const title = matched?.title?.trim();
  return title || "新会话";
}

function resolveCurrentPendingAskUserQuestion(
  state: AppStateSubset,
  sessionId: string | null,
) {
  if (!sessionId) return null;
  return state.pendingAskUserQuestionsBySession[sessionId] ?? null;
}

function buildPendingAskUserQuestionPatch(
  state: AppStateSubset,
  sessionId: string,
  pending: AppStateSubset["pendingAskUserQuestion"],
) {
  const nextPendingBySession = { ...state.pendingAskUserQuestionsBySession };
  if (pending) {
    nextPendingBySession[sessionId] = pending;
  } else {
    delete nextPendingBySession[sessionId];
  }
  return {
    pendingAskUserQuestionsBySession: nextPendingBySession,
    pendingAskUserQuestion: resolveCurrentPendingAskUserQuestion(
      { ...state, pendingAskUserQuestionsBySession: nextPendingBySession },
      state.sessionId,
    ),
  };
}

function maybeNotifyAskUserQuestion(
  state: AppStateSubset,
  pending: NonNullable<AppStateSubset["pendingAskUserQuestion"]>,
): void {
  if (state.askUserQuestionNotificationPreference !== "enabled") return;
  if (state.sessionId === pending.sessionId && typeof document !== "undefined" && !document.hidden) {
    return;
  }
  const notificationApi =
    typeof window !== "undefined" && "Notification" in window
      ? window.Notification
      : typeof Notification !== "undefined"
        ? Notification
        : null;
  if (!notificationApi || notificationApi.permission !== "granted") return;

  const body =
    pending.questionCount > 1
      ? `需要你回答 ${pending.questionCount} 个问题以继续执行`
      : "需要你回答 1 个问题以继续执行";
  const notification = new notificationApi(pending.sessionTitle, {
    body,
    tag: `ask-user-question:${pending.toolCallId}`,
  });

  notification.onclick = () => {
    if (typeof window !== "undefined") {
      window.focus();
    }
    void state.switchSession?.(pending.sessionId);
    notification.close();
  };
}

export function handleEvent(
  evt: WSEvent,
  set: SetStateFn,
  get: GetStateFn,
): Promise<void> | void {
  switch (evt.type) {
    case "session": {
      const data = evt.data;
      if (isRecord(data) && typeof data.session_id === "string") {
        const currentSessionId = get().sessionId;
        if (!currentSessionId || currentSessionId === data.session_id) {
          set({ sessionId: data.session_id });
        }
        // 新会话创建后刷新会话列表
        get().fetchSessions();
        get().fetchDatasets();
        get().fetchWorkspaceFiles();
        get().fetchSkills();
      }
      break;
    }

    case "iteration_start": {
      const backgroundSessionId = getBackgroundSessionId(evt, get);
      if (backgroundSessionId) {
        updateSessionUiCacheEntry(backgroundSessionId, (entry) => ({
          ...entry,
          currentTurnId: evt.turn_id || null,
          streamingText: "",
          lastHandledSeq: undefined,
          harnessRunContext: null,
          completionCheck: null,
          blockedState: null,
          streamingMetrics: entry.streamingMetrics.startedAt
            ? {
                ...entry.streamingMetrics,
                turnId: evt.turn_id || null,
              }
            : {
                ...entry.streamingMetrics,
                startedAt: Date.now(),
                turnId: evt.turn_id || null,
              },
        }));
        break;
      }
      // 新迭代开始：重置流式文本累积，记录 turnId，同时重置序列号
      set((s) => ({
        _streamingText: "",
        _currentTurnId: evt.turn_id || null,
        _lastHandledSeq: undefined,
        modelFallback: null,
        harnessRunContext: null,
        completionCheck: null,
        blockedState: null,
        _streamingMetrics: s._streamingMetrics.startedAt
          ? {
              ...s._streamingMetrics,
              turnId: evt.turn_id || null,
            }
          : s._streamingMetrics,
      }));
      break;
    }

    case "text": {
      const backgroundSessionId = getBackgroundSessionId(evt, get);
      const rawText =
        typeof evt.data === "string"
          ? evt.data
          : isRecord(evt.data) && typeof evt.data.content === "string"
            ? evt.data.content
            : "";
      const text = stripReasoningMarkers(rawText);

      // ============================================================
      // 消息去重架构 (Message Deduplication Architecture)
      // ============================================================
      // 问题：后端流式推送时，同一消息可能分多次发送，且 generate_report 等
      // 工具会再次发送完整内容，导致前端显示重复。
      //
      // 解决方案：
      // 1. 后端为每个消息分配唯一 message_id (格式: {turn_id}-{sequence})
      // 2. 通过 operation 字段区分操作类型：
      //    - "append": 累积到现有消息（流式生成）
      //    - "replace": 替换整个消息内容（工具结果）
      //    - "complete": 标记消息结束，清理缓冲区
      // 3. 前端使用 _messageBuffer 按 message_id 累积内容
      //
      // 向后兼容：无 message_id 的事件使用旧逻辑（简单追加）
      // ============================================================

      const messageId = evt.metadata?.message_id as string | undefined;
      const operation = (evt.metadata?.operation as "append" | "replace" | "complete" | undefined) || "append";

      // 如果存在 message_id，使用新逻辑（消息去重）
      if (messageId) {
        if (backgroundSessionId) {
          updateSessionUiCacheEntry(backgroundSessionId, (entry) => {
            const turnId = evt.turn_id || entry.currentTurnId || undefined;
            const timestamp = Date.now();
            let effectiveOperation = operation;
            let finalContent = text;
            if (!text && operation === "complete") {
              return entry;
            }
            if (operation === "complete") {
              effectiveOperation = "replace";
            }
            const nextMessages = upsertAssistantTextMessage(entry.messages, {
              content: finalContent,
              timestamp,
              messageId,
              turnId,
              operation: effectiveOperation,
            });
            const currentContent =
              nextMessages.find(
                (msg) =>
                  msg.role === "assistant" &&
                  !msg.isReasoning &&
                  msg.messageId === messageId,
              )?.content ?? finalContent;
            return {
              ...entry,
              messages: nextMessages,
              streamingText: operation === "complete" ? "" : currentContent,
              currentTurnId: turnId ?? entry.currentTurnId,
            };
          });
          break;
        }
        set((s) => {
          const buffer = { ...s._messageBuffer };
          const turnId = evt.turn_id || s._currentTurnId || undefined;
          const timestamp = Date.now();
          if (!text && operation === "complete") {
            delete buffer[messageId];
            return { _messageBuffer: buffer };
          }

          let effectiveOperation = operation;
          let finalContent = text;
          if (operation === "complete") {
            effectiveOperation = "replace";
            // complete 事件以服务端返回的完整内容为权威来源，直接替换。
            // 原有的"本地缓冲 + 服务端内容拼接"逻辑会在 HarnessRunner 以同一
            // turn_id 多次调用 AgentRunner 时，把两轮回答内容错误地拼到同一气泡中。
            finalContent = text;
          }

          const nextMessages = upsertAssistantTextMessage(s.messages, {
            content: finalContent,
            timestamp,
            messageId,
            turnId,
            operation: effectiveOperation,
          });
          const currentContent =
            nextMessages.find(
              (msg) =>
                msg.role === "assistant" &&
                !msg.isReasoning &&
                msg.messageId === messageId,
            )?.content ?? finalContent;

          if (operation === "complete") {
            delete buffer[messageId];
          } else {
            buffer[messageId] = {
              content: currentContent,
              operation: effectiveOperation,
              timestamp,
            };
          }

          return {
            messages: nextMessages,
            _streamingText: currentContent,
            _messageBuffer: buffer,
          };
        });
        break;
      }

      // ===== 旧逻辑（向后兼容）=====
      if (!text) break;
      if (backgroundSessionId) {
        updateSessionUiCacheEntry(backgroundSessionId, (entry) => {
          const seq = evt.metadata?.seq as number | undefined;
          if (
            seq !== undefined &&
            entry.lastHandledSeq !== undefined &&
            seq <= entry.lastHandledSeq
          ) {
            return entry;
          }
          const newStreamText = entry.streamingText + text;
          const turnId = evt.turn_id || entry.currentTurnId || undefined;
          const msgs = [...entry.messages];
          const last = msgs[msgs.length - 1];
          let targetIndex = -1;
          if (
            last &&
            last.role === "assistant" &&
            !last.toolName &&
            !last.retrievals &&
            !last.isReasoning &&
            last.turnId === turnId
          ) {
            targetIndex = msgs.length - 1;
          } else {
            for (let i = msgs.length - 1; i >= 0; i -= 1) {
              const message = msgs[i];
              if (
                message.role === "assistant" &&
                !message.toolName &&
                !message.retrievals &&
                !message.isReasoning &&
                message.turnId === turnId
              ) {
                targetIndex = i;
                break;
              }
            }
          }
          if (targetIndex >= 0) {
            msgs[targetIndex] = { ...msgs[targetIndex], content: newStreamText };
          } else {
            const isDuplicate = msgs.some(
              (message) =>
                message.role === "assistant" &&
                !message.isReasoning &&
                message.content === newStreamText,
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
          return {
            ...entry,
            messages: msgs,
            streamingText: newStreamText,
            currentTurnId: turnId ?? entry.currentTurnId,
            lastHandledSeq: seq,
          };
        });
        break;
      }

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

    case "model_fallback": {
      if (!isActiveSessionEvent(evt, get)) break;
      const data = isRecord(evt.data) ? evt.data : null;
      if (!data) break;

      const toProviderId =
        typeof data.to_provider_id === "string" ? data.to_provider_id.trim() : "";
      const toProviderName =
        typeof data.to_provider_name === "string"
          ? data.to_provider_name.trim()
          : toProviderId || "unknown";
      const toModel =
        typeof data.to_model === "string" ? data.to_model.trim() : "";
      if (!toProviderId || !toModel) break;

      const reason =
        typeof data.reason === "string" && data.reason.trim()
          ? data.reason.trim()
          : null;
      const fromModel =
        typeof data.from_model === "string" && data.from_model.trim()
          ? data.from_model.trim()
          : null;

      const summary = fromModel
        ? `首选模型 ${fromModel} 不可用，已降级到 ${toModel}${reason ? `（${reason}）` : ""}`
        : `模型不可用，已降级到 ${toModel}${reason ? `（${reason}）` : ""}`;
      const turnId = evt.turn_id || get()._currentTurnId || undefined;

      set((s) => ({
        runtimeModel: {
          provider_id: toProviderId,
          provider_name: toProviderName,
          model: toModel,
          preferred_provider: s.activeModel?.preferred_provider ?? null,
        },
        modelFallback: {
          purpose:
            typeof data.purpose === "string" && data.purpose.trim()
              ? data.purpose.trim()
              : "chat",
          attempt:
            typeof data.attempt === "number" && Number.isFinite(data.attempt)
              ? Math.max(1, Math.floor(data.attempt))
              : 1,
          from_provider_id:
            typeof data.from_provider_id === "string"
              ? data.from_provider_id.trim()
              : null,
          from_provider_name:
            typeof data.from_provider_name === "string"
              ? data.from_provider_name.trim()
              : null,
          from_model: fromModel,
          to_provider_id: toProviderId,
          to_provider_name: toProviderName,
          to_model: toModel,
          reason,
          fallback_chain: Array.isArray(data.fallback_chain)
            ? (data.fallback_chain as Array<Record<string, unknown>>)
            : [],
          occurred_at: Date.now(),
        },
        messages: [
          ...s.messages,
          {
            id: nextId(),
            role: "assistant",
            content: `模型降级：${summary}`,
            turnId,
            timestamp: Date.now(),
          },
        ],
      }));
      break;
    }

    case "run_context": {
      const data = isRecord(evt.data) ? evt.data : null;
      if (!data) break;
      const datasets = Array.isArray(data.datasets) ? data.datasets : [];
      const artifacts = Array.isArray(data.artifacts) ? data.artifacts : [];
      const nextRunContext = {
        turnId:
          typeof data.turn_id === "string" && data.turn_id.trim()
            ? data.turn_id.trim()
            : evt.turn_id || "",
        datasets: datasets
          .filter((item): item is Record<string, unknown> => isRecord(item))
          .map((item) => ({
            name: typeof item.name === "string" ? item.name.trim() : "",
            rows:
              typeof item.rows === "number" && Number.isFinite(item.rows)
                ? item.rows
                : null,
            columns:
              typeof item.columns === "number" && Number.isFinite(item.columns)
                ? item.columns
                : null,
          }))
          .filter((item) => item.name),
        artifacts: artifacts
          .filter((item): item is Record<string, unknown> => isRecord(item))
          .map((item) => ({
            name: typeof item.name === "string" ? item.name.trim() : "",
            artifactType:
              typeof item.artifact_type === "string"
                ? item.artifact_type.trim()
                : null,
          }))
          .filter((item) => item.name),
        toolHints: Array.isArray(data.tool_hints)
          ? data.tool_hints
              .filter((item): item is string => typeof item === "string")
              .map((item) => item.trim())
              .filter(Boolean)
          : [],
        constraints: Array.isArray(data.constraints)
          ? data.constraints
              .filter((item): item is string => typeof item === "string")
              .map((item) => item.trim())
              .filter(Boolean)
          : [],
      };
      const backgroundSessionId = getBackgroundSessionId(evt, get);
      if (backgroundSessionId) {
        updateSessionUiCacheEntry(backgroundSessionId, (entry) => ({
          ...entry,
          harnessRunContext: nextRunContext,
          workspacePanelTab: "tasks",
        }));
        break;
      }
      set({
        harnessRunContext: nextRunContext,
        workspacePanelOpen: true,
        workspacePanelTab: "tasks",
      });
      break;
    }

    case "completion_check": {
      const data = isRecord(evt.data) ? evt.data : null;
      if (!data) break;
      const items = Array.isArray(data.items) ? data.items : [];
      const state: CompletionCheckState = {
        turnId:
          typeof data.turn_id === "string" && data.turn_id.trim()
            ? data.turn_id.trim()
            : evt.turn_id || "",
        passed: data.passed === true,
        attempt:
          typeof data.attempt === "number" && Number.isFinite(data.attempt)
            ? Math.max(1, Math.floor(data.attempt))
            : 1,
        items: items
          .filter((item): item is Record<string, unknown> => isRecord(item))
          .map((item) => ({
            key: typeof item.key === "string" ? item.key.trim() : "",
            label: typeof item.label === "string" ? item.label.trim() : "",
            passed: item.passed === true,
            detail: typeof item.detail === "string" ? item.detail.trim() : "",
          }))
          .filter((item) => item.key && item.label),
        missingActions: Array.isArray(data.missing_actions)
          ? data.missing_actions
              .filter((item): item is string => typeof item === "string")
              .map((item) => item.trim())
              .filter(Boolean)
          : [],
      };
      const backgroundSessionId = getBackgroundSessionId(evt, get);
      if (backgroundSessionId) {
        updateSessionUiCacheEntry(backgroundSessionId, (entry) => ({
          ...entry,
          completionCheck: state,
          analysisPlanProgress:
            entry.analysisPlanProgress && !state.passed
              ? {
                  ...entry.analysisPlanProgress,
                  next_hint:
                    state.missingActions.length > 0
                      ? `系统正在补齐：${state.missingActions.join("、")}`
                      : entry.analysisPlanProgress.next_hint,
                }
              : entry.analysisPlanProgress,
          workspacePanelTab: "tasks",
        }));
        break;
      }
      set((s) => ({
        completionCheck: state,
        analysisPlanProgress:
          s.analysisPlanProgress && !state.passed
            ? {
                ...s.analysisPlanProgress,
                next_hint:
                  state.missingActions.length > 0
                    ? `系统正在补齐：${state.missingActions.join("、")}`
                    : s.analysisPlanProgress.next_hint,
              }
            : s.analysisPlanProgress,
        workspacePanelOpen: true,
        workspacePanelTab: "tasks",
      }));
      break;
    }

    case "blocked": {
      const data = isRecord(evt.data) ? evt.data : null;
      if (!data) break;
      const blockedState: HarnessBlockedState = {
        turnId:
          typeof data.turn_id === "string" && data.turn_id.trim()
            ? data.turn_id.trim()
            : evt.turn_id || "",
        reasonCode:
          typeof data.reason_code === "string" ? data.reason_code.trim() : "blocked",
        message: typeof data.message === "string" ? data.message.trim() : "当前轮已阻塞",
        recoverable: data.recoverable !== false,
        suggestedAction:
          typeof data.suggested_action === "string"
            ? data.suggested_action.trim()
            : null,
      };
      const backgroundSessionId = getBackgroundSessionId(evt, get);
      if (backgroundSessionId) {
        updateSessionUiCacheEntry(backgroundSessionId, (entry) => ({
          ...entry,
          blockedState,
          analysisPlanProgress: entry.analysisPlanProgress
            ? (() => {
                const idx = entry.analysisPlanProgress.current_step_index - 1;
                const steps: AnalysisStep[] = entry.analysisPlanProgress.steps.map((step, stepIdx) =>
                  stepIdx === idx ? { ...step, status: "blocked" } : step,
                );
                return {
                  ...entry.analysisPlanProgress,
                  step_status: "blocked",
                  block_reason: blockedState.message,
                  next_hint:
                    blockedState.suggestedAction || "请根据阻塞原因补充信息后继续。",
                  steps,
                };
              })()
            : entry.analysisPlanProgress,
          workspacePanelTab: "tasks",
        }));
        break;
      }
      set((s) => ({
        blockedState,
        isStreaming: false,
        analysisPlanProgress: s.analysisPlanProgress
          ? (() => {
              const idx = s.analysisPlanProgress.current_step_index - 1;
              const steps: AnalysisStep[] = s.analysisPlanProgress.steps.map((step, stepIdx) =>
                stepIdx === idx ? { ...step, status: "blocked" } : step,
              );
              return {
                ...s.analysisPlanProgress,
                step_status: "blocked",
                block_reason: blockedState.message,
                next_hint:
                  blockedState.suggestedAction || "请根据阻塞原因补充信息后继续。",
                steps,
              };
            })()
          : s.analysisPlanProgress,
        workspacePanelOpen: true,
        workspacePanelTab: "tasks",
      }));
      break;
    }

    case "analysis_plan":
    case "plan_step_update":
    case "plan_progress":
    case "task_attempt":
      return import("./event-handler-extended").then(({ handleExtendedEvent }) => {
        handleExtendedEvent(evt, set, get);
      });

    case "ask_user_question": {
      const data = isRecord(evt.data) ? evt.data : null;
      const sessionId =
        typeof evt.session_id === "string" && evt.session_id.trim()
          ? evt.session_id.trim()
          : get().sessionId || "";
      const toolCallId =
        typeof evt.tool_call_id === "string" && evt.tool_call_id.trim()
          ? evt.tool_call_id.trim()
          : "";
      const rawQuestions =
        data && Array.isArray(data.questions) ? data.questions : [];
      if (!sessionId || !toolCallId || rawQuestions.length === 0) break;

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

          const validQuestionTypes = [
            "missing_info",
            "ambiguous_requirement",
            "approach_choice",
            "risk_confirmation",
            "suggestion",
          ] as const;
          const rawType = item.question_type;
          const question_type =
            typeof rawType === "string" &&
            (validQuestionTypes as readonly string[]).includes(rawType)
              ? (rawType as AskUserQuestionItem["question_type"])
              : undefined;

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
            question_type,
            context:
              typeof item.context === "string" ? item.context.trim() : undefined,
          };
        })
        .filter((item) => item.question && item.options.length >= 2);

      if (questions.length === 0) break;
      const pending = {
        sessionId,
        sessionTitle: resolveSessionTitle(get(), sessionId),
        toolCallId,
        questions,
        questionCount: questions.length,
        createdAt: Date.now(),
        attentionRequestedAt: Date.now(),
      };
      set((s) => buildPendingAskUserQuestionPatch(s, sessionId, pending));
      maybeNotifyAskUserQuestion(get(), pending);
      break;
    }

    case "reasoning": {
      const backgroundSessionId = getBackgroundSessionId(evt, get);
      const backgroundEntry = backgroundSessionId
        ? getSessionUiCacheEntry(backgroundSessionId)
        : null;
      // 如果同一 turnId 已有 analysis_plan 消息，则跳过 reasoning（避免重复）
      const turnId =
        evt.turn_id ||
        (backgroundSessionId
          ? backgroundEntry?.currentTurnId ?? undefined
          : get()._currentTurnId) ||
        undefined;
      if (turnId) {
        const hasPlan = (
          backgroundSessionId
            ? backgroundEntry?.messages ?? []
            : get().messages
        ).some(
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
      if (looksLikeToolCallReasoningPollution(content)) break;

      // 获取 reasoning_id（如果后端提供）
      const reasoningId =
        data && typeof data.reasoning_id === "string"
          ? data.reasoning_id
          : undefined;

      // 获取 reasoningLive 状态（流式中=true，完成=false）
      const operation = evt.metadata?.operation;
      const operationFromData =
        data && typeof data.operation === "string" ? data.operation : undefined;
      const explicitReasoningLive =
        data && typeof data.reasoningLive === "boolean"
          ? data.reasoningLive
          : data && typeof data.reasoning_live === "boolean"
            ? data.reasoning_live
            : undefined;
      const isLive =
        typeof explicitReasoningLive === "boolean"
          ? explicitReasoningLive
          : operation === "complete" || operationFromData === "complete"
            ? false
            : true; // 默认流式中
      if (backgroundSessionId) {
        updateSessionUiCacheEntry(backgroundSessionId, (entry) => ({
          ...entry,
          messages: upsertReasoningMessage(entry.messages, {
            content,
            reasoningId,
            reasoningLive: isLive,
            turnId: evt.turn_id || entry.currentTurnId || undefined,
            timestamp: Date.now(),
          }),
        }));
        break;
      }

      set((s) => {
        const nextMessages = upsertReasoningMessage(s.messages, {
          content,
          reasoningId,
          reasoningLive: isLive,
          turnId,
          timestamp: Date.now(),
        });
        return { messages: nextMessages };
      });
      break;
    }

    case "tool_call": {
      const backgroundSessionId = getBackgroundSessionId(evt, get);
      const data = isRecord(evt.data) ? evt.data : {};
      const toolName =
        typeof data.name === "string" && data.name.trim()
          ? data.name
          : evt.tool_name || "";
      if (!toolName) break;

      const turnId = evt.turn_id || get()._currentTurnId || undefined;
      let toolArgs: Record<string, unknown> = {};
      const rawArguments = data.arguments;
      if (isRecord(rawArguments)) {
        toolArgs = rawArguments;
      } else if (typeof rawArguments === "string") {
        try {
          const parsed = JSON.parse(rawArguments);
          toolArgs = isRecord(parsed) ? parsed : { value: parsed };
        } catch {
          toolArgs = { raw: rawArguments };
        }
      } else if (rawArguments !== undefined) {
        toolArgs = { raw: rawArguments };
      }
      toolArgs = normalizeRunCodeIntent(toolName, toolArgs);
      const intent =
        typeof evt.metadata?.intent === "string"
          ? evt.metadata.intent
          : toolName === "run_code" && typeof toolArgs.intent === "string"
            ? toolArgs.intent
            : undefined;
      if (backgroundSessionId) {
        updateSessionUiCacheEntry(backgroundSessionId, (entry) => ({
          ...entry,
          messages: upsertToolCallMessage(entry.messages, {
            content:
              toolName === "run_code" && intent
                ? `🔧 ${toolName}: ${intent}`
                : `调用工具: **${toolName}**`,
            toolName,
            toolCallId: evt.tool_call_id || undefined,
            toolInput: toolArgs,
            toolIntent: intent,
            turnId: evt.turn_id || entry.currentTurnId || undefined,
            timestamp: Date.now(),
          }),
        }));
        break;
      }
      set((s) => ({
        messages: upsertToolCallMessage(s.messages, {
          content:
            toolName === "run_code" && intent
              ? `🔧 ${toolName}: ${intent}`
              : `调用工具: **${toolName}**`,
          toolName,
          toolCallId: evt.tool_call_id || undefined,
          toolInput: toolArgs,
          toolIntent: intent,
          turnId,
          timestamp: Date.now(),
        }),
      }));
      break;
    }

    case "tool_result": {
      const pendingQuestionSessionId =
        typeof evt.session_id === "string" && evt.session_id.trim()
          ? evt.session_id.trim()
          : get().sessionId || "";
      const shouldClearPendingQuestion =
        evt.tool_name === "ask_user_question" && pendingQuestionSessionId.length > 0;
      if (shouldClearPendingQuestion) {
        set((s) => buildPendingAskUserQuestionPatch(s, pendingQuestionSessionId, null));
      }
      const backgroundSessionId = getBackgroundSessionId(evt, get);
      const data = isRecord(evt.data) ? evt.data : {};
      const legacyResult =
        isRecord(data.data) && "result" in data.data ? data.data.result : undefined;
      const compatResult = data.result ?? legacyResult;
      const normalized = normalizeToolResult(
        isRecord(compatResult) ? JSON.stringify(compatResult) : data.message,
      );
      const status =
        (data.status as "success" | "error") || normalized.status || "success";
      const resultMessage =
        normalized.message ||
        (status === "error" ? "工具执行失败" : "工具执行完成");
      const toolCallId = evt.tool_call_id;
      if (backgroundSessionId) {
        updateSessionUiCacheEntry(backgroundSessionId, (entry) => ({
          ...entry,
          messages: upsertToolResultMessage(entry.messages, {
            content: resultMessage,
            toolName: evt.tool_name || undefined,
            toolCallId: toolCallId || undefined,
            toolResult: resultMessage,
            toolStatus: status,
            toolIntent:
              typeof evt.metadata?.intent === "string"
                ? evt.metadata.intent
                : undefined,
            turnId: evt.turn_id || entry.currentTurnId || undefined,
            timestamp: Date.now(),
          }),
        }));
        break;
      }
      const turnId = evt.turn_id || get()._currentTurnId || undefined;
      set((s) => {
        const msgs = upsertToolResultMessage(s.messages, {
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
        return {
          messages: msgs,
          ...(shouldClearPendingQuestion
            ? buildPendingAskUserQuestionPatch(s, pendingQuestionSessionId, null)
            : {}),
        };
      });
      break;
    }

    case "retrieval":
    case "chart":
    case "data":
    case "artifact":
    case "image":
    case "session_title":
    case "workspace_update":
      return import("./event-handler-extended").then(({ handleExtendedEvent }) => {
        handleExtendedEvent(evt, set, get);
      });

    case "trial_expired": {
      // 试用到期：推送系统消息并通过全局事件通知 UI 打开 AI 设置
      const payload = isRecord(evt.data) ? evt.data : {};
      const message =
        typeof payload.message === "string" && payload.message.trim()
          ? payload.message.trim()
          : "试用已结束，请在「AI 设置」中配置自己的 API 密钥继续使用。";
      const expiredMsg = {
        id: `trial_expired_${Date.now()}`,
        role: "assistant" as const,
        content: message,
        timestamp: Date.now(),
        isError: true,
        errorKind: "quota" as const,
        errorHint: "点击右上角「AI 设置」配置自己的密钥",
      };
      set((s) => ({
        isStreaming: false,
        messages: [...s.messages, expiredMsg],
      }));
      window.dispatchEvent(new Event("nini:trial-expired"));
      break;
    }

    case "trial_activated": {
      // 试用激活：刷新横幅状态
      window.dispatchEvent(new Event("nini:model-config-updated"));
      break;
    }

    case "code_execution":
    case "context_compressed":
    case "token_usage":
      return import("./event-handler-extended").then(({ handleExtendedEvent }) => {
        handleExtendedEvent(evt, set, get);
      });

    case "done": {
      const doneEvtSid = evt.session_id ?? get().sessionId ?? null;
      const doneCurSid = get().sessionId;
      const doneIsActive = !doneEvtSid || doneEvtSid === doneCurSid;
      set((s) => {
        // 从 runningSessions 中移除已完成的会话
        const nextRunning = doneEvtSid
          ? new Set([...s.runningSessions].filter((id) => id !== doneEvtSid))
          : new Set<string>();

        if (!doneIsActive) {
          if (doneEvtSid) {
            updateSessionUiCacheEntry(doneEvtSid, (entry) => {
              let progress = entry.analysisPlanProgress;
              let tasks = entry.analysisTasks;
              const turnId = evt.turn_id || entry.currentTurnId;
              if (progress && progress.step_status === "in_progress") {
                const taskId = findTaskIdByStepAndTurn(
                  entry.analysisTasks,
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
                  current_activity: null,
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
                ...entry,
                messages: finalizeReasoningMessages(entry.messages, turnId, true),
                currentTurnId: null,
                streamingText: "",
                activePlanMsgId: null,
                activePlanTaskIds: [],
                planActionTaskMap: {},
                analysisPlanOrder: entry.analysisPlanOrder,
                streamingMetrics: resetStreamingMetrics(),
                analysisPlanProgress: progress,
                analysisTasks: tasks,
              };
            });
          }
          // 后台会话完成：只更新运行状态，不改消息
          return {
            runningSessions: nextRunning,
            ...(doneEvtSid ? buildPendingAskUserQuestionPatch(s, doneEvtSid, null) : {}),
          };
        }

        // 当前会话完成：完整处理
        let progress = s.analysisPlanProgress;
        let tasks = s.analysisTasks;
        const turnId = evt.turn_id || s._currentTurnId;
        if (progress && progress.step_status === "in_progress") {
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
            current_activity: null,
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
          messages: finalizeReasoningMessages(s.messages, turnId, true),
          isStreaming: false,
          runningSessions: nextRunning,
          ...(doneEvtSid ? buildPendingAskUserQuestionPatch(s, doneEvtSid, null) : {}),
          _streamingText: "",
          _currentTurnId: null,
          _activePlanMsgId: null,
          _activePlanTaskIds: [],
          _planActionTaskMap: {},
          _streamingMetrics: resetStreamingMetrics(),
          analysisPlanProgress: progress,
          analysisTasks: tasks,
        };
      });
      // 对话结束后刷新会话列表（更新消息计数）
      get().fetchSessions();
      break;
    }

    case "stopped": {
      const stoppedEvtSid = evt.session_id ?? get().sessionId ?? null;
      const stoppedCurSid = get().sessionId;
      const stoppedIsActive = !stoppedEvtSid || stoppedEvtSid === stoppedCurSid;
      set((s) => {
        const nextRunning = stoppedEvtSid
          ? new Set([...s.runningSessions].filter((id) => id !== stoppedEvtSid))
          : new Set<string>();

        if (!stoppedIsActive) {
          if (stoppedEvtSid) {
            updateSessionUiCacheEntry(stoppedEvtSid, (entry) => {
              let progress = entry.analysisPlanProgress;
              let tasks = entry.analysisTasks;
              const turnId = evt.turn_id || entry.currentTurnId;
              if (progress && progress.step_status === "in_progress") {
                const taskId = findTaskIdByStepAndTurn(
                  entry.analysisTasks,
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
                  next_hint:
                    entry.blockedState?.suggestedAction || "你可以重新发送请求继续当前流程。",
                  block_reason: entry.blockedState?.message || "用户手动停止当前请求",
                  steps,
                };
              }
              return {
                ...entry,
                messages: finalizeReasoningMessages(entry.messages, turnId, true),
                currentTurnId: null,
                streamingText: "",
                activePlanMsgId: null,
                activePlanTaskIds: [],
                planActionTaskMap: {},
                streamingMetrics: resetStreamingMetrics(),
                blockedState: entry.blockedState,
                analysisPlanProgress: progress,
                analysisTasks: tasks,
              };
            });
          }
          return {
            runningSessions: nextRunning,
            ...(stoppedEvtSid
              ? buildPendingAskUserQuestionPatch(s, stoppedEvtSid, null)
              : {}),
          };
        }

        let progress = s.analysisPlanProgress;
        let tasks = s.analysisTasks;
        const turnId = evt.turn_id || s._currentTurnId;
        if (progress && progress.step_status === "in_progress") {
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
            next_hint:
              s.blockedState?.suggestedAction || "你可以重新发送请求继续当前流程。",
            block_reason: s.blockedState?.message || "用户手动停止当前请求",
            steps,
          };
        }
        return {
          messages: finalizeReasoningMessages(s.messages, turnId, true),
          isStreaming: false,
          runningSessions: nextRunning,
          ...(stoppedEvtSid
            ? buildPendingAskUserQuestionPatch(s, stoppedEvtSid, null)
            : {}),
          _streamingText: "",
          _currentTurnId: null,
          _activePlanMsgId: null,
          _activePlanTaskIds: [],
          _planActionTaskMap: {},
          _streamingMetrics: resetStreamingMetrics(),
          blockedState: s.blockedState,
          analysisPlanProgress: progress,
          analysisTasks: tasks,
        };
      });
      break;
    }

    case "error": {
      const errorEvtSid = evt.session_id ?? get().sessionId ?? null;
      const errorCurSid = get().sessionId;
      const errorIsActive = !errorEvtSid || errorEvtSid === errorCurSid;
      // 后台会话报错：只更新 runningSessions，不污染当前会话消息
      if (!errorIsActive) {
        if (errorEvtSid) {
          const normalizedError = normalizeWsError(evt.data);
          updateSessionUiCacheEntry(errorEvtSid, (entry) => {
            const turnId = evt.turn_id || entry.currentTurnId || undefined;
            return {
              ...entry,
              messages: [
                ...finalizeReasoningMessages(entry.messages, turnId, true),
                {
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
                },
              ],
              currentTurnId: null,
              streamingText: "",
              activePlanMsgId: null,
              activePlanTaskIds: [],
              planActionTaskMap: {},
              streamingMetrics: resetStreamingMetrics(),
              analysisTasks: (() => {
                const progress = entry.analysisPlanProgress;
                if (!progress || progress.step_status !== "in_progress") {
                  return entry.analysisTasks;
                }
                const taskId = findTaskIdByStepAndTurn(
                  entry.analysisTasks,
                  progress.current_step_index,
                  entry.currentTurnId,
                );
                const currentTask = taskId
                  ? entry.analysisTasks.find((task) => task.id === taskId)
                  : undefined;
                const mergedStatus = currentTask
                  ? mergePlanStepStatus(currentTask.status, "failed")
                  : "failed";
                return updateAnalysisTaskById(entry.analysisTasks, taskId, {
                  status: mergedStatus,
                  current_activity: "步骤执行失败",
                  last_error: normalizedError.detail || normalizedError.message,
                });
              })(),
              analysisPlanProgress: (() => {
                const progress = entry.analysisPlanProgress;
                if (!progress || progress.step_status !== "in_progress") {
                  return progress;
                }
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
            };
          });
        }
        set((s) => ({
          runningSessions: errorEvtSid
            ? new Set([...s.runningSessions].filter((id) => id !== errorEvtSid))
            : new Set<string>(),
          ...(errorEvtSid
            ? buildPendingAskUserQuestionPatch(s, errorEvtSid, null)
            : {}),
        }));
        break;
      }
      const normalizedError = normalizeWsError(evt.data);
      const turnId = evt.turn_id || get()._currentTurnId || undefined;
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
          ...finalizeReasoningMessages(s.messages, turnId, true),
          errMsg,
        ],
        isStreaming: false,
        runningSessions: errorEvtSid
          ? new Set([...s.runningSessions].filter((id) => id !== errorEvtSid))
          : new Set<string>(),
        ...(errorEvtSid
          ? buildPendingAskUserQuestionPatch(s, errorEvtSid, null)
          : {}),
        _streamingText: "",
        _currentTurnId: null,
        _activePlanMsgId: null,
        _activePlanTaskIds: [],
        _planActionTaskMap: {},
        _streamingMetrics: resetStreamingMetrics(),
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

    case "agent_start":
    case "agent_progress":
    case "agent_complete":
    case "agent_error": {
      handleAgentEvent(evt, set, get);
      break;
    }

    case "paradigm_switched":
    case "hypothesis_generated":
    case "evidence_collected":
    case "hypothesis_validated":
    case "hypothesis_refuted": {
      handleHypothesisEvent(evt, set, get);
      break;
    }
  }
}
