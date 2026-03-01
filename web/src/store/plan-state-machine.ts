/**
 * 计划/任务状态机逻辑
 */

import type {
  AnalysisStep,
  AnalysisTaskItem,
  AnalysisTaskAttempt,
  PlanStepStatus,
  AnalysisPlanProgress,
} from "./types";

import {
  normalizePlanStepStatus,
  mergePlanStepStatus,
  isTerminalPlanStepStatus,
  truncatePlanText,
  createDefaultPlanSteps,
} from "./normalizers";

export {
  normalizePlanStepStatus,
  mergePlanStepStatus,
  isTerminalPlanStepStatus,
  truncatePlanText,
  createDefaultPlanSteps,
};

export interface PlanState {
  steps: AnalysisStep[];
  currentStepIndex: number;
  stepStatus: PlanStepStatus;
}

export function createInitialPlanState(totalSteps: number): PlanState {
  return {
    steps: createDefaultPlanSteps(totalSteps),
    currentStepIndex: 1,
    stepStatus: "not_started",
  };
}

export function applyPlanStepUpdate(
  state: PlanState,
  stepIndex: number,
  status: PlanStepStatus,
): PlanState {
  const safeIndex = Math.max(0, stepIndex - 1);
  const newSteps = [...state.steps];

  if (safeIndex >= 0 && safeIndex < newSteps.length) {
    const currentStatus = newSteps[safeIndex].status;
    newSteps[safeIndex] = {
      ...newSteps[safeIndex],
      status: mergePlanStepStatus(currentStatus, status),
    };
  }

  // Recalculate current step index
  const inProgress = newSteps.find((s) => s.status === "in_progress");
  const failed = newSteps.find((s) => s.status === "failed" || s.status === "blocked");
  const nextPending = newSteps.find((s) => s.status === "not_started");
  const lastDone = [...newSteps].reverse().find((s) => s.status === "done");

  const newCurrentIndex = inProgress?.id ?? failed?.id ?? nextPending?.id ?? lastDone?.id ?? 0;

  return {
    ...state,
    steps: newSteps,
    currentStepIndex: newCurrentIndex,
    stepStatus: status,
  };
}

export function createPlanProgress(
  steps: AnalysisStep[],
  currentStepIndex: number,
  stepStatus: PlanStepStatus,
): AnalysisPlanProgress {
  const currentStep = steps.find(s => s.id === currentStepIndex);

  return {
    steps,
    current_step_index: currentStepIndex,
    total_steps: steps.length,
    step_title: currentStep?.title || "",
    step_status: stepStatus,
    next_hint: deriveNextHint(steps, currentStepIndex, stepStatus),
    block_reason: stepStatus === "blocked" ? "步骤被阻塞" : null,
  };
}

export function deriveNextHint(
  steps: AnalysisStep[],
  currentStepIndex: number,
  currentStatus: PlanStepStatus,
): string | null {
  if (steps.length === 0) return null;

  const safeIndex = Math.max(1, Math.min(currentStepIndex, steps.length));
  const nextStep = steps[safeIndex]; // 0-indexed, so this is the next step

  if (currentStatus === "failed" || currentStatus === "blocked") {
    return "可尝试重试当前步骤或补充输入后继续。";
  }
  if (currentStatus === "done" && safeIndex >= steps.length) {
    return "全部步骤已完成。";
  }
  if (currentStatus === "done" && nextStep) {
    return `下一步：${truncatePlanText(nextStep.title)}`;
  }
  if (currentStatus === "in_progress" && nextStep) {
    return `完成后将进入：${truncatePlanText(nextStep.title)}`;
  }
  return `下一步：${truncatePlanText(steps[safeIndex - 1]?.title || "继续执行")}`;
}

export function updateAnalysisTaskById(
  tasks: AnalysisTaskItem[],
  taskId: string | null,
  update: Partial<AnalysisTaskItem>,
): AnalysisTaskItem[] {
  if (!taskId) return tasks;
  return tasks.map((task) =>
    task.id === taskId ? { ...task, ...update, updated_at: Date.now() } : task,
  );
}

export function addTaskAttempt(
  task: AnalysisTaskItem,
  attempt: AnalysisTaskAttempt,
): AnalysisTaskItem {
  return {
    ...task,
    attempts: [...task.attempts, attempt],
    updated_at: Date.now(),
  };
}

export function areAllPlanStepsDone(steps: AnalysisStep[]): boolean {
  return steps.length > 0 && steps.every((s) => isTerminalPlanStepStatus(s.status));
}

export function getPlanCompletionPercentage(steps: AnalysisStep[]): number {
  if (steps.length === 0) return 0;
  const doneCount = steps.filter((s) => isTerminalPlanStepStatus(s.status)).length;
  return Math.round((doneCount / steps.length) * 100);
}

export function findTaskByPlanStepId(
  tasks: AnalysisTaskItem[],
  planStepId: number,
): AnalysisTaskItem | undefined {
  return tasks.find((t) => t.plan_step_id === planStepId);
}

export function getLatestAttempt(
  task: AnalysisTaskItem,
): AnalysisTaskAttempt | null {
  if (task.attempts.length === 0) return null;
  return task.attempts[task.attempts.length - 1];
}
