/**
 * Store 工具函数
 *
 * 通用工具函数和 ID 生成器
 */

import type {
  MemoryFile,
  AnalysisStep,
  AnalysisPlanProgress,
  AnalysisTaskItem,
  AnalysisTaskAttemptStatus,
  Message,
  MessageBuffer,
  MessageOperation,
} from "./types";

// Import functions from normalizers and plan-state-machine for local use
import {
  normalizePlanStepStatus,
  mergePlanStepStatus,
  truncatePlanText,
  createDefaultPlanSteps,
} from "./normalizers";

import {
  deriveNextHint,
} from "./plan-state-machine";

// Re-export plan-state-machine functions for convenience
export {
  deriveNextHint,
  updateAnalysisTaskById,
  areAllPlanStepsDone,
} from "./plan-state-machine";

// ---- ID 生成器 ----

let msgCounter = 0;
export function nextId(): string {
  return `msg-${Date.now()}-${++msgCounter}`;
}

let analysisTaskCounter = 0;
export function nextAnalysisTaskId(): string {
  return `task-${Date.now()}-${++analysisTaskCounter}`;
}

let analysisAttemptCounter = 0;
export function nextAnalysisAttemptId(): string {
  return `attempt-${Date.now()}-${++analysisAttemptCounter}`;
}

// ---- 类型守卫 ----

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

// ---- WebSocket URL ----

export function getWsUrl(): string {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  const host = window.location.host;
  return `${proto}://${host}/ws`;
}

// ---- 文件类型推断 ----

export function inferMemoryFileType(name: string): MemoryFile["type"] {
  if (name === "memory.jsonl") return "memory";
  if (name === "knowledge.md") return "knowledge";
  if (name.startsWith("archive/")) return "archive";
  return "meta";
}

// ---- 时间戳规范化 ----

export function normalizeMemoryTimestamp(value: unknown): string {
  if (typeof value === "number" && Number.isFinite(value)) {
    const millis = value > 1e12 ? value : value * 1000;
    return new Date(millis).toISOString();
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Date.parse(value);
    if (!Number.isNaN(parsed)) return new Date(parsed).toISOString();
  }
  return new Date().toISOString();
}

// ---- 推理标记处理 ----

/**
 * 合并 reasoning 内容
 * @param previous - 之前的内容
 * @param incoming - 新收到的内容
 * @param isLive - 是否为流式中（true=增量追加，false=完整替换）
 * @returns 合并后的内容
 */
export function mergeReasoningContent(
  previous: string,
  incoming: string,
  isLive?: boolean,
): string {
  if (!previous) return incoming;
  if (!incoming) return previous;

  // 如果是最终事件（非流式），直接替换为完整内容
  if (isLive === false) return incoming;

  // 兼容累计流（新内容包含旧内容前缀）
  if (incoming.startsWith(previous)) return incoming;

  // 兼容增量流（新内容仅为 delta）
  return previous + incoming;
}

// ---- 计划状态机辅助函数 ----

export function clampStepIndex(index: number, total: number): number {
  if (total <= 0) return 0;
  return Math.max(1, Math.min(index, total));
}

export function inferCurrentStepIndex(steps: AnalysisStep[]): number {
  const inProgress = steps.find((step) => step.status === "in_progress");
  if (inProgress) return inProgress.id;
  const failed = steps.find(
    (step) => step.status === "failed" || step.status === "blocked",
  );
  if (failed) return failed.id;
  const nextPending = steps.find((step) => step.status === "not_started");
  if (nextPending) return nextPending.id;
  const lastDone = [...steps].reverse().find((step) => step.status === "done");
  return lastDone?.id ?? 0;
}

export function findLastUserMessageIndex(messages: Message[]): number {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    if (messages[i].role === "user") return i;
  }
  return -1;
}

export function findLatestTurnSpan(messages: Message[]): {
  turnId: string | null;
  userIndex: number;
  firstTurnIndex: number;
  lastTurnIndex: number;
} | null {
  const fallbackUserIndex = findLastUserMessageIndex(messages);
  let turnId: string | null = null;

  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const msg = messages[i];
    if (msg.role !== "user" && typeof msg.turnId === "string" && msg.turnId) {
      turnId = msg.turnId;
      break;
    }
  }

  if (!turnId) {
    if (fallbackUserIndex < 0) return null;
    return {
      turnId: messages[fallbackUserIndex].turnId ?? null,
      userIndex: fallbackUserIndex,
      firstTurnIndex: fallbackUserIndex,
      lastTurnIndex: messages.length - 1,
    };
  }

  let firstTurnIndex = -1;
  let lastTurnIndex = -1;
  for (let i = 0; i < messages.length; i += 1) {
    if (messages[i].turnId !== turnId) continue;
    if (firstTurnIndex < 0) firstTurnIndex = i;
    lastTurnIndex = i;
  }

  let userIndex = -1;
  for (let i = firstTurnIndex; i >= 0; i -= 1) {
    if (messages[i].role === "user") {
      userIndex = i;
      break;
    }
  }
  if (userIndex < 0) {
    userIndex = fallbackUserIndex;
  }
  if (userIndex < 0 || firstTurnIndex < 0 || lastTurnIndex < 0) {
    return null;
  }

  return {
    turnId,
    userIndex,
    firstTurnIndex,
    lastTurnIndex,
  };
}

// Note: deriveNextHint is imported from ./plan-state-machine

// ---- 计划进度辅助函数 ----

export function makePlanProgressFromSteps(
  steps: AnalysisStep[],
  rawText = "",
  nextHint: string | null = null,
  blockReason: string | null = null,
): AnalysisPlanProgress | null {
  if (steps.length === 0) return null;
  const currentStepIndex = clampStepIndex(
    inferCurrentStepIndex(steps),
    steps.length,
  );
  const currentStep = steps[currentStepIndex - 1];
  const stepStatus = currentStep?.status || "not_started";
  return {
    steps,
    current_step_index: currentStepIndex,
    total_steps: steps.length,
    step_title: currentStep?.title || truncatePlanText(rawText, 48),
    step_status: stepStatus,
    next_hint: nextHint ?? deriveNextHint(steps, currentStepIndex, stepStatus),
    block_reason: blockReason,
  };
}

// Note: areAllPlanStepsDone and updateAnalysisTaskById are imported from ./plan-state-machine

// ---- 分析任务更新 ----

/**
 * 根据 plan_step_id 和当前 turn_id 查找任务ID
 * 优先匹配当前 turn 的任务，找不到则返回 null
 */
export function findTaskIdByStepAndTurn(
  tasks: AnalysisTaskItem[],
  stepId: number,
  turnId: string | null | undefined,
): string | null {
  if (stepId <= 0) return null;

  // 优先在当前 turn 中查找匹配 step_id 的任务
  const matchingTasks = tasks.filter(
    (t) => t.plan_step_id === stepId && (turnId ? t.turn_id === turnId : true),
  );

  if (matchingTasks.length === 0) return null;

  // 如果有多个匹配（理论上不应该），返回最新的
  return matchingTasks[matchingTasks.length - 1].id;
}

export function updateAnalysisTaskWithAttempt(
  tasks: AnalysisTaskItem[],
  taskId: string | null | undefined,
  payload: {
    action_id?: string | null;
    tool_name: string;
    attempt: number;
    max_attempts: number;
    status: AnalysisTaskAttemptStatus;
    note?: string | null;
    error?: string | null;
  },
): AnalysisTaskItem[] {
  if (!taskId) return tasks;
  const idx = tasks.findIndex((task) => task.id === taskId);
  if (idx < 0) return tasks;

  const task = tasks[idx];
  const now = Date.now();
  const existingAttemptIdx = task.attempts.findIndex(
    (item) => item.attempt === payload.attempt,
  );
  const attempts = [...task.attempts];
  if (existingAttemptIdx >= 0) {
    attempts[existingAttemptIdx] = {
      ...attempts[existingAttemptIdx],
      tool_name: payload.tool_name,
      max_attempts: payload.max_attempts,
      status: payload.status,
      note:
        payload.note !== undefined
          ? payload.note
          : attempts[existingAttemptIdx].note,
      error:
        payload.error !== undefined
          ? payload.error
          : attempts[existingAttemptIdx].error,
      updated_at: now,
    };
  } else {
    attempts.push({
      id: nextAnalysisAttemptId(),
      tool_name: payload.tool_name,
      attempt: payload.attempt,
      max_attempts: payload.max_attempts,
      status: payload.status,
      note: payload.note ?? null,
      error: payload.error ?? null,
      created_at: now,
      updated_at: now,
    });
    attempts.sort((a, b) => a.attempt - b.attempt);
  }

  let nextStatus = task.status;
  if (payload.status === "failed") {
    nextStatus = mergePlanStepStatus(task.status, "failed");
  } else if (
    payload.status === "in_progress" ||
    payload.status === "retrying"
  ) {
    nextStatus = mergePlanStepStatus(task.status, "in_progress");
  } else if (payload.status === "success") {
    // attempt 成功表示"工具层成功"，步骤最终 done 仍由 plan_step_update/plan_progress 决定。
    // 但若此前处于 failed/blocked，先恢复到 in_progress，避免卡死在失败态。
    if (task.status === "failed" || task.status === "blocked") {
      nextStatus = mergePlanStepStatus(task.status, "in_progress");
    }
  }

  const next = [...tasks];
  next[idx] = {
    ...task,
    action_id: payload.action_id ?? task.action_id,
    status: nextStatus,
    current_activity:
      payload.note ??
      (payload.status === "success"
        ? `${payload.tool_name} 执行成功，等待步骤状态确认`
        : payload.status === "failed"
          ? `${payload.tool_name} 执行失败`
          : `正在执行 ${payload.tool_name}（第 ${payload.attempt}/${payload.max_attempts} 次）`),
    last_error:
      payload.error ?? (payload.status === "success" ? null : task.last_error),
    attempts,
    updated_at: now,
  };
  return next;
}

// ---- 计划进度更新 ----

export function applyPlanStepUpdateToProgress(
  progress: AnalysisPlanProgress | null,
  stepId: number,
  rawStatus: unknown,
): AnalysisPlanProgress | null {
  if (!progress) return null;
  if (stepId <= 0 || stepId > progress.steps.length) return progress;

  const incomingStatus = normalizePlanStepStatus(rawStatus);
  const steps = progress.steps.map((step) => {
    if (step.id !== stepId) return step;
    return {
      ...step,
      status: mergePlanStepStatus(step.status, incomingStatus),
      raw_status: typeof rawStatus === "string" ? rawStatus : step.raw_status,
    };
  });

  const currentStep = steps[stepId - 1];
  const currentStatus = currentStep?.status || incomingStatus;
  return {
    ...progress,
    steps,
    current_step_index: stepId,
    total_steps: steps.length,
    step_title: currentStep?.title || progress.step_title,
    step_status: currentStatus,
    next_hint:
      progress.next_hint && progress.next_hint.trim()
        ? progress.next_hint
        : deriveNextHint(steps, stepId, currentStatus),
    block_reason: currentStatus === "failed" ? progress.block_reason : null,
  };
}

export function applyPlanProgressPayload(
  existing: AnalysisPlanProgress | null,
  payload: Record<string, unknown>,
): AnalysisPlanProgress | null {
  const totalRaw = payload.total_steps;
  const total =
    typeof totalRaw === "number" && Number.isFinite(totalRaw) && totalRaw > 0
      ? Math.floor(totalRaw)
      : existing?.total_steps || 0;
  if (total <= 0) return existing;

  const currentRaw = payload.current_step_index;
  const currentStepIndex =
    typeof currentRaw === "number" && Number.isFinite(currentRaw)
      ? clampStepIndex(Math.floor(currentRaw), total)
      : existing?.current_step_index
        ? clampStepIndex(existing.current_step_index, total)
        : 1;

  const incomingStatus = normalizePlanStepStatus(payload.step_status);
  const stepTitleRaw = payload.step_title;
  const incomingStepTitle =
    typeof stepTitleRaw === "string" && stepTitleRaw.trim()
      ? stepTitleRaw.trim()
      : existing?.step_title || `步骤 ${currentStepIndex}`;
  const incomingNextHint =
    typeof payload.next_hint === "string" && payload.next_hint.trim()
      ? payload.next_hint.trim()
      : null;
  const blockReason =
    typeof payload.block_reason === "string" && payload.block_reason.trim()
      ? payload.block_reason.trim()
      : null;

  const baseSteps =
    existing && existing.steps.length > 0
      ? [...existing.steps]
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

// ---- 上传进度跟踪 ----

export function uploadWithProgress(
  form: FormData,
  onProgress: (percent: number) => void,
): Promise<Record<string, unknown>> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/upload");
    xhr.responseType = "json";

    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable) return;
      const percent = Math.min(
        100,
        Math.round((event.loaded / event.total) * 100),
      );
      onProgress(percent);
    };

    xhr.onload = () => {
      if (xhr.status < 200 || xhr.status >= 300) {
        if (xhr.status === 401 && typeof window !== "undefined") {
          window.dispatchEvent(
            new CustomEvent("nini:auth-invalid", {
              detail: {
                status: 401,
                message: "API Key 无效或已过期，请重新输入。",
              },
            }),
          );
        }
        reject(new Error(`上传失败: HTTP ${xhr.status}`));
        return;
      }
      const jsonResp = xhr.response;
      if (jsonResp && typeof jsonResp === "object") {
        resolve(jsonResp as Record<string, unknown>);
        return;
      }
      try {
        const parsed = JSON.parse(xhr.responseText) as Record<string, unknown>;
        resolve(parsed);
      } catch {
        reject(new Error("上传响应解析失败"));
      }
    };

    xhr.onerror = () => reject(new Error("上传请求失败"));
    xhr.send(form);
  });
}

// ---- 消息缓冲区辅助函数 ----

/**
 * 缓冲区条目最大存活时间（毫秒）
 * 超过此时间的条目将被清理
 */
const MESSAGE_BUFFER_MAX_AGE = 5 * 60 * 1000; // 5分钟

/**
 * 添加或更新缓冲区条目
 * @param buffer - 当前缓冲区
 * @param messageId - 消息ID
 * @param content - 内容
 * @param operation - 操作类型
 * @returns 更新后的缓冲区
 */
export function updateMessageBuffer(
  buffer: MessageBuffer,
  messageId: string,
  content: string,
  operation: MessageOperation,
): MessageBuffer {
  const now = Date.now();

  // 根据操作类型处理内容
  let newContent: string;
  const existing = buffer[messageId];

  if (operation === "append" && existing) {
    // 追加模式：累加内容
    newContent = existing.content + content;
  } else if (operation === "replace") {
    // 替换模式：直接替换
    newContent = content;
  } else {
    // 默认或 complete 操作：使用现有内容或新内容
    newContent = content ?? existing?.content ?? "";
  }

  return {
    ...buffer,
    [messageId]: {
      content: newContent,
      operation,
      timestamp: now,
    },
  };
}

/**
 * 从缓冲区获取内容
 * @param buffer - 当前缓冲区
 * @param messageId - 消息ID
 * @returns 内容或 null
 */
export function getMessageBufferContent(
  buffer: MessageBuffer,
  messageId: string,
): string | null {
  return buffer[messageId]?.content ?? null;
}

/**
 * 完成并清理缓冲区条目
 * @param buffer - 当前缓冲区
 * @param messageId - 消息ID
 * @returns 更新后的缓冲区（已移除该条目）
 */
export function completeMessageBuffer(
  buffer: MessageBuffer,
  messageId: string,
): MessageBuffer {
  if (!buffer[messageId]) return buffer;

  const { [messageId]: _, ...rest } = buffer;
  return rest;
}

/**
 * 清理过期的缓冲区条目
 * @param buffer - 当前缓冲区
 * @param maxAge - 最大存活时间（毫秒），默认 5 分钟
 * @returns 清理后的缓冲区
 */
export function cleanupMessageBuffer(
  buffer: MessageBuffer,
  maxAge: number = MESSAGE_BUFFER_MAX_AGE,
): MessageBuffer {
  const now = Date.now();
  const result: MessageBuffer = {};

  for (const [id, entry] of Object.entries(buffer)) {
    if (now - entry.timestamp < maxAge) {
      result[id] = entry;
    }
  }

  return result;
}

/**
 * 检查消息ID是否已在缓冲区中（用于去重）
 * @param buffer - 当前缓冲区
 * @param messageId - 消息ID
 * @returns 是否已存在
 */
export function hasMessageBuffer(
  buffer: MessageBuffer,
  messageId: string,
): boolean {
  return messageId in buffer;
}
