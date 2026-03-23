/**
 * 从后端 OpenAPI 规范自动生成的 TypeScript 类型
 *
 * 生成时间：自动生成，请勿手动修改
 * 修改源：更新后端 Pydantic 模型后重新运行 generate_api_types.py
 */

/** APIResponse */
export interface APIResponse {
  data?: any;
  error?: string | null;
  message?: string | null;
  success?: boolean;
}

/** DatasetInfo */
export interface DatasetInfo {
  column_count?: number;
  file_path: string;
  file_size?: number;
  file_type: string;
  id: string;
  name: string;
  row_count?: number;
  session_id: string;
}

/** FileRenameRequest */
export interface FileRenameRequest {
  name: string;
}

/** MarkdownToolDirCreateRequest */
export interface MarkdownToolDirCreateRequest {
  path: string;
}

/** MarkdownToolEnabledRequest */
export interface MarkdownToolEnabledRequest {
  enabled: boolean;
}

/** MarkdownToolFileWriteRequest */
export interface MarkdownToolFileWriteRequest {
  content?: string;
  path: string;
}

/** MarkdownToolPathDeleteRequest */
export interface MarkdownToolPathDeleteRequest {
  path: string;
}

/** MarkdownToolUpdateRequest */
export interface MarkdownToolUpdateRequest {
  category?: string;
  content?: string;
  description: string;
}

/** ModelConfigRequest */
export interface ModelConfigRequest {
  api_key?: string | null;
  api_mode?: string | null;
  base_url?: string | null;
  is_active?: boolean;
  model?: string | null;
  priority?: number | null;
  provider_id: string;
}

/** ModelPrioritiesRequest */
export interface ModelPrioritiesRequest {
  priorities?: Record<string, any>;
}

/** ModelPurposeRouteRequest */
export interface ModelPurposeRouteRequest {
  base_url?: string | null;
  model?: string | null;
  provider_id?: string | null;
}

/** ModelRoutingRequest */
export interface ModelRoutingRequest {
  preferred_provider?: string | null;
  purpose_providers?: Record<string, any>;
  purpose_routes?: Record<string, any>;
}

/** ReportExportRequest */
export interface ReportExportRequest {
  filename?: string | null;
  format?: string;
  report_id?: string | null;
}

/** ReportGenerateRequest */
export interface ReportGenerateRequest {
  dataset_names?: string[] | null;
  detail_level?: string;
  include_figures?: boolean;
  include_tables?: boolean;
  sections?: string[];
  template?: string;
  title?: string;
}

/** ResearchProfileUpdateRequest */
export interface ResearchProfileUpdateRequest {
  auto_check_assumptions?: boolean | null;
  color_palette?: string | null;
  confidence_interval?: number | null;
  domain?: string | null;
  figure_dpi?: number | null;
  figure_height?: number | null;
  figure_width?: number | null;
  include_ci?: boolean | null;
  include_effect_size?: boolean | null;
  include_power_analysis?: boolean | null;
  journal_style?: string | null;
  output_language?: string | null;
  preferred_correction?: string | null;
  preferred_methods?: Record<string, any> | null;
  report_detail_level?: string | null;
  research_domains?: string[] | null;
  research_interest?: string | null;
  research_notes?: string | null;
  significance_level?: number | null;
  typical_sample_size?: string | null;
}

/** SaveWorkspaceTextRequest */
export interface SaveWorkspaceTextRequest {
  content: string;
  filename?: string | null;
}

/** SessionUpdateRequest */
export interface SessionUpdateRequest {
  title?: string | null;
}

/** SetActiveModelRequest */
export interface SetActiveModelRequest {
  model?: string | null;
  provider_id: string;
}

/** UploadResponse */
export interface UploadResponse {
  dataset?: DatasetInfo | null;
  error?: string | null;
  success: boolean;
  workspace_file?: Record<string, any> | null;
}

/** ValidationError */
export interface ValidationError {
  ctx?: Record<string, any>;
  input?: any;
  loc: number | string[];
  msg: string;
  type: string;
}
