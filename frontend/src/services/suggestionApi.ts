import type { ApiResponse } from '../types';
import type { SuggestionItem } from '../types/task';
import { apiClient } from './api';

export const suggestionApi = {
  createSuggestion: async (taskId: string, summary?: Record<string, unknown>): Promise<ApiResponse<SuggestionItem>> => {
    const response = await apiClient.post(`/v1/tasks/${taskId}/suggestions`, summary ? { summary } : undefined);
    return response.data;
  },

  acceptSuggestion: async (taskId: string): Promise<ApiResponse<unknown>> => {
    const response = await apiClient.post(`/v1/tasks/${taskId}/suggestions/accept`);
    return response.data;
  },

  rejectSuggestion: async (taskId: string): Promise<ApiResponse<unknown>> => {
    const response = await apiClient.post(`/v1/tasks/${taskId}/suggestions/reject`);
    return response.data;
  },
};
