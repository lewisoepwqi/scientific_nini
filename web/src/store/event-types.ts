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
}

export interface BlockedEventData {
  turn_id: string;
  reason_code: string;
  message: string;
  recoverable: boolean;
  suggested_action?: string | null;
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
}

/** WORKSPACE_UPDATE 事件的数据结构 */
export interface WorkspaceUpdateEventData {
  /** 操作类型 */
  action: "add" | "remove" | "update";
  /** 文件 ID */
  file_id?: string;
  /** 文件夹 ID */
  folder_id?: string;
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
  | TokenUsageEventData
  | SessionTokenUsageEventData
  | ToolCallEventData
  | ToolResultEventData
  | TextEventData
  | ErrorEventData
  | DoneEventData
  | WorkspaceUpdateEventData
  | SessionTitleEventData
  | CodeExecutionEventData
  | SessionEventData
  | StoppedEventData
  | PongEventData;
