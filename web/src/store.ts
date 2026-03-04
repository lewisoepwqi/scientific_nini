/**
 * Zustand Store - 使用 Slices 模式
 *
 * Nini 2.0 架构重构 - Phase 3.2.10
 * 将原单体 store.ts 拆分为多个 slice 模块
 */

import { create } from "zustand";
import type { WsConnectionStatus } from "./store/websocket-status";
import { resolveWsClosedStatus } from "./store/websocket-status";

// ---- 类型导入 ----
export type {
  ArtifactInfo,
  RetrievalItem,
  SkillItem,
  CapabilityItem,
  SkillDetail,
  SkillPathEntry,
  SkillFileContent,
  DatasetItem,
  WorkspaceFile,
  WorkspaceFolder,
  PlanStepStatus,
  AnalysisStep,
  AnalysisPlanData,
  AnalysisPlanProgress,
  AnalysisTaskAttemptStatus,
  AnalysisTaskAttempt,
  AnalysisTaskItem,
  AskUserQuestionOption,
  AskUserQuestionItem,
  PendingAskUserQuestion,
  IntentOption,
  IntentSkillCall,
  IntentSkillSummary,
  IntentCandidateView,
  IntentAnalysisView,
  ResearchProfile,
  ModelTokenUsage,
  TokenUsage,
  StreamingMetrics,
  SessionCostSummary,
  AggregateCostSummary,
  ModelPricing,
  PricingTierDefinition,
  PricingConfig,
  Message,
  SessionItem,
  ActiveModelInfo,
  ModelProviderInfo,
  CodeExecution,
  MemoryFile,
  WSEvent,
  RawSessionMessage,
  DisplayPreference,
  UserDisplayPreference,
  MessageBuffer,
} from "./store/types";

import type {
  SkillItem,
  CapabilityItem,
  SkillDetail,
  SkillPathEntry,
  SkillFileContent,
  DatasetItem,
  WorkspaceFile,
  WorkspaceFolder,
  AnalysisPlanProgress,
  AnalysisTaskItem,
  PendingAskUserQuestion,
  IntentAnalysisView,
  ResearchProfile,
  TokenUsage,
  StreamingMetrics,
  SessionCostSummary,
  AggregateCostSummary,
  PricingConfig,
  Message,
  SessionItem,
  ActiveModelInfo,
  ModelProviderInfo,
  CodeExecution,
  MemoryFile,
  WSEvent,
  RawSessionMessage,
  DisplayPreference,
  MessageBuffer,
} from "./store/types";

// ---- 工具函数导入 ----
import {
  isRecord,
  nextId,
  nextAnalysisTaskId,
  nextAnalysisAttemptId,
  getWsUrl,
  inferMemoryFileType,
  normalizeMemoryTimestamp,
  mergeReasoningContent,
  clampStepIndex,
  inferCurrentStepIndex,
  findLatestTurnSpan,
  makePlanProgressFromSteps,
  areAllPlanStepsDone,
  updateAnalysisTaskById,
  updateAnalysisTaskWithAttempt,
  applyPlanStepUpdateToProgress,
  applyPlanProgressPayload,
  uploadWithProgress,
  updateMessageBuffer,
  getMessageBufferContent,
  completeMessageBuffer,
  cleanupMessageBuffer,
  hasMessageBuffer,
} from "./store/utils";

// ---- 规范化函数导入 ----
import {
  normalizeIntentOption,
  normalizeIntentCandidate,
  normalizeIntentSkillCall,
  normalizeIntentSkillSummary,
  normalizeIntentAnalysis,
  normalizePlanStepStatus,
  normalizeTaskAttemptStatus,
  stripReasoningMarkers,
  isTerminalPlanStepStatus,
  mergePlanStepStatus,
  truncatePlanText,
  createDefaultPlanSteps,
  normalizeAnalysisSteps,
} from "./store/normalizers";

// ---- 计划状态机导入 ----
import { deriveNextHint } from "./store/plan-state-machine";

// ---- 事件处理器导入 ----
import { handleEvent } from "./store/event-handler";

// ---- API 动作导入 ----
import * as api from "./store/api-actions";

// ============================================================================
// Store 状态接口
// ============================================================================

export interface AppState {
  // 会话状态
  sessionId: string | null;
  messages: Message[];
  sessions: SessionItem[];
  contextCompressionTick: number;
  datasets: DatasetItem[];
  workspaceFiles: WorkspaceFile[];
  skills: SkillItem[];
  capabilities: CapabilityItem[];

  // 记忆面板
  memoryFiles: MemoryFile[];

  // 模型选择
  activeModel: ActiveModelInfo | null;
  modelProviders: ModelProviderInfo[];
  modelProvidersLoading: boolean;

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

  // 连接状态
  ws: WebSocket | null;
  wsConnected: boolean;
  wsStatus: WsConnectionStatus;
  isStreaming: boolean;
  pendingAskUserQuestion: PendingAskUserQuestion | null;
  currentIntentAnalysis: IntentAnalysisView | null;
  intentAnalysisLoading: boolean;
  composerDraft: string;

  // 内部状态
  _streamingText: string;
  _currentTurnId: string | null;
  _reconnectAttempts: number;
  _lastHandledSeq: number | undefined;
  _activePlanMsgId: string | null;
  analysisPlanProgress: AnalysisPlanProgress | null;
  _analysisPlanOrder: number;
  _activePlanTaskIds: Array<string | null>;
  _planActionTaskMap: Record<string, string>;
  // 消息缓冲区（用于去重）
  _messageBuffer: MessageBuffer;
  _streamingMetrics: StreamingMetrics;

  // ResearchProfile
  researchProfile: ResearchProfile | null;
  researchProfileLoading: boolean;

  // 成本透明化
  tokenUsage: TokenUsage | null;
  costHistory: SessionCostSummary[];
  aggregateCost: AggregateCostSummary | null;
  pricingConfig: PricingConfig | null;
  costPanelOpen: boolean;

  // 用户展示偏好
  displayPreference: DisplayPreference;

  // ---- 操作 ----

  // WebSocket 操作
  connect: () => void;
  disconnect: () => void;

  // 会话操作
  initApp: () => Promise<void>;
  sendMessage: (content: string) => Promise<void>;
  submitAskUserQuestionAnswers: (answers: Record<string, string>) => void;
  stopStreaming: () => void;
  retryLastTurn: () => Promise<void>;
  setComposerDraft: (value: string) => void;
  uploadFile: (file: File) => Promise<void>;
  clearMessages: () => void;

  // 数据获取操作
  fetchSessions: () => Promise<void>;
  fetchDatasets: () => Promise<void>;
  fetchWorkspaceFiles: () => Promise<void>;
  fetchSkills: () => Promise<void>;
  fetchCapabilities: () => Promise<void>;
  analyzeIntent: (content: string) => Promise<void>;

  // 技能管理操作
  uploadSkillFile: (file: File) => Promise<{ success: boolean; message: string }>;
  getSkillDetail: (skillName: string) => Promise<{ success: boolean; skill?: SkillDetail; message: string }>;
  updateSkill: (skillName: string, payload: { description: string; category: string; content: string }) => Promise<{ success: boolean; message: string }>;
  toggleSkillEnabled: (skillName: string, enabled: boolean) => Promise<{ success: boolean; message: string }>;
  deleteSkill: (skillName: string) => Promise<{ success: boolean; message: string }>;
  listSkillFiles: (skillName: string) => Promise<{ success: boolean; files?: SkillPathEntry[]; message: string }>;
  getSkillFileContent: (skillName: string, path: string) => Promise<{ success: boolean; file?: SkillFileContent; message: string }>;
  saveSkillFileContent: (skillName: string, path: string, content: string) => Promise<{ success: boolean; message: string }>;
  uploadSkillAttachment: (skillName: string, file: File, dirPath?: string, overwrite?: boolean) => Promise<{ success: boolean; message: string }>;
  createSkillDir: (skillName: string, path: string) => Promise<{ success: boolean; message: string }>;
  deleteSkillPath: (skillName: string, path: string) => Promise<{ success: boolean; message: string }>;
  downloadSkillBundle: (skillName: string) => Promise<{ success: boolean; message: string }>;

  // 数据集操作
  loadDataset: (datasetId: string) => Promise<void>;

  // 会话管理操作
  compressCurrentSession: () => Promise<{ success: boolean; message: string }>;
  createNewSession: () => Promise<void>;
  switchSession: (sessionId: string) => Promise<void>;
  deleteSession: (sessionId: string) => Promise<void>;
  updateSessionTitle: (sessionId: string, title: string) => Promise<void>;

  // 记忆文件操作
  fetchMemoryFiles: () => Promise<void>;

  // 模型配置操作
  fetchActiveModel: () => Promise<void>;
  setPreferredProvider: (providerId: string) => Promise<void>;
  setChatRoute: (providerId: string, model: string | null) => Promise<void>;
  fetchModelProviders: () => Promise<void>;

  // 工作区面板操作
  toggleWorkspacePanel: () => void;
  setWorkspacePanelTab: (tab: "files" | "executions" | "tasks") => void;
  setFileSearchQuery: (query: string) => void;
  deleteAnalysisTask: (taskId: string) => void;
  clearAnalysisTasks: () => void;
  deleteWorkspaceFile: (filePath: string) => Promise<void>;
  renameWorkspaceFile: (filePath: string, newName: string) => Promise<void>;
  openPreview: (fileId: string) => void;
  setActivePreview: (fileId: string | null) => void;
  closePreview: (fileId?: string) => void;
  fetchCodeExecutions: () => Promise<void>;
  fetchFolders: () => Promise<void>;
  createFolder: (name: string, parent?: string | null) => Promise<void>;
  moveFileToFolder: (filePath: string, folderId: string | null) => Promise<void>;
  createWorkspaceFile: (filename: string, content?: string) => Promise<void>;

  // ResearchProfile 操作
  fetchResearchProfile: () => Promise<void>;
  updateResearchProfile: (updates: Partial<ResearchProfile>) => Promise<boolean>;

  // 成本透明化操作
  fetchTokenUsage: (sessionId: string) => Promise<void>;
  fetchCostHistory: () => Promise<void>;
  fetchPricingConfig: () => Promise<void>;
  toggleCostPanel: () => void;
  setCostPanelOpen: (open: boolean) => void;

  // 用户展示偏好操作
  setDisplayPreference: (mode: DisplayPreference) => void;
}

// ============================================================================
// 常量定义
// ============================================================================

const SESSION_RESET_STATE = {
  pendingAskUserQuestion: null as PendingAskUserQuestion | null,
  contextCompressionTick: 0,
  previewTabs: [] as string[],
  previewFileId: null as string | null,
  _streamingText: "",
  isStreaming: false,
  _activePlanMsgId: null as string | null,
  _analysisPlanOrder: 0,
  analysisPlanProgress: null as AnalysisPlanProgress | null,
  _activePlanTaskIds: [] as string[],
  _planActionTaskMap: {} as Record<string, string>,
  _messageBuffer: {} as MessageBuffer,
  _streamingMetrics: {
    startedAt: null,
    turnId: null,
    totalTokens: 0,
    hasTokenUsage: false,
  } as StreamingMetrics,
  analysisTasks: [] as AnalysisTaskItem[],
  currentIntentAnalysis: null as IntentAnalysisView | null,
  intentAnalysisLoading: false,
  composerDraft: "",
};

// ============================================================================
// Store 创建
// ============================================================================

export const useStore = create<AppState>((set, get) => ({
  // ---- 初始状态 ----
  sessionId: null,
  messages: [],
  sessions: [],
  contextCompressionTick: 0,
  datasets: [],
  workspaceFiles: [],
  skills: [],
  capabilities: [],
  memoryFiles: [],
  activeModel: null,
  modelProviders: [],
  modelProvidersLoading: false,
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
  wsStatus: "disconnected",
  isStreaming: false,
  pendingAskUserQuestion: null,
  currentIntentAnalysis: null,
  intentAnalysisLoading: false,
  composerDraft: "",
  _streamingText: "",
  _currentTurnId: null,
  _reconnectAttempts: 0,
  _lastHandledSeq: undefined,
  _activePlanMsgId: null,
  analysisPlanProgress: null,
  _analysisPlanOrder: 0,
  _activePlanTaskIds: [],
  _planActionTaskMap: {},
  _messageBuffer: {},
  _streamingMetrics: {
    startedAt: null,
    turnId: null,
    totalTokens: 0,
    hasTokenUsage: false,
  },
  researchProfile: null,
  researchProfileLoading: false,
  tokenUsage: null,
  costHistory: [],
  aggregateCost: null,
  pricingConfig: null,
  costPanelOpen: false,
  displayPreference: (() => {
    // 从 localStorage 读取用户偏好，默认为简化模式
    if (typeof window !== "undefined") {
      try {
        const saved = localStorage.getItem("nini_display_preference");
        if (saved === "simplified" || saved === "detailed" || saved === "hidden") {
          return saved;
        }
      } catch {
        // localStorage 不可用则使用默认值
      }
    }
    return "simplified";
  })(),

  // ============================================================================
  // WebSocket 操作
  // ============================================================================

  connect() {
    const existing = get().ws;
    if (existing && existing.readyState === WebSocket.OPEN) return;
    if (existing && existing.readyState === WebSocket.CONNECTING) {
      set({ wsStatus: get()._reconnectAttempts > 0 ? "reconnecting" : "connecting" });
      return;
    }

    if (typeof document !== "undefined" && document.hidden) return;

    const reconnectTimer = (
      window as Window & { __niniReconnectTimer?: number }
    ).__niniReconnectTimer;
    if (reconnectTimer) {
      window.clearTimeout(reconnectTimer);
      delete (window as Window & { __niniReconnectTimer?: number }).__niniReconnectTimer;
    }

    const attempts = get()._reconnectAttempts;
    set({
      wsConnected: false,
      wsStatus: attempts > 0 ? "reconnecting" : "connecting",
    });

    const ws = new WebSocket(getWsUrl());
    let heartbeatTimer: number | undefined;

    ws.onopen = () => {
      const wasReconnecting = get()._reconnectAttempts > 0;
      const activeSessionId = get().sessionId;
      set({
        wsConnected: true,
        wsStatus: "connected",
        _reconnectAttempts: 0,
        _messageBuffer: {},
      });
      heartbeatTimer = window.setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "ping" }));
        } else {
          window.clearInterval(heartbeatTimer);
        }
      }, 15000);
      if (wasReconnecting && activeSessionId) {
        void get().switchSession(activeSessionId);
      }
    };

    ws.onclose = () => {
      if (heartbeatTimer) clearInterval(heartbeatTimer);
      const attempts = get()._reconnectAttempts;
      const maxAttempts = 10;
      const hidden = typeof document !== "undefined" ? document.hidden : false;
      const nextStatus = resolveWsClosedStatus(attempts, maxAttempts, hidden);

      set({
        ws: null,
        wsConnected: false,
        wsStatus: nextStatus,
        isStreaming: false,
        pendingAskUserQuestion: null,
        _streamingText: "",
        _currentTurnId: null,
        _lastHandledSeq: undefined,
        _activePlanMsgId: null,
        _messageBuffer: {},
        _streamingMetrics: {
          startedAt: null,
          turnId: null,
          totalTokens: 0,
          hasTokenUsage: false,
        },
      });

      if (attempts < maxAttempts && !hidden) {
        const delay = Math.min(1000 * Math.pow(2, attempts), 30000);
        set({ _reconnectAttempts: attempts + 1, wsStatus: "reconnecting" });
        (window as Window & { __niniReconnectTimer?: number }).__niniReconnectTimer =
          window.setTimeout(() => {
            delete (window as Window & { __niniReconnectTimer?: number }).__niniReconnectTimer;
            get().connect();
          }, delay);
      }
    };

    ws.onerror = () => {
      // onclose 会紧随触发
    };

    ws.onmessage = (event) => {
      try {
        const evt: WSEvent = JSON.parse(event.data);
        if (evt.type === "pong") return;
        handleEvent(evt, set, get);
      } catch {
        // 忽略非法消息
      }
    };

    set({ ws });
  },

  disconnect() {
    const reconnectTimer = (
      window as Window & { __niniReconnectTimer?: number }
    ).__niniReconnectTimer;
    if (reconnectTimer) {
      window.clearTimeout(reconnectTimer);
      delete (window as Window & { __niniReconnectTimer?: number }).__niniReconnectTimer;
    }
    const ws = get().ws;
    if (ws) {
      const pingInterval = (ws as WebSocket & { _pingInterval?: number })._pingInterval;
      if (pingInterval) window.clearInterval(pingInterval);
      ws.onclose = null;
      ws.close();
    }
    set({
      ws: null,
      wsConnected: false,
      wsStatus: "disconnected",
      _reconnectAttempts: 0,
      isStreaming: false,
      pendingAskUserQuestion: null,
      _streamingText: "",
      _currentTurnId: null,
      _lastHandledSeq: undefined,
      _activePlanMsgId: null,
      _messageBuffer: {},
      _streamingMetrics: {
        startedAt: null,
        turnId: null,
        totalTokens: 0,
        hasTokenUsage: false,
      },
    });
  },

  // ============================================================================
  // 会话操作
  // ============================================================================

  async initApp() {
    await get().fetchSessions();
    await get().fetchSkills();

    const handleModelConfigUpdated = () => {
      void get().fetchActiveModel();
      void get().fetchModelProviders();
    };
    window.removeEventListener("nini:model-config-updated", handleModelConfigUpdated);
    window.addEventListener("nini:model-config-updated", handleModelConfigUpdated);

    const savedSessionId = localStorage.getItem("nini_last_session_id");
    const { sessions } = get();

    if (savedSessionId) {
      const sessionExists = sessions.some((s) => s.id === savedSessionId);
      if (sessionExists) {
        await get().switchSession(savedSessionId);
        return;
      }
    }

    if (sessions.length > 0) {
      await get().switchSession(sessions[0].id);
    }
  },

  async sendMessage(content: string) {
    const { ws, sessionId, pendingAskUserQuestion } = get();
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    if (pendingAskUserQuestion) return;

    const userMsg: Message = {
      id: nextId(),
      role: "user",
      content,
      timestamp: Date.now(),
    };
    set((s) => ({ messages: [...s.messages, userMsg] }));

    try {
      await get().analyzeIntent(content);
    } catch (e) {
      console.error("分析意图失败:", e);
    }

    ws.send(
      JSON.stringify({
        type: "chat",
        content,
        session_id: sessionId,
      })
    );

    set({
      isStreaming: true,
      composerDraft: "",
      pendingAskUserQuestion: null,
      _streamingText: "",
      _analysisPlanOrder: 0,
      analysisPlanProgress: null,
      _activePlanTaskIds: [],
      _planActionTaskMap: {},
      _messageBuffer: {},
      _streamingMetrics: {
        startedAt: Date.now(),
        turnId: null,
        totalTokens: 0,
        hasTokenUsage: false,
      },
    });
  },

  submitAskUserQuestionAnswers(answers: Record<string, string>) {
    const { ws, sessionId, pendingAskUserQuestion } = get();
    if (!pendingAskUserQuestion) return;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;

    const normalizedAnswers: Record<string, string> = {};
    for (const [rawKey, rawValue] of Object.entries(answers)) {
      const key = rawKey.trim();
      if (!key) continue;
      const value = String(rawValue ?? "").trim();
      normalizedAnswers[key] = value;
    }
    if (Object.keys(normalizedAnswers).length === 0) return;

    ws.send(
      JSON.stringify({
        type: "ask_user_question_answer",
        session_id: sessionId,
        tool_call_id: pendingAskUserQuestion.toolCallId,
        answers: normalizedAnswers,
      })
    );
    set({ pendingAskUserQuestion: null });
  },

  stopStreaming() {
    const { ws, isStreaming, sessionId } = get();
    if (!isStreaming) return;

    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(
        JSON.stringify({
          type: "stop",
          session_id: sessionId,
        })
      );
    }

    set({
      isStreaming: false,
      pendingAskUserQuestion: null,
      _streamingText: "",
      _currentTurnId: null,
      _lastHandledSeq: undefined,
      _activePlanMsgId: null,
      _activePlanTaskIds: [],
      _planActionTaskMap: {},
      _messageBuffer: {},
      _streamingMetrics: {
        startedAt: null,
        turnId: null,
        totalTokens: 0,
        hasTokenUsage: false,
      },
    });
  },

  async retryLastTurn() {
    const { ws, sessionId, messages, isStreaming } = get();
    if (isStreaming) return;
    if (!sessionId || !ws || ws.readyState !== WebSocket.OPEN) return;

    const latestTurn = findLatestTurnSpan(messages);
    if (!latestTurn || latestTurn.userIndex < 0) return;

    const retryContent = messages[latestTurn.userIndex].content.trim();
    if (!retryContent) return;

    const trimmedMessages = latestTurn.turnId
      ? messages.filter(
          (msg, index) =>
            index <= latestTurn.userIndex || msg.turnId !== latestTurn.turnId,
        )
      : messages.slice(0, latestTurn.userIndex + 1);
    set({
      messages: trimmedMessages,
      isStreaming: true,
      currentIntentAnalysis: null,
      intentAnalysisLoading: false,
      pendingAskUserQuestion: null,
      _streamingText: "",
      _currentTurnId: null,
      _activePlanMsgId: null,
      _analysisPlanOrder: 0,
      analysisPlanProgress: null,
      _activePlanTaskIds: [],
      _planActionTaskMap: {},
      _messageBuffer: {},
      _streamingMetrics: {
        startedAt: Date.now(),
        turnId: null,
        totalTokens: 0,
        hasTokenUsage: false,
      },
    });

    try {
      await get().analyzeIntent(retryContent);
    } catch (e) {
      console.error("重试前分析意图失败:", e);
    }

    ws.send(
      JSON.stringify({
        type: "retry",
        session_id: sessionId,
        content: retryContent,
      })
    );
  },

  setComposerDraft(value: string) {
    set({ composerDraft: value });
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
        const datasetName = typeof dataset.name === "string" ? dataset.name : file.name;
        const rowCount = typeof dataset.row_count === "number" ? dataset.row_count : 0;
        const columnCount = typeof dataset.column_count === "number" ? dataset.column_count : 0;
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
        throw new Error(typeof payload.error === "string" ? payload.error : "上传失败");
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
      ...SESSION_RESET_STATE,
      messages: [],
      sessionId: null,
      datasets: [],
      workspaceFiles: [],
    });
  },

  // ============================================================================
  // 数据获取操作
  // ============================================================================

  async fetchSessions() {
    const sessions = await api.fetchSessions();
    set({ sessions });
  },

  async fetchDatasets() {
    const datasets = await api.fetchDatasets(get().sessionId ?? "");
    set({ datasets });
  },

  async fetchWorkspaceFiles() {
    const files = await api.fetchWorkspaceFiles(get().sessionId ?? "");
    set({ workspaceFiles: files });
  },

  async fetchSkills() {
    const skills = await api.fetchSkills();
    set({ skills });
  },

  async fetchCapabilities() {
    const capabilities = await api.fetchCapabilities();
    set({ capabilities });
  },

  async analyzeIntent(content: string) {
    set({ intentAnalysisLoading: true });
    const result = await api.analyzeIntent(content);
    set({
      currentIntentAnalysis: result,
      intentAnalysisLoading: false,
    });
  },

  // ============================================================================
  // 技能管理操作
  // ============================================================================

  async uploadSkillFile(file: File) {
    const result = await api.uploadSkillFile(file);
    if (result.success) await get().fetchSkills();
    return result;
  },

  async getSkillDetail(skillName: string) {
    return api.getSkillDetail(skillName);
  },

  async updateSkill(skillName: string, payload: { description: string; category: string; content: string }) {
    const result = await api.updateSkill(skillName, payload);
    if (result.success) await get().fetchSkills();
    return result;
  },

  async toggleSkillEnabled(skillName: string, enabled: boolean) {
    const result = await api.toggleSkillEnabled(skillName, enabled);
    if (result.success) await get().fetchSkills();
    return result;
  },

  async deleteSkill(skillName: string) {
    const result = await api.deleteSkill(skillName);
    if (result.success) await get().fetchSkills();
    return result;
  },

  async listSkillFiles(skillName: string) {
    return api.listSkillFiles(skillName);
  },

  async getSkillFileContent(skillName: string, path: string) {
    return api.getSkillFileContent(skillName, path);
  },

  async saveSkillFileContent(skillName: string, path: string, content: string) {
    return api.saveSkillFileContent(skillName, path, content);
  },

  async uploadSkillAttachment(skillName: string, file: File, dirPath?: string, overwrite?: boolean) {
    return api.uploadSkillAttachment(skillName, file, dirPath, overwrite);
  },

  async createSkillDir(skillName: string, path: string) {
    return api.createSkillDir(skillName, path);
  },

  async deleteSkillPath(skillName: string, path: string) {
    return api.deleteSkillPath(skillName, path);
  },

  async downloadSkillBundle(skillName: string) {
    return api.downloadSkillBundle(skillName);
  },

  // ============================================================================
  // 数据集操作
  // ============================================================================

  async loadDataset(datasetId: string) {
    const success = await api.loadDataset(get().sessionId ?? "", datasetId);
    if (success) {
      await get().fetchDatasets();
      await get().fetchWorkspaceFiles();
    }
  },

  // ============================================================================
  // 会话管理操作
  // ============================================================================

  async compressCurrentSession() {
    const result = await api.compressCurrentSession(get().sessionId ?? "");
    if (result.success && result.archivedCount && result.archivedCount > 0) {
      await get().switchSession(get().sessionId ?? "");
    }
    return result;
  },

  async createNewSession() {
    const newSessionId = await api.createNewSession();
    if (newSessionId) {
      await get().fetchSessions();
      await get().switchSession(newSessionId);
    }
  },

  async switchSession(targetSessionId: string) {
    const result = await api.switchSession(targetSessionId);
    if (!result.success) return;

    const rawMessages = result.messages || [];
    const restored = api.buildSessionRestoreState(
      rawMessages as RawSessionMessage[],
    );

    set({
      sessionId: targetSessionId,
      ...SESSION_RESET_STATE,
      messages: restored.messages,
      analysisTasks: restored.analysisTasks,
      analysisPlanProgress: restored.analysisPlanProgress,
      workspacePanelTab:
        restored.analysisPlanProgress || restored.analysisTasks.length > 0
          ? "tasks"
          : "files",
    });
    localStorage.setItem("nini_last_session_id", targetSessionId);

    await get().fetchDatasets();
    await get().fetchWorkspaceFiles();
    await get().fetchCodeExecutions();
    await get().fetchFolders();
  },

  async deleteSession(targetSessionId: string) {
    const success = await api.deleteSession(targetSessionId);
    if (!success) return;

    const { sessionId } = get();
    await get().fetchSessions();

    if (sessionId === targetSessionId) {
      const { sessions } = get();
      if (sessions.length > 0) {
        await get().switchSession(sessions[0].id);
      } else {
        get().clearMessages();
      }
    }
  },

  async updateSessionTitle(targetSessionId: string, title: string) {
    const success = await api.updateSessionTitle(targetSessionId, title);
    if (!success) return;

    set((s) => ({
      sessions: s.sessions.map((sess) =>
        sess.id === targetSessionId ? { ...sess, title } : sess
      ),
    }));
  },

  // ============================================================================
  // 记忆文件操作
  // ============================================================================

  async fetchMemoryFiles() {
    const files = await api.fetchMemoryFiles(get().sessionId ?? "");
    set({ memoryFiles: files });
  },

  // ============================================================================
  // 模型配置操作
  // ============================================================================

  async fetchActiveModel() {
    const model = await api.fetchActiveModel();
    set({ activeModel: model });
  },

  async setPreferredProvider(providerId: string) {
    const result = await api.setPreferredProvider(providerId);
    if (result) {
      await get().fetchActiveModel();
      await get().fetchModelProviders();
    }
  },

  async setChatRoute(providerId: string, model: string | null) {
    const success = await api.setChatRoute(providerId, model);
    if (success) {
      await get().fetchActiveModel();
    }
  },

  async fetchModelProviders() {
    set({ modelProvidersLoading: true });
    const providers = await api.fetchModelProviders();
    set({ modelProviders: providers, modelProvidersLoading: false });
  },

  // ============================================================================
  // 工作区面板操作
  // ============================================================================

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
      const nextTasks = s.analysisTasks.filter((t) => t.id !== taskId);
      const nextActionMap = Object.fromEntries(
        Object.entries(s._planActionTaskMap).filter(([, mappedTaskId]) => mappedTaskId !== taskId)
      );
      return {
        analysisTasks: nextTasks,
        _activePlanTaskIds: s._activePlanTaskIds.map((id) => (id === taskId ? null : id)),
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

  async deleteWorkspaceFile(filePath: string) {
    const success = await api.deleteWorkspaceFile(get().sessionId ?? "", filePath);
    if (success) {
      await get().fetchWorkspaceFiles();
      await get().fetchDatasets();
    }
  },

  async renameWorkspaceFile(filePath: string, newName: string) {
    const success = await api.renameWorkspaceFile(get().sessionId ?? "", filePath, newName);
    if (success) await get().fetchWorkspaceFiles();
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
    const executions = await api.fetchCodeExecutions(get().sessionId ?? "");
    set({ codeExecutions: executions });
  },

  async fetchFolders() {
    const folders = await api.fetchFolders(get().sessionId ?? "");
    set({ workspaceFolders: folders });
  },

  async createFolder(name: string, parent?: string | null) {
    const success = await api.createFolder(get().sessionId ?? "", name, parent);
    if (success) await get().fetchFolders();
  },

  async moveFileToFolder(filePath: string, folderId: string | null) {
    const success = await api.moveFileToFolder(get().sessionId ?? "", filePath, folderId);
    if (success) {
      await get().fetchWorkspaceFiles();
      await get().fetchFolders();
    }
  },

  async createWorkspaceFile(filename: string, content?: string) {
    const success = await api.createWorkspaceFile(get().sessionId ?? "", filename, content);
    if (success) await get().fetchWorkspaceFiles();
  },

  // ============================================================================
  // ResearchProfile 操作
  // ============================================================================

  async fetchResearchProfile() {
    set({ researchProfileLoading: true });
    const profile = await api.fetchResearchProfile();
    set({ researchProfile: profile, researchProfileLoading: false });
  },

  async updateResearchProfile(updates: Partial<ResearchProfile>) {
    const result = await api.updateResearchProfile(updates);
    if (result) {
      await get().fetchResearchProfile();
      return true;
    }
    return false;
  },

  // ============================================================================
  // 成本透明化操作
  // ============================================================================

  async fetchTokenUsage(sessionId: string) {
    const usage = await api.fetchTokenUsage(sessionId);
    if (usage) set({ tokenUsage: usage });
  },

  async fetchCostHistory() {
    const { sessions, aggregate } = await api.fetchCostHistory();
    set({ costHistory: sessions, aggregateCost: aggregate });
  },

  async fetchPricingConfig() {
    const config = await api.fetchPricingConfig();
    set({ pricingConfig: config });
  },

  toggleCostPanel() {
    set((s) => ({ costPanelOpen: !s.costPanelOpen }));
  },

  setCostPanelOpen(open: boolean) {
    set({ costPanelOpen: open });
  },

  // ============================================================================
  // 用户展示偏好操作
  // ============================================================================

  setDisplayPreference(mode: DisplayPreference) {
    // 持久化到 localStorage（含错误处理）
    if (typeof window !== "undefined") {
      try {
        localStorage.setItem("nini_display_preference", mode);
      } catch (e) {
        // localStorage 被禁用或已满，仅更新内存状态
        console.warn("无法保存展示偏好到 localStorage:", e);
      }
    }
    set({ displayPreference: mode });
  },
}));

// ============================================================================
// 选择性导出（保持向后兼容）
// ============================================================================

export {
  // 工具函数
  isRecord,
  nextId,
  nextAnalysisTaskId,
  nextAnalysisAttemptId,
  getWsUrl,
  inferMemoryFileType,
  normalizeMemoryTimestamp,
  mergeReasoningContent,
  clampStepIndex,
  inferCurrentStepIndex,
  makePlanProgressFromSteps,
  areAllPlanStepsDone,
  updateAnalysisTaskById,
  updateAnalysisTaskWithAttempt,
  applyPlanStepUpdateToProgress,
  applyPlanProgressPayload,
  uploadWithProgress,
  // 消息缓冲区辅助函数
  updateMessageBuffer,
  getMessageBufferContent,
  completeMessageBuffer,
  cleanupMessageBuffer,
  hasMessageBuffer,
  // 规范化函数
  normalizeIntentOption,
  normalizeIntentCandidate,
  normalizeIntentSkillCall,
  normalizeIntentSkillSummary,
  normalizeIntentAnalysis,
  normalizePlanStepStatus,
  normalizeTaskAttemptStatus,
  stripReasoningMarkers,
  isTerminalPlanStepStatus,
  mergePlanStepStatus,
  truncatePlanText,
  createDefaultPlanSteps,
  normalizeAnalysisSteps,
  // 计划状态机
  deriveNextHint,
  // 事件处理器
  handleEvent,
};

export { api };
export default useStore;
