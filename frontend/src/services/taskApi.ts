import type { ApiResponse } from '../types';
import type { Task, TaskStatus } from '../types/task';
import { apiClient } from './api';

export const taskApi = {
  createTask: async (datasetId: string): Promise<ApiResponse<Task>> => {
    const response = await apiClient.post('/v1/tasks', { dataset_id: datasetId });
    return response.data;
  },

  listTasks: async (params?: { limit?: number; offset?: number }): Promise<ApiResponse<Task[]>> => {
    const response = await apiClient.get('/v1/tasks', { params });
    return response.data;
  },

  getTask: async (taskId: string): Promise<ApiResponse<Task>> => {
    const response = await apiClient.get(`/v1/tasks/${taskId}`);
    return response.data;
  },

  getTaskStatus: async (taskId: string): Promise<ApiResponse<TaskStatus>> => {
    const response = await apiClient.get(`/v1/tasks/${taskId}/status`);
    return response.data;
  },
};
