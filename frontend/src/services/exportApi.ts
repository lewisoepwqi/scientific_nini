import type { ApiResponse } from '../types';
import { apiClient } from './api';

export interface ExportPackage {
  id: string;
  visualizationId: string;
  datasetVersionRef: string;
  configSnapshot: Record<string, unknown>;
  renderLogSnapshot?: Record<string, unknown> | null;
  expiresAt?: string | null;
}

export const exportApi = {
  createExport: async (visualizationId: string): Promise<ApiResponse<ExportPackage>> => {
    const response = await apiClient.post(`/v1/visualizations/${visualizationId}/exports`);
    return response.data;
  },

  getExport: async (exportId: string): Promise<ApiResponse<ExportPackage>> => {
    const response = await apiClient.get(`/v1/exports/${exportId}`);
    return response.data;
  },
};
