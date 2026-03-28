import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import DeepTaskProgressCard from "./DeepTaskProgressCard";

let mockState: Record<string, unknown>;

vi.mock("../store", () => ({
 useStore: (
 selector: (
 state: Record<string, unknown>,
 ) => unknown,
 ) => selector(mockState),
}));

describe("DeepTaskProgressCard", () => {
 beforeEach(() => {
 mockState = {
 activeRecipeId: "literature_review",
 recipes: [{ recipe_id: "literature_review", name: "文献综述提纲" }],
 deepTaskState: {
 task_id: "task-1",
 status: "retrying",
 current_step_index: 2,
 total_steps: 3,
 current_step_title: "规划检索",
 next_hint: "正在根据回退策略重试。",
 retry_count: 1,
 },
 analysisPlanProgress: {
 current_step_index: 2,
 total_steps: 3,
 step_title: "规划检索",
 step_status: "retrying",
 next_hint: "正在根据回退策略重试。",
 block_reason: null,
 steps: [
 { id: 1, title: "明确范围", status: "done" },
 { id: 2, title: "规划检索", status: "in_progress" },
 { id: 3, title: "输出提纲", status: "not_started" },
 ],
 },
 };
 });

 it("应展示 deep task 当前步骤和重试状态", () => {
 render(<DeepTaskProgressCard />);

 expect(screen.getByText("文献综述提纲")).toBeInTheDocument();
 expect(screen.getByText(/Step 2 \/ 3/u)).toBeInTheDocument();
 expect(screen.getByText("重试中")).toBeInTheDocument();
 expect(screen.getByText("已触发重试 1 次")).toBeInTheDocument();
 });
});
