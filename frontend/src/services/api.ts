import axios, { AxiosInstance, AxiosProgressEvent } from 'axios';
import type { Layout } from 'plotly.js';
import type {
  ApiResponse,
  DatasetInfo,
  ChartConfig,
  ChartData,
  StatisticalResult,
  DescriptiveStatsMap,
  TTestResultData,
  AnovaResultData,
  CorrelationResultData,
  ParseOptions,
  SavedChart,
  AIAnalysisSuggestion,
} from '../types';

// ==================== Axios 实例配置 ====================

const apiClient: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 请求拦截器
apiClient.interceptors.request.use(
  (config) => {
    // 可以在这里添加认证 token
    const token = localStorage.getItem('auth_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 响应拦截器
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    // 统一错误处理
    const errorMessage = error.response?.data?.error?.message || '网络请求失败';
    console.error('API Error:', errorMessage);
    return Promise.reject(error);
  }
);

// ==================== 文件上传 API ====================

export const uploadAPI = {
  /**
   * 上传文件
   */
  uploadFile: async (
    file: File,
    options: ParseOptions = {},
    onProgress?: (progress: AxiosProgressEvent) => void
  ): Promise<ApiResponse<Record<string, unknown>>> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('options', JSON.stringify(options));

    const response = await apiClient.post<ApiResponse<Record<string, unknown>>>(
      '/v1/datasets/upload',
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        onUploadProgress: onProgress,
      }
    );
    return response.data;
  },

  /**
   * 预览数据集
   */
  previewFile: async (
    datasetId: string,
    rows: number = 10
  ): Promise<ApiResponse<Record<string, unknown>>> => {
    const response = await apiClient.get(`/v1/datasets/${datasetId}/preview`, {
      params: { rows },
    });
    return response.data;
  },

  /**
   * 获取数据集列表
   */
  getDatasets: async (): Promise<ApiResponse<DatasetInfo[]>> => {
    const response = await apiClient.get('/v1/datasets');
    return response.data;
  },

  /**
   * 获取数据集详情
   */
  getDataset: async (id: string): Promise<ApiResponse<DatasetInfo>> => {
    const response = await apiClient.get(`/v1/datasets/${id}`);
    return response.data;
  },

  /**
   * 删除数据集
   */
  deleteDataset: async (id: string): Promise<ApiResponse<void>> => {
    const response = await apiClient.delete(`/v1/datasets/${id}`);
    return response.data;
  },

  /**
   * 获取数据集预览数据
   */
  getDatasetData: async (
    id: string,
    rows: number = 100
  ): Promise<ApiResponse<Record<string, unknown>>> => {
    const response = await apiClient.get(`/v1/datasets/${id}/preview`, {
      params: { rows },
    });
    return response.data;
  },
};

// ==================== 图表 API ====================

export const chartAPI = {
  /**
   * 生成图表
   */
  generateChart: async (
    datasetId: string,
    config: ChartConfig,
    options?: { columns?: string[] }
  ): Promise<ApiResponse<ChartData>> => {
    const baseConfig = {
      title: config.title,
      width: config.width,
      height: config.height,
      journal_style: config.journalStyle,
      show_legend: config.showLegend,
    };

    // 检查是否有叠加层，如果有则调用叠加端点
    if (config.layers && config.layers.length > 0) {
      return chartAPI.generateOverlayChart(datasetId, config);
    }

    let endpoint = '';
    let body: Record<string, unknown> = { ...baseConfig };

    const valueColumn = config.yColumn || config.xColumn;
    const groupColumn =
      config.groupColumn || (config.xColumn && config.xColumn !== valueColumn ? config.xColumn : null);

    switch (config.chartType) {
      case 'scatter':
      case 'line':
        endpoint = '/v1/visualizations/scatter';
        body = {
          ...baseConfig,
          x_column: config.xColumn,
          y_column: config.yColumn,
          color_column: config.colorColumn,
          show_regression: false,
        };
        break;
      case 'bar':
        endpoint = '/v1/visualizations/bar';
        body = {
          ...baseConfig,
          x_column: config.xColumn,
          y_column: config.yColumn,
          group_column: config.groupColumn,
        };
        break;
      case 'box':
        endpoint = '/v1/visualizations/box';
        body = {
          ...baseConfig,
          value_column: valueColumn,
          group_column: groupColumn,
        };
        break;
      case 'violin':
        endpoint = '/v1/visualizations/violin';
        body = {
          ...baseConfig,
          value_column: valueColumn,
          group_column: groupColumn,
        };
        break;
      case 'histogram':
        endpoint = '/v1/visualizations/histogram';
        body = {
          ...baseConfig,
          column: valueColumn,
          group_column: config.groupColumn,
        };
        break;
      case 'heatmap':
      case 'correlation': {
        endpoint = '/v1/visualizations/heatmap';
        const heatmapColumns = options?.columns || [config.xColumn, config.yColumn].filter(Boolean);
        if (heatmapColumns.length < 2) {
          throw new Error('热图至少需要两列数值数据');
        }
        body = {
          ...baseConfig,
          columns: heatmapColumns,
          center_at_zero: config.chartType === 'correlation',
          show_values: config.showStatistics,
        };
        break;
      }
      default:
        throw new Error('不支持的图表类型');
    }

    const response = await apiClient.post(endpoint, body, {
      params: { dataset_id: datasetId },
    });

    const plotlyData = response.data?.data || {};
    return {
      ...response.data,
      data: {
        data: plotlyData.data || [],
        layout: plotlyData.layout || {},
        config: plotlyData.config || {},
      },
    };
  },

  /**
   * 生成叠加图表
   */
  generateOverlayChart: async (
    datasetId: string,
    config: ChartConfig
  ): Promise<ApiResponse<ChartData>> => {
    // 构建主图层配置
    const primaryLayer = {
      chart_type: config.chartType,
      name: '主图层',
      x_column: config.xColumn,
      y_column: config.yColumn,
      group_column: config.groupColumn,
      color_column: config.colorColumn,
      opacity: 0.7,
    };

    // 构建叠加层配置
    const overlayLayers = (config.layers || []).map((layer) => ({
      chart_type: layer.chartType,
      name: layer.name,
      x_column: layer.xColumn,
      y_column: layer.yColumn,
      group_column: layer.groupColumn,
      color_column: layer.colorColumn,
      opacity: layer.opacity,
      color_override: layer.colorOverride,
      y_axis: layer.yAxisMode || 'primary',
      show_regression: layer.showRegression,
      error_type: layer.errorType,
      show_points: layer.showPoints,
      show_mean: layer.showMean,
      show_box: layer.showBox,
    }));

    const body = {
      title: config.title,
      width: config.width,
      height: config.height,
      journal_style: config.journalStyle,
      show_legend: config.showLegend,
      primary_layer: primaryLayer,
      overlay_layers: overlayLayers,
    };

    const response = await apiClient.post('/v1/visualizations/overlay', body, {
      params: { dataset_id: datasetId },
    });

    const plotlyData = response.data?.data || {};
    return {
      ...response.data,
      data: {
        data: plotlyData.data || [],
        layout: plotlyData.layout || {},
        config: plotlyData.config || {},
      },
    };
  },

  /**
   * 保存图表
   */
  saveChart: async (chart: SavedChart): Promise<ApiResponse<SavedChart>> => {
    return Promise.resolve({
      success: true,
      data: chart,
    });
  },

  /**
   * 获取图表列表
   */
  getCharts: async (): Promise<ApiResponse<SavedChart[]>> => {
    return Promise.resolve({
      success: true,
      data: [],
    });
  },

  /**
   * 获取图表详情
   */
  getChart: async (id: string): Promise<ApiResponse<SavedChart>> => {
    void id;
    return Promise.reject(new Error('本地模式不支持读取单个图表'));
  },

  /**
   * 删除图表
   */
  deleteChart: async (id: string): Promise<ApiResponse<void>> => {
    void id;
    return Promise.resolve({
      success: true,
      data: undefined,
    });
  },

  /**
   * 导出图表
   */
  exportChart: async (
    chartId: string,
    format: 'svg' | 'png' | 'pdf' | 'html',
    options?: { width?: number; height?: number; scale?: number }
  ): Promise<Blob> => {
    void chartId;
    void format;
    void options;
    return Promise.reject(new Error('前端暂未支持无后端图表导出'));
  },

  /**
   * 获取可用的颜色方案
   */
  getColorPalettes: async (): Promise<ApiResponse<{ name: string; colors: string[] }[]>> => {
    return Promise.reject(new Error('后端未提供颜色方案接口'));
  },

  /**
   * 获取期刊样式配置
   */
  getJournalStyles: async (): Promise<
    ApiResponse<
      Record<
        string,
        {
          font: string;
          fontSize: number;
          colors: string[];
          layout: Partial<Layout>;
        }
      >
    >
  > => {
    const response = await apiClient.get('/v1/visualizations/journal-styles');
    return response.data;
  },
};

// ==================== 统计分析 API ====================

export const analysisAPI = {
  /**
   * 执行描述性统计
   */
  descriptiveStats: async (
    datasetId: string,
    columns: string[]
  ): Promise<
    ApiResponse<
      DescriptiveStatsMap
    >
  > => {
    const response = await apiClient.post(
      '/v1/analysis/descriptive',
      { columns },
      { params: { dataset_id: datasetId } }
    );

    const list = Array.isArray(response.data?.data)
      ? (response.data.data as Array<Record<string, unknown>>)
      : [];
    const mapped = list.reduce((acc: DescriptiveStatsMap, item: Record<string, unknown>) => {
      const row = item as {
        column?: string;
        count?: number;
        mean?: number;
        std?: number;
        min?: number;
        max?: number;
        median?: number;
        percentiles?: {
          p25?: number;
          p75?: number;
        };
      };
      if (!row.column) {
        return acc;
      }
      acc[row.column] = {
        count: row.count ?? 0,
        mean: row.mean ?? 0,
        std: row.std ?? 0,
        min: row.min ?? 0,
        max: row.max ?? 0,
        median: row.median ?? 0,
        q1: row.percentiles?.p25 ?? 0,
        q3: row.percentiles?.p75 ?? 0,
        missing: null,
      };
      return acc;
    }, {});

    return {
      ...response.data,
      data: mapped,
    };
  },

  /**
   * 执行 t 检验
   */
  tTest: async (
    datasetId: string,
    column: string,
    groupColumn: string,
    groups?: [string, string],
    options?: { alternative?: 'two-sided' | 'less' | 'greater'; alpha?: number }
  ): Promise<ApiResponse<TTestResultData>> => {
    void groups;
    // 构建请求体，只包含有效的字段
    const body: Record<string, unknown> = {
      column,
      group_column: groupColumn,
      alternative: options?.alternative || 'two-sided',
    };
    // 只有在明确指定 alpha 时才设置 confidence_level
    if (options?.alpha !== undefined) {
      body.confidence_level = 1 - options.alpha;
    }
    const response = await apiClient.post(
      '/v1/analysis/t-test',
      body,
      { params: { dataset_id: datasetId } }
    );
    return response.data;
  },

  /**
   * 执行 ANOVA
   */
  anova: async (
    datasetId: string,
    column: string,
    groupColumn: string,
    options?: { postHoc?: boolean; alpha?: number }
  ): Promise<ApiResponse<AnovaResultData>> => {
    const response = await apiClient.post(
      '/v1/analysis/anova',
      {
        value_column: column,
        group_columns: [groupColumn],
        post_hoc: options?.postHoc ?? true,
      },
      { params: { dataset_id: datasetId } }
    );
    return response.data;
  },

  /**
   * 执行相关性分析
   */
  correlation: async (
    datasetId: string,
    columns: string[],
    method?: 'pearson' | 'spearman' | 'kendall'
  ): Promise<ApiResponse<CorrelationResultData>> => {
    const response = await apiClient.post(
      '/v1/analysis/correlation',
      {
        columns,
        method: method || 'pearson',
      },
      { params: { dataset_id: datasetId } }
    );
    const payload = response.data?.data as
      | {
          correlation_matrix?: Record<string, Record<string, number>>;
          pvalue_matrix?: Record<string, Record<string, number>>;
          method?: string;
        }
      | undefined;
    const normalized: CorrelationResultData = {
      matrix: payload?.correlation_matrix || {},
      pValues: payload?.pvalue_matrix || {},
      method: payload?.method || method || 'pearson',
    };
    return {
      ...response.data,
      data: normalized,
    };
  },

  /**
   * 执行卡方检验
   */
  chiSquare: async (
    datasetId: string,
    column1: string,
    column2: string
  ): Promise<ApiResponse<StatisticalResult>> => {
    void datasetId;
    void column1;
    void column2;
    return Promise.reject(new Error('后端未提供卡方检验接口'));
  },

  /**
   * 执行 Mann-Whitney U 检验
   */
  mannWhitney: async (
    datasetId: string,
    column: string,
    groupColumn: string,
    groups?: [string, string]
  ): Promise<ApiResponse<StatisticalResult>> => {
    void datasetId;
    void column;
    void groupColumn;
    void groups;
    return Promise.reject(new Error('后端未提供 Mann-Whitney U 接口'));
  },

  /**
   * 执行 Kruskal-Wallis 检验
   */
  kruskalWallis: async (
    datasetId: string,
    column: string,
    groupColumn: string,
    options?: { postHoc?: boolean; alpha?: number }
  ): Promise<ApiResponse<StatisticalResult>> => {
    void datasetId;
    void column;
    void groupColumn;
    void options;
    return Promise.reject(new Error('后端未提供 Kruskal-Wallis 接口'));
  },

  /**
   * 获取分析历史
   */
  getAnalysisHistory: async (): Promise<ApiResponse<StatisticalResult[]>> => {
    return Promise.reject(new Error('后端未提供分析历史接口'));
  },

  /**
   * 删除分析结果
   */
  deleteAnalysis: async (id: string): Promise<ApiResponse<void>> => {
    void id;
    return Promise.reject(new Error('后端未提供删除分析接口'));
  },
};

// ==================== AI 助手 API ====================

export const aiAPI = {
  /**
   * 发送消息（非流式）
   */
  sendMessage: async (
    message: string,
    context?: {
      datasetId?: string;
      chartConfig?: ChartConfig;
      analysisResults?: StatisticalResult[];
    }
  ): Promise<ApiResponse<{ response: string; suggestions?: AIAnalysisSuggestion[] }>> => {
    const response = await apiClient.post('/ai/chat', {
      message,
      context,
    });
    return response.data;
  },

  /**
   * 发送消息（流式）
   */
  sendMessageStream: async (
    message: string,
    onChunk: (chunk: string) => void,
    context?: {
      datasetId?: string;
      chartConfig?: ChartConfig;
      analysisResults?: StatisticalResult[];
    }
  ): Promise<void> => {
    const response = await fetch(`${apiClient.defaults.baseURL}/ai/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${localStorage.getItem('auth_token') || ''}`,
      },
      body: JSON.stringify({ message, context }),
    });

    if (!response.ok) {
      throw new Error('Stream request failed');
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('No response body');
    }

    const decoder = new TextDecoder();
    let isDone = false;
    while (!isDone) {
      const { done, value } = await reader.read();
      if (done) {
        isDone = true;
        break;
      }
      
      const chunk = decoder.decode(value, { stream: true });
      const lines = chunk.split('\n');
      
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6);
          if (data === '[DONE]') return;
          try {
            const parsed = JSON.parse(data);
            if (parsed.content) {
              onChunk(parsed.content);
            }
          } catch {
            // 忽略解析错误
          }
        }
      }
    }
  },

  /**
   * 获取分析建议
   */
  getSuggestions: async (
    datasetId: string
  ): Promise<ApiResponse<AIAnalysisSuggestion[]>> => {
    const response = await apiClient.get('/ai/suggestions', {
      params: { datasetId },
    });
    return response.data;
  },

  /**
   * 生成图表建议
   */
  suggestChart: async (
    datasetId: string,
    goal?: string
  ): Promise<ApiResponse<ChartConfig[]>> => {
    const response = await apiClient.post('/ai/suggest-chart', {
      datasetId,
      goal,
    });
    return response.data;
  },

  /**
   * 解释统计结果
   */
  explainResult: async (
    resultId: string
  ): Promise<ApiResponse<{ explanation: string; keyPoints: string[] }>> => {
    const response = await apiClient.get(`/ai/explain/${resultId}`);
    return response.data;
  },

  /**
   * 生成分析报告
   */
  generateReport: async (
    datasetId: string,
    options?: {
      includeCharts?: boolean;
      includeStats?: boolean;
      language?: 'zh' | 'en';
    }
  ): Promise<ApiResponse<{ report: string; sections: string[] }>> => {
    const response = await apiClient.post('/ai/generate-report', {
      datasetId,
      options,
    });
    return response.data;
  },
};

// ==================== 导出 API 集合 ====================

export const api = {
  upload: uploadAPI,
  chart: chartAPI,
  analysis: analysisAPI,
  ai: aiAPI,
};

export default api;
