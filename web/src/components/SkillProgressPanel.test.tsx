import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SkillProgressPanel from "./SkillProgressPanel";

let mockState: Record<string, unknown>;

vi.mock("../store", () => ({
  useStore: (
    selector: (
      state: Record<string, unknown>,
    ) => unknown,
  ) => selector(mockState),
}));

describe("SkillProgressPanel", () => {
  beforeEach(() => {
    mockState = {
      submitSkillReviewDecision: vi.fn(),
      skillExecution: {
        skillName: "experiment-design",
        activeSkill: "experiment-design",
        steps: [
          {
            stepId: "generate_plan",
            stepName: "生成方案",
            status: "review_required",
            layer: 0,
            trustLevel: "t1",
            outputLevel: null,
            outputSummary: "",
            errorMessage: null,
            durationMs: null,
            updatedAt: 1,
          },
        ],
        trustCeiling: "t1",
        outputLevel: null,
        overallStatus: null,
        totalDurationMs: null,
        totalSteps: 1,
        completedSteps: 0,
        skippedSteps: 0,
        failedSteps: 0,
        pendingReviewStepId: "generate_plan",
        submittingReviewStepId: null,
        updatedAt: 1,
      },
    };
  });

  it("收到 review_required 后按钮应可点击", () => {
    render(<SkillProgressPanel />);

    expect(screen.getByRole("button", { name: "确认继续" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "取消" })).toBeEnabled();
  });

  it("提交中时按钮应禁用并继续调用 store action", () => {
    mockState = {
      ...mockState,
      skillExecution: {
        ...(mockState.skillExecution as Record<string, unknown>),
        submittingReviewStepId: "generate_plan",
      },
    };

    render(<SkillProgressPanel />);

    expect(screen.getByRole("button", { name: "确认继续" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "取消" })).toBeDisabled();
  });

  it("点击确认应调用提交动作", () => {
    render(<SkillProgressPanel />);

    fireEvent.click(screen.getByRole("button", { name: "确认继续" }));

    expect(mockState.submitSkillReviewDecision).toHaveBeenCalledWith(
      "generate_plan",
      "confirm",
    );
  });
});
