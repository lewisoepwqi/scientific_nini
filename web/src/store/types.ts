/**
 * Store 类型定义
 *
 * 从 store.ts 提取的所有类型定义
 */

// ---- 基础类型 ----

export interface ArtifactInfo {
  name: string;
  type: string;
  format?: string;
  download_url: string;
}

export interface RetrievalItem {
  source: string;
  score?: number;
  hits?: number;
  snippet: string;
}

export interface SkillItem {
  type: "function" | "markdown" | string;
  name: string;
  description: string;
  category?: string;
  location: string;
  enabled: boolean;
  expose_to_llm?: boolean;
  metadata?: Record<string, unknown>;
}

export interface CapabilityItem {
  name: string;
  display_name: string;
  description: string;
  icon?: string;
  required_tools: string[];
  suggested_workflow: string[];
  is_executable?: boolean;
  execution_message?: string;
}

export interface SkillDetail extends SkillItem {
  content: string;
}

export interface SkillPathEntry {
  path: string;
  name: string;
  type: "file" | "dir";
  size: number;
  updated_at?: string;
}

export interface SkillFileContent {
  path: string;
  is_text: boolean;
  size: number;
  content: string | null;
}

export interface DatasetItem {
  id: string;
  name: string;
  file_type: string;
  file_size: number;
  row_count: number;
  column_count: number;
  created_at?: string;
  loaded: boolean;
}

export interface WorkspaceFile {
  id: string;
  name: string;
  kind: "dataset" | "artifact" | "note";
  path?: string;
  size: number;
  created_at?: string;
  download_url: string;
  meta?: Record<string, unknown>;
  folder?: string | null;
}

export interface WorkspaceFolder {
  id: string;
  name: string;
  parent: string | null;
  created_at: string;
}

// ---- 计划任务类型 ----

export type PlanStepStatus =
  | "not_started"
  | "in_progress"
  | "done"
  | "blocked"
  | "failed"
  | "skipped";

export interface AnalysisStep {
  id: number;
  title: string;
  tool_hint: string | null;
  status: PlanStepStatus;
  raw_status?: string;
  action_id?: string | null;
}

export interface AnalysisPlanData {
  steps: AnalysisStep[];
  raw_text: string;
}

export interface AnalysisPlanProgress {
  steps: AnalysisStep[];
  current_step_index: number;
  total_steps: number;
  step_title: string;
  step_status: PlanStepStatus;
  next_hint: string | null;
  block_reason: string | null;
}

export type AnalysisTaskAttemptStatus =
  | "in_progress"
  | "retrying"
  | "success"
  | "failed";

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
  turn_id?: string | null; // 关联的回合ID，用于区分不同对话的任务
}

// ---- 意图分析类型 ----

export interface AskUserQuestionOption {
  label: string;
  description: string;
}

export interface AskUserQuestionItem {
  question: string;
  header?: string;
  options: AskUserQuestionOption[];
  multiSelect?: boolean;
  allowTextInput?: boolean;
}

export interface PendingAskUserQuestion {
  toolCallId: string;
  questions: AskUserQuestionItem[];
  createdAt: number;
}

export interface IntentOption {
  label: string;
  description: string;
}

export interface IntentSkillCall {
  name: string;
  arguments: string;
}

export interface IntentSkillSummary {
  name: string;
  description: string;
  category: string;
  research_domain: string;
  difficulty_level: string;
  location: string;
  allowed_tools: string[];
}

export interface IntentCandidateView {
  name: string;
  score: number;
  reason: string;
  payload?: Record<string, unknown>;
}

export interface IntentAnalysisView {
  query: string;
  capability_candidates: IntentCandidateView[];
  skill_candidates: IntentCandidateView[];
  explicit_skill_calls: IntentSkillCall[];
  active_skills: IntentSkillSummary[];
  tool_hints: string[];
  allowed_tools: string[];
  allowed_tool_sources: string[];
  clarification_needed: boolean;
  clarification_question: string | null;
  clarification_options: IntentOption[];
  analysis_method: string;
}

// ---- 研究画像类型 ----

export interface ResearchProfile {
  user_id: string;
  domain: string;
  research_interest: string;
  significance_level: number;
  preferred_correction: string;
  confidence_interval: number;
  journal_style: string;
  color_palette: string;
  figure_width: number;
  figure_height: number;
  figure_dpi: number;
  auto_check_assumptions: boolean;
  include_effect_size: boolean;
  include_ci: boolean;
  include_power_analysis: boolean;
  total_analyses: number;
  favorite_tests: string[];
  recent_datasets: string[];
  research_domains: string[];
  preferred_methods: Record<string, number>;
  output_language: string;
  report_detail_level: string;
  typical_sample_size: string;
  research_notes: string;
}

// ---- 成本透明化类型 ----

export interface ModelTokenUsage {
  model_id: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_cny: number;
  cost_usd: number;
  call_count: number;
}

export interface TokenUsage {
  session_id: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost_cny: number;
  estimated_cost_usd: number;
  model_breakdown: Record<string, ModelTokenUsage>;
  created_at?: string;
  updated_at?: string;
}

export interface SessionCostSummary {
  session_id: string;
  title: string;
  total_tokens: number;
  estimated_cost_cny: number;
  model_count: number;
}

export interface AggregateCostSummary {
  total_sessions: number;
  total_tokens: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost_cny: number;
  total_cost_usd: number;
  average_cost_per_session: number;
  most_used_model?: string;
}

export interface ModelPricing {
  input_price: number;
  output_price: number;
  currency: string;
  tier: "economy" | "standard" | "premium";
}

export interface PricingTierDefinition {
  label: string;
  color: string;
  description: string;
}

export interface PricingConfig {
  models: Record<string, ModelPricing>;
  usd_to_cny_rate: number;
  default_model: string;
  tier_definitions: Record<string, PricingTierDefinition>;
  cost_warnings: {
    high_cost_multiplier: number;
    daily_budget_limit: number;
  };
}

// ---- 消息和会话类型 ----

export interface Message {
  id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  toolName?: string;
  toolCallId?: string;
  toolInput?: Record<string, unknown>;
  toolResult?: string;
  toolStatus?: "success" | "error";
  toolIntent?: string;
  chartData?: unknown;
  dataPreview?: unknown;
  artifacts?: ArtifactInfo[];
  images?: string[];
  retrievals?: RetrievalItem[];
  isReasoning?: boolean;
  reasoningLive?: boolean;
  reasoningId?: string;
  analysisPlan?: AnalysisPlanData;
  isError?: boolean;
  errorKind?:
    | "quota"
    | "rate_limit"
    | "context_limit"
    | "request"
    | "server"
    | "unknown";
  errorCode?: string | null;
  errorHint?: string | null;
  errorDetail?: string | null;
  retryable?: boolean;
  turnId?: string;
  timestamp: number;
}

export interface SessionItem {
  id: string;
  title: string;
  message_count: number;
  source: "memory" | "disk";
}

export interface ActiveModelInfo {
  provider_id: string;
  provider_name: string;
  model: string;
  preferred_provider: string | null;
}

export interface ModelProviderInfo {
  id: string;
  name: string;
  configured: boolean;
  current_model: string;
  available_models: string[];
  api_key_hint: string;
  base_url: string;
  priority: number;
  config_source: "db" | "env" | "none";
}

export interface CodeExecution {
  id: string;
  session_id: string;
  code: string;
  output: string;
  status: string;
  language: string;
  created_at: string;
  tool_name?: string;
  tool_args?: Record<string, unknown>;
  context_token_count?: number;
  intent?: string;
}

export interface MemoryFile {
  name: string;
  size: number;
  modified_at: string;
  type: "memory" | "knowledge" | "meta" | "archive";
}

// ---- WebSocket 事件类型 ----

export interface WSEvent {
  type: string;
  data?: unknown;
  session_id?: string;
  tool_call_id?: string;
  tool_name?: string;
  turn_id?: string;
  metadata?: Record<string, unknown>;
}

export interface RawSessionMessage {
  role?: string;
  content?: string | null;
  event_type?: string | null;
  tool_calls?: Array<{
    id?: string;
    type?: string;
    function?: {
      name?: string;
      arguments?: string;
    };
  }>;
  tool_call_id?: string | null;
  chart_data?: unknown;
  data_preview?: unknown;
  artifacts?: ArtifactInfo[];
  images?: string[];
}
