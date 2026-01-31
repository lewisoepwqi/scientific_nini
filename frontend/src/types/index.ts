import type { Config, Data, Layout } from 'plotly.js';

// ==================== 数据类型定义 ====================

/**
 * 列数据类型
 */
export type ColumnType = 'numeric' | 'categorical' | 'datetime' | 'text';

/**
 * 数据列信息
 */
export interface ColumnInfo {
  name: string;
  type: ColumnType;
  nullable: boolean;
  uniqueCount: number;
  sample: unknown[];
  // 数值列统计
  min?: number;
  max?: number;
  mean?: number;
  median?: number;
  std?: number;
  // 类别列统计
  categories?: string[];
  categoryCounts?: Record<string, number>;
}

/**
 * 数据集信息
 */
export interface DatasetInfo {
  id: string;
  name: string;
  fileName: string;
  fileSize: number;
  rowCount: number;
  columnCount: number;
  columns: ColumnInfo[];
  uploadTime: Date;
  previewData: Record<string, unknown>[];
}

/**
 * 上传进度
 */
export interface UploadProgress {
  loaded: number;
  total: number;
  percentage: number;
  status: 'pending' | 'uploading' | 'processing' | 'completed' | 'error';
  message?: string;
}

// ==================== 图表类型定义 ====================

/**
 * 图表类型
 */
export type ChartType = 
  | 'scatter'      // 散点图
  | 'line'         // 折线图
  | 'bar'          // 柱状图
  | 'box'          // 箱线图
  | 'violin'       // 小提琴图
  | 'histogram'    // 直方图
  | 'heatmap'      // 热图
  | 'correlation'; // 相关性矩阵

/**
 * 期刊样式
 */
export type JournalStyle = 'nature' | 'science' | 'cell' | 'default';

/**
 * 图表配置
 */
export interface ChartConfig {
  // 基础配置
  chartType: ChartType;
  title: string;

  // 轴配置
  xColumn: string | null;
  yColumn: string | null;
  zColumn?: string | null; // 用于3D或热图

  // 分组与着色
  groupColumn: string | null;
  colorColumn: string | null;

  // 样式配置
  journalStyle: JournalStyle;
  colorPalette: string[];

  // 统计配置
  showStatistics: boolean;
  showSignificance: boolean;
  significanceMethod: 't-test' | 'anova' | 'mann-whitney' | 'kruskal-wallis';
  significancePairs?: Array<[string, string]>;

  // 外观配置
  width: number;
  height: number;
  fontSize: number;
  showGrid: boolean;
  showLegend: boolean;

  // 叠加图层配置
  layers?: ChartLayer[];

  // 高级配置
  customLayout?: Partial<Layout>;
  customConfig?: Partial<Config>;
}

/**
 * 图表数据
 */
export interface ChartData {
  data: Data[];
  layout: Partial<Layout>;
  config: Partial<Config>;
}

/**
 * 图表层配置 - 用于叠加图表
 */
export interface ChartLayer {
  id: string;
  chartType: ChartType;
  name: string;

  // 数据列配置
  xColumn: string | null;
  yColumn: string | null;
  groupColumn: string | null;
  colorColumn: string | null;

  // 样式配置
  opacity: number;
  colorOverride: string | null;
  yAxisMode?: 'primary' | 'secondary';

  // 图表类型特定配置
  showRegression?: boolean;
  errorType?: 'sem' | 'sd' | 'ci';
  showPoints?: boolean;
  showMean?: boolean;
  showBox?: boolean;
}

/**
 * 最大叠加图层数
 */
export const MAX_OVERLAY_LAYERS = 3;

/**
 * 图表兼容性组
 */
export const CHART_COMPATIBILITY: Record<ChartType, ChartType[]> = {
  scatter: ['scatter', 'line', 'bar'],
  line: ['scatter', 'line', 'bar'],
  bar: ['scatter', 'line', 'bar'],
  box: ['box', 'violin'],
  violin: ['box', 'violin'],
  histogram: [],
  heatmap: [],
  correlation: [],
};

/**
 * 保存的图表
 */
export interface SavedChart {
  id: string;
  name: string;
  config: ChartConfig;
  data: ChartData;
  createdAt: Date;
  updatedAt: Date;
  thumbnail?: string;
}

// ==================== 统计结果类型定义 ====================

/**
 * 统计检验结果
 */
export interface StatisticalResult {
  id: string;
  testName: string;
  testType: string;
  columnX: string;
  columnY?: string;
  groupColumn?: string;
  
  // 检验统计量
  statistic: number;
  pValue: number;
  confidence: number;
  
  // 效应量
  effectSize?: number;
  effectSizeType?: string;
  
  // 描述性统计
  descriptiveStats: Record<string, {
    count: number;
    mean: number;
    std: number;
    min: number;
    max: number;
    median: number;
    q1: number;
    q3: number;
  }>;
  
  // 事后检验
  postHoc?: Array<{
    group1: string;
    group2: string;
    pValue: number;
    significant: boolean;
  }>;
  
  // 原始数据
  rawData?: unknown;
  
  createdAt: Date;
}

/**
 * t 检验原始结果（后端返回）
 */
export interface TTestResultData {
  statistic: number;
  pvalue: number;
  df: number;
  confidence_interval: number[];
  effect_size?: number | null;
  mean_diff?: number | null;
  std_diff?: number | null;
}

/**
 * ANOVA 原始结果（后端返回）
 */
export interface AnovaResultData {
  f_statistic: number;
  pvalue: number;
  df_between: number;
  df_within: number;
  sum_sq_between: number;
  sum_sq_within: number;
  mean_sq_between: number;
  mean_sq_within: number;
  eta_squared?: number | null;
  post_hoc_results?: Array<{
    group1: string;
    group2: string;
    pvalue: number;
    reject: boolean;
    mean_diff?: number;
    ci_lower?: number;
    ci_upper?: number;
  }>;
}

/**
 * 相关性分析原始结果（前端归一化格式）
 */
export interface CorrelationResultData {
  matrix: Record<string, Record<string, number>>;
  pValues: Record<string, Record<string, number>>;
  method: string;
}

/**
 * 描述性统计结果映射（前端使用）
 */
export type DescriptiveStatsMap = Record<
  string,
  {
    count: number;
    mean: number;
    std: number;
    min: number;
    max: number;
    median: number;
    q1: number;
    q3: number;
    missing?: number | null;
  }
>;

// ==================== AI 类型定义 ====================

/**
 * AI 消息类型
 */
export interface AIMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  isStreaming?: boolean;
  suggestions?: string[];
  codeBlocks?: Array<{
    language: string;
    code: string;
  }>;
}

/**
 * AI 分析建议
 */
export interface AIAnalysisSuggestion {
  type: 'chart' | 'statistical' | 'data_cleaning' | 'interpretation';
  title: string;
  description: string;
  confidence: number;
  action?: {
    type: string;
    payload: unknown;
  };
}

// ==================== 应用状态类型定义 ====================

/**
 * 应用页面
 */
export type AppPage = 'upload' | 'preview' | 'chart' | 'analysis' | 'chat';

/**
 * 通知类型
 */
export interface Notification {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  message: string;
  duration?: number;
  read?: boolean;
}

// ==================== API 响应类型定义 ====================

/**
 * API 响应标准格式
 */
export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: {
    code: string;
    message: string;
    details?: unknown;
  };
  meta?: {
    page?: number;
    pageSize?: number;
    total?: number;
  };
}

/**
 * 分页请求参数
 */
export interface PaginationParams {
  page: number;
  pageSize: number;
  sortBy?: string;
  sortOrder?: 'asc' | 'desc';
}

// ==================== 文件处理类型定义 ====================

/**
 * 支持的文件类型
 */
export type SupportedFileType = 'csv' | 'xlsx' | 'xls' | 'txt' | 'tsv';

/**
 * 文件解析选项
 */
export interface ParseOptions {
  delimiter?: string;
  encoding?: string;
  headerRow?: number;
  hasHeader?: boolean;
  sheetName?: string;
  dateColumns?: string[];
}

/**
 * 解析后的数据
 */
export interface ParsedData {
  headers: string[];
  rows: Record<string, unknown>[];
  rowCount: number;
  columnCount: number;
}

export * from './task';
