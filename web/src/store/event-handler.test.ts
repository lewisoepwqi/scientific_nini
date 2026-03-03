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
});
