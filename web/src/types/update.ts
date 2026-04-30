export type UpdateCheckStatus =
  | "idle"
  | "checking"
  | "available"
  | "up_to_date"
  | "not_configured"
  | "disabled"
  | "check_failed";

export type UpdateDownloadStatus =
  | "idle"
  | "checking"
  | "available"
  | "up_to_date"
  | "check_failed"
  | "downloading"
  | "download_failed"
  | "verifying"
  | "verify_failed"
  | "ready"
  | "applying"
  | "restarting";

export interface UpdateCheckResult {
  current_version: string;
  latest_version?: string | null;
  update_available: boolean;
  important: boolean;
  status: UpdateCheckStatus | string;
  title?: string | null;
  notes: string[];
  asset_size?: number | null;
  error?: string | null;
}

export interface UpdateDownloadState {
  status: UpdateDownloadStatus;
  version?: string | null;
  progress: number;
  downloaded_bytes: number;
  total_bytes?: number | null;
  installer_path?: string | null;
  verified: boolean;
  error?: string | null;
}

export interface UpdateStatus {
  check?: UpdateCheckResult | null;
  download: UpdateDownloadState;
}

export interface ApiResponse<T> {
  success: boolean;
  data: T;
  message?: string | null;
  error?: string | null;
}
