import { beforeEach, describe, expect, it } from "vitest";

import {
  appendApiToken,
  buildAuthHeaders,
  clearStoredApiKey,
  setStoredApiKey,
} from "./auth";

describe("auth helpers", () => {
  beforeEach(() => {
    clearStoredApiKey();
    sessionStorage.clear();
  });

  it("应为 API 请求头注入 Bearer Token", () => {
    setStoredApiKey("test-key");

    const headers = buildAuthHeaders();

    expect(headers.get("Authorization")).toBe("Bearer test-key");
  });

  it("应为同源 API 资源和 WebSocket 地址追加 token 参数", () => {
    setStoredApiKey("test-key");
    const wsUrl = `ws://${window.location.host}/ws`;

    expect(appendApiToken("/api/workspace/demo/files/report.md")).toBe(
      "/api/workspace/demo/files/report.md?token=test-key",
    );
    expect(appendApiToken(wsUrl)).toBe(
      `${wsUrl}?token=test-key`,
    );
  });

  it("不应改写外部地址", () => {
    setStoredApiKey("test-key");

    expect(appendApiToken("https://example.com/file.png")).toBe(
      "https://example.com/file.png",
    );
  });
});
