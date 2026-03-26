import { afterEach, describe, expect, it, vi } from "vitest";

import { handleEvent, type AppStateSubset } from "./event-handler";
import {
  clearAllSessionUiCacheEntries,
  getSessionUiCacheEntry,
} from "./session-ui-cache";
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
    activeModel: null,
    runtimeModel: null,
    modelFallback: null,
    harnessRunContext: null,
    completionCheck: null,
    blockedState: null,
    pendingAskUserQuestionsBySession: {},
    pendingAskUserQuestion: null,
    askUserQuestionNotificationPreference: "default",
    isStreaming: false,
    runningSessions: new Set<string>(),
    tokenUsage: null,
    contextCompressionTick: 0,
    workspacePanelOpen: false,
    workspacePanelTab: "files",
    previewFileId: null,
    codeExecutions: [],
    activeAgents: {},
    completedAgents: [],
    hypotheses: [],
    currentPhase: "generation",
    iterationCount: 0,
    activeAgentId: null,
    fetchSessions: async () => {},
    fetchDatasets: async () => {},
    fetchWorkspaceFiles: async () => {},
    fetchSkills: async () => {},
    switchSession: async () => {},
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
    async dispatch(evt: WSEvent) {
      await handleEvent(evt, set, get);
    },
    getState() {
      return state;
    },
  };
}

describe("handleEvent 文本去重", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    clearAllSessionUiCacheEntries();
  });

  it("后台会话的 ask_user_question 应保存到按会话映射，不污染当前会话面板", async () => {
    const harness = createHarness({
      sessionId: "session-current",
      sessions: [
        { id: "session-current", title: "当前会话", message_count: 3, source: "memory" },
        { id: "session-bg", title: "后台会话", message_count: 5, source: "memory" },
      ],
    });

    await harness.dispatch({
      type: "ask_user_question",
      session_id: "session-bg",
      tool_call_id: "tool-ask-bg",
      data: {
        questions: [
          {
            question: "请选择导出格式",
            header: "导出",
            options: [
              { label: "HTML", description: "交互式页面" },
              { label: "PNG", description: "静态图片" },
            ],
          },
        ],
      },
    });

    expect(harness.getState().pendingAskUserQuestion).toBeNull();
    expect(harness.getState().pendingAskUserQuestionsBySession["session-bg"]).toMatchObject({
      sessionId: "session-bg",
      sessionTitle: "后台会话",
      toolCallId: "tool-ask-bg",
      questionCount: 1,
    });
  });

  it("后台会话的 text 事件应写入对应会话缓存", async () => {
    const harness = createHarness({
      sessionId: "session-current",
    });

    await harness.dispatch({
      type: "text",
      session_id: "session-bg",
      turn_id: "turn-bg",
      data: "后台分析中",
      metadata: {
        message_id: "msg-bg-1",
        operation: "append",
      },
    });

    const cached = getSessionUiCacheEntry("session-bg");
    expect(cached?.messages).toHaveLength(1);
    expect(cached?.messages[0]).toMatchObject({
      turnId: "turn-bg",
      content: "后台分析中",
    });
    expect(harness.getState().messages).toHaveLength(0);
  });

  it("后台会话的 token_usage 事件应写入对应会话缓存", async () => {
    const harness = createHarness({
      sessionId: "session-current",
    });

    await harness.dispatch({
      type: "token_usage",
      session_id: "session-bg",
      turn_id: "turn-bg",
      data: {
        model: "gpt-test",
        input_tokens: 100,
        output_tokens: 50,
        total_tokens: 150,
        cost_usd: 0.01,
        session_total_tokens: 150,
        session_total_cost: 0.01,
      },
    });

    const cached = getSessionUiCacheEntry("session-bg");
    expect(cached?.streamingMetrics).toMatchObject({
      turnId: "turn-bg",
      totalTokens: 150,
      hasTokenUsage: true,
    });
    expect(cached?.tokenUsage).toMatchObject({
      session_id: "session-bg",
      total_tokens: 150,
    });
    expect(harness.getState().tokenUsage).toBeNull();
  });

  it("后台会话的 ask_user_question 在通知已启用时应触发系统通知", async () => {
    const notificationMock = vi.fn();
    const notificationInstance = { close: vi.fn(), onclick: null as (() => void) | null };
    class NotificationCtor {
      static permission = "granted";
      static calls: Array<{ title: string; options: { body?: string; tag?: string } }> = [];

      onclick: (() => void) | null = null;

      constructor(
        public title: string,
        public options: { body?: string; tag?: string },
      ) {
        NotificationCtor.calls.push({ title, options });
        return notificationInstance as unknown as NotificationCtor;
      }
    }
    vi.stubGlobal("Notification", NotificationCtor);
    window.focus = vi.fn();

    const harness = createHarness({
      sessionId: "session-current",
      sessions: [
        { id: "session-current", title: "当前会话", message_count: 3, source: "memory" },
        { id: "session-bg", title: "后台会话", message_count: 5, source: "memory" },
      ],
      askUserQuestionNotificationPreference: "enabled",
      switchSession: notificationMock,
    });

    await harness.dispatch({
      type: "ask_user_question",
      session_id: "session-bg",
      tool_call_id: "tool-ask-bg",
      data: {
        questions: [
          {
            question: "请选择导出格式",
            options: [
              { label: "HTML", description: "交互式页面" },
              { label: "PNG", description: "静态图片" },
            ],
          },
        ],
      },
    });

    expect(NotificationCtor.calls).toEqual([
      {
        title: "后台会话",
        options: {
          body: "需要你回答 1 个问题以继续执行",
          tag: "ask-user-question:tool-ask-bg",
        },
      },
    ]);
    notificationInstance.onclick?.();
    expect(notificationMock).toHaveBeenCalledWith("session-bg");
  });

  it("后台会话结束后应清理对应待回答状态", async () => {
    const harness = createHarness({
      sessionId: "session-current",
      pendingAskUserQuestionsBySession: {
        "session-bg": {
          sessionId: "session-bg",
          sessionTitle: "后台会话",
          toolCallId: "tool-ask-bg",
          questionCount: 1,
          questions: [],
          createdAt: 1,
          attentionRequestedAt: 1,
        },
      },
    });

    await harness.dispatch({
      type: "done",
      session_id: "session-bg",
    });

    expect(harness.getState().pendingAskUserQuestionsBySession["session-bg"]).toBeUndefined();
  });

  it("应保存 run_context 事件到 harness 状态", async () => {
    const harness = createHarness({ sessionId: "session-current" });

    await harness.dispatch({
      type: "run_context",
      session_id: "session-current",
      data: {
        turn_id: "turn-ctx",
        datasets: [{ name: "demo.csv", rows: 10, columns: 3 }],
        artifacts: [],
        tool_hints: ["dataset_catalog"],
        constraints: ["结束前必须检查失败工具"],
      },
      turn_id: "turn-ctx",
    });

    expect(harness.getState().harnessRunContext).toMatchObject({
      turnId: "turn-ctx",
      toolHints: ["dataset_catalog"],
    });
  });

  it("completion_check 未通过时应写入校验状态", async () => {
    const harness = createHarness({ sessionId: "session-current" });

    await harness.dispatch({
      type: "completion_check",
      session_id: "session-current",
      data: {
        turn_id: "turn-check",
        passed: false,
        attempt: 1,
        items: [
          { key: "artifact_generated", label: "承诺产物已生成", passed: false, detail: "缺少报告" },
        ],
        missing_actions: ["承诺产物已生成"],
      },
      turn_id: "turn-check",
    });

    expect(harness.getState().completionCheck).toMatchObject({
      turnId: "turn-check",
      passed: false,
      missingActions: ["承诺产物已生成"],
    });
  });

  it("blocked 事件应标记阻塞状态并停止流式运行", async () => {
    const harness = createHarness({ isStreaming: true, sessionId: "session-current" });

    await harness.dispatch({
      type: "blocked",
      session_id: "session-current",
      data: {
        turn_id: "turn-blocked",
        reason_code: "tool_loop",
        message: "工具连续失败",
        recoverable: true,
        suggested_action: "调整参数后重试",
      },
      turn_id: "turn-blocked",
    });

    expect(harness.getState().blockedState).toMatchObject({
      turnId: "turn-blocked",
      reasonCode: "tool_loop",
    });
    expect(harness.getState().isStreaming).toBe(false);
  });

  it("blocked 事件应同步更新当前计划步骤为 blocked", async () => {
    const harness = createHarness({
      sessionId: "session-current",
      analysisPlanProgress: {
        current_step_index: 1,
        total_steps: 2,
        step_title: "加载数据",
        step_status: "in_progress",
        next_hint: "随后开始分析",
        block_reason: null,
        steps: [
          { id: 1, title: "加载数据", tool_hint: null, status: "in_progress" },
          { id: 2, title: "分析差异", tool_hint: null, status: "not_started" },
        ],
      },
    });

    await harness.dispatch({
      type: "blocked",
      session_id: "session-current",
      data: {
        turn_id: "turn-blocked",
        reason_code: "tool_loop",
        message: "工具连续失败",
        recoverable: true,
        suggested_action: "调整参数后重试",
      },
      turn_id: "turn-blocked",
    });

    expect(harness.getState().analysisPlanProgress).toMatchObject({
      step_status: "blocked",
      block_reason: "工具连续失败",
      next_hint: "调整参数后重试",
    });
    expect(harness.getState().analysisPlanProgress?.steps[0]?.status).toBe("blocked");
  });

  it("iteration_start 应清空上一轮 harness 运行上下文", async () => {
    const harness = createHarness({
      harnessRunContext: {
        turnId: "turn-old",
        datasets: [{ name: "old.csv", rows: 10, columns: 3 }],
        artifacts: [],
        toolHints: ["dataset_catalog"],
        constraints: ["旧约束"],
      },
    });

    await harness.dispatch({
      type: "iteration_start",
      turn_id: "turn-new",
    });

    expect(harness.getState().harnessRunContext).toBeNull();
  });

  it("对同一 message_id 的 replace 应更新现有消息，而不是创建新气泡", async () => {
    const harness = createHarness({ _currentTurnId: "turn-1" });

    await harness.dispatch({
      type: "text",
      data: "正在生成报告...",
      turn_id: "turn-1",
      metadata: {
        message_id: "turn-1-0",
        operation: "append",
      },
    });

    await harness.dispatch({
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

  it("complete 操作携带内容时应保留完整消息", async () => {
    const harness = createHarness({ _currentTurnId: "turn-1" });

    await harness.dispatch({
      type: "text",
      data: "部分内容",
      turn_id: "turn-1",
      metadata: {
        message_id: "turn-1-1",
        operation: "append",
      },
    });

    await harness.dispatch({
      type: "text",
      data: "部分内容，现已完整",
      turn_id: "turn-1",
      metadata: {
        message_id: "turn-1-1",
        operation: "complete",
      },
    });

    const state = harness.getState();
    expect(state.messages).toHaveLength(1);
    expect(state.messages[0]?.messageId).toBe("turn-1-1");
    expect(state.messages[0]?.content).toBe("部分内容，现已完整");
  });

  it("对同一 reasoning_id 应合并为单条 reasoning 消息", async () => {
    const harness = createHarness({ _currentTurnId: "turn-1" });

    await harness.dispatch({
      type: "reasoning",
      data: {
        content: "先检查字段",
        reasoning_id: "reason-1",
        reasoningLive: true,
      },
      turn_id: "turn-1",
    });

    await harness.dispatch({
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

  it("应识别后端 snake_case 的 reasoning_live=false 并标记为已完成", async () => {
    const harness = createHarness({ _currentTurnId: "turn-1" });

    await harness.dispatch({
      type: "reasoning",
      data: {
        content: "最终推理结论",
        reasoning_id: "reason-snake-1",
        reasoning_live: false,
      },
      turn_id: "turn-1",
      metadata: {
        operation: "complete",
      },
    });

    const state = harness.getState();
    expect(state.messages).toHaveLength(1);
    expect(state.messages[0]).toMatchObject({
      isReasoning: true,
      reasoningId: "reason-snake-1",
      reasoningLive: false,
      content: "最终推理结论",
    });
  });

  it("artifact 事件应生成独立的 canonical assistant 消息", async () => {
    const harness = createHarness({
      sessionId: "session-current",
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

    await harness.dispatch({
      type: "artifact",
      session_id: "session-current",
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

  it("不同 session 的 artifact 事件不应污染当前会话消息", async () => {
    const harness = createHarness({
      sessionId: "session-current",
      messages: [
        {
          id: "msg-1",
          role: "assistant",
          content: "当前会话消息",
          turnId: "turn-current",
          timestamp: Date.now(),
        },
      ],
      _currentTurnId: "turn-current",
    });

    await harness.dispatch({
      type: "artifact",
      session_id: "session-other",
      data: {
        name: "report.md",
        type: "report",
        download_url: "/api/artifacts/other/report.md",
      },
      turn_id: "turn-other",
    });

    const state = harness.getState();
    expect(state.messages).toHaveLength(1);
    expect(state.messages[0]?.content).toBe("当前会话消息");
  });

  it("不同 session 的 run_context 不应切换当前工作区任务状态", async () => {
    const harness = createHarness({
      sessionId: "session-current",
      workspacePanelOpen: false,
      workspacePanelTab: "files",
    });

    await harness.dispatch({
      type: "run_context",
      session_id: "session-other",
      data: {
        turn_id: "turn-other",
        datasets: [{ name: "other.csv", rows: 10, columns: 3 }],
        artifacts: [],
        tool_hints: ["dataset_catalog"],
        constraints: ["旧会话约束"],
      },
      turn_id: "turn-other",
    });

    expect(harness.getState().harnessRunContext).toBeNull();
    expect(harness.getState().workspacePanelOpen).toBe(false);
    expect(harness.getState().workspacePanelTab).toBe("files");
  });

  it("不同 session 的 session 事件不应反向覆盖当前会话", async () => {
    const fetchSessions = vi.fn(async () => {});
    const fetchDatasets = vi.fn(async () => {});
    const fetchWorkspaceFiles = vi.fn(async () => {});
    const fetchSkills = vi.fn(async () => {});
    const harness = createHarness({
      sessionId: "session-current",
      fetchSessions,
      fetchDatasets,
      fetchWorkspaceFiles,
      fetchSkills,
    });

    await harness.dispatch({
      type: "session",
      data: {
        session_id: "session-other",
      },
    });

    expect(harness.getState().sessionId).toBe("session-current");
    expect(fetchSessions).toHaveBeenCalledTimes(1);
    expect(fetchDatasets).toHaveBeenCalledTimes(1);
    expect(fetchWorkspaceFiles).toHaveBeenCalledTimes(1);
    expect(fetchSkills).toHaveBeenCalledTimes(1);
  });

  it("token_usage 应累加当前请求 token，并绑定 turn_id", async () => {
    const harness = createHarness({
      sessionId: "session-current",
      isStreaming: true,
      _streamingMetrics: {
        startedAt: Date.now(),
        turnId: null,
        totalTokens: 0,
        hasTokenUsage: false,
      },
    });

    await harness.dispatch({
      type: "iteration_start",
      turn_id: "turn-1",
    });
    await harness.dispatch({
      type: "token_usage",
      session_id: "session-current",
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
    await harness.dispatch({
      type: "token_usage",
      session_id: "session-current",
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

  it("不同 turn 的 token_usage 不应污染当前请求指标", async () => {
    const harness = createHarness({
      isStreaming: true,
      _streamingMetrics: {
        startedAt: Date.now(),
        turnId: "turn-1",
        totalTokens: 420,
        hasTokenUsage: true,
      },
    });

    await harness.dispatch({
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

  it("token_usage 应继承 activeModel 的 provider 信息", async () => {
    const harness = createHarness({
      sessionId: "session-current",
      isStreaming: true,
      activeModel: {
        provider_id: "zhipu",
        provider_name: "智谱 GLM",
        model: "glm-5",
        preferred_provider: "zhipu",
      },
      _streamingMetrics: {
        startedAt: Date.now(),
        turnId: null,
        totalTokens: 0,
        hasTokenUsage: false,
      },
    });

    await harness.dispatch({
      type: "iteration_start",
      turn_id: "turn-1",
    });
    await harness.dispatch({
      type: "token_usage",
      session_id: "session-current",
      turn_id: "turn-1",
      data: {
        model: "glm-5",
        input_tokens: 10,
        output_tokens: 5,
        total_tokens: 15,
        session_total_tokens: 15,
      },
    });

    expect(harness.getState().runtimeModel).toMatchObject({
      provider_id: "zhipu",
      provider_name: "智谱 GLM",
      model: "glm-5",
    });
  });

  it("done 后应清空当前请求指标", async () => {
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

    await harness.dispatch({
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

  it("done 在缺少 currentTurnId 时应兜底关闭所有运行中的 reasoning", async () => {
    const now = Date.now();
    const harness = createHarness({
      _currentTurnId: null,
      messages: [
        {
          id: "r-1",
          role: "assistant",
          content: "思考中 1",
          isReasoning: true,
          reasoningLive: true,
          turnId: "turn-a",
          timestamp: now,
        },
        {
          id: "r-2",
          role: "assistant",
          content: "思考中 2",
          isReasoning: true,
          reasoningLive: true,
          turnId: "turn-b",
          timestamp: now,
        },
      ],
    });

    await harness.dispatch({
      type: "done",
      turn_id: undefined,
    });

    const state = harness.getState();
    expect(state.messages).toHaveLength(2);
    expect(state.messages[0]?.reasoningLive).toBe(false);
    expect(state.messages[1]?.reasoningLive).toBe(false);
  });

  it("ask_user_question 的工具结果应先展示问题再展示用户回答", async () => {
    const harness = createHarness({ _currentTurnId: "turn-ask-1" });

    await harness.dispatch({
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
                options: [
                  {
                    label: "effect_size",
                    description: "效应量与置信区间",
                  },
                ],
              },
              {
                question: "还需要补充什么要求？",
                header: "补充要求",
                options: [
                  {
                    label: "confidence_interval",
                    description: "请同时报告置信区间",
                  },
                ],
              },
            ],
            answers: {
              "你更关注哪类结果？": "effect_size",
              "还需要补充什么要求？": "confidence_interval",
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
    expect(toolResult).toContain("→ 效应量与置信区间");
    expect(toolResult).toContain("补充要求：还需要补充什么要求？");
    expect(toolResult).toContain("→ 请同时报告置信区间");

    // 验证问题出现在答案之前（通过索引位置判断）
    const questionIndex = toolResult.indexOf("你更关注哪类结果？");
    const answerIndex = toolResult.indexOf("→ 效应量与置信区间");
    expect(questionIndex).toBeLessThan(answerIndex);
  });

  it("analysis_plan 事件应通过扩展处理器更新计划状态", async () => {
    const harness = createHarness({
      sessionId: "session-current",
      _currentTurnId: "turn-plan-1",
    });

    await harness.dispatch({
      type: "analysis_plan",
      session_id: "session-current",
      turn_id: "turn-plan-1",
      data: {
        raw_text: "分析计划",
        steps: [
          { id: 1, title: "读取数据", status: "in_progress" },
          { id: 2, title: "生成图表", status: "not_started" },
        ],
      },
    });

    const state = harness.getState();
    expect(state.analysisPlanProgress?.total_steps).toBe(2);
    expect(state.analysisTasks).toHaveLength(2);
    expect(state.workspacePanelTab).toBe("tasks");
  });

  it("retrieval 事件不应误触发试用到期状态", async () => {
    const harness = createHarness({
      sessionId: "session-current",
      _currentTurnId: "turn-ret-1",
    });

    await harness.dispatch({
      type: "retrieval",
      session_id: "session-current",
      turn_id: "turn-ret-1",
      data: {
        query: "test query",
        results: [
          { source: "paper-1", snippet: "snippet", score: 0.9 },
        ],
      },
    });

    const state = harness.getState();
    expect(state.messages).toHaveLength(1);
    expect(state.messages[0]?.content).toBe("检索上下文：test query");
    expect(state.messages[0]?.isError).not.toBe(true);
  });
});
