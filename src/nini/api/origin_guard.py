"""更新入口 Origin/Referer 校验依赖。

API Key（`Authorization: Bearer` / `X-API-Key`）已通过 header 鉴权阻断浏览器跨域简单 POST，
本模块在 `/api/update/download`、`/api/update/apply` 上额外做 Origin/Referer 校验作为
CSRF 防御补强：限定本地 web 壳与显式配置的 Tauri/Electron 来源。
"""

from __future__ import annotations

from urllib.parse import urlparse

from fastapi import HTTPException, Request

from nini.config import Settings, settings


_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}
# Tauri / Electron / file:// 壳的常见来源；Electron file:// 可能上送 Origin: null
_DEFAULT_SHELL_ORIGINS = {
    "null",
    "tauri://localhost",
    "https://tauri.localhost",
    "http://tauri.localhost",
}


def _parse_extra_origins(raw: str) -> set[str]:
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def _origin_allowed(origin: str, *, extra_origins: set[str]) -> bool:
    """判断给定 Origin/Referer 字符串是否落在白名单内。

    允许：
    - 本机 http/https + 127.0.0.1 / localhost / [::1]（任意端口）
    - file:// scheme（Electron 直接加载 file 资源）
    - 显式配置的额外 origin（Tauri/Electron 自定义 scheme 等）
    """
    if not origin:
        return False
    normalized = origin.strip().lower()
    if normalized in extra_origins:
        return True
    if normalized in _DEFAULT_SHELL_ORIGINS:
        return True
    parsed = urlparse(normalized)
    if parsed.scheme in {"file"}:
        return True
    if parsed.scheme in {"http", "https"} and parsed.hostname in _LOCAL_HOSTS:
        return True
    return False


def check_local_origin(request: Request, app_settings: Settings) -> None:
    """核心校验逻辑（单元测试可直接调用）。

    - `update_require_origin_check=False` 时直接放行（企业离线部署）。
    - Origin / Referer 均缺失时放行：通常是非浏览器客户端（已通过 API Key 鉴权）。
    - 任一存在但不在白名单 → 403。
    """
    if not app_settings.update_require_origin_check:
        return

    origin = request.headers.get("origin", "").strip()
    referer = request.headers.get("referer", "").strip()
    if not origin and not referer:
        return

    extra = _parse_extra_origins(app_settings.update_allowed_origins)

    if origin and not _origin_allowed(origin, extra_origins=extra):
        raise HTTPException(status_code=403, detail="更新入口 Origin 校验失败")
    if referer and not _origin_allowed(referer, extra_origins=extra):
        parsed = urlparse(referer.lower())
        referer_origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else referer
        if not _origin_allowed(referer_origin, extra_origins=extra):
            raise HTTPException(status_code=403, detail="更新入口 Referer 校验失败")


def verify_local_origin(request: Request) -> None:
    """FastAPI 依赖：使用全局 settings 校验 update 请求来源。"""
    check_local_origin(request, settings)
