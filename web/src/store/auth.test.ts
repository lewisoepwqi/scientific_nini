import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  AUTH_INVALID_EVENT,
  apiFetch,
  clearAuthSession,
  createAuthSession,
  fetchAuthStatus,
} from "./auth";

describe("auth helpers", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("fetchAuthStatus 应返回服务端鉴权状态", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ api_key_required: true, authenticated: false }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(fetchAuthStatus()).resolves.toEqual({
      api_key_required: true,
      authenticated: false,
    });
  });

  it("apiFetch 在 401 时应派发统一鉴权失效事件", async () => {
    const listener = vi.fn();
    window.addEventListener(AUTH_INVALID_EVENT, listener);
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("", { status: 401 }));

    await apiFetch("/api/sessions");

    expect(listener).toHaveBeenCalledTimes(1);
    window.removeEventListener(AUTH_INVALID_EVENT, listener);
  });

  it("createAuthSession 应携带 Bearer API Key", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("", { status: 200 }));

    await createAuthSession("test-key");

    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/auth/session",
      expect.objectContaining({
        method: "POST",
        credentials: "same-origin",
        headers: { Authorization: "Bearer test-key" },
      }),
    );
  });

  it("clearAuthSession 应调用服务端删除 Cookie", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("", { status: 200 }));

    await clearAuthSession();

    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/auth/session",
      expect.objectContaining({
        method: "DELETE",
        credentials: "same-origin",
      }),
    );
  });
});
