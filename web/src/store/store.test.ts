import { afterAll, beforeEach, describe, expect, it, vi } from "vitest";

import type { Message } from "./types";
import { useStore } from "../store";

class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  static instances: MockWebSocket[] = [];

  readyState = MockWebSocket.CONNECTING;
  url: string;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  send(data: string) {
    this.sent.push(data);
  }

  close() {
    this.readyState = MockWebSocket.CLOSED;
  }

  triggerOpen() {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.();
  }
}

const initialState = useStore.getInitialState();
const originalWebSocket = globalThis.WebSocket;

function createMessage(
  overrides: Partial<Message>,
): Message {
  return {
    id: `msg-${Math.random()}`,
    role: "assistant",
    content: "",
    timestamp: Date.now(),
    ...overrides,
  };
}

describe("store reconnect / retry / stop", () => {
  beforeEach(() => {
    MockWebSocket.instances = [];
    Object.defineProperty(document, "hidden", {
      configurable: true,
      value: false,
    });
    globalThis.WebSocket = MockWebSocket as unknown as typeof WebSocket;
    useStore.setState(initialState, true);
    localStorage.clear();
  });

  it("重连成功后应清理旧 buffer 并重新拉取当前会话", async () => {
    const switchSession = vi.fn(async () => {});

    useStore.setState({
      ...useStore.getInitialState(),
      sessionId: "session-1",
      _reconnectAttempts: 1,
      _messageBuffer: {
        stale: {
          content: "旧内容",
          operation: "append",
          timestamp: Date.now(),
        },
      },
      switchSession,
    });

    useStore.getState().connect();
    const ws = MockWebSocket.instances[0];
    expect(ws).toBeDefined();

    ws.triggerOpen();
    await Promise.resolve();

    expect(useStore.getState()._messageBuffer).toEqual({});
    expect(switchSession).toHaveBeenCalledWith("session-1");
  });

  it("stopStreaming 应清理流式状态与消息缓冲区", () => {
    const ws = {
      readyState: MockWebSocket.OPEN,
      send: vi.fn(),
    } as unknown as WebSocket;

    useStore.setState({
      ...useStore.getInitialState(),
      ws,
      sessionId: "session-1",
      isStreaming: true,
      pendingAskUserQuestion: {
        toolCallId: "call-1",
        questions: [],
        createdAt: Date.now(),
      },
      _messageBuffer: {
        "turn-1-0": {
          content: "流式内容",
          operation: "append",
          timestamp: Date.now(),
        },
      },
      _currentTurnId: "turn-1",
      _streamingText: "流式内容",
    });

    useStore.getState().stopStreaming();

    expect((ws.send as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(
      JSON.stringify({
        type: "stop",
        session_id: "session-1",
      }),
    );
    expect(useStore.getState().isStreaming).toBe(false);
    expect(useStore.getState()._currentTurnId).toBeNull();
    expect(useStore.getState()._messageBuffer).toEqual({});
  });

  it("retryLastTurn 应按 turn_id 精确裁剪上一轮输出", async () => {
    const ws = {
      readyState: MockWebSocket.OPEN,
      send: vi.fn(),
    } as unknown as WebSocket;
    const analyzeIntent = vi.fn(async () => undefined);

    useStore.setState({
      ...useStore.getInitialState(),
      ws,
      sessionId: "session-1",
      analyzeIntent,
      messages: [
        createMessage({ id: "u1", role: "user", content: "第一问" }),
        createMessage({ id: "a1", role: "assistant", content: "第一答", turnId: "turn-1" }),
        createMessage({ id: "u2", role: "user", content: "第二问" }),
        createMessage({ id: "a2", role: "assistant", content: "第二答", turnId: "turn-2" }),
        createMessage({
          id: "r2",
          role: "assistant",
          content: "第二轮推理",
          turnId: "turn-2",
          isReasoning: true,
        }),
      ],
      _messageBuffer: {
        "turn-2-0": {
          content: "第二答",
          operation: "replace",
          timestamp: Date.now(),
        },
      },
    });

    await useStore.getState().retryLastTurn();

    expect(useStore.getState().messages.map((msg) => msg.id)).toEqual([
      "u1",
      "a1",
      "u2",
    ]);
    expect(analyzeIntent).toHaveBeenCalledWith("第二问");
    expect((ws.send as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(
      JSON.stringify({
        type: "retry",
        session_id: "session-1",
        content: "第二问",
      }),
    );
    expect(useStore.getState()._messageBuffer).toEqual({});
  });
});

afterAll(() => {
  globalThis.WebSocket = originalWebSocket;
});
