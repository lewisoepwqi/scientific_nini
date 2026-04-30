import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useUpdateStore } from "./update";

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("update store", () => {
  beforeEach(() => {
    localStorage.clear();
    useUpdateStore.setState({
      check: null,
      download: {
        status: "idle",
        progress: 0,
        downloaded_bytes: 0,
        total_bytes: null,
        installer_path: null,
        verified: false,
        error: null,
      },
      dialogOpen: false,
      busy: false,
      error: null,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("未配置更新源时不会打开弹窗", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({
        success: true,
        data: {
          current_version: "0.1.1",
          update_available: false,
          important: false,
          status: "not_configured",
          notes: [],
        },
      }),
    );

    await useUpdateStore.getState().checkForUpdates({ manual: true });

    expect(useUpdateStore.getState().check?.status).toBe("not_configured");
    expect(useUpdateStore.getState().dialogOpen).toBe(false);
  });

  it("发现更新时打开弹窗", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({
        success: true,
        data: {
          current_version: "0.1.1",
          latest_version: "0.1.2",
          update_available: true,
          important: true,
          status: "available",
          notes: ["更新"],
          asset_size: 100,
        },
      }),
    );

    await useUpdateStore.getState().checkForUpdates({ manual: true });

    expect(useUpdateStore.getState().check?.update_available).toBe(true);
    expect(useUpdateStore.getState().dialogOpen).toBe(true);
  });

  it("下载成功后记录 ready 状态", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({
        success: true,
        data: {
          status: "ready",
          version: "0.1.2",
          progress: 100,
          downloaded_bytes: 10,
          total_bytes: 10,
          installer_path: "setup.exe",
          verified: true,
          error: null,
        },
      }),
    );

    await useUpdateStore.getState().downloadUpdate();

    expect(useUpdateStore.getState().download.status).toBe("ready");
    expect(useUpdateStore.getState().download.verified).toBe(true);
  });
});
