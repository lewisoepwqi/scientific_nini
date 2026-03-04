import { describe, expect, it } from "vitest";

import { handleEvent, type AppStateSubset } from "./event-handler";
import type { WSEvent } from "./types";

function createState(
  overrides: Partial<AppStateSubset> = {},
): AppStateSubset {
  return {
    sessionId: null,
    messages: [],
    sessions: [],
    _currentTurnId: null,
    _streamingText: "",
    _lastHandledSeq: undefined,
    _activePlanMsgId: null,
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
    analysisPlanProgress: null,
    analysisTasks: [],
    pendingAskUserQuestion: null,
    isStreaming: false,
    tokenUsage: null,
    contextCompressionTick: 0,
    workspacePanelOpen: false,
    workspacePanelTab: "files",
    previewFileId: null,
    codeExecutions: [],
    fetchSessions: async () => {},
    fetchDatasets: async () => {},
    fetchWorkspaceFiles: async () => {},
    fetchSkills: async () => {},
    ...overrides,
  };
}

function createHarness(initial: Partial<AppStateSubset> = {}) {
  let state = createState(initial);

  const set = (
    update:
      | Partial<AppStateSubset>
      | ((s: AppStateSubset) => Partial<AppStateSubset>),
  ) => {
    const patch = typeof update === "function" ? update(state) : update;
    state = { ...state, ...patch };
  };

  const get = () => state;

  return {
    dispatch(evt: WSEvent) {
      handleEvent(evt, set, get);
    },
    getState() {
      return state;
    },
  };
}

describe("handleEvent 文本去重", () => {
  it("对同一 message_id 的 replace 应更新现有消息，而不是创建新气泡", () => {
    const harness = createHarness({ _currentTurnId: "turn-1" });

    harness.dispatch({
      type: "text",
      data: "正在生成报告...",
      turn_id: "turn-1",
      metadata: {
        message_id: "turn-1-0",
        operation: "append",
      },
    });

    harness.dispatch({
      type: "text",
      data: "# 完整报告内容",
      turn_id: "turn-1",
      metadata: {
        message_id: "turn-1-0",
        operation: "replace",
      },
    });

    const state = harness.getState();
    expect(state.messages).toHaveLength(1);
    expect(state.messages[0]?.messageId).toBe("turn-1-0");
    expect(state.messages[0]?.content).toBe("# 完整报告内容");
  });

  it("对同一 reasoning_id 应合并为单条 reasoning 消息", () => {
    const harness = createHarness({ _currentTurnId: "turn-1" });

    harness.dispatch({
      type: "reasoning",
      data: {
        content: "先检查字段",
        reasoning_id: "reason-1",
        reasoningLive: true,
      },
      turn_id: "turn-1",
    });

    harness.dispatch({
      type: "reasoning",
      data: {
        content: "完整推理结论",
        reasoning_id: "reason-1",
        reasoningLive: false,
      },
      turn_id: "turn-1",
    });

    const state = harness.getState();
    expect(state.messages).toHaveLength(1);
    expect(state.messages[0]).toMatchObject({
      isReasoning: true,
      reasoningId: "reason-1",
      reasoningLive: false,
      content: "完整推理结论",
    });
  });

  it("artifact 事件应生成独立的 canonical assistant 消息", () => {
    const harness = createHarness({
      messages: [
        {
          id: "msg-1",
          role: "assistant",
          content: "分析已完成",
          turnId: "turn-1",
          timestamp: Date.now(),
        },
      ],
      _currentTurnId: "turn-1",
    });

    harness.dispatch({
      type: "artifact",
      data: {
        name: "report.md",
        type: "report",
        download_url: "/api/artifacts/demo/report.md",
      },
      turn_id: "turn-1",
    });

    const state = harness.getState();
    expect(state.messages).toHaveLength(2);
    expect(state.messages[1]).toMatchObject({
      role: "assistant",
      content: "产物已生成",
      turnId: "turn-1",
    });
    expect(state.messages[1]?.artifacts).toEqual([
      {
        name: "report.md",
        type: "report",
        download_url: "/api/artifacts/demo/report.md",
      },
    ]);
  });

  it("token_usage 应累加当前请求 token，并绑定 turn_id", () => {
    const harness = createHarness({
      isStreaming: true,
      _streamingMetrics: {
        startedAt: Date.now(),
        turnId: null,
        totalTokens: 0,
        hasTokenUsage: false,
      },
    });

    harness.dispatch({
      type: "iteration_start",
      turn_id: "turn-1",
    });
    harness.dispatch({
      type: "token_usage",
      turn_id: "turn-1",
      data: {
        model: "gpt-5",
        input_tokens: 300,
        output_tokens: 120,
        total_tokens: 420,
        session_total_tokens: 420,
        session_total_cost: 0.1,
      },
    });
    harness.dispatch({
      type: "token_usage",
      turn_id: "turn-1",
      data: {
        model: "gpt-5",
        input_tokens: 200,
        output_tokens: 200,
        total_tokens: 400,
        session_total_tokens: 820,
        session_total_cost: 0.2,
      },
    });

    const state = harness.getState();
    expect(state._streamingMetrics).toMatchObject({
      turnId: "turn-1",
      totalTokens: 820,
      hasTokenUsage: true,
    });
    expect(state.tokenUsage?.total_tokens).toBe(820);
  });

  it("不同 turn 的 token_usage 不应污染当前请求指标", () => {
    const harness = createHarness({
      isStreaming: true,
      _streamingMetrics: {
        startedAt: Date.now(),
        turnId: "turn-1",
        totalTokens: 420,
        hasTokenUsage: true,
      },
    });

    harness.dispatch({
      type: "token_usage",
      turn_id: "turn-2",
      data: {
        model: "gpt-5",
        input_tokens: 10,
        output_tokens: 10,
        total_tokens: 20,
        session_total_tokens: 999,
      },
    });

    const state = harness.getState();
    expect(state._streamingMetrics.totalTokens).toBe(420);
    expect(state.tokenUsage).toBeNull();
  });

  it("done 后应清空当前请求指标", () => {
    const harness = createHarness({
      isStreaming: true,
      _currentTurnId: "turn-1",
      _streamingMetrics: {
        startedAt: Date.now(),
        turnId: "turn-1",
        totalTokens: 820,
        hasTokenUsage: true,
      },
    });

    harness.dispatch({
      type: "done",
      turn_id: "turn-1",
    });

    expect(harness.getState()._streamingMetrics).toEqual({
      startedAt: null,
      turnId: null,
      totalTokens: 0,
      hasTokenUsage: false,
    });
  });

  it("ask_user_question 的工具结果应先展示问题再展示用户回答", () => {
    const harness = createHarness({ _currentTurnId: "turn-ask-1" });

    harness.dispatch({
      type: "tool_result",
      tool_name: "ask_user_question",
      tool_call_id: "tool-ask-1",
      turn_id: "turn-ask-1",
      data: {
        status: "success",
        message: "已收到用户回答。",
        result: {
          success: true,
          message: "已收到用户回答。",
          data: {
            questions: [
              {
                question: "你更关注哪类结果？",
                header: "分析偏好",
              },
              {
                question: "还需要补充什么要求？",
                header: "补充要求",
              },
            ],
            answers: {
              "你更关注哪类结果？": "效应量",
              "还需要补充什么要求？": "请同时报告置信区间",
            },
          },
        },
      },
    });

    expect(harness.getState().messages).toHaveLength(1);
    expect(harness.getState().messages[0]).toMatchObject({
      role: "tool",
      toolName: "ask_user_question",
      toolStatus: "success",
    });

    const toolResult = harness.getState().messages[0]?.toolResult || "";
    // 验证先展示问题，再展示回答（用 → 标记）
    expect(toolResult).toContain("分析偏好：你更关注哪类结果？");
    expect(toolResult).toContain("→ 效应量");
    expect(toolResult).toContain("补充要求：还需要补充什么要求？");
    expect(toolResult).toContain("→ 请同时报告置信区间");

    // 验证问题出现在答案之前（通过索引位置判断）
    const questionIndex = toolResult.indexOf("你更关注哪类结果？");
    const answerIndex = toolResult.indexOf("→ 效应量");
    expect(questionIndex).toBeLessThan(answerIndex);
  });
});
