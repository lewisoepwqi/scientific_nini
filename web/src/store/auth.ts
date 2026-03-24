/**
 * 前端 API Key 辅助函数。
 *
 * 统一处理：
 * - sessionStorage 中的 API Key 持久化
 * - API 请求头注入
 * - 资源/下载/WS URL 的 token 查询参数
 * - 401 失效通知
 */

export const API_KEY_STORAGE_KEY = "nini_api_key";
export const AUTH_INVALID_EVENT = "nini:auth-invalid";

let interceptedFetch: typeof fetch | null = null;
let interceptorInstalled = false;
let runtimeApiKey = "";

function readSessionStorageApiKey(): string {
  if (typeof window === "undefined") return runtimeApiKey;
  try {
    return sessionStorage.getItem(API_KEY_STORAGE_KEY)?.trim() || "";
  } catch {
    return "";
  }
}

function getBaseFetch(): typeof fetch {
  if (interceptedFetch) {
    return interceptedFetch;
  }
  return globalThis.fetch.bind(globalThis);
}

function emitAuthInvalid(message: string): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent(AUTH_INVALID_EVENT, {
      detail: { status: 401, message },
    }),
  );
}

function isProtectedApiUrl(input: RequestInfo | URL): boolean {
  try {
    const url =
      typeof input === "string" || input instanceof URL
        ? new URL(String(input), window.location.origin)
        : new URL(input.url, window.location.origin);
    return url.origin === window.location.origin && url.pathname.startsWith("/api/");
  } catch {
    if (typeof input !== "string") {
      return false;
    }
    return input.startsWith("/api/");
  }
}

async function performAuthedFetch(
  fetchImpl: typeof fetch,
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  const shouldAttachAuth = typeof window !== "undefined" && isProtectedApiUrl(input);
  const requestInit = shouldAttachAuth
    ? {
        ...init,
        headers: buildAuthHeaders(init?.headers),
      }
    : init;
  const response = await fetchImpl(input, requestInit);
  if (shouldAttachAuth && response.status === 401) {
    emitAuthInvalid("API Key 无效或已过期，请重新输入。");
  }
  return response;
}

export function getStoredApiKey(): string {
  const stored = readSessionStorageApiKey();
  if (stored) {
    runtimeApiKey = stored;
  }
  return runtimeApiKey;
}

export function setStoredApiKey(apiKey: string): void {
  runtimeApiKey = apiKey.trim();
  if (typeof window === "undefined") return;
  try {
    if (runtimeApiKey) {
      sessionStorage.setItem(API_KEY_STORAGE_KEY, runtimeApiKey);
    } else {
      sessionStorage.removeItem(API_KEY_STORAGE_KEY);
    }
  } catch {
    // 忽略 sessionStorage 不可用场景
  }
}

export function clearStoredApiKey(): void {
  runtimeApiKey = "";
  if (typeof window === "undefined") return;
  try {
    sessionStorage.removeItem(API_KEY_STORAGE_KEY);
  } catch {
    // 忽略 sessionStorage 不可用场景
  }
}

export function buildAuthHeaders(headers?: HeadersInit): Headers {
  const merged = new Headers(headers);
  const apiKey = getStoredApiKey();
  if (apiKey && !merged.has("Authorization") && !merged.has("X-API-Key")) {
    merged.set("Authorization", `Bearer ${apiKey}`);
  }
  return merged;
}

export function appendApiToken(url: string | undefined): string | undefined {
  if (!url) return url;
  const apiKey = getStoredApiKey();
  if (!apiKey || typeof window === "undefined") {
    return url;
  }
  try {
    const parsed = new URL(url, window.location.origin);
    if (
      parsed.host !== window.location.host ||
      (!parsed.pathname.startsWith("/api/") && parsed.pathname !== "/ws")
    ) {
      return url;
    }
    if (!parsed.searchParams.has("token")) {
      parsed.searchParams.set("token", apiKey);
    }
    if (/^[a-z]+:\/\//i.test(url)) {
      return parsed.toString();
    }
    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch {
    return url;
  }
}

export async function apiFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  return performAuthedFetch(getBaseFetch(), input, init);
}

export async function fetchAuthStatus(): Promise<{ api_key_required: boolean }> {
  const response = await getBaseFetch()("/api/auth/status");
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return (await response.json()) as { api_key_required: boolean };
}

export function installApiFetchInterceptor(): void {
  if (interceptorInstalled || typeof window === "undefined") {
    return;
  }
  interceptedFetch = window.fetch.bind(window);
  window.fetch = ((input: RequestInfo | URL, init?: RequestInit) =>
    performAuthedFetch(interceptedFetch!, input, init)) as typeof fetch;
  interceptorInstalled = true;
}
