import { describe, expect, it } from "vitest";

import {
  buildAgentRunId,
  buildRootRunId,
  initialAgentSlice,
  setAgentComplete,
  setAgentStart,
} from "./agent-slice";

describe("agent-slice 子 agent tab 顺序", () => {
  it("任务状态变化后应保持既有 tab 顺序稳定", () => {
    const turnId = "turn-1";
    const firstRunId = buildAgentRunId(turnId, "agent-a", 1);
    const secondRunId = buildAgentRunId(turnId, "agent-b", 1);

    let state = initialAgentSlice;
    state = setAgentStart(state, "agent-a", "文献检索", "检索论文", turnId, firstRunId, 1, 0);
    state = setAgentStart(state, "agent-b", "统计分析", "拟合模型", turnId, secondRunId, 1, 0);

    expect(state.agentRunTabs).toEqual([
      buildRootRunId(turnId),
      firstRunId,
      secondRunId,
    ]);

    state = setAgentComplete(state, "agent-b", "模型拟合完成", turnId, secondRunId, 1200, 1);
    state = setAgentComplete(state, "agent-a", "检索完成", turnId, firstRunId, 900, 1);

    expect(state.agentRunTabs).toEqual([
      buildRootRunId(turnId),
      firstRunId,
      secondRunId,
    ]);
  });

  it("新的重试尝试应追加到末尾，不应挪动旧 tab", () => {
    const turnId = "turn-2";
    const firstRunId = buildAgentRunId(turnId, "agent-a", 1);
    const secondRunId = buildAgentRunId(turnId, "agent-b", 1);
    const retryRunId = buildAgentRunId(turnId, "agent-a", 2);

    let state = initialAgentSlice;
    state = setAgentStart(state, "agent-a", "文献检索", "检索论文", turnId, firstRunId, 1, 0);
    state = setAgentStart(state, "agent-b", "统计分析", "拟合模型", turnId, secondRunId, 1, 0);
    state = setAgentComplete(state, "agent-a", "首次检索完成", turnId, firstRunId, 800, 1);
    state = setAgentStart(state, "agent-a", "文献检索", "补充检索", turnId, retryRunId, 2, 1);

    expect(state.agentRunTabs).toEqual([
      buildRootRunId(turnId),
      firstRunId,
      secondRunId,
      retryRunId,
    ]);
  });
});
