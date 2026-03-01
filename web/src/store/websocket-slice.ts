/**
 * WebSocket Slice
 *
 * 管理 WebSocket 连接、心跳、重连和消息发送
 */

import type { StateCreator } from "zustand";
import type {
  WSEvent,
  Message,
  PendingAskUserQuestion,
  AnalysisPlanProgress,
  AnalysisTaskItem,
} from "./types";
import { getWsUrl, nextId } from "./utils";

// ---- 事件处理导入 ----
// 注意：event-handler 在 store.ts 中定义，这里通过回调方式处理事件
// 避免循环依赖

export interface WebSocketSlice {
  // State
  ws: WebSocket | null;
  wsConnected: boolean;
  isStreaming: boolean;
  _reconnectAttempts: number;
  _currentTurnId: string | null;
  _streamingText: string;

  // Actions
  connect: (_sessionId: string | null) => void;
  disconnect: () => void;
  stopStreaming: () => void;
  sendMessage: (content: string) => Promise<void>;
  submitAskUserQuestionAnswers: (answers: Record<string, string>) => void;
  retryLastTurn: () => Promise<void>;
}

// 辅助类型：扩展 WebSocket 以存储心跳定时器
interface WebSocketWithHeartbeat extends WebSocket {
  _pingInterval?: number;
}

// 创建 WebSocket slice 的工厂函数
// 需要传入依赖的其他 slice 方法
export interface WebSocketSliceDependencies {
  sessionId: string | null;
  messages: Message[];
  pendingAskUserQuestion: PendingAskUserQuestion | null;
  analysisPlanProgress: AnalysisPlanProgress | null;
  analysisTasks: AnalysisTaskItem[];
  _activePlanMsgId: string | null;
  _activePlanTaskIds: Array<string | null>;
  _planActionTaskMap: Record<string, string>;
  _analysisPlanOrder: number;
  composerDraft: string;

  // 需要调用的其他 actions
  setComposerDraft: (value: string) => void;
  analyzeIntent: (content: string) => Promise<void>;
  fetchSessions: () => Promise<void>;
  fetchDatasets: () => Promise<void>;
  fetchWorkspaceFiles: () => Promise<void>;
  fetchSkills: () => Promise<void>;

  // 事件处理回调
  onWSEvent: (evt: WSEvent) => void;
}

export const createWebSocketSlice: StateCreator<
  WebSocketSlice & WebSocketSliceDependencies,
  [],
  [],
  WebSocketSlice
> = (set, get) => ({
  // ---- State ----
  ws: null,
  wsConnected: false,
  isStreaming: false,
  _reconnectAttempts: 0,
  _currentTurnId: null,
  _streamingText: "",

  // ---- Actions ----

  connect(_sessionId: string | null) {
    const existing = get().ws;
    if (existing && existing.readyState === WebSocket.OPEN) return;
    if (existing && existing.readyState === WebSocket.CONNECTING) return;

    // 页面不可见时不主动连接
    if (typeof document !== "undefined" && document.hidden) return;

    const ws: WebSocketWithHeartbeat = new WebSocket(getWsUrl());
    let heartbeatTimer: number | undefined;

    ws.onopen = () => {
      set({ wsConnected: true, _reconnectAttempts: 0 });

      // 启动心跳检测 - 15秒间隔，保持连接活跃
      heartbeatTimer = window.setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "ping" }));
        } else {
          window.clearInterval(heartbeatTimer);
        }
      }, 15000);

      // 存储心跳定时器引用以便清理
      ws._pingInterval = heartbeatTimer;
    };

    ws.onclose = () => {
      if (heartbeatTimer) clearInterval(heartbeatTimer);

      const attempts = get()._reconnectAttempts;
      const maxAttempts = 10;

      set({
        ws: null,
        wsConnected: false,
        isStreaming: false,
        pendingAskUserQuestion: null,
        _streamingText: "",
        _currentTurnId: null,
        _activePlanMsgId: null,
      });

      // 指数退避重连：1s, 2s, 4s, 8s, 16s, 30s(max)
      if (attempts < maxAttempts && !document.hidden) {
        const delay = Math.min(1000 * Math.pow(2, attempts), 30000);
        set({ _reconnectAttempts: attempts + 1 });
        // 使用当前 store 中的 sessionId，而不是闭包中捕获的旧值
        setTimeout(() => get().connect(get().sessionId), delay);
      }
    };

    ws.onerror = () => {
      // onclose 会紧随触发，错误处理在 onclose 中完成
    };

    ws.onmessage = (event) => {
      try {
        const evt: WSEvent = JSON.parse(event.data);
        // 忽略 pong 消息
        if (evt.type === "pong") return;
        // 调用外部传入的事件处理器
        get().onWSEvent(evt);
      } catch {
        // 忽略非法消息
      }
    };

    set({ ws });
  },

  disconnect() {
    const ws = get().ws as WebSocketWithHeartbeat | null;
    if (ws) {
      // 清除心跳
      if (ws._pingInterval) {
        window.clearInterval(ws._pingInterval);
      }
      // 避免触发自动重连
      ws.onclose = null;
      ws.close();
    }
    set({
      ws: null,
      wsConnected: false,
      _reconnectAttempts: 0,
      isStreaming: false,
      pendingAskUserQuestion: null,
      _streamingText: "",
      _currentTurnId: null,
      _activePlanMsgId: null,
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
      pendingAskUserQuestion: null,
      _streamingText: "",
      _currentTurnId: null,
      _activePlanMsgId: null,
      _activePlanTaskIds: [],
      _planActionTaskMap: {},
    });
  },

  async sendMessage(content: string) {
    const { ws, sessionId, pendingAskUserQuestion } = get();
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    if (pendingAskUserQuestion) return;

    // 添加用户消息
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
      composerDraft: "",
      pendingAskUserQuestion: null,
      _streamingText: "",
      _analysisPlanOrder: 0,
      analysisPlanProgress: null,
      analysisTasks: [],
      _activePlanTaskIds: [],
      _planActionTaskMap: {},
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
      }),
    );
    set({ pendingAskUserQuestion: null });
  },

  async retryLastTurn() {
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
      pendingAskUserQuestion: null,
      _streamingText: "",
      _currentTurnId: null,
      _activePlanMsgId: null,
      _analysisPlanOrder: 0,
      analysisPlanProgress: null,
      analysisTasks: [],
      _activePlanTaskIds: [],
      _planActionTaskMap: {},
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
      }),
    );
  },
});

// ---- 页面可见性变化处理 ----

let visibilityHandlerInstalled = false;

/**
 * 安装页面可见性变化处理器
 * 当页面重新可见时自动重连 WebSocket
 */
export function installVisibilityHandler(
  connect: (_sessionId: string | null) => void,
  _disconnect: () => void,
  getSessionId: () => string | null,
): void {
  if (visibilityHandlerInstalled) return;
  visibilityHandlerInstalled = true;

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      // 页面隐藏时断开连接（可选，取决于业务需求）
      // 当前实现保持连接以便后台接收消息
    } else {
      // 页面重新可见时检查连接状态
      connect(getSessionId());
    }
  });
}

/**
 * 卸载页面可见性变化处理器
 */
export function uninstallVisibilityHandler(): void {
  visibilityHandlerInstalled = false;
}
