/**
 * 分析计划相关类型定义
 *
 * 与后端 src/nini/models/event_schemas.py 保持同步
 */

/** 计划步骤状态 */
export type PlanStepStatus =
  | "not_started"
  | "in_progress"
  | "done"
  | "failed"
  | "blocked"
  | "skipped";

/** 分析计划步骤
 *
 * 与后端 AnalysisPlanStep 模型对应
 */
export interface AnalysisStep {
  /** 步骤 ID（1-based） */
  id: number;
  /** 步骤标题 */
  title: string;
  /** 推荐工具提示 */
  tool_hint: string | null;
  /** 步骤状态 */
  status: PlanStepStatus;
  /** 动作 ID，用于任务关联（与后端 TaskItem.action_id 对应） */
  action_id?: string | null;
  /** 后端原始状态 */
  raw_status?: string;
  /** 依赖的步骤 ID 列表，用于依赖关系展示 */
  depends_on?: number[];
}

/** 分析计划数据结构
 *
 * 与后端 AnalysisPlanEventData 模型对应
 */
export interface AnalysisPlanData {
  steps: AnalysisStep[];
  raw_text: string;
}

/** 分析计划进度
 *
 * 用于 PLAN_PROGRESS 事件
 */
export interface AnalysisPlanProgress {
  steps: AnalysisStep[];
  current_step_index: number;
  total_steps: number;
  step_title: string;
  step_status: PlanStepStatus;
  next_hint: string | null;
  block_reason: string | null;
}

/** 任务尝试状态 */
export type AnalysisTaskAttemptStatus =
  | "in_progress"
  | "retrying"
  | "success"
  | "failed";

/** 任务尝试记录 */
export interface AnalysisTaskAttempt {
  id: string;
  tool_name: string;
  attempt: number;
  max_attempts: number;
  status: AnalysisTaskAttemptStatus;
  note: string | null;
  error: string | null;
  created_at: number;
  updated_at: number;
}

/** 分析任务项
 *
 * 对应 store 中的 analysisTasks
 */
export interface AnalysisTaskItem {
  id: string;
  plan_step_id: number;
  action_id: string | null;
  title: string;
  tool_hint: string | null;
  status: PlanStepStatus;
  raw_status?: string;
  current_activity: string | null;
  last_error: string | null;
  attempts: AnalysisTaskAttempt[];
  created_at: number;
  updated_at: number;
  turn_id?: string | null;
  depends_on?: number[]; // 依赖的步骤 ID 列表
}

/** 计划步骤更新数据
 *
 * 与后端 PlanStepUpdateEventData 模型对应
 */
export interface PlanStepUpdateData {
  id: number;
  status: string;
  error?: string;
}

/** 计划进度数据
 *
 * 与后端 PlanProgressEventData 模型对应
 */
export interface PlanProgressData {
  steps: AnalysisStep[];
  current_step_index: number;
  total_steps: number;
  step_title: string;
  step_status: string;
  next_hint?: string | null;
  block_reason?: string | null;
}

/** 任务尝试数据
 *
 * 与后端 TaskAttemptEventData 模型对应
 */
export interface TaskAttemptData {
  action_id: string;
  step_id: number;
  tool_name: string;
  attempt: number;
  max_attempts: number;
  status: AnalysisTaskAttemptStatus;
  note?: string;
  error?: string;
}
