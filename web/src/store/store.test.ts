import { afterAll, beforeEach, describe, expect, it, vi } from "vitest";

import type { Message } from "./types";
import { useStore } from "../store";
import { clearAllSessionUiCacheEntries } from "./session-ui-cache";

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
  onclose: ((event: CloseEvent) => void) | null = null;
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

  triggerClose(code = 1000) {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({ code } as unknown as CloseEvent);
  }
}

const initialState = useStore.getInitialState();
const originalWebSocket = globalThis.WebSocket;
const originalFetch = globalThis.fetch;

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

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
    globalThis.fetch = vi.fn();
    useStore.setState(initialState, true);
    clearAllSessionUiCacheEntries();
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

  it("收到 4401 关闭码后应进入重新认证状态且不重连", async () => {
    useStore.setState({
      ...useStore.getInitialState(),
      apiKeyRequired: true,
      authReady: true,
      _reconnectAttempts: 3,
    });

    useStore.getState().connect();
    const ws = MockWebSocket.instances[0];
    expect(ws).toBeDefined();

    ws.triggerClose(4401);
    await Promise.resolve();

    expect(useStore.getState().authReady).toBe(false);
    expect(useStore.getState().authError).toContain("API Key");
    expect(useStore.getState().wsStatus).toBe("disconnected");
    expect(useStore.getState()._reconnectAttempts).toBe(0);
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
      pendingAskUserQuestionsBySession: {
        "session-1": {
          sessionId: "session-1",
          sessionTitle: "当前会话",
          toolCallId: "call-1",
          questions: [],
          questionCount: 0,
          createdAt: Date.now(),
          attentionRequestedAt: Date.now(),
        },
      },
      pendingAskUserQuestion: {
        sessionId: "session-1",
        sessionTitle: "当前会话",
        toolCallId: "call-1",
        questions: [],
        questionCount: 0,
        createdAt: Date.now(),
        attentionRequestedAt: Date.now(),
      },
      _messageBuffer: {
        "turn-1-0": {
          content: "流式内容",
          operation: "append",
          timestamp: Date.now(),
        },
      },
      _streamingMetrics: {
        startedAt: Date.now(),
        turnId: "turn-1",
        totalTokens: 820,
        hasTokenUsage: true,
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
    expect(useStore.getState()._streamingMetrics).toEqual({
      startedAt: null,
      turnId: null,
      totalTokens: 0,
      hasTokenUsage: false,
    });
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
      _streamingMetrics: {
        startedAt: 1,
        turnId: "old-turn",
        totalTokens: 999,
        hasTokenUsage: true,
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
    expect(useStore.getState()._streamingMetrics.turnId).toBeNull();
    expect(useStore.getState()._streamingMetrics.totalTokens).toBe(0);
    expect(useStore.getState()._streamingMetrics.hasTokenUsage).toBe(false);
    expect(useStore.getState()._streamingMetrics.startedAt).toBeTypeOf("number");
  });

  it("sendMessage 应初始化当前请求指标", async () => {
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
      _streamingMetrics: {
        startedAt: 1,
        turnId: "old-turn",
        totalTokens: 999,
        hasTokenUsage: true,
      },
    });

    await useStore.getState().sendMessage("请分析数据");

    expect(useStore.getState().isStreaming).toBe(true);
    expect(useStore.getState()._streamingMetrics.turnId).toBeNull();
    expect(useStore.getState()._streamingMetrics.totalTokens).toBe(0);
    expect(useStore.getState()._streamingMetrics.hasTokenUsage).toBe(false);
    expect(useStore.getState()._streamingMetrics.startedAt).toBeTypeOf("number");
  });

  it("switchSession 应恢复历史任务状态", async () => {
    const fetchMock = vi.mocked(globalThis.fetch);
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.endsWith("/api/sessions/session-restore/messages")) {
        return Promise.resolve({
          json: async () => ({
            success: true,
            data: {
              messages: [
                {
                  role: "assistant",
                  turn_id: "turn-restore",
                  _ts: "2026-03-04T10:00:00Z",
                  tool_calls: [
                    {
                      id: "call-init",
                      type: "function",
                      function: {
                        name: "task_write",
                        arguments: JSON.stringify({
                          mode: "init",
                          tasks: [
                            { id: 1, title: "检查数据质量", status: "pending" },
                            { id: 2, title: "执行相关性分析", status: "in_progress" },
                          ],
                        }),
                      },
                    },
                  ],
                },
              ],
            },
          }),
        } as Response);
      }
      return Promise.resolve({
        json: async () => ({ success: true, data: {} }),
        ok: true,
      } as Response);
    });

    await useStore.getState().switchSession("session-restore");

    expect(useStore.getState().analysisTasks).toHaveLength(2);
    expect(useStore.getState().analysisTasks[1]).toMatchObject({
      title: "执行相关性分析",
      status: "in_progress",
    });
    expect(useStore.getState().analysisPlanProgress).not.toBeNull();
    expect(useStore.getState().workspacePanelTab).toBe("tasks");
  });

  it("switchSession 应恢复 task_state 历史任务状态", async () => {
    const fetchMock = vi.mocked(globalThis.fetch);
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.endsWith("/api/sessions/session-task-state/messages")) {
        return Promise.resolve({
          json: async () => ({
            success: true,
            data: {
              messages: [
                {
                  role: "assistant",
                  turn_id: "turn-task-state",
                  _ts: "2026-03-04T10:00:00Z",
                  tool_calls: [
                    {
                      id: "call-init",
                      type: "function",
                      function: {
                        name: "task_state",
                        arguments: JSON.stringify({
                          operation: "init",
                          tasks: [
                            { id: 1, title: "检查数据质量", status: "pending" },
                            { id: 2, title: "执行相关性分析", status: "in_progress" },
                          ],
                        }),
                      },
                    },
                  ],
                },
              ],
            },
          }),
        } as Response);
      }
      return Promise.resolve({
        json: async () => ({ success: true, data: {} }),
        ok: true,
      } as Response);
    });

    await useStore.getState().switchSession("session-task-state");

    expect(useStore.getState().analysisTasks).toHaveLength(2);
    expect(useStore.getState().analysisTasks[1]).toMatchObject({
      title: "执行相关性分析",
      status: "in_progress",
    });
    expect(useStore.getState().analysisPlanProgress).not.toBeNull();
    expect(useStore.getState().workspacePanelTab).toBe("tasks");
  });

  it("switchSession 应恢复 agent 运行摘要而不依赖全量事件回放", async () => {
    const fetchMock = vi.mocked(globalThis.fetch);
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.endsWith("/api/sessions/session-agent-summary/messages")) {
        return Promise.resolve({
          json: async () => ({ success: true, data: { messages: [] } }),
        } as Response);
      }
      if (url.endsWith("/api/sessions/session-agent-summary")) {
        return Promise.resolve({
          json: async () => ({
            success: true,
            data: { id: "session-agent-summary", title: "Agent Summary", message_count: 0 },
          }),
        } as Response);
      }
      if (url.endsWith("/api/sessions/session-agent-summary/agent-runs")) {
        return Promise.resolve({
          json: async () => ({
            success: true,
            data: {
              runs: [
                {
                  run_id: "agent:turn-agent-summary:statistician:task1:1",
                  run_scope: "subagent",
                  parent_run_id: "root:turn-agent-summary",
                  agent_id: "statistician",
                  agent_name: "统计分析",
                  attempt: 1,
                  turn_id: "turn-agent-summary",
                  latest_phase: "tool_result",
                  status: "running",
                  task: "执行统计分析",
                  progress_message: "工具已返回结果",
                  updated_at: "2026-03-04T10:00:00Z",
                },
              ],
              event_count: 42,
            },
          }),
        } as Response);
      }
      if (url.endsWith("/api/sessions/session-agent-summary/dispatch-ledger")) {
        return Promise.resolve({
          json: async () => ({
            success: true,
            data: {
              ledgers: [
                {
                  run_id: "dispatch:call-agent-summary",
                  run_scope: "dispatch",
                  parent_run_id: "root:turn-agent-summary",
                  agent_id: "dispatch_agents",
                  agent_name: "任务派发",
                  attempt: 1,
                  turn_id: "turn-agent-summary",
                  latest_phase: "fused",
                  status: "completed",
                  progress_message: "执行汇总：成功 1 个，失败 0 个，停止 0 个",
                  dispatch_ledger: [
                    {
                      agent_id: "statistician",
                      agent_name: "统计分析",
                      task: "执行统计分析",
                      status: "success",
                      summary: "已完成分析",
                    },
                  ],
                },
              ],
            },
          }),
        } as Response);
      }
      return Promise.resolve({
        json: async () => ({ success: true, data: {} }),
        ok: true,
      } as Response);
    });

    await useStore.getState().switchSession("session-agent-summary");

    expect(useStore.getState().agentRunTabs).toContain(
      "agent:turn-agent-summary:statistician:task1:1",
    );
    expect(
      useStore.getState().agentRuns["agent:turn-agent-summary:statistician:task1:1"],
    ).toMatchObject({
      agentName: "统计分析",
      task: "执行统计分析",
      progressMessage: "工具已返回结果",
      eventsLoaded: false,
    });
    expect(useStore.getState().dispatchLedgers).toMatchObject([
      {
        run_id: "dispatch:call-agent-summary",
        agent_name: "任务派发",
      },
    ]);
  });

  it("fetchSessions 应同步拉取跨会话 dispatch ledger 聚合摘要", async () => {
    const fetchMock = vi.mocked(globalThis.fetch);
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.endsWith("/api/sessions")) {
        return Promise.resolve({
          json: async () => ({
            success: true,
            data: [
              {
                id: "session-risk",
                title: "风险会话",
                message_count: 3,
              },
            ],
          }),
        } as Response);
      }
      if (url.includes("/api/sessions/dispatch-ledger/aggregate")) {
        return Promise.resolve({
          json: async () => ({
            success: true,
            data: {
              total_session_count: 1,
              dispatch_session_count: 1,
              dispatch_run_count: 2,
              subtask_count: 4,
              success_count: 2,
              stopped_count: 1,
              preflight_failure_count: 0,
              routing_failure_count: 1,
              execution_failure_count: 1,
              failure_count: 2,
              returned_session_count: 1,
              sessions: [
                {
                  session_id: "session-risk",
                  title: "风险会话",
                  latest_run_id: "dispatch:risk:1",
                  dispatch_run_count: 2,
                  subtask_count: 4,
                  success_count: 2,
                  stopped_count: 1,
                  preflight_failure_count: 0,
                  routing_failure_count: 1,
                  execution_failure_count: 1,
                  failure_count: 2,
                },
              ],
            },
          }),
        } as Response);
      }
      return Promise.resolve({
        json: async () => ({ success: true, data: {} }),
        ok: true,
      } as Response);
    });

    await useStore.getState().fetchSessions();

    expect(useStore.getState().sessions).toMatchObject([
      {
        id: "session-risk",
        title: "风险会话",
      },
    ]);
    expect(useStore.getState().dispatchLedgerAggregate).toMatchObject({
      dispatch_session_count: 1,
      dispatch_run_count: 2,
      failure_count: 2,
    });
  });

  it("fetchWorkspaceFiles 应忽略过期会话请求返回，避免覆盖当前工作区", async () => {
    const fetchMock = vi.mocked(globalThis.fetch);
    const deferred = createDeferred<Response>();

    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.endsWith("/api/workspace/session-old/files")) {
        return deferred.promise;
      }
      return Promise.resolve({
        json: async () => ({ success: true, data: { files: [] } }),
      } as Response);
    });

    useStore.setState({
      ...useStore.getInitialState(),
      sessionId: "session-old",
      workspaceFiles: [
        {
          id: "file-current",
          name: "current.md",
          path: "notes/current.md",
          kind: "document",
          size: 1,
          created_at: new Date().toISOString(),
          download_url: "/api/workspace/session-current/files/notes/current.md",
        },
      ],
    });

    const pendingFetch = useStore.getState().fetchWorkspaceFiles();
    useStore.setState({ sessionId: "session-current" });

    deferred.resolve({
      json: async () => ({
        success: true,
        data: {
          files: [
            {
              id: "file-old",
              name: "old.md",
              path: "notes/old.md",
              kind: "document",
              size: 1,
              created_at: new Date().toISOString(),
              download_url: "/api/workspace/session-old/files/notes/old.md",
            },
          ],
        },
      }),
    } as Response);

    await pendingFetch;

    expect(useStore.getState().sessionId).toBe("session-current");
    expect(useStore.getState().workspaceFiles).toHaveLength(1);
    expect(useStore.getState().workspaceFiles[0]?.id).toBe("file-current");
  });

  it("switchSession 切回运行中会话时应恢复缓存的 reasoning 与运行指标", async () => {
    const fetchMock = vi.mocked(globalThis.fetch);
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.endsWith("/api/sessions/session-new/messages")) {
        return Promise.resolve({
          json: async () => ({ success: true, data: { messages: [] } }),
        } as Response);
      }
      if (url.endsWith("/api/sessions/session-old/messages")) {
        return Promise.resolve({
          json: async () => ({ success: true, data: { messages: [] } }),
        } as Response);
      }
      if (url.endsWith("/api/cost/session/session-new")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            session_id: "session-new",
            input_tokens: 1,
            output_tokens: 2,
            total_tokens: 3,
            estimated_cost_cny: 0,
            estimated_cost_usd: 0,
            model_breakdown: {},
          }),
        } as Response);
      }
      if (url.endsWith("/api/cost/session/session-old")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            session_id: "session-old",
            input_tokens: 120,
            output_tokens: 80,
            total_tokens: 200,
            estimated_cost_cny: 0.1,
            estimated_cost_usd: 0.02,
            model_breakdown: {},
          }),
        } as Response);
      }
      return Promise.resolve({
        json: async () => ({ success: true, data: {} }),
        ok: true,
      } as Response);
    });

    const startedAt = new Date("2026-03-15T00:00:00Z").getTime();
    useStore.setState({
      ...useStore.getInitialState(),
      sessionId: "session-old",
      runningSessions: new Set(["session-old"]),
      isStreaming: true,
      messages: [
        {
          id: "reasoning-1",
          role: "assistant",
          content: "先检查字段完整性",
          isReasoning: true,
          reasoningLive: true,
          turnId: "turn-old",
          timestamp: startedAt,
        },
      ],
      _streamingMetrics: {
        startedAt,
        turnId: "turn-old",
        totalTokens: 42,
        hasTokenUsage: true,
      },
      tokenUsage: {
        session_id: "session-old",
        input_tokens: 25,
        output_tokens: 17,
        total_tokens: 42,
        estimated_cost_cny: 0.05,
        estimated_cost_usd: 0.01,
        model_breakdown: {},
      },
    });

    await useStore.getState().switchSession("session-new");
    await useStore.getState().switchSession("session-old");

    expect(useStore.getState().sessionId).toBe("session-old");
    expect(useStore.getState().isStreaming).toBe(true);
    expect(useStore.getState().messages[0]).toMatchObject({
      id: "reasoning-1",
      isReasoning: true,
      reasoningLive: true,
      content: "先检查字段完整性",
    });
    expect(useStore.getState()._streamingMetrics).toMatchObject({
      startedAt,
      turnId: "turn-old",
      totalTokens: 42,
      hasTokenUsage: true,
    });
    expect(useStore.getState().tokenUsage?.session_id).toBe("session-old");
  });

  it("switchSession 应刷新为目标会话的 tokenUsage", async () => {
    const fetchMock = vi.mocked(globalThis.fetch);
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.endsWith("/api/sessions/session-target/messages")) {
        return Promise.resolve({
          json: async () => ({ success: true, data: { messages: [] } }),
        } as Response);
      }
      if (url.endsWith("/api/cost/session/session-target")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            session_id: "session-target",
            input_tokens: 300,
            output_tokens: 200,
            total_tokens: 500,
            estimated_cost_cny: 0.3,
            estimated_cost_usd: 0.04,
            model_breakdown: {},
          }),
        } as Response);
      }
      return Promise.resolve({
        json: async () => ({ success: true, data: {} }),
        ok: true,
      } as Response);
    });

    useStore.setState({
      ...useStore.getInitialState(),
      sessionId: "session-old",
      tokenUsage: {
        session_id: "session-old",
        input_tokens: 1,
        output_tokens: 1,
        total_tokens: 2,
        estimated_cost_cny: 0,
        estimated_cost_usd: 0,
        model_breakdown: {},
      },
    });

    await useStore.getState().switchSession("session-target");

    expect(useStore.getState().sessionId).toBe("session-target");
    expect(useStore.getState().tokenUsage).toMatchObject({
      session_id: "session-target",
      total_tokens: 500,
    });
  });
});

afterAll(() => {
  globalThis.WebSocket = originalWebSocket;
  globalThis.fetch = originalFetch;
});
