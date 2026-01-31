export type TaskStage =
  | 'uploading'
  | 'parsed'
  | 'profiling'
  | 'suggestion_pending'
  | 'processing'
  | 'analysis_ready'
  | 'visualization_ready';

export type SuggestionStatus = 'pending' | 'accepted' | 'rejected' | 'skipped';

export type SharePermission = 'view' | 'edit';

export interface Task {
  id: string;
  datasetId: string;
  ownerId: string;
  stage: TaskStage;
  suggestionStatus: SuggestionStatus;
  activeVersionId?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface TaskStatus {
  taskId: string;
  stage: TaskStage;
  message?: string | null;
}

export interface SuggestionItem {
  id: string;
  taskId: string;
  cleaning: string[];
  statistics: string[];
  chartRecommendations: string[];
  notes: string[];
  status: SuggestionStatus;
}

export interface TaskShare {
  id: string;
  taskId: string;
  memberId: string;
  permission: SharePermission;
  expiresAt?: string | null;
}
