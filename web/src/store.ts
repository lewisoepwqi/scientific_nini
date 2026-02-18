/**
 * 单一 Zustand Store —— 管理会话、消息、WebSocket 连接。
 */
import { create } from "zustand";

// ---- 类型 ----

export interface ArtifactInfo {
  name: string;
  type: string;
  format?: string;
  download_url: string;
}

export interface RetrievalItem {
  source: string;
  score?: number;
  hits?: number;
  snippet: string;
}

export interface SkillItem {
  type: "function" | "markdown" | string;
  name: string;
  description: string;
  category?: string;
  location: string;
  enabled: boolean;
  expose_to_llm?: boolean;
  metadata?: Record<string, unknown>;
}

export interface DatasetItem {
  id: string;
  name: string;
  file_type: string;
  file_size: number;
  row_count: number;
  column_count: number;
  created_at?: string;
  loaded: boolean;
}

export interface WorkspaceFile {
  id: string;
  name: string;
  kind: "dataset" | "artifact" | "note";
  size: number;
  created_at?: string;
  download_url: string;
  meta?: Record<string, unknown>;
  folder?: string | null;
}

export interface WorkspaceFolder {
  id: string;
  name: string;
  parent: string | null;
  created_at: string;
}

export type PlanStepStatus =
  | "not_started"
  | "in_progress"
  | "done"
  | "blocked"
  | "failed";

export interface AnalysisStep {
  id: number;
  title: string;
  tool_hint: string | null;
  status: PlanStepStatus;
  raw_status?: string;
  action_id?: string | null;
}

export interface AnalysisPlanData {
  steps: AnalysisStep[];
  raw_text: string;
}

export interface AnalysisPlanProgress {
  steps: AnalysisStep[];
  current_step_index: number;
  total_steps: number;
  step_title: string;
  step_status: PlanStepStatus;
  next_hint: string | null;
  block_reason: string | null;
}

export type AnalysisTaskAttemptStatus =
  | "in_progress"
  | "retrying"
  | "success"
  | "failed";

export interface AnalysisTaskAttempt {
  id: string;
  tool_name: string;
  attempt: number;
  max_attempts: number;
  status: AnalysisTaskAttemptStatus;
  note: string | null;
  error: string | null;
  created_at: number;
  updated_at: number;
}

export interface AnalysisTaskItem {
  id: string;
  plan_step_id: number;
  action_id: string | null;
  title: string;
  tool_hint: string | null;
  status: PlanStepStatus;
  raw_status?: string;
  current_activity: string | null;
  last_error: string | null;
  attempts: AnalysisTaskAttempt[];
  created_at: number;
  updated_at: number;
}

export interface Message {
  id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  toolName?: string;
  toolCallId?: string;
  toolInput?: Record<string, unknown>; // 工具调用参数
  toolResult?: string; // 工具执行结果
  toolStatus?: "success" | "error"; // 工具执行状态
  toolIntent?: string; // 工具执行意图
  chartData?: unknown;
  dataPreview?: unknown;
  artifacts?: ArtifactInfo[];
  images?: string[]; // 图片 URL 列表
  retrievals?: RetrievalItem[]; // 检索命中结果
  isReasoning?: boolean; // 分析思路消息标记
  analysisPlan?: AnalysisPlanData; // 结构化分析计划
  turnId?: string; // Agent 回合 ID，用于消息分组
  timestamp: number;
}

export interface SessionItem {
  id: string;
  title: string;
  message_count: number;
  source: "memory" | "disk";
}

export interface ActiveModelInfo {
  provider_id: string;
  provider_name: string;
  model: string;
  preferred_provider: string | null;
}

export interface CodeExecution {
  id: string;
  session_id: string;
  code: string;
  output: string;
  status: string;
  language: string;
  created_at: string;
  tool_name?: string;
  tool_args?: Record<string, unknown>;
  context_token_count?: number;
  intent?: string;
}

export interface MemoryFile {
  name: string;
  size: number;
  modified_at: string;
  type: "memory" | "knowledge" | "meta" | "archive";
}

interface WSEvent {
  type: string;
  data?: unknown;
  session_id?: string;
  tool_call_id?: string;
  tool_name?: string;
  turn_id?: string;
  metadata?: Record<string, unknown>;
}

interface RawSessionMessage {
  role?: string;
  content?: string | null;
  event_type?: string | null;
  tool_calls?: Array<{
    id?: string;
    type?: string;
    function?: {
      name?: string;
      arguments?: string;
    };
  }>;
  tool_call_id?: string | null;
  chart_data?: unknown;
  data_preview?: unknown;
  artifacts?: ArtifactInfo[];
  images?: string[];
}

interface AppState {
  // 会话
  sessionId: string | null;
  messages: Message[];
  sessions: SessionItem[];
  contextCompressionTick: number;
  datasets: DatasetItem[];
  workspaceFiles: WorkspaceFile[];
  skills: SkillItem[];

  // 记忆面板
  memoryFiles: MemoryFile[];

  // 模型选择（统一为全局首选）
  activeModel: ActiveModelInfo | null;

  // 工作区面板状态
  workspacePanelOpen: boolean;
  workspacePanelTab: "files" | "executions" | "tasks";
  fileSearchQuery: string;
  previewTabs: string[];
  previewFileId: string | null;
  codeExecutions: CodeExecution[];
  workspaceFolders: WorkspaceFolder[];
  analysisTasks: AnalysisTaskItem[];
  isUploading: boolean;
  uploadProgress: number;
  uploadingFileName: string | null;

  // 连接
  ws: WebSocket | null;
  wsConnected: boolean;
  isStreaming: boolean;

  // 当前流式文本的累积
  _streamingText: string;
  _currentTurnId: string | null;
  _reconnectAttempts: number;
  _activePlanMsgId: string | null;
  analysisPlanProgress: AnalysisPlanProgress | null;
  _analysisPlanOrder: number;
  _activePlanTaskIds: Array<string | null>;
  _planActionTaskMap: Record<string, string>;

  // 操作
  connect: () => void;
  disconnect: () => void;
  initApp: () => Promise<void>;
  sendMessage: (content: string) => void;
  stopStreaming: () => void;
  retryLastTurn: () => void;
  uploadFile: (file: File) => Promise<void>;
  clearMessages: () => void;
  fetchSessions: () => Promise<void>;
  fetchDatasets: () => Promise<void>;
  fetchWorkspaceFiles: () => Promise<void>;
  fetchSkills: () => Promise<void>;
  loadDataset: (datasetId: string) => Promise<void>;
  compressCurrentSession: () => Promise<{ success: boolean; message: string }>;
  createNewSession: () => Promise<void>;
  switchSession: (sessionId: string) => Promise<void>;
  deleteSession: (sessionId: string) => Promise<void>;
  updateSessionTitle: (sessionId: string, title: string) => Promise<void>;
  fetchMemoryFiles: () => Promise<void>;
  fetchActiveModel: () => Promise<void>;
  setPreferredProvider: (providerId: string) => Promise<void>;

  // 工作区面板操作
  toggleWorkspacePanel: () => void;
  setWorkspacePanelTab: (tab: "files" | "executions" | "tasks") => void;
  setFileSearchQuery: (query: string) => void;
  deleteAnalysisTask: (taskId: string) => void;
  clearAnalysisTasks: () => void;
  deleteWorkspaceFile: (fileId: string) => Promise<void>;
  renameWorkspaceFile: (fileId: string, newName: string) => Promise<void>;
  openPreview: (fileId: string) => void;
  setActivePreview: (fileId: string | null) => void;
  closePreview: (fileId?: string) => void;
  fetchCodeExecutions: () => Promise<void>;
  fetchFolders: () => Promise<void>;
  createFolder: (name: string, parent?: string | null) => Promise<void>;
  moveFileToFolder: (fileId: string, folderId: string | null) => Promise<void>;
  createWorkspaceFile: (filename: string, content?: string) => Promise<void>;
}

// ---- 工具函数 ----

let msgCounter = 0;
function nextId(): string {
  return `msg-${Date.now()}-${++msgCounter}`;
}

let analysisTaskCounter = 0;
function nextAnalysisTaskId(): string {
  return `task-${Date.now()}-${++analysisTaskCounter}`;
}

let analysisAttemptCounter = 0;
function nextAnalysisAttemptId(): string {
  return `attempt-${Date.now()}-${++analysisAttemptCounter}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function inferMemoryFileType(name: string): MemoryFile["type"] {
  if (name === "memory.jsonl") return "memory";
  if (name === "knowledge.md") return "knowledge";
  if (name.startsWith("archive/")) return "archive";
  return "meta";
}

function normalizeMemoryTimestamp(value: unknown): string {
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

function normalizePlanStepStatus(raw: unknown): PlanStepStatus {
  if (typeof raw !== "string") return "not_started";
  const normalized = raw.trim().toLowerCase();
  switch (normalized) {
    case "pending":
    case "not_started":
      return "not_started";
    case "in_progress":
      return "in_progress";
    case "completed":
    case "done":
      return "done";
    case "error":
    case "failed":
      return "failed";
    case "blocked":
      return "blocked";
    default:
      return "not_started";
  }
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

const REASONING_MARKER_PATTERN =
  /<\/?think>|<\/?thinking>|◁think▷|◁\/think▷/gi;

function stripReasoningMarkers(text: string): string {
  if (!text) return text;
  return text.replace(REASONING_MARKER_PATTERN, "");
}

function planStatusRank(status: PlanStepStatus): number {
  switch (status) {
    case "done":
      return 4;
    case "failed":
      return 3;
    case "blocked":
      return 2;
    case "in_progress":
      return 1;
    default:
      return 0;
  }
}

function mergePlanStepStatus(current: PlanStepStatus, incoming: PlanStepStatus): PlanStepStatus {
  return planStatusRank(incoming) >= planStatusRank(current) ? incoming : current;
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
    status: "not_started",
  }));
}

function inferCurrentStepIndex(steps: AnalysisStep[]): number {
  const inProgress = steps.find((step) => step.status === "in_progress");
  if (inProgress) return inProgress.id;
  const failed = steps.find((step) => step.status === "failed" || step.status === "blocked");
  if (failed) return failed.id;
  const nextPending = steps.find((step) => step.status === "not_started");
  if (nextPending) return nextPending.id;
  const lastDone = [...steps].reverse().find((step) => step.status === "done");
  return lastDone?.id ?? 0;
}

function deriveNextHint(
  steps: AnalysisStep[],
  currentStepIndex: number,
  currentStatus: PlanStepStatus,
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

function normalizeAnalysisSteps(rawSteps: unknown): AnalysisStep[] {
  if (!Array.isArray(rawSteps)) return [];
  return rawSteps
    .filter((item): item is Record<string, unknown> => isRecord(item))
    .map((item, idx) => {
      const idRaw = item.id;
      const id =
        typeof idRaw === "number" && Number.isFinite(idRaw) && idRaw > 0
          ? Math.floor(idRaw)
          : idx + 1;
      const title =
        typeof item.title === "string" && item.title.trim()
          ? item.title.trim()
          : `步骤 ${id}`;
      const toolHint =
        typeof item.tool_hint === "string" && item.tool_hint.trim()
          ? item.tool_hint.trim()
          : null;
      const status = normalizePlanStepStatus(item.status);
      return {
        id,
        title,
        tool_hint: toolHint,
        status,
        raw_status: typeof item.status === "string" ? item.status : undefined,
        action_id:
          typeof item.action_id === "string" && item.action_id.trim()
            ? item.action_id.trim()
            : null,
      };
    })
    .sort((a, b) => a.id - b.id);
}

function extractPlanEventOrder(evt: WSEvent, payload?: Record<string, unknown> | null): number {
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

function makePlanProgressFromSteps(
  steps: AnalysisStep[],
  rawText = "",
  nextHint: string | null = null,
  blockReason: string | null = null,
): AnalysisPlanProgress | null {
  if (steps.length === 0) return null;
  const currentStepIndex = clampStepIndex(inferCurrentStepIndex(steps), steps.length);
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

function areAllPlanStepsDone(steps: AnalysisStep[]): boolean {
  return steps.length > 0 && steps.every((step) => step.status === "done");
}

function updateAnalysisTaskById(
  tasks: AnalysisTaskItem[],
  taskId: string | null | undefined,
  patch: Partial<
    Pick<
      AnalysisTaskItem,
      "title" | "status" | "raw_status" | "action_id" | "current_activity" | "last_error"
    >
  >,
): AnalysisTaskItem[] {
  if (!taskId) return tasks;
  const idx = tasks.findIndex((task) => task.id === taskId);
  if (idx < 0) return tasks;
  const next = [...tasks];
  const normalizedPatch = Object.fromEntries(
    Object.entries(patch).filter(([, value]) => value !== undefined),
  ) as Partial<AnalysisTaskItem>;
  next[idx] = {
    ...next[idx],
    ...normalizedPatch,
    updated_at: Date.now(),
  };
  return next;
}

function updateAnalysisTaskWithAttempt(
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

  const nextStatus: PlanStepStatus =
    payload.status === "failed"
      ? "failed"
      : payload.status === "success"
        ? "in_progress"
        : "in_progress";

  const next = [...tasks];
  next[idx] = {
    ...task,
    action_id: payload.action_id ?? task.action_id,
    status: mergePlanStepStatus(task.status, nextStatus),
    current_activity:
      payload.note ??
      `正在执行 ${payload.tool_name}（第 ${payload.attempt}/${payload.max_attempts} 次）`,
    last_error: payload.error ?? (payload.status === "success" ? null : task.last_error),
    attempts,
    updated_at: now,
  };
  return next;
}

function applyPlanStepUpdateToProgress(
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

function applyPlanProgressPayload(
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
    next_hint: incomingNextHint ?? deriveNextHint(steps, currentStepIndex, mergedStatus),
    block_reason: blockReason,
  };
}

function getWsUrl(): string {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  const host = window.location.host;
  return `${proto}://${host}/ws`;
}

function uploadWithProgress(
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

// ---- Store ----

export const useStore = create<AppState>((set, get) => ({
  sessionId: null,
  messages: [],
  sessions: [],
  contextCompressionTick: 0,
  datasets: [],
  workspaceFiles: [],
  skills: [],
  memoryFiles: [],
  activeModel: null,
  workspacePanelOpen: false,
  workspacePanelTab: "files",
  fileSearchQuery: "",
  previewTabs: [],
  previewFileId: null,
  codeExecutions: [],
  workspaceFolders: [],
  analysisTasks: [],
  isUploading: false,
  uploadProgress: 0,
  uploadingFileName: null,
  ws: null,
  wsConnected: false,
  isStreaming: false,
  _streamingText: "",
  _currentTurnId: null,
  _reconnectAttempts: 0,
  _activePlanMsgId: null,
  analysisPlanProgress: null,
  _analysisPlanOrder: 0,
  _activePlanTaskIds: [],
  _planActionTaskMap: {},

  connect() {
    const existing = get().ws;
    if (existing && existing.readyState === WebSocket.OPEN) return;
    if (existing && existing.readyState === WebSocket.CONNECTING) return;

    // 页面不可见时不主动连接
    if (document.hidden) return;

    const ws = new WebSocket(getWsUrl());

    ws.onopen = () => {
      set({ wsConnected: true, _reconnectAttempts: 0 });
      // 启动心跳检测 - 15秒间隔，保持连接活跃
      const pingInterval = window.setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "ping" }));
        } else {
          window.clearInterval(pingInterval);
        }
      }, 15000);
      (ws as WebSocket & { _pingInterval?: number })._pingInterval =
        pingInterval;
    };

    ws.onclose = () => {
      const pingInterval = (ws as WebSocket & { _pingInterval?: number })
        ._pingInterval;
      if (pingInterval) clearInterval(pingInterval);

      const state = get();
      const attempts =
        (state as unknown as Record<string, number>)._reconnectAttempts || 0;
      const maxAttempts = 10;

      set({
        ws: null,
        wsConnected: false,
        isStreaming: false,
        _streamingText: "",
        _currentTurnId: null,
        _activePlanMsgId: null,
      });

      // 指数退避重连：1s, 2s, 4s, 8s, 16s, 30s(max)
      if (attempts < maxAttempts && !document.hidden) {
        const delay = Math.min(1000 * Math.pow(2, attempts), 30000);
        set({ _reconnectAttempts: attempts + 1 } as Partial<AppState>);
        setTimeout(() => get().connect(), delay);
      }
    };

    ws.onerror = () => {
      // onclose 会紧随触发
    };

    ws.onmessage = (event) => {
      try {
        const evt: WSEvent = JSON.parse(event.data);
        // 忽略 pong 消息
        if (evt.type === "pong") return;
        handleEvent(evt, set, get);
      } catch {
        // 忽略非法消息
      }
    };

    set({ ws });
  },

  disconnect() {
    const ws = get().ws;
    if (ws) {
      // 清除心跳
      const pingInterval = (ws as WebSocket & { _pingInterval?: number })
        ._pingInterval;
      if (pingInterval) window.clearInterval(pingInterval);
      // 避免触发自动重连
      ws.onclose = null;
      ws.close();
    }
    set({
      ws: null,
      wsConnected: false,
      _reconnectAttempts: 0,
      isStreaming: false,
      _streamingText: "",
      _currentTurnId: null,
      _activePlanMsgId: null,
    });
  },

  async initApp() {
    // 1. 获取会话列表
    await get().fetchSessions();
    await get().fetchSkills();

    // 2. 尝试恢复上次使用的会话
    const savedSessionId = localStorage.getItem("nini_last_session_id");
    const { sessions } = get();

    if (savedSessionId) {
      // 检查保存的会话是否仍存在
      const sessionExists = sessions.some((s) => s.id === savedSessionId);
      if (sessionExists) {
        await get().switchSession(savedSessionId);
        return;
      }
    }

    // 3. 如果没有保存的会话或会话已不存在，自动切换到最近的会话（如果有）
    if (sessions.length > 0) {
      // sessions 已按时间倒序排列，第一个是最新的
      await get().switchSession(sessions[0].id);
    }
    // 4. 如果没有现有会话，保持空状态，等待用户点击"新建会话"
  },

  sendMessage(content: string) {
    const { ws, sessionId } = get();
    if (!ws || ws.readyState !== WebSocket.OPEN) return;

    // 添加用户消息
    const userMsg: Message = {
      id: nextId(),
      role: "user",
      content,
      timestamp: Date.now(),
    };
    set((s) => ({ messages: [...s.messages, userMsg] }));

    // 发送到服务器
    ws.send(
      JSON.stringify({
        type: "chat",
        content,
        session_id: sessionId,
      }),
    );

    set({
      isStreaming: true,
      _streamingText: "",
      _analysisPlanOrder: 0,
      analysisPlanProgress: null,
      _activePlanTaskIds: [],
      _planActionTaskMap: {},
    });
  },

  stopStreaming() {
    const { ws, isStreaming, sessionId } = get();
    if (!isStreaming) return;

    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(
        JSON.stringify({
          type: "stop",
          session_id: sessionId,
        }),
      );
    }

    // 立即停止前端流式状态，避免继续渲染后续 token
    set({
      isStreaming: false,
      _streamingText: "",
      _currentTurnId: null,
      _activePlanMsgId: null,
      _activePlanTaskIds: [],
      _planActionTaskMap: {},
    });
  },

  retryLastTurn() {
    const { ws, sessionId, messages, isStreaming } = get();
    if (isStreaming) return;
    if (!sessionId || !ws || ws.readyState !== WebSocket.OPEN) return;

    let lastUserIndex = -1;
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "user") {
        lastUserIndex = i;
        break;
      }
    }
    if (lastUserIndex < 0) return;

    const retryContent = messages[lastUserIndex].content.trim();
    if (!retryContent) return;

    // 清空最后一条用户消息之后的 Agent 输出
    const trimmedMessages = messages.slice(0, lastUserIndex + 1);
    set({
      messages: trimmedMessages,
      isStreaming: true,
      _streamingText: "",
      _currentTurnId: null,
      _activePlanMsgId: null,
      _analysisPlanOrder: 0,
      analysisPlanProgress: null,
      _activePlanTaskIds: [],
      _planActionTaskMap: {},
    });

    ws.send(
      JSON.stringify({
        type: "retry",
        session_id: sessionId,
        content: retryContent,
      }),
    );
  },

  async uploadFile(file: File) {
    let { sessionId } = get();
    if (!sessionId) {
      try {
        const resp = await fetch("/api/sessions", { method: "POST" });
        const payload = await resp.json();
        const data = isRecord(payload) ? payload.data : null;
        const createdSessionId = isRecord(data) ? data.session_id : null;
        if (typeof createdSessionId !== "string" || !createdSessionId) {
          throw new Error("会话创建失败");
        }
        sessionId = createdSessionId;
        set({ sessionId });
        localStorage.setItem("nini_last_session_id", createdSessionId);
      } catch {
        const errMsg: Message = {
          id: nextId(),
          role: "assistant",
          content: "错误: 自动创建会话失败，请先发送一条消息后重试上传。",
          timestamp: Date.now(),
        };
        set((s) => ({ messages: [...s.messages, errMsg] }));
        return;
      }
    }

    const form = new FormData();
    form.append("file", file);
    form.append("session_id", sessionId);

    set({
      isUploading: true,
      uploadProgress: 0,
      uploadingFileName: file.name,
    });

    try {
      const payload = await uploadWithProgress(form, (percent) => {
        set({ uploadProgress: percent });
      });
      const success = payload.success === true;
      const dataset = isRecord(payload.dataset) ? payload.dataset : null;
      if (success && dataset) {
        const datasetName =
          typeof dataset.name === "string" ? dataset.name : file.name;
        const rowCount =
          typeof dataset.row_count === "number" ? dataset.row_count : 0;
        const columnCount =
          typeof dataset.column_count === "number" ? dataset.column_count : 0;
        // 通知用户上传成功
        const sysMsg: Message = {
          id: nextId(),
          role: "assistant",
          content: `数据集 **${datasetName}** 已加载（${rowCount} 行 × ${columnCount} 列）`,
          timestamp: Date.now(),
        };
        set((s) => ({ messages: [...s.messages, sysMsg] }));
        await get().fetchDatasets();
        await get().fetchWorkspaceFiles();
      } else {
        throw new Error(
          typeof payload.error === "string" ? payload.error : "上传失败",
        );
      }
    } catch (e) {
      console.error("上传失败:", e);
      const err = e instanceof Error ? e.message : "上传失败";
      const errMsg: Message = {
        id: nextId(),
        role: "assistant",
        content: `错误: ${err}`,
        timestamp: Date.now(),
      };
      set((s) => ({ messages: [...s.messages, errMsg] }));
    } finally {
      set({
        isUploading: false,
        uploadProgress: 0,
        uploadingFileName: null,
      });
    }
  },

  clearMessages() {
    set({
      messages: [],
      sessionId: null,
      contextCompressionTick: 0,
      datasets: [],
      workspaceFiles: [],
      previewTabs: [],
      previewFileId: null,
      _activePlanMsgId: null,
      _analysisPlanOrder: 0,
      analysisPlanProgress: null,
      _activePlanTaskIds: [],
      _planActionTaskMap: {},
      analysisTasks: [],
    });
  },

  async fetchSessions() {
    try {
      const resp = await fetch("/api/sessions");
      const payload = await resp.json();
      if (payload.success && Array.isArray(payload.data)) {
        set({ sessions: payload.data as SessionItem[] });
      }
    } catch (e) {
      console.error("获取会话列表失败:", e);
    }
  },

  async fetchDatasets() {
    const sid = get().sessionId;
    if (!sid) {
      set({ datasets: [] });
      return;
    }
    try {
      const resp = await fetch(`/api/sessions/${sid}/datasets`);
      const payload = await resp.json();
      const data = isRecord(payload.data) ? payload.data : null;
      const datasets =
        data && Array.isArray(data.datasets) ? data.datasets : [];
      set({ datasets: datasets as DatasetItem[] });
    } catch (e) {
      console.error("获取数据集列表失败:", e);
    }
  },

  async fetchWorkspaceFiles() {
    const sid = get().sessionId;
    if (!sid) {
      set({ workspaceFiles: [] });
      return;
    }
    try {
      const resp = await fetch(`/api/sessions/${sid}/workspace/files`);
      const payload = await resp.json();
      const data = isRecord(payload.data) ? payload.data : null;
      const files = data && Array.isArray(data.files) ? data.files : [];
      set({ workspaceFiles: files as WorkspaceFile[] });
    } catch (e) {
      console.error("获取工作空间文件失败:", e);
    }
  },

  async fetchSkills() {
    try {
      const resp = await fetch("/api/skills");
      const payload = await resp.json();
      const data = isRecord(payload.data) ? payload.data : null;
      const skills = data && Array.isArray(data.skills) ? data.skills : [];
      set({ skills: skills as SkillItem[] });
    } catch (e) {
      console.error("获取技能列表失败:", e);
    }
  },

  async loadDataset(datasetId: string) {
    const sid = get().sessionId;
    if (!sid || !datasetId) return;
    try {
      await fetch(`/api/sessions/${sid}/datasets/${datasetId}/load`, {
        method: "POST",
      });
      await get().fetchDatasets();
    } catch (e) {
      console.error("加载数据集失败:", e);
    }
  },

  async compressCurrentSession() {
    const sid = get().sessionId;
    if (!sid) {
      return { success: false, message: "请先选择会话" };
    }
    try {
      const resp = await fetch(`/api/sessions/${sid}/compress`, {
        method: "POST",
      });
      const payload = await resp.json();
      if (!payload.success) {
        return {
          success: false,
          message:
            typeof payload.error === "string" ? payload.error : "会话压缩失败",
        };
      }
      const data = isRecord(payload.data) ? payload.data : null;
      const archivedCount =
        typeof data?.archived_count === "number" ? data.archived_count : 0;
      const remainingCount =
        typeof data?.remaining_count === "number" ? data.remaining_count : 0;
      const message = `会话压缩完成：归档 ${archivedCount} 条，剩余 ${remainingCount} 条`;

      // 压缩成功后刷新当前消息列表
      await get().switchSession(sid);
      set((s) => ({ contextCompressionTick: s.contextCompressionTick + 1 }));
      return { success: true, message };
    } catch (e) {
      console.error("压缩会话失败:", e);
      return { success: false, message: "压缩会话失败，请稍后重试" };
    }
  },

  async createNewSession() {
    // 防重复：如果已有未使用的空会话，直接切换过去
    const { sessions, sessionId } = get();
    const emptySession = sessions.find(
      (s) => s.message_count === 0 && s.title === "新会话",
    );
    if (emptySession) {
      if (emptySession.id !== sessionId) {
        await get().switchSession(emptySession.id);
      }
      return;
    }

    try {
      const resp = await fetch("/api/sessions", { method: "POST" });
      const payload = await resp.json();
      const data = isRecord(payload) ? payload.data : null;
      const newSessionId = isRecord(data) ? data.session_id : null;
      if (typeof newSessionId !== "string" || !newSessionId) {
        throw new Error("会话创建失败");
      }
      // 切换到新会话，清空当前消息显示
      set({
        sessionId: newSessionId,
        messages: [],
        contextCompressionTick: 0,
        datasets: [],
        workspaceFiles: [],
        previewTabs: [],
        previewFileId: null,
        _streamingText: "",
        isStreaming: false,
        _activePlanMsgId: null,
        _analysisPlanOrder: 0,
        analysisPlanProgress: null,
        _activePlanTaskIds: [],
        _planActionTaskMap: {},
        analysisTasks: [],
      });
      // 清除保存的 session_id（新会话不需要恢复）
      localStorage.removeItem("nini_last_session_id");
      // 刷新会话列表
      await get().fetchSessions();
    } catch (e) {
      console.error("创建新会话失败:", e);
    }
  },

  async switchSession(targetSessionId: string) {
    const { sessionId } = get();
    if (targetSessionId === sessionId) return;

    try {
      const resp = await fetch(`/api/sessions/${targetSessionId}/messages`);
      const payload = await resp.json();
      if (!payload.success) {
        // 会话存在但无消息，直接切换到空会话
        set({
          sessionId: targetSessionId,
          messages: [],
          contextCompressionTick: 0,
          previewTabs: [],
          previewFileId: null,
          _streamingText: "",
          isStreaming: false,
          _activePlanMsgId: null,
          _analysisPlanOrder: 0,
          analysisPlanProgress: null,
          _activePlanTaskIds: [],
          _planActionTaskMap: {},
          analysisTasks: [],
        });
        await get().fetchDatasets();
        await get().fetchWorkspaceFiles();
        return;
      }

      const data = isRecord(payload.data) ? payload.data : null;
      const rawMessages =
        isRecord(data) && Array.isArray(data.messages) ? data.messages : [];

      // 将后端消息格式转换为前端 Message 格式（包含工具调用与结果）
      const messages = buildMessagesFromHistory(
        rawMessages as RawSessionMessage[],
      );

      set({
        sessionId: targetSessionId,
        messages,
        contextCompressionTick: 0,
        previewTabs: [],
        previewFileId: null,
        _streamingText: "",
        isStreaming: false,
        _activePlanMsgId: null,
        _analysisPlanOrder: 0,
        analysisPlanProgress: null,
        _activePlanTaskIds: [],
        _planActionTaskMap: {},
        analysisTasks: [],
      });
      // 保存当前会话 ID 到 localStorage
      localStorage.setItem("nini_last_session_id", targetSessionId);
      await get().fetchDatasets();
      await get().fetchWorkspaceFiles();
      await get().fetchCodeExecutions();
      await get().fetchFolders();
    } catch (e) {
      console.error("切换会话失败:", e);
    }
  },

  async deleteSession(targetSessionId: string) {
    try {
      await fetch(`/api/sessions/${targetSessionId}`, { method: "DELETE" });
      const { sessionId } = get();
      // 如果删除的是当前会话，清空状态
      if (targetSessionId === sessionId) {
        set({
          sessionId: null,
          messages: [],
          contextCompressionTick: 0,
          datasets: [],
          workspaceFiles: [],
          previewTabs: [],
          previewFileId: null,
          _streamingText: "",
          isStreaming: false,
          _activePlanMsgId: null,
          _analysisPlanOrder: 0,
          analysisPlanProgress: null,
          _activePlanTaskIds: [],
          _planActionTaskMap: {},
          analysisTasks: [],
        });
      }
      // 刷新会话列表
      await get().fetchSessions();
    } catch (e) {
      console.error("删除会话失败:", e);
    }
  },

  async updateSessionTitle(targetSessionId: string, title: string) {
    try {
      await fetch(`/api/sessions/${targetSessionId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title }),
      });
      // 更新本地状态
      set((s) => ({
        sessions: s.sessions.map((sess) =>
          sess.id === targetSessionId ? { ...sess, title } : sess,
        ),
      }));
    } catch (e) {
      console.error("更新会话标题失败:", e);
    }
  },

  async fetchMemoryFiles() {
    const sid = get().sessionId;
    if (!sid) {
      set({ memoryFiles: [] });
      return;
    }
    try {
      const resp = await fetch(`/api/sessions/${sid}/memory-files`);
      const payload = await resp.json();
      const rawData = isRecord(payload.data) ? payload.data : null;
      const rawFiles: unknown[] = Array.isArray(payload.data)
        ? payload.data
        : rawData && Array.isArray(rawData.files)
          ? rawData.files
          : [];

      const normalized: MemoryFile[] = rawFiles
        .filter((item): item is Record<string, unknown> => isRecord(item))
        .map((item) => {
          const name = typeof item.name === "string" ? item.name : "unknown";
          const size =
            typeof item.size === "number" && Number.isFinite(item.size)
              ? item.size
              : 0;
          return {
            name,
            size,
            modified_at: normalizeMemoryTimestamp(item.modified_at),
            type: inferMemoryFileType(name),
          };
        });

      if (payload.success) {
        set({ memoryFiles: normalized });
      } else {
        set({ memoryFiles: [] });
      }
    } catch (e) {
      console.error("获取记忆文件失败:", e);
      set({ memoryFiles: [] });
    }
  },

  async fetchActiveModel() {
    try {
      const resp = await fetch("/api/models/active");
      const payload = await resp.json();
      if (payload.success && isRecord(payload.data)) {
        set({ activeModel: payload.data as ActiveModelInfo });
      }
    } catch (e) {
      console.error("获取活跃模型失败:", e);
    }
  },

  async setPreferredProvider(providerId: string) {
    try {
      // 同时设为内存首选和持久化默认
      const resp = await fetch("/api/models/preferred", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider_id: providerId }),
      });
      const payload = await resp.json();
      if (payload.success && isRecord(payload.data)) {
        set({ activeModel: payload.data as ActiveModelInfo });
      }
    } catch (e) {
      console.error("设置首选模型失败:", e);
    }
  },

  toggleWorkspacePanel() {
    set((s) => ({ workspacePanelOpen: !s.workspacePanelOpen }));
  },

  setWorkspacePanelTab(tab: "files" | "executions" | "tasks") {
    set({ workspacePanelTab: tab });
  },

  setFileSearchQuery(query: string) {
    set({ fileSearchQuery: query });
  },

  deleteAnalysisTask(taskId: string) {
    set((s) => {
      const nextTasks = s.analysisTasks.filter((task) => task.id !== taskId);
      if (nextTasks.length === s.analysisTasks.length) return {};
      const nextActionMap = Object.fromEntries(
        Object.entries(s._planActionTaskMap).filter(([, mappedTaskId]) => mappedTaskId !== taskId),
      );
      return {
        analysisTasks: nextTasks,
        _activePlanTaskIds: s._activePlanTaskIds.map((id) =>
          id === taskId ? null : id,
        ),
        _planActionTaskMap: nextActionMap,
      };
    });
  },

  clearAnalysisTasks() {
    set({
      analysisTasks: [],
      _activePlanTaskIds: [],
      _planActionTaskMap: {},
      analysisPlanProgress: null,
      _activePlanMsgId: null,
    });
  },

  async deleteWorkspaceFile(fileId: string) {
    const sid = get().sessionId;
    if (!sid) return;
    try {
      const resp = await fetch(
        `/api/sessions/${sid}/workspace/files/${fileId}`,
        {
          method: "DELETE",
        },
      );
      const payload = await resp.json();
      if (payload.success) {
        await get().fetchWorkspaceFiles();
        await get().fetchDatasets();
      }
    } catch (e) {
      console.error("删除文件失败:", e);
    }
  },

  openPreview(fileId: string) {
    set((s) => {
      if (s.previewTabs.includes(fileId)) {
        return { previewFileId: fileId };
      }
      return {
        previewTabs: [...s.previewTabs, fileId],
        previewFileId: fileId,
      };
    });
  },

  setActivePreview(fileId: string | null) {
    set({ previewFileId: fileId });
  },

  closePreview(fileId?: string) {
    set((s) => {
      const target = fileId ?? s.previewFileId;
      if (!target) return { previewFileId: null };
      const nextTabs = s.previewTabs.filter((id) => id !== target);
      if (nextTabs.length === 0) {
        return { previewTabs: [], previewFileId: null };
      }
      if (s.previewFileId !== target) {
        return { previewTabs: nextTabs };
      }
      return {
        previewTabs: nextTabs,
        previewFileId: nextTabs[nextTabs.length - 1],
      };
    });
  },

  async fetchCodeExecutions() {
    const sid = get().sessionId;
    if (!sid) {
      set({ codeExecutions: [] });
      return;
    }
    try {
      const resp = await fetch(`/api/sessions/${sid}/workspace/executions`);
      const payload = await resp.json();
      const data = isRecord(payload.data) ? payload.data : null;
      const executions =
        data && Array.isArray(data.executions) ? data.executions : [];
      set({ codeExecutions: executions as CodeExecution[] });
    } catch (e) {
      console.error("获取执行历史失败:", e);
    }
  },

  async renameWorkspaceFile(fileId: string, newName: string) {
    const sid = get().sessionId;
    if (!sid || !newName.trim()) return;
    try {
      const resp = await fetch(
        `/api/sessions/${sid}/workspace/files/${fileId}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: newName }),
        },
      );
      const payload = await resp.json();
      if (payload.success) {
        await get().fetchWorkspaceFiles();
        await get().fetchDatasets();
      }
    } catch (e) {
      console.error("重命名文件失败:", e);
    }
  },

  async fetchFolders() {
    const sid = get().sessionId;
    if (!sid) {
      set({ workspaceFolders: [] });
      return;
    }
    try {
      const resp = await fetch(`/api/sessions/${sid}/workspace/folders`);
      const payload = await resp.json();
      const data = isRecord(payload.data) ? payload.data : null;
      const folders = data && Array.isArray(data.folders) ? data.folders : [];
      set({ workspaceFolders: folders as WorkspaceFolder[] });
    } catch (e) {
      console.error("获取文件夹失败:", e);
    }
  },

  async createFolder(name: string, parent?: string | null) {
    const sid = get().sessionId;
    if (!sid || !name.trim()) return;
    try {
      await fetch(`/api/sessions/${sid}/workspace/folders`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, parent: parent ?? null }),
      });
      await get().fetchFolders();
    } catch (e) {
      console.error("创建文件夹失败:", e);
    }
  },

  async moveFileToFolder(fileId: string, folderId: string | null) {
    const sid = get().sessionId;
    if (!sid) return;
    try {
      await fetch(`/api/sessions/${sid}/workspace/files/${fileId}/move`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ folder_id: folderId }),
      });
      await get().fetchWorkspaceFiles();
    } catch (e) {
      console.error("移动文件失败:", e);
    }
  },

  async createWorkspaceFile(filename: string, content?: string) {
    const sid = get().sessionId;
    if (!sid || !filename.trim()) return;
    try {
      await fetch(`/api/sessions/${sid}/workspace/files`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename, content: content ?? "" }),
      });
      await get().fetchWorkspaceFiles();
    } catch (e) {
      console.error("创建文件失败:", e);
    }
  },
}));

// ---- 页面可见性处理 ----
// 页面切出时断开连接，切回时重连
document.addEventListener("visibilitychange", () => {
  const store = useStore.getState();
  if (document.hidden) {
    // 页面隐藏时若在生成中则保留连接，避免中途断线
    if (!store.isStreaming) {
      store.disconnect();
    }
  } else {
    // 页面可见时重置重连计数并连接
    useStore.setState({ _reconnectAttempts: 0 } as Partial<AppState>);
    store.connect();
  }
});

function parseToolArgs(rawArgs: unknown): Record<string, unknown> {
  if (typeof rawArgs !== "string" || !rawArgs.trim()) return {};
  try {
    const parsed = JSON.parse(rawArgs);
    return isRecord(parsed) ? parsed : { value: parsed };
  } catch {
    return { raw: rawArgs };
  }
}

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

function normalizeToolResult(rawContent: unknown): {
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

function buildMessagesFromHistory(rawMessages: RawSessionMessage[]): Message[] {
  const messages: Message[] = [];
  const toolCallMap = new Map<
    string,
    { name?: string; input?: Record<string, unknown> }
  >();
  let tsOffset = 0;

  const nextTimestamp = () => Date.now() + tsOffset++;

  for (const raw of rawMessages) {
    const role = raw.role;
    if (role === "user" && typeof raw.content === "string" && raw.content) {
      messages.push({
        id: nextId(),
        role: "user",
        content: raw.content,
        timestamp: nextTimestamp(),
      });
      continue;
    }

    if (role === "assistant") {
      const eventType =
        typeof raw.event_type === "string" ? raw.event_type : "";
      if (eventType === "chart") {
        messages.push({
          id: nextId(),
          role: "assistant",
          content:
            typeof raw.content === "string" && raw.content
              ? raw.content
              : "图表已生成",
          chartData: raw.chart_data,
          timestamp: nextTimestamp(),
        });
        continue;
      }
      if (eventType === "data") {
        messages.push({
          id: nextId(),
          role: "assistant",
          content:
            typeof raw.content === "string" && raw.content
              ? raw.content
              : "数据预览如下",
          dataPreview: raw.data_preview,
          timestamp: nextTimestamp(),
        });
        continue;
      }
      if (eventType === "artifact") {
        messages.push({
          id: nextId(),
          role: "assistant",
          content:
            typeof raw.content === "string" && raw.content
              ? raw.content
              : "产物已生成",
          artifacts: Array.isArray(raw.artifacts) ? raw.artifacts : [],
          timestamp: nextTimestamp(),
        });
        continue;
      }
      if (eventType === "image") {
        messages.push({
          id: nextId(),
          role: "assistant",
          content:
            typeof raw.content === "string" && raw.content
              ? raw.content
              : "图片已生成",
          images: Array.isArray(raw.images) ? raw.images : [],
          timestamp: nextTimestamp(),
        });
        continue;
      }

      if (typeof raw.content === "string" && raw.content) {
        const cleanedContent = stripReasoningMarkers(raw.content);
        if (!cleanedContent.trim()) {
          continue;
        }
        messages.push({
          id: nextId(),
          role: "assistant",
          content: cleanedContent,
          timestamp: nextTimestamp(),
        });
      }

      const toolCalls = Array.isArray(raw.tool_calls) ? raw.tool_calls : [];
      for (const tc of toolCalls) {
        const name = tc.function?.name || "工具调用";
        const argsRaw = tc.function?.arguments || "";
        const toolArgs = normalizeRunCodeIntent(name, parseToolArgs(argsRaw));
        const toolCallId = tc.id;
        const toolIntent =
          name === "run_code" && typeof toolArgs.intent === "string"
            ? toolArgs.intent
            : undefined;
        const msg: Message = {
          id: nextId(),
          role: "tool",
          content: toolIntent
            ? `🔧 ${name}: ${toolIntent}`
            : `调用工具: **${name}**`,
          toolName: name,
          toolCallId: toolCallId || undefined,
          toolInput: toolArgs,
          toolIntent,
          timestamp: nextTimestamp(),
        };
        messages.push(msg);
        if (toolCallId) {
          toolCallMap.set(toolCallId, { name, input: toolArgs });
        }
      }
      continue;
    }

    if (role === "tool") {
      const toolCallId =
        typeof raw.tool_call_id === "string" ? raw.tool_call_id : undefined;
      const normalized = normalizeToolResult(raw.content);
      const existingIndex = toolCallId
        ? messages.findIndex(
            (m) =>
              m.role === "tool" && m.toolCallId === toolCallId && !m.toolResult,
          )
        : -1;

      if (existingIndex >= 0) {
        messages[existingIndex] = {
          ...messages[existingIndex],
          toolResult: normalized.message,
          toolStatus: normalized.status,
        };
      } else {
        const meta = toolCallId ? toolCallMap.get(toolCallId) : undefined;
        messages.push({
          id: nextId(),
          role: "tool",
          content: normalized.message,
          toolName: meta?.name,
          toolCallId: toolCallId,
          toolInput: meta?.input,
          toolResult: normalized.message,
          toolStatus: normalized.status,
          timestamp: nextTimestamp(),
        });
      }
    }
  }

  return messages;
}

// ---- 事件处理 ----

function handleEvent(
  evt: WSEvent,
  set: (fn: Partial<AppState> | ((s: AppState) => Partial<AppState>)) => void,
  get: () => AppState,
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
      // 新迭代开始：重置流式文本累积，记录 turnId
      set({ _streamingText: "", _currentTurnId: evt.turn_id || null });
      break;
    }

    case "text": {
      const text = stripReasoningMarkers((evt.data as string) || "");
      if (!text) break;
      const newStreamText = get()._streamingText + text;
      const turnId = evt.turn_id || get()._currentTurnId || undefined;

      set((s) => {
        // 更新或创建 assistant 消息（同一迭代内）
        const msgs = [...s.messages];
        const last = msgs[msgs.length - 1];
        if (
          last &&
          last.role === "assistant" &&
          !last.toolName &&
          !last.retrievals &&
          last.turnId === turnId
        ) {
          msgs[msgs.length - 1] = { ...last, content: newStreamText };
        } else {
          msgs.push({
            id: nextId(),
            role: "assistant",
            content: newStreamText,
            turnId,
            timestamp: Date.now(),
          });
        }
        return { messages: msgs, _streamingText: newStreamText };
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
        }));
        const actionMap = {
          ...s._planActionTaskMap,
          ...Object.fromEntries(
            appendedTasks
              .filter((task) => typeof task.action_id === "string" && task.action_id)
              .map((task) => [task.action_id as string, task.id]),
          ),
        };
        return {
          messages: [...s.messages, msg],
          _activePlanMsgId: msgId,
          analysisPlanProgress: makePlanProgressFromSteps(steps, rawText),
          analysisTasks: [...s.analysisTasks, ...appendedTasks],
          _activePlanTaskIds: appendedTasks.map((task) => task.id),
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
                      typeof stepStatus === "string" ? stepStatus : step.raw_status,
                  }
                : step,
            );
            msgs[idx] = {
              ...msgs[idx],
              analysisPlan: { ...plan, steps: updatedSteps },
            };
          }
        }

        const taskId =
          stepId > 0 && stepId <= s._activePlanTaskIds.length
            ? s._activePlanTaskIds[stepId - 1]
            : null;
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
        const nextProgress = applyPlanProgressPayload(s.analysisPlanProgress, data);
        if (!nextProgress) return {};
        const stepId = nextProgress.current_step_index;
        const taskId =
          stepId > 0 && stepId <= s._activePlanTaskIds.length
            ? s._activePlanTaskIds[stepId - 1]
            : null;
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
        if (actionId && s._planActionTaskMap[actionId]) {
          taskId = s._planActionTaskMap[actionId];
        } else if (stepId && stepId > 0 && stepId <= s._activePlanTaskIds.length) {
          taskId = s._activePlanTaskIds[stepId - 1] ?? null;
        } else if (stepId) {
          const fallback = [...s.analysisTasks]
            .reverse()
            .find((task) => task.plan_step_id === stepId);
          taskId = fallback?.id || null;
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
      const msg: Message = {
        id: nextId(),
        role: "assistant",
        content,
        isReasoning: true,
        turnId,
        timestamp: Date.now(),
      };
      set((s) => ({ messages: [...s.messages, msg] }));
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
        return { messages: msgs };
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

    case "done":
      set((s) => {
        let progress = s.analysisPlanProgress;
        let tasks = s.analysisTasks;
        if (progress && progress.step_status === "in_progress") {
          const taskId =
            progress.current_step_index > 0 &&
            progress.current_step_index <= s._activePlanTaskIds.length
              ? s._activePlanTaskIds[progress.current_step_index - 1]
              : null;
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
          isStreaming: false,
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
        if (progress && progress.step_status === "in_progress") {
          const taskId =
            progress.current_step_index > 0 &&
            progress.current_step_index <= s._activePlanTaskIds.length
              ? s._activePlanTaskIds[progress.current_step_index - 1]
              : null;
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
          isStreaming: false,
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
      const errMsg: Message = {
        id: nextId(),
        role: "assistant",
        content: `错误: ${evt.data}`,
        timestamp: Date.now(),
      };
      set((s) => ({
        messages: [...s.messages, errMsg],
        isStreaming: false,
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
          const taskId =
            progress.current_step_index > 0 &&
            progress.current_step_index <= s._activePlanTaskIds.length
              ? s._activePlanTaskIds[progress.current_step_index - 1]
              : null;
          const currentTask = taskId
            ? s.analysisTasks.find((task) => task.id === taskId)
            : undefined;
          const mergedStatus = currentTask
            ? mergePlanStepStatus(currentTask.status, "failed")
            : "failed";
          return updateAnalysisTaskById(s.analysisTasks, taskId, {
            status: mergedStatus,
            current_activity: "步骤执行失败",
            last_error: typeof evt.data === "string" ? evt.data : undefined,
          });
        })(),
        analysisPlanProgress: (() => {
          const progress = s.analysisPlanProgress;
          if (!progress || progress.step_status !== "in_progress") return progress;
          const failedIndex = progress.current_step_index - 1;
          return {
            ...progress,
            step_status: "failed",
            block_reason: typeof evt.data === "string" ? evt.data : "执行失败",
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
