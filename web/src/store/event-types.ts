/**
 * WebSocket 事件数据结构类型定义
 *
 * 与后端 src/nini/models/event_schemas.py 保持同步
 * 修改后端类型后，需要同步更新此文件
 */

// ---- 分析计划相关事件 ----

/** 分析计划步骤 */
export interface AnalysisPlanStep {
  /** 步骤 ID（1-based） */
  id: number;
  /** 步骤标题 */
  title: string;
  /** 推荐工具提示 */
  tool_hint?: string | null;
  /** 步骤状态 */
  status: "pending" | "in_progress" | "completed" | "failed" | "skipped";
  /** 动作 ID，用于任务关联 */
  action_id?: string | null;
  /** 后端原始状态 */
  raw_status?: string;
}

/** ANALYSIS_PLAN 事件的数据结构 */
export interface AnalysisPlanEventData {
  /** 分析步骤列表 */
  steps: AnalysisPlanStep[];
  /** 原始文本内容 */
  raw_text: string;
}

/** PLAN_STEP_UPDATE 事件的数据结构 */
export interface PlanStepUpdateEventData {
  /** 步骤 ID */
  id: number;
  /** 新状态 */
  status: string;
  /** 错误信息（如果失败） */
  error?: string;
}

/** PLAN_PROGRESS 事件的数据结构 */
export interface PlanProgressEventData {
  /** 所有步骤 */
  steps: AnalysisPlanStep[];
  /** 当前步骤索引（1-based） */
  current_step_index: number;
  /** 总步骤数 */
  total_steps: number;
  /** 当前步骤标题 */
  step_title: string;
  /** 当前步骤状态 */
  step_status: string;
  /** 下一步提示 */
  next_hint?: string | null;
  /** 阻塞原因 */
  block_reason?: string | null;
  /** 绑定的 Recipe 标识 */
  recipe_id?: string | null;
  /** deep task 标识 */
  task_id?: string | null;
  /** 任务类型 */
  task_kind?: string | null;
  /** 当前重试次数 */
  retry_count?: number | null;
}

/** TASK_ATTEMPT 事件的数据结构 */
export interface TaskAttemptEventData {
  /** 动作 ID */
  action_id: string;
  /** 步骤 ID */
  step_id: number;
  /** 工具名称 */
  tool_name: string;
  /** 当前尝试次数 */
  attempt: number;
  /** 最大尝试次数 */
  max_attempts: number;
  /** 尝试状态 */
  status: "in_progress" | "retrying" | "success" | "failed";
  /** deep task 标识 */
  task_id?: string | null;
  /** 尝试标识 */
  attempt_id?: string | null;
  /** 备注 */
  note?: string;
  /** 错误信息 */
  error?: string;
}

export interface RunContextDatasetSummary {
  name: string;
  rows?: number | null;
  columns?: number | null;
}

export interface RunContextArtifactSummary {
  name: string;
  artifact_type?: string | null;
}

export interface RunContextEventData {
  turn_id: string;
  datasets: RunContextDatasetSummary[];
  artifacts: RunContextArtifactSummary[];
  tool_hints: string[];
  constraints: string[];
  task_id?: string | null;
  recipe_id?: string | null;
}

export interface CompletionCheckItemEventData {
  key: string;
  label: string;
  passed: boolean;
  detail: string;
}

export interface CompletionCheckEventData {
  turn_id: string;
  passed: boolean;
  attempt: number;
  items: CompletionCheckItemEventData[];
  missing_actions: string[];
  task_id?: string | null;
}

export interface BlockedEventData {
  turn_id: string;
  reason_code: string;
  message: string;
  recoverable: boolean;
  task_id?: string | null;
  attempt_id?: string | null;
  suggested_action?: string | null;
}

/** BUDGET_WARNING 事件的数据结构 */
export interface BudgetWarningEventData {
  /** deep task 标识 */
  task_id: string;
  /** 预算指标 */
  metric: "tokens" | "cost_usd" | "tool_calls";
  /** 预算阈值 */
  threshold: number;
  /** 当前值 */
  current_value: number;
  /** 告警级别 */
  warning_level: "warning" | "critical";
  /** 告警摘要 */
  message: string;
  /** Recipe 标识 */
  recipe_id?: string | null;
}

// ---- Token 使用相关事件 ----

/** TOKEN_USAGE 事件的数据结构 */
export interface TokenUsageEventData {
  /** 输入 token 数 */
  input_tokens: number;
  /** 输出 token 数 */
  output_tokens: number;
  /** 模型名称 */
  model: string;
  /** 成本（USD） */
  cost_usd?: number;
}

/** 单个模型的 token 使用详情 */
export interface ModelTokenUsageDetail {
  /** 模型 ID */
  model_id: string;
  /** 输入 token 数 */
  input_tokens: number;
  /** 输出 token 数 */
  output_tokens: number;
  /** 总 token 数 */
  total_tokens: number;
  /** 成本（USD） */
  cost_usd: number;
  /** 成本（CNY） */
  cost_cny: number;
  /** 调用次数 */
  call_count: number;
}

/** 会话级别 TOKEN_USAGE 事件的数据结构 */
export interface SessionTokenUsageEventData {
  /** 会话 ID */
  session_id: string;
  /** 总输入 token 数 */
  input_tokens: number;
  /** 总输出 token 数 */
  output_tokens: number;
  /** 总 token 数 */
  total_tokens: number;
  /** 预估成本（USD） */
  estimated_cost_usd: number;
  /** 预估成本（CNY） */
  estimated_cost_cny: number;
  /** 各模型使用详情 */
  model_breakdown: Record<string, ModelTokenUsageDetail>;
}

// ---- 工具调用相关事件 ----

/** TOOL_CALL 事件的数据结构 */
export interface ToolCallEventData {
  /** 工具调用 ID */
  id: string;
  /** 工具名称 */
  name: string;
  /** 参数 */
  arguments: Record<string, unknown>;
}

/** TOOL_RESULT 事件的数据结构 */
export interface ToolResultEventData {
  /** 工具调用 ID */
  id: string;
  /** 工具名称 */
  name: string;
  /** 执行状态 */
  status: "success" | "error";
  /** 结果消息 */
  message: string;
  /** 结果数据 */
  data?: Record<string, unknown>;
}

export interface AgentStartEventData {
  agent_id: string;
  agent_name: string;
  task: string;
  attempt: number;
  retry_count: number;
}

export interface AgentProgressEventData {
  agent_id: string;
  agent_name: string;
  phase: string;
  message: string;
  progress_hint?: string | null;
  attempt: number;
  retry_count: number;
}

export interface AgentCompleteEventData {
  agent_id: string;
  agent_name: string;
  summary: string;
  execution_time_ms: number;
  attempt: number;
  retry_count: number;
}

export interface AgentErrorEventData {
  agent_id: string;
  agent_name: string;
  error: string;
  execution_time_ms: number;
  attempt: number;
  retry_count: number;
}

export interface AgentStoppedEventData {
  agent_id: string;
  agent_name: string;
  reason: string;
  execution_time_ms: number;
  attempt: number;
  retry_count: number;
}

// ---- 其他事件 ----

/** TEXT 事件的数据结构 */
export interface TextEventData {
  /** 文本内容 */
  content: string;
}

/** ERROR 事件的数据结构 */
export interface ErrorEventData {
  /** 错误消息 */
  message: string;
  /** 错误代码 */
  code?: string;
}

/** DONE 事件的数据结构 */
export interface DoneEventData {
  /** 结束原因 */
  reason: "completed" | "stopped" | "error";
  /** 本轮回复的综合输出等级 */
  output_level?: "o1" | "o2" | "o3" | "o4" | null;
}

/** SKILL_STEP 事件的数据结构 */
export interface SkillStepEventData {
  skill_name: string;
  skill_version: string;
  step_id: string;
  step_name: string;
  status: "started" | "completed" | "failed" | "skipped" | "review_required";
  layer?: number | null;
  trust_level?: string | null;
  output_level?: "o1" | "o2" | "o3" | "o4" | null;
  input_summary?: string;
  output_summary?: string;
  error_message?: string | null;
  duration_ms?: number | null;
}

/** SKILL_SUMMARY 事件的数据结构 */
export interface SkillSummaryEventData {
  skill_name: string;
  total_steps: number;
  completed_steps: number;
  skipped_steps: number;
  failed_steps: number;
  total_duration_ms: number;
  overall_status: "completed" | "partial" | "failed";
  trust_ceiling?: string | null;
  output_level?: "o1" | "o2" | "o3" | "o4" | null;
}

/** WORKSPACE_UPDATE 事件的数据结构 */
export interface WorkspaceUpdateEventData {
  /** 操作类型 */
  action: "add" | "remove" | "update";
  /** 文件 ID */
  file_id?: string;
  /** 文件夹 ID */
  folder_id?: string;
  /** 绑定的 Recipe 标识 */
  recipe_id?: string | null;
  /** deep task 标识 */
  task_id?: string | null;
  /** 尝试标识 */
  attempt_id?: string | null;
  /** 是否完成工作区初始化 */
  initialized?: boolean | null;
}

/** SESSION_TITLE 事件的数据结构 */
export interface SessionTitleEventData {
  /** 会话 ID */
  session_id: string;
  /** 生成的标题 */
  title: string;
}

/** CODE_EXECUTION 事件的数据结构 */
export interface CodeExecutionEventData {
  /** 执行记录 ID */
  id: string;
  /** 执行的代码 */
  code: string;
  /** 输出结果 */
  output: string;
  /** 执行状态 */
  status: "success" | "error";
  /** 编程语言 */
  language: string;
  /** 创建时间 */
  created_at: string;
}

/** SESSION 事件的数据结构 */
export interface SessionEventData {
  /** 会话 ID */
  session_id: string;
  task_kind?: string | null;
  recipe_id?: string | null;
  deep_task_state?: Record<string, unknown> | null;
  recommended_recipe_id?: string | null;
}

/** STOPPED 事件的数据结构 */
export interface StoppedEventData {
  /** 停止消息 */
  message: string;
}

/** PONG 事件的数据结构 */
export interface PongEventData {
  /** 时间戳 */
  timestamp?: number;
}

// ---- 事件类型联合 ----

/** 所有 WebSocket 事件数据类型的联合 */
export type WSEventData =
  | AnalysisPlanEventData
  | PlanStepUpdateEventData
  | PlanProgressEventData
  | TaskAttemptEventData
  | RunContextEventData
  | CompletionCheckEventData
  | BlockedEventData
  | BudgetWarningEventData
  | TokenUsageEventData
  | SessionTokenUsageEventData
  | ToolCallEventData
  | ToolResultEventData
  | AgentStartEventData
  | AgentProgressEventData
  | AgentCompleteEventData
  | AgentErrorEventData
  | AgentStoppedEventData
  | TextEventData
  | ErrorEventData
  | DoneEventData
  | SkillStepEventData
  | SkillSummaryEventData
  | WorkspaceUpdateEventData
  | SessionTitleEventData
  | CodeExecutionEventData
  | SessionEventData
  | StoppedEventData
  | PongEventData;
