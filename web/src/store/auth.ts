/**
 * 鉴权请求辅助函数。
 *
 * 统一处理：
 * - 同源请求附带 Cookie
 * - 401 失效广播
 * - API Key 登录/登出
 */

/** 鉴权失效时派发的全局事件名。 */
export const AUTH_INVALID_EVENT = "nini:auth-invalid";

/** 服务端返回的鉴权状态快照。 */
export interface AuthStatus {
  api_key_required: boolean;
  authenticated: boolean;
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
    const origin = typeof window !== "undefined" ? window.location.origin : "http://localhost";
    const url =
      typeof input === "string" || input instanceof URL
        ? new URL(String(input), origin)
        : new URL(input.url, origin);
    return typeof window !== "undefined" && url.origin === window.location.origin && url.pathname.startsWith("/api/");
  } catch {
    return typeof input === "string" && input.startsWith("/api/");
  }
}

/**
 * 发起同源 API 请求，并在 401 时派发统一失效事件。
 */
export async function apiFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  const response = await fetch(input, {
    credentials: "same-origin",
    ...init,
  });
  if (isProtectedApiUrl(input) && response.status === 401) {
    emitAuthInvalid("API Key 无效、已过期，或鉴权会话已失效，请重新输入。");
  }
  return response;
}

/**
 * 获取服务端鉴权状态。
 */
export async function fetchAuthStatus(): Promise<AuthStatus> {
  const response = await fetch("/api/auth/status", {
    credentials: "same-origin",
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return (await response.json()) as AuthStatus;
}

/**
 * 使用 API Key 建立 HttpOnly 鉴权会话。
 */
export async function createAuthSession(apiKey: string): Promise<void> {
  const response = await fetch("/api/auth/session", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      Authorization: `Bearer ${apiKey.trim()}`,
    },
  });
  if (response.status === 401) {
    emitAuthInvalid("API Key 无效或已过期，请重新输入。");
  }
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
}

/**
 * 清除当前 HttpOnly 鉴权会话。
 */
export async function clearAuthSession(): Promise<void> {
  await fetch("/api/auth/session", {
    method: "DELETE",
    credentials: "same-origin",
  });
}
