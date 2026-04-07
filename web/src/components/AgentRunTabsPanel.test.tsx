import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import AgentRunTabsPanel from "./AgentRunTabsPanel";

const mockSelectAgentRun = vi.fn();

vi.mock("../store", () => ({
  useStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      agentRunTabs: [
        "root:turn-1",
        "dispatch:call-1",
        "agent:turn-1:search:1",
        "agent:turn-1:stats:1",
      ],
      agentRuns: {
        "root:turn-1": {
          runId: "root:turn-1",
          turnId: "turn-1",
          parentRunId: null,
          runScope: "root",
          agentId: null,
          agentName: "主 Agent",
          status: "running",
          task: "主任务",
          attempt: 1,
          retryCount: 0,
          startTime: 0,
          updatedAt: 0,
          latestExecutionTimeMs: null,
          messages: [],
        },
        "dispatch:call-1": {
          runId: "dispatch:call-1",
          turnId: "turn-1",
          parentRunId: "root:turn-1",
          runScope: "dispatch",
          agentId: "dispatch_agents",
          agentName: "任务派发",
          status: "running",
          task: "多 Agent 任务派发",
          attempt: 1,
          retryCount: 0,
          startTime: 0,
          updatedAt: 0,
          latestExecutionTimeMs: null,
          progressMessage: "第 1/2 波次预检：可执行 2 个，预检失败 1 个",
          preflightFailureCount: 1,
          routingFailureCount: 0,
          executionFailureCount: 0,
          runnableCount: 2,
          messages: [],
        },
        "agent:turn-1:search:1": {
          runId: "agent:turn-1:search:1",
          turnId: "turn-1",
          parentRunId: "root:turn-1",
          runScope: "subagent",
          agentId: "search",
          agentName: "文献检索",
          status: "running",
          task: "检索最新论文",
          attempt: 1,
          retryCount: 0,
          startTime: 0,
          updatedAt: 0,
          latestExecutionTimeMs: null,
          progressMessage: "正在读取数据库",
          messages: [],
        },
        "agent:turn-1:stats:1": {
          runId: "agent:turn-1:stats:1",
          turnId: "turn-1",
          parentRunId: "root:turn-1",
          runScope: "subagent",
          agentId: "stats",
          agentName: "统计分析",
          status: "completed",
          task: "拟合模型",
          attempt: 2,
          retryCount: 1,
          startTime: 0,
          updatedAt: 0,
          latestExecutionTimeMs: 4200,
          progressMessage: "摘要已生成",
          messages: [],
        },
      },
      selectedRunId: "agent:turn-1:search:1",
      selectAgentRun: mockSelectAgentRun,
      unreadByRun: {
        "agent:turn-1:stats:1": 3,
      },
    }),
}));

describe("AgentRunTabsPanel", () => {
  it("应展示清晰状态和未读文案，并移除 tab 内终止按钮", () => {
    render(<AgentRunTabsPanel />);

    const tabs = screen.getAllByRole("tab");
    expect(tabs).toHaveLength(4);
    expect(tabs[0]).toHaveTextContent("主 Agent");
    expect(tabs[1]).toHaveTextContent("任务派发");
    expect(tabs[2]).toHaveTextContent("文献检索");
    expect(tabs[3]).toHaveTextContent("统计分析");
    expect(tabs[2].className).toContain("items-start");

    expect(screen.getAllByText("运行中").length).toBeGreaterThan(0);
    expect(screen.getAllByText("已完成").length).toBeGreaterThan(0);
    expect(screen.getByText("新消息 3")).toBeInTheDocument();
    expect(screen.getByText("可执行 2 · 预检失败 1")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "终止" })).not.toBeInTheDocument();
  });
});
