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
import { cloneMessages } from "./session-ui-cache";

const INTERNAL_STATUS_ALLOWED_KEYS = new Set([
  "success",
  "message",
  "error",
  "status",
  "error_code",
  "recovery_hint",
  "data_summary",
]);
const INTERNAL_STATUS_PATTERNS = [
  "任务状态已更新",
  "还有 ",
  "所有任务已完成",
  "复盘检查",
  "报告章节已更新",
  "报告会话已创建",
  "脚本会话已创建",
  "图表会话已创建",
  "工作区会话已创建",
];
const REPORT_SECTION_LABELS: Record<string, string> = {
  methods: "方法",
  summary: "摘要",
  conclusions: "结论",
};

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

function normalizeInternalAssistantStatusText(content: string): string {
  const text = content.trim();
  if (!text.startsWith("{") || !text.endsWith("}")) {
    return content;
  }

  try {
    const parsed = JSON.parse(text) as Record<string, unknown>;
    const keys = Object.keys(parsed);
    if (
      !keys.includes("message") ||
      keys.some((key) => !INTERNAL_STATUS_ALLOWED_KEYS.has(key)) ||
      typeof parsed.message !== "string"
    ) {
      return content;
    }

    const message = parsed.message.trim();
    if (!message) {
      return content;
    }

    const dataSummary = parsed.data_summary;
    const summaryKeys =
      dataSummary && typeof dataSummary === "object" && Array.isArray((dataSummary as Record<string, unknown>).keys)
        ? ((dataSummary as Record<string, unknown>).keys as unknown[]).filter(
            (item): item is string => typeof item === "string",
          )
        : [];
    const hasInternalSummary = summaryKeys.some((key) =>
      ["keys", "mode", "updated_ids", "auto_completed_ids", "report_id", "resource_id"].includes(key),
    );
    const hasInternalPattern = INTERNAL_STATUS_PATTERNS.some((pattern) => message.includes(pattern));
    if (!hasInternalSummary && !hasInternalPattern) {
      return content;
    }

    const reportPrefix = "报告章节已更新：";
    if (message.startsWith(reportPrefix)) {
      const sectionKey = message.slice(reportPrefix.length).trim();
      const sectionLabel = REPORT_SECTION_LABELS[sectionKey] || sectionKey;
      return sectionLabel ? `报告${sectionLabel}章节已更新。` : "报告章节已更新。";
    }
    if (message === "报告章节已更新") {
      return "报告章节已更新。";
    }
    return message;
  } catch {
    return content;
  }
}

export function upsertAssistantTextMessage(
  messages: Message[],
  payload: AssistantTextPayload,
): Message[] {
  const next = cloneMessages(messages);
  const operation = payload.operation ?? "complete";
  const normalizedContent = normalizeInternalAssistantStatusText(payload.content);
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
        ? `${existing.content}${normalizedContent}`
        : normalizedContent;
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
    content: normalizedContent,
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

export function mergeArtifactLists(
  existing: Message["artifacts"],
  incoming: Message["artifacts"],
): Message["artifacts"] {
  const merged = [...(existing ?? [])];
  for (const artifact of incoming ?? []) {
    const duplicate = merged.some(
      (item) =>
        item.name === artifact.name &&
        item.download_url === artifact.download_url &&
        item.type === artifact.type,
    );
    if (!duplicate) {
      merged.push(artifact);
    }
  }
  return merged;
}

export function attachArtifactsToLatestAssistantMessage(
  messages: Message[],
  options: {
    artifacts: Message["artifacts"];
    turnId?: string;
    timestamp: number;
  },
): boolean {
  const { artifacts, turnId, timestamp } = options;
  if (!artifacts || artifacts.length === 0) {
    return false;
  }

  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.role !== "assistant" || message.isReasoning) {
      continue;
    }
    if (turnId && message.turnId !== turnId) {
      continue;
    }
    if (message.content === "产物已生成" && message.artifacts?.length) {
      continue;
    }
    messages[index] = {
      ...message,
      artifacts: mergeArtifactLists(message.artifacts, artifacts),
      timestamp: Math.max(message.timestamp, timestamp),
    };
    return true;
  }

  return false;
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
