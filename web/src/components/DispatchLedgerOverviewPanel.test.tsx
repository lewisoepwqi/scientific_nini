import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import DispatchLedgerOverviewPanel from "./DispatchLedgerOverviewPanel";

const mockSelectAgentRun = vi.fn();
const mockSwitchSession = vi.fn(async () => undefined);

vi.mock("../store", () => ({
  useStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      dispatchLedgerAggregate: {
        dispatch_session_count: 2,
        dispatch_run_count: 3,
        subtask_count: 5,
        failure_count: 3,
        preflight_failure_count: 1,
        routing_failure_count: 1,
        execution_failure_count: 1,
        sessions: [
          {
            session_id: "session-risk",
            title: "风险会话",
            last_dispatch_at: "2026-04-07T11:00:00Z",
            latest_run_id: "dispatch:risk:1",
            dispatch_run_count: 2,
            subtask_count: 4,
            failure_count: 3,
          },
        ],
      },
      dispatchLedgers: [
        {
          run_id: "dispatch:call-1",
          agent_name: "任务派发",
          latest_phase: "fused",
          progress_message: "执行汇总：成功 1 个，失败 1 个，停止 1 个",
          runnable_count: 2,
          preflight_failure_count: 0,
          routing_failure_count: 1,
          execution_failure_count: 1,
          dispatch_ledger: [
            {
              agent_name: "数据清洗",
              task: "标准化列名",
            },
            {
              agent_name: "调度器",
              task: "等待人工确认",
            },
          ],
        },
      ],
      selectAgentRun: mockSelectAgentRun,
      switchSession: mockSwitchSession,
    }),
}));

describe("DispatchLedgerOverviewPanel", () => {
  it("应展示独立调度账本并支持跳转到 dispatch 线程", async () => {
    render(<DispatchLedgerOverviewPanel />);

    expect(screen.getByText("调度账本")).toBeInTheDocument();
    expect(screen.getByText("跨 2 个会话累计 3 次多 Agent 派发")).toBeInTheDocument();
    expect(screen.getByText("近期高风险会话")).toBeInTheDocument();
    expect(screen.getByText("风险会话")).toBeInTheDocument();
    expect(screen.getByText("执行汇总：成功 1 个，失败 1 个，停止 1 个")).toBeInTheDocument();
    expect(screen.getByText("数据清洗 · 标准化列名")).toBeInTheDocument();
    expect(screen.getByText("当前会话共 1 次多 Agent 派发")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /风险会话/u }));
    expect(mockSwitchSession).toHaveBeenCalledWith("session-risk");
    await waitFor(() => {
      expect(mockSelectAgentRun).toHaveBeenCalledWith("dispatch:risk:1");
    });

    fireEvent.click(screen.getByRole("button", { name: /任务派发/u }));
    expect(mockSelectAgentRun).toHaveBeenCalledWith("dispatch:call-1");
  });
});
