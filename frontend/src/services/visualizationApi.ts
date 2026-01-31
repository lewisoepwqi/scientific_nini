import type { ApiResponse, ChartConfig } from '../types';
import { apiClient } from './api';

export interface VisualizationCreatePayload {
  chartType: string;
  config: ChartConfig;
  datasetVersionId?: string;
}

export interface VisualizationItem {
  id: string;
  taskId: string;
  datasetVersionId?: string | null;
  chartType: string;
  configId?: string | null;
  renderLog?: Record<string, unknown> | null;
  createdAt?: string;
  updatedAt?: string;
}

export const visualizationApi = {
  createVisualization: async (
    taskId: string,
    payload: VisualizationCreatePayload
  ): Promise<ApiResponse<VisualizationItem>> => {
    const response = await apiClient.post(`/v1/tasks/${taskId}/visualizations`, {
      chart_type: payload.chartType,
      config: payload.config,
      dataset_version_id: payload.datasetVersionId,
    });
    return response.data;
  },

  listTaskVisualizations: async (taskId: string): Promise<ApiResponse<VisualizationItem[]>> => {
    const response = await apiClient.get(`/v1/tasks/${taskId}/visualizations`);
    return response.data;
  },

  cloneChartConfig: async (configId: string): Promise<ApiResponse<{ id: string; version: number }>> => {
    const response = await apiClient.post(`/v1/chart-configs/${configId}/clone`);
    return response.data;
  },
};
