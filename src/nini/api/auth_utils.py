"""API Key 鉴权辅助函数。"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Any

from starlette.requests import Request
from starlette.responses import Response

AUTH_SESSION_COOKIE_NAME = "nini_auth_session"
AUTH_SESSION_TTL = timedelta(hours=8)


def _normalize_api_key(api_key: str | None) -> str:
    return str(api_key or "").strip()


def _extract_header_token(headers: Any) -> str:
    auth = str(headers.get("Authorization", "") or "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    api_key_header = str(headers.get("X-API-Key", "") or "")
    if api_key_header:
        return api_key_header.strip()
    return ""


def _build_cookie_signature(api_key: str, issued_at_ts: int) -> str:
    payload = f"{issued_at_ts}".encode("utf-8")
    secret = api_key.encode("utf-8")
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def build_auth_session_cookie_value(api_key: str, now: datetime | None = None) -> str:
    """生成 HttpOnly 鉴权 Cookie 值。"""
    current = now or datetime.now(timezone.utc)
    issued_at_ts = int(current.timestamp())
    signature = _build_cookie_signature(api_key, issued_at_ts)
    return f"{issued_at_ts}.{signature}"


def is_valid_auth_session_cookie(
    cookie_value: str | None,
    api_key: str | None,
    *,
    now: datetime | None = None,
) -> bool:
    """校验 HttpOnly 鉴权 Cookie。"""
    normalized_key = _normalize_api_key(api_key)
    if not cookie_value or not normalized_key:
        return False
    try:
        issued_at_raw, signature = cookie_value.split(".", 1)
        issued_at_ts = int(issued_at_raw)
    except (ValueError, TypeError):
        return False

    current = now or datetime.now(timezone.utc)
    issued_at = datetime.fromtimestamp(issued_at_ts, timezone.utc)
    if current - issued_at > AUTH_SESSION_TTL:
        return False

    expected = _build_cookie_signature(normalized_key, issued_at_ts)
    return hmac.compare_digest(signature, expected)


def is_request_authenticated(request: Request, api_key: str | None) -> bool:
    """判断 HTTP 请求是否携带有效鉴权信息。"""
    normalized_key = _normalize_api_key(api_key)
    if not normalized_key:
        return True

    header_token = _extract_header_token(request.headers)
    if header_token and hmac.compare_digest(header_token, normalized_key):
        return True

    cookie_value = request.cookies.get(AUTH_SESSION_COOKIE_NAME)
    return is_valid_auth_session_cookie(cookie_value, normalized_key)


def is_websocket_authenticated(websocket: Any, api_key: str | None) -> bool:
    """判断 WebSocket 握手是否携带有效鉴权信息。"""
    normalized_key = _normalize_api_key(api_key)
    if not normalized_key:
        return True

    headers = getattr(websocket, "headers", {})
    header_token = _extract_header_token(headers)
    if header_token and hmac.compare_digest(header_token, normalized_key):
        return True

    cookies = getattr(websocket, "cookies", {}) or {}
    cookie_value = cookies.get(AUTH_SESSION_COOKIE_NAME)
    return is_valid_auth_session_cookie(cookie_value, normalized_key)


def set_auth_session_cookie(response: Response, api_key: str, *, secure: bool) -> None:
    """写入 HttpOnly 鉴权 Cookie。"""
    response.set_cookie(
        key=AUTH_SESSION_COOKIE_NAME,
        value=build_auth_session_cookie_value(api_key),
        max_age=int(AUTH_SESSION_TTL.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )


def clear_auth_session_cookie(response: Response, *, secure: bool) -> None:
    """清除 HttpOnly 鉴权 Cookie。"""
    response.delete_cookie(
        key=AUTH_SESSION_COOKIE_NAME,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )
