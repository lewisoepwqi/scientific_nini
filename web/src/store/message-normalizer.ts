import type {
  ArtifactInfo,
  ChartDataPayload,
  DataPreviewPayload,
  GeneratedWidgetPayload,
  Message,
  MessageOperation,
  OutputLevel,
  RetrievalItem,
} from "./types";

import { mergeReasoningContent, nextId } from "./utils";

interface AssistantTextPayload {
  content: string;
  timestamp: number;
  messageId?: string;
  turnId?: string;
  operation?: MessageOperation;
  chartData?: ChartDataPayload;
  dataPreview?: DataPreviewPayload;
  artifacts?: ArtifactInfo[];
  images?: string[];
  retrievals?: RetrievalItem[];
  outputLevel?: OutputLevel | null;
  errorMeta?: Partial<Message>;
}

interface ReasoningPayload {
  content: string;
  timestamp: number;
  turnId?: string;
  reasoningId?: string;
  reasoningLive: boolean;
}

interface ToolCallPayload {
  content: string;
  timestamp: number;
  turnId?: string;
  toolCallId?: string;
  toolName: string;
  toolInput?: Record<string, unknown>;
  toolIntent?: string;
}

interface ToolResultPayload {
  content: string;
  timestamp: number;
  turnId?: string;
  toolCallId?: string;
  toolName?: string;
  toolInput?: Record<string, unknown>;
  toolResult: string;
  toolStatus: "success" | "error";
  toolIntent?: string;
  widget?: GeneratedWidgetPayload;
}

function cloneMessages(messages: Message[]): Message[] {
  return messages.map((msg) => ({ ...msg }));
}

export function normalizeMessageTimestamp(rawTimestamp: unknown): number {
  if (typeof rawTimestamp === "number" && Number.isFinite(rawTimestamp)) {
    return rawTimestamp;
  }
  if (typeof rawTimestamp === "string" && rawTimestamp.trim()) {
    const parsed = Date.parse(rawTimestamp);
    if (!Number.isNaN(parsed)) return parsed;
  }
  return Date.now();
}

export function upsertAssistantTextMessage(
  messages: Message[],
  payload: AssistantTextPayload,
): Message[] {
  const next = cloneMessages(messages);
  const operation = payload.operation ?? "complete";
  const existingIndex =
    payload.messageId
      ? next.findIndex(
          (msg) =>
            msg.role === "assistant" &&
            !msg.isReasoning &&
            msg.messageId === payload.messageId,
        )
      : -1;

  if (existingIndex >= 0) {
    const existing = next[existingIndex];
    const nextContent =
      operation === "append"
        ? `${existing.content}${payload.content}`
        : payload.content;
    next[existingIndex] = {
      ...existing,
      content: nextContent,
      messageId: payload.messageId ?? existing.messageId,
      turnId: payload.turnId ?? existing.turnId,
      chartData: payload.chartData ?? existing.chartData,
      dataPreview: payload.dataPreview ?? existing.dataPreview,
      artifacts: payload.artifacts ?? existing.artifacts,
      images: payload.images ?? existing.images,
      retrievals: payload.retrievals ?? existing.retrievals,
      outputLevel: payload.outputLevel ?? existing.outputLevel,
      timestamp: payload.timestamp,
      ...payload.errorMeta,
    };
    return next;
  }

  next.push({
    id: nextId(),
    role: "assistant",
    content: payload.content,
    messageId: payload.messageId,
    turnId: payload.turnId,
    chartData: payload.chartData,
    dataPreview: payload.dataPreview,
    artifacts: payload.artifacts,
    images: payload.images,
    retrievals: payload.retrievals,
    outputLevel: payload.outputLevel,
    timestamp: payload.timestamp,
    ...payload.errorMeta,
  });
  return next;
}

export function upsertReasoningMessage(
  messages: Message[],
  payload: ReasoningPayload,
): Message[] {
  const next = cloneMessages(messages);
  const existingIndex = payload.reasoningId
    ? next.findIndex(
        (msg) => msg.isReasoning && msg.reasoningId === payload.reasoningId,
      )
    : (() => {
        for (let i = next.length - 1; i >= 0; i -= 1) {
          const msg = next[i];
          if (!msg.isReasoning || msg.analysisPlan) continue;
          if (payload.turnId && msg.turnId !== payload.turnId) continue;
          return i;
        }
        return -1;
      })();

  if (existingIndex >= 0) {
    const existing = next[existingIndex];
    next[existingIndex] = {
      ...existing,
      content: mergeReasoningContent(
        existing.content,
        payload.content,
        payload.reasoningLive,
      ),
      reasoningLive: payload.reasoningLive,
      reasoningId: payload.reasoningId ?? existing.reasoningId,
      turnId: payload.turnId ?? existing.turnId,
      timestamp: payload.timestamp,
    };
    return next;
  }

  next.push({
    id: nextId(),
    role: "assistant",
    content: payload.content,
    isReasoning: true,
    reasoningLive: payload.reasoningLive,
    reasoningId: payload.reasoningId,
    turnId: payload.turnId,
    timestamp: payload.timestamp,
  });
  return next;
}

export function upsertToolCallMessage(
  messages: Message[],
  payload: ToolCallPayload,
): Message[] {
  const next = cloneMessages(messages);
  const existingIndex = payload.toolCallId
    ? next.findIndex(
        (msg) => msg.role === "tool" && msg.toolCallId === payload.toolCallId,
      )
    : -1;

  if (existingIndex >= 0) {
    next[existingIndex] = {
      ...next[existingIndex],
      content: payload.content,
      toolName: payload.toolName,
      toolInput: payload.toolInput,
      toolIntent: payload.toolIntent ?? next[existingIndex].toolIntent,
      turnId: payload.turnId ?? next[existingIndex].turnId,
      timestamp: payload.timestamp,
    };
    return next;
  }

  next.push({
    id: nextId(),
    role: "tool",
    content: payload.content,
    toolName: payload.toolName,
    toolCallId: payload.toolCallId,
    toolInput: payload.toolInput,
    toolIntent: payload.toolIntent,
    turnId: payload.turnId,
    timestamp: payload.timestamp,
  });
  return next;
}

export function upsertToolResultMessage(
  messages: Message[],
  payload: ToolResultPayload,
): Message[] {
  const next = cloneMessages(messages);
  const existingIndex = payload.toolCallId
    ? next.findIndex(
        (msg) =>
          msg.role === "tool" &&
          msg.toolCallId === payload.toolCallId &&
          !msg.toolResult,
      )
    : -1;

  if (existingIndex >= 0) {
    next[existingIndex] = {
      ...next[existingIndex],
      content: payload.content,
      toolName: payload.toolName ?? next[existingIndex].toolName,
      toolInput: payload.toolInput ?? next[existingIndex].toolInput,
      toolResult: payload.toolResult,
      toolStatus: payload.toolStatus,
      toolIntent: payload.toolIntent ?? next[existingIndex].toolIntent,
      widget: payload.widget ?? next[existingIndex].widget,
      turnId: payload.turnId ?? next[existingIndex].turnId,
      timestamp: payload.timestamp,
    };
    return next;
  }

  next.push({
    id: nextId(),
    role: "tool",
    content: payload.content,
    toolName: payload.toolName,
    toolCallId: payload.toolCallId,
    toolInput: payload.toolInput,
    toolResult: payload.toolResult,
    toolStatus: payload.toolStatus,
    toolIntent: payload.toolIntent,
    widget: payload.widget,
    turnId: payload.turnId,
    timestamp: payload.timestamp,
  });
  return next;
}
