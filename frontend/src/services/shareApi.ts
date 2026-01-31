import type { ApiResponse } from '../types';
import { apiClient } from './api';

export interface TaskShare {
  id: string;
  taskId: string;
  memberId: string;
  permission: 'view' | 'edit';
  createdAt?: string;
  expiresAt?: string | null;
}

export const shareApi = {
  createShare: async (taskId: string, payload: { memberId: string; permission: 'view' | 'edit' }): Promise<ApiResponse<TaskShare>> => {
    const response = await apiClient.post(`/v1/tasks/${taskId}/shares`, {
      member_id: payload.memberId,
      permission: payload.permission,
    });
    return response.data;
  },
};
