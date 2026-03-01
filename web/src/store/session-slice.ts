/**
 * Session Slice - Zustand slice for session management
 *
 * Extracted from store.ts as part of Nini 2.0 architecture refactoring
 */
import type { StateCreator } from "zustand";
import type {
  SessionItem,
  Message,
  DatasetItem,
  WorkspaceFile,
  SkillItem,
  CapabilityItem,
  MemoryFile,
  CodeExecution,
  WorkspaceFolder,
  AnalysisTaskItem,
  RawSessionMessage,
  AnalysisPlanProgress,
} from "./types";
import { isRecord, nextId } from "./utils";
import { buildMessagesFromHistory } from "./api-actions";

// ---- Session Reset State ----
// Common state fields to reset when switching/clearing sessions
const SESSION_RESET_STATE = {
  pendingAskUserQuestion: null as null,
  contextCompressionTick: 0,
  previewTabs: [] as string[],
  previewFileId: null as string | null,
  _streamingText: "",
  isStreaming: false,
  _activePlanMsgId: null as string | null,
  _analysisPlanOrder: 0,
  analysisPlanProgress: null as AnalysisPlanProgress | null,
  _activePlanTaskIds: [] as (string | null)[],
  _planActionTaskMap: {} as Record<string, string>,
  analysisTasks: [] as AnalysisTaskItem[],
  currentIntentAnalysis: null as null,
  intentAnalysisLoading: false,
  composerDraft: "",
};

// ---- Session Slice Interface ----

export interface SessionSlice {
  // State
  sessionId: string | null;
  sessions: SessionItem[];
  messages: Message[];
  datasets: DatasetItem[];
  workspaceFiles: WorkspaceFile[];
  skills: SkillItem[];
  capabilities: CapabilityItem[];
  memoryFiles: MemoryFile[];
  codeExecutions: CodeExecution[];
  workspaceFolders: WorkspaceFolder[];
  analysisTasks: AnalysisTaskItem[];
  contextCompressionTick: number;
  composerDraft: string;

  // Workspace panel state (related to session)
  workspacePanelOpen: boolean;
  workspacePanelTab: "files" | "executions" | "tasks";
  fileSearchQuery: string;
  previewTabs: string[];
  previewFileId: string | null;

  // Internal state (needed for session operations)
  _streamingText: string;
  isStreaming: boolean;
  pendingAskUserQuestion: null;
  _activePlanMsgId: string | null;
  _analysisPlanOrder: number;
  analysisPlanProgress: AnalysisPlanProgress | null;
  _activePlanTaskIds: (string | null)[];
  _planActionTaskMap: Record<string, string>;
  currentIntentAnalysis: null;
  intentAnalysisLoading: boolean;
  _currentTurnId: string | null;

  // Upload state
  isUploading: boolean;
  uploadProgress: number;
  uploadingFileName: string | null;

  // Actions
  initApp: () => Promise<void>;
  clearMessages: () => void;
  setComposerDraft: (value: string) => void;
  createNewSession: () => Promise<void>;
  switchSession: (sessionId: string) => Promise<void>;
  deleteSession: (sessionId: string) => Promise<void>;
  updateSessionTitle: (sessionId: string, title: string) => Promise<void>;
  uploadFile: (file: File) => Promise<void>;
  compressCurrentSession: () => Promise<{ success: boolean; message: string }>;

  // Workspace panel actions
  toggleWorkspacePanel: () => void;
  setWorkspacePanelTab: (tab: "files" | "executions" | "tasks") => void;
  setFileSearchQuery: (query: string) => void;
  deleteAnalysisTask: (taskId: string) => void;
  clearAnalysisTasks: () => void;
  openPreview: (fileId: string) => void;
  setActivePreview: (fileId: string | null) => void;
  closePreview: (fileId?: string) => void;

  // Data fetching actions (used by session management)
  fetchSessions: () => Promise<void>;
  fetchSkills: () => Promise<void>;
  fetchDatasets: () => Promise<void>;
  fetchWorkspaceFiles: () => Promise<void>;
  fetchCodeExecutions: () => Promise<void>;
  fetchFolders: () => Promise<void>;
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

// ---- Session Slice Creator ----

export const createSessionSlice: StateCreator<SessionSlice> = (set, get) => ({
  // Initial state
  sessionId: null,
  sessions: [],
  messages: [],
  datasets: [],
  workspaceFiles: [],
  skills: [],
  capabilities: [],
  memoryFiles: [],
  codeExecutions: [],
  workspaceFolders: [],
  analysisTasks: [],
  contextCompressionTick: 0,
  composerDraft: "",

  // Workspace panel state
  workspacePanelOpen: false,
  workspacePanelTab: "files",
  fileSearchQuery: "",
  previewTabs: [],
  previewFileId: null,

  // Internal state
  _streamingText: "",
  isStreaming: false,
  pendingAskUserQuestion: null,
  _activePlanMsgId: null,
  _analysisPlanOrder: 0,
  analysisPlanProgress: null,
  _activePlanTaskIds: [],
  _planActionTaskMap: {},
  currentIntentAnalysis: null,
  intentAnalysisLoading: false,
  _currentTurnId: null,

  // Upload state
  isUploading: false,
  uploadProgress: 0,
  uploadingFileName: null,

  // ---- Actions ----

  async initApp() {
    // 1. Fetch session list and skills
    await get().fetchSessions();
    await get().fetchSkills();

    // Register global model config update listener
    const handleModelConfigUpdated = () => {
      // These will be handled by the model slice in the future
      // For now, we just log the event
      console.log("Model config updated");
    };
    window.removeEventListener(
      "nini:model-config-updated",
      handleModelConfigUpdated,
    );
    window.addEventListener(
      "nini:model-config-updated",
      handleModelConfigUpdated,
    );

    // 2. Try to restore last used session
    const savedSessionId = localStorage.getItem("nini_last_session_id");
    const { sessions } = get();

    if (savedSessionId) {
      // Check if saved session still exists
      const sessionExists = sessions.some((s) => s.id === savedSessionId);
      if (sessionExists) {
        await get().switchSession(savedSessionId);
        return;
      }
    }

    // 3. If no saved session or session doesn't exist, switch to most recent
    if (sessions.length > 0) {
      // Sessions are sorted by time desc, first is most recent
      await get().switchSession(sessions[0].id);
    }
    // 4. If no existing sessions, keep empty state, wait for user to create
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

  setComposerDraft(value: string) {
    set({ composerDraft: value });
  },

  async createNewSession() {
    // Prevent duplicate: if there's already an unused empty session, switch to it
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
      // Switch to new session, clear current messages
      set({
        ...SESSION_RESET_STATE,
        sessionId: newSessionId,
        messages: [],
        datasets: [],
        workspaceFiles: [],
      });
      // Clear saved session_id (new session doesn't need restore)
      localStorage.removeItem("nini_last_session_id");
      // Refresh session list
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
        // Session exists but no messages, switch to empty session
        set({
          ...SESSION_RESET_STATE,
          sessionId: targetSessionId,
          messages: [],
        });
        await get().fetchDatasets();
        await get().fetchWorkspaceFiles();
        return;
      }

      const data = isRecord(payload.data) ? payload.data : null;
      const rawMessages =
        isRecord(data) && Array.isArray(data.messages) ? data.messages : [];

      // Convert backend message format to frontend Message format
      const messages = buildMessagesFromHistory(
        rawMessages as RawSessionMessage[],
      );

      set({
        ...SESSION_RESET_STATE,
        sessionId: targetSessionId,
        messages,
      });
      // Save current session ID to localStorage
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
      // If deleting current session, clear state
      if (targetSessionId === sessionId) {
        set({
          ...SESSION_RESET_STATE,
          sessionId: null,
          messages: [],
          datasets: [],
          workspaceFiles: [],
        });
      }
      // Refresh session list
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
      // Update local state
      set((s) => ({
        sessions: s.sessions.map((sess) =>
          sess.id === targetSessionId ? { ...sess, title } : sess,
        ),
      }));
    } catch (e) {
      console.error("更新会话标题失败:", e);
    }
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
        // Notify user of successful upload
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

      // Refresh current message list after compression
      await get().switchSession(sid);
      set((s) => ({ contextCompressionTick: s.contextCompressionTick + 1 }));
      return { success: true, message };
    } catch (e) {
      console.error("压缩会话失败:", e);
      return { success: false, message: "压缩会话失败，请稍后重试" };
    }
  },

  // ---- Workspace Panel Actions ----

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
        Object.entries(s._planActionTaskMap).filter(
          ([, mappedTaskId]) => mappedTaskId !== taskId,
        ),
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

  // ---- Data Fetching Actions ----

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

  async fetchSkills() {
    try {
      const [skillsResp, toolsResp] = await Promise.all([
        fetch("/api/skills"),
        fetch("/api/tools"),
      ]);
      const [skillsPayload, toolsPayload] = await Promise.all([
        skillsResp.json(),
        toolsResp.json(),
      ]);

      const skillsData = isRecord(skillsPayload.data)
        ? skillsPayload.data
        : null;
      const toolsData = isRecord(toolsPayload.data) ? toolsPayload.data : null;

      const markdownSkills =
        skillsData && Array.isArray(skillsData.skills)
          ? skillsData.skills
          : [];
      const functionTools =
        toolsData && Array.isArray(toolsData.tools) ? toolsData.tools : [];

      set({
        skills: [
          ...(functionTools as SkillItem[]),
          ...(markdownSkills as SkillItem[]),
        ],
      });
    } catch (e) {
      console.error("获取技能列表失败:", e);
    }
  },

  async fetchDatasets() {
    const sid = get().sessionId;
    if (!sid) {
      set({ datasets: [] });
      return;
    }
    try {
      const resp = await fetch(`/api/datasets/${sid}`);
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
      const resp = await fetch(`/api/workspace/${sid}/files`);
      const payload = await resp.json();
      const data = isRecord(payload.data) ? payload.data : null;
      const files = data && Array.isArray(data.files) ? data.files : [];
      set({ workspaceFiles: files as WorkspaceFile[] });
    } catch (e) {
      console.error("获取工作空间文件失败:", e);
    }
  },

  async fetchCodeExecutions() {
    const sid = get().sessionId;
    if (!sid) {
      set({ codeExecutions: [] });
      return;
    }
    try {
      const resp = await fetch(`/api/workspace/${sid}/executions`);
      const payload = await resp.json();
      const data = isRecord(payload.data) ? payload.data : null;
      const executions =
        data && Array.isArray(data.executions) ? data.executions : [];
      set({ codeExecutions: executions as CodeExecution[] });
    } catch (e) {
      console.error("获取执行历史失败:", e);
    }
  },

  async fetchFolders() {
    const sid = get().sessionId;
    if (!sid) {
      set({ workspaceFolders: [] });
      return;
    }
    try {
      const resp = await fetch(`/api/workspace/${sid}/folders`);
      const payload = await resp.json();
      const data = isRecord(payload.data) ? payload.data : null;
      const folders = data && Array.isArray(data.folders) ? data.folders : [];
      set({ workspaceFolders: folders as WorkspaceFolder[] });
    } catch (e) {
      console.error("获取文件夹失败:", e);
    }
  },
});

export { SESSION_RESET_STATE };
