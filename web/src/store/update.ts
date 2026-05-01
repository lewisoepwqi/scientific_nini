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
  busy: boolean;
  error: string | null;
  checkForUpdates: (options?: { manual?: boolean }) => Promise<void>;
  downloadUpdate: () => Promise<void>;
  refreshStatus: () => Promise<void>;
  applyUpdate: () => Promise<void>;
  closeDialog: () => void;
  openDialog: () => void;
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
  busy: false,
  error: null,

  async checkForUpdates(options) {
    const manual = options?.manual === true;
    if (!manual && !shouldAutoCheck()) return;
    set({ busy: true, error: null });
    try {
      const response = await apiFetch("/api/update/check");
      const payload = await readApiResponse<UpdateCheckResult>(response);
      const check = payload.data;
      if (!manual) recordAutoCheck();
      set({
        check,
        busy: false,
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
        busy: false,
        error: error instanceof Error ? error.message : "检查更新失败",
      });
    }
  },

  async downloadUpdate() {
    set({ busy: true, error: null });
    try {
      const response = await apiFetch("/api/update/download", { method: "POST" });
      const payload = await readApiResponse<UpdateDownloadState>(response);
      set({ download: payload.data, busy: false, dialogOpen: true, error: payload.data.error ?? null });
    } catch (error) {
      set({
        busy: false,
        error: error instanceof Error ? error.message : "下载更新失败",
      });
    }
  },

  async refreshStatus() {
    try {
      const response = await apiFetch("/api/update/status");
      const payload = await readApiResponse<UpdateStatus>(response);
      set({
        check: payload.data.check ?? get().check,
        download: payload.data.download ?? get().download,
      });
    } catch {
      // 状态轮询失败不打断用户当前操作。
    }
  },

  async applyUpdate() {
    set({ busy: true, error: null });
    try {
      const response = await apiFetch("/api/update/apply", { method: "POST" });
      await readApiResponse<{ status: string }>(response);
      set({
        busy: false,
        download: { ...get().download, status: "restarting" },
      });
    } catch (error) {
      set({
        busy: false,
        error: error instanceof Error ? error.message : "启动升级失败",
      });
    }
  },

  closeDialog() {
    set({ dialogOpen: false });
  },

  openDialog() {
    set({ dialogOpen: true });
  },
}));
