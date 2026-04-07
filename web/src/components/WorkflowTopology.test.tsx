import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import WorkflowTopology from "./WorkflowTopology";

vi.mock("../store", () => ({
  useStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      activeAgents: {},
      completedAgents: [],
      agentRunTabs: ["root:turn-1", "dispatch:call-1"],
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
          routingFailureCount: 1,
          executionFailureCount: 0,
          runnableCount: 2,
          messages: [],
        },
      },
    }),
}));

describe("WorkflowTopology", () => {
  it("应在仅有 dispatch 预检时也显示派发摘要", () => {
    render(<WorkflowTopology />);

    expect(screen.getByText("并行执行中")).toBeInTheDocument();
    expect(screen.getByText("任务派发预检")).toBeInTheDocument();
    expect(
      screen.getByText("第 1/2 波次预检：可执行 2 个，预检失败 1 个"),
    ).toBeInTheDocument();
    expect(screen.getByText("可执行 2")).toBeInTheDocument();
    expect(screen.getByText("预检失败 1")).toBeInTheDocument();
    expect(screen.getByText("路由失败 1")).toBeInTheDocument();
    expect(screen.getByText("等待子 Agent 启动...")).toBeInTheDocument();
  });
});
