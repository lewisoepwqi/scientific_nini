import { create } from "zustand";
import { apiFetch } from "./auth";
import type {
  ApiResponse,
  UpdateCheckResult,
  UpdateDownloadState,
  UpdateStatus,
} from "../types/update";

const AUTO_CHECK_KEY = "nini:update:last-check";
const AUTO_CHECK_INTERVAL_MS = 24 * 60 * 60 * 1000;
const POLL_INTERVAL_MS = 2000;

const EMPTY_DOWNLOAD: UpdateDownloadState = {
  status: "idle",
  progress: 0,
  downloaded_bytes: 0,
  total_bytes: null,
  installer_path: null,
  verified: false,
  error: null,
};

interface UpdateStore {
  check: UpdateCheckResult | null;
  download: UpdateDownloadState;
  dialogOpen: boolean;
  checking: boolean;
  downloading: boolean;
  applying: boolean;
  error: string | null;
  checkCompleted: boolean;
  pollTimer: ReturnType<typeof setInterval> | null;
  checkForUpdates: (options?: { manual?: boolean }) => Promise<void>;
  downloadUpdate: () => Promise<void>;
  refreshStatus: () => Promise<void>;
  applyUpdate: () => Promise<void>;
  closeDialog: () => void;
  openDialog: () => void;
  resetCheckCompleted: () => void;
  startPolling: () => void;
  stopPolling: () => void;
}

function shouldAutoCheck(): boolean {
  if (typeof window === "undefined") return false;
  const raw = window.localStorage.getItem(AUTO_CHECK_KEY);
  const last = raw ? Number(raw) : 0;
  return !Number.isFinite(last) || Date.now() - last > AUTO_CHECK_INTERVAL_MS;
}

function recordAutoCheck(): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(AUTO_CHECK_KEY, String(Date.now()));
}

async function readApiResponse<T>(response: Response): Promise<ApiResponse<T>> {
  const payload = (await response.json()) as ApiResponse<T>;
  if (!response.ok || payload.success === false) {
    throw new Error(payload.error || payload.message || `HTTP ${response.status}`);
  }
  return payload;
}

export const useUpdateStore = create<UpdateStore>((set, get) => ({
  check: null,
  download: EMPTY_DOWNLOAD,
  dialogOpen: false,
  checking: false,
  downloading: false,
  applying: false,
  error: null,
  checkCompleted: false,
  pollTimer: null,

  async checkForUpdates(options) {
    const manual = options?.manual === true;
    if (!manual && !shouldAutoCheck()) return;
    set({ checking: true, error: null });
    try {
      const response = await apiFetch("/api/update/check");
      const payload = await readApiResponse<UpdateCheckResult>(response);
      const check = payload.data;
      if (!manual) recordAutoCheck();
      set({
        check,
        checking: false,
        checkCompleted: true,
        dialogOpen: check.update_available ? true : get().dialogOpen,
        error:
          check.status === "check_failed"
            ? check.error ?? "检查更新失败"
            : check.status === "channel_mismatch"
              ? "当前版本高于所选更新渠道，渠道切换无法降级。"
              : null,
      });
    } catch (error) {
      if (!manual) recordAutoCheck();
      set({
        checking: false,
        checkCompleted: true,
        error: error instanceof Error ? error.message : "检查更新失败",
      });
    }
  },

  async downloadUpdate() {
    set({ downloading: true, error: null });
    try {
      // 启动下载，不等待完成
      const response = await apiFetch("/api/update/download", { method: "POST" });
      const payload = await readApiResponse<UpdateDownloadState>(response);
      set({ download: payload.data, downloading: false, error: payload.data.error ?? null });
      // 如果下载未完成，开始轮询
      if (payload.data.status === "downloading" || payload.data.status === "verifying") {
        get().startPolling();
      }
    } catch (error) {
      set({
        downloading: false,
        error: error instanceof Error ? error.message : "下载更新失败",
      });
    }
  },

  async refreshStatus() {
    try {
      const response = await apiFetch("/api/update/status");
      const payload = await readApiResponse<UpdateStatus>(response);
      const newDownload = payload.data.download ?? get().download;
      set({
        check: payload.data.check ?? get().check,
        download: newDownload,
      });
      // 如果下载完成或失败，停止轮询
      if (newDownload.status === "ready" || newDownload.status === "download_failed" || newDownload.status === "verify_failed") {
        get().stopPolling();
      }
    } catch {
      // 状态轮询失败不打断用户当前操作。
    }
  },

  async applyUpdate() {
    set({ applying: true, error: null });
    try {
      // 启动应用更新，不等待完成
      const response = await apiFetch("/api/update/apply", { method: "POST" });
      await readApiResponse<{ status: string }>(response);
      set({
        applying: false,
        download: { ...get().download, status: "restarting" },
      });
    } catch (error) {
      set({
        applying: false,
        error: error instanceof Error ? error.message : "启动升级失败",
      });
    }
  },

  startPolling() {
    const existing = get().pollTimer;
    if (existing) clearInterval(existing);
    const timer = setInterval(() => {
      void get().refreshStatus();
    }, POLL_INTERVAL_MS);
    set({ pollTimer: timer });
  },

  stopPolling() {
    const timer = get().pollTimer;
    if (timer) {
      clearInterval(timer);
      set({ pollTimer: null });
    }
  },

  closeDialog() {
    set({ dialogOpen: false });
  },

  openDialog() {
    set({ dialogOpen: true });
  },

  resetCheckCompleted() {
    set({ checkCompleted: false });
  },
}));
