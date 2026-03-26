"""FastAPI 应用工厂。

一个进程同时提供：
- HTTP API（文件上传/下载/会话管理）
- WebSocket（Agent 实时交互）
- 静态文件（前端页面）
"""

from __future__ import annotations

import inspect
import logging
import secrets
from contextlib import asynccontextmanager
from typing import Awaitable, Callable

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.responses import Response

from nini.api.auth_utils import is_request_authenticated
from nini.config import settings, _get_bundle_web_dist_dir
from nini.logging_config import bind_log_context, reset_log_context, setup_logging
from nini.models.database import init_db
from nini.plugins.network import NetworkPlugin
from nini.plugins.registry import PluginRegistry
from nini.tools.registry import create_default_tool_registry
from nini.api.websocket import set_tool_registry

logger = logging.getLogger(__name__)

# 前端构建产物目录（冻结模式下从 bundle 内读取）
_WEB_DIST = _get_bundle_web_dist_dir()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动/关闭时执行。"""
    # 启动
    log_path = setup_logging()
    app.state.log_file_path = log_path
    logger.info("Nini 启动中 ...")
    if log_path is not None:
        logger.info("日志文件已启用: %s", log_path)

    # 初始化数据库
    await init_db()

    # 从数据库加载用户保存的模型配置，合并 .env 后重载客户端
    try:
        from nini.agent.model_resolver import reload_model_resolver

        await reload_model_resolver()
        logger.info("已从数据库加载模型配置")
    except Exception as e:
        logger.warning("加载数据库模型配置失败（将使用 .env 配置）: %s", e)

    # 初始化插件注册表
    plugin_registry = PluginRegistry()
    plugin_registry.register(NetworkPlugin())
    await plugin_registry.initialize_all()
    app.state.plugin_registry = plugin_registry
    available = plugin_registry.list_available()
    unavailable = plugin_registry.list_unavailable()
    logger.info(
        "插件初始化完成：可用 %d 个，不可用 %d 个",
        len(available),
        len(unavailable),
    )

    # 初始化工具注册中心
    if "plugin_registry" in inspect.signature(create_default_tool_registry).parameters:
        registry = create_default_tool_registry(plugin_registry=plugin_registry)
    else:
        registry = create_default_tool_registry()
    set_tool_registry(registry)
    logger.info("已注册 %d 个工具", len(registry.list_tools()))

    logger.info("Nini 启动完成 ✓")

    yield

    # 关闭
    logger.info("Nini 关闭中 ...")
    await plugin_registry.shutdown_all()


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例。"""
    setup_logging()
    app = FastAPI(
        title="Nini - 科研数据分析 AI Agent",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS：调试模式允许所有来源，生产模式按配置限制
    if settings.debug:
        cors_origins: list[str] = ["*"]
        cors_credentials = False  # allow_origins=["*"] 时不能启用 credentials
    else:
        cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
        cors_credentials = bool(cors_origins)
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=cors_credentials,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # 安全响应头 + Request ID 中间件
    @app.middleware("http")
    async def security_headers_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or secrets.token_hex(8)
        token = bind_log_context(request_id=request_id)
        try:
            logger.info("处理 HTTP 请求: %s %s", request.method, request.url.path)
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            logger.info(
                "HTTP 请求处理完成: %s %s status=%s",
                request.method,
                request.url.path,
                response.status_code,
            )
            return response
        except Exception:
            logger.exception("HTTP 请求处理异常: %s %s", request.method, request.url.path)
            raise
        finally:
            reset_log_context(token)

    # 可选 API Key 认证中间件
    if settings.api_key:
        from starlette.responses import JSONResponse

        _AUTH_EXEMPT_PATHS = {"/api/auth/status", "/api/auth/session", "/api/health"}
        _AUTH_EXEMPT_PREFIXES = ("/docs", "/redoc", "/openapi.json")

        @app.middleware("http")
        async def api_key_middleware(
            request: Request,
            call_next: Callable[[Request], Awaitable[Response]],
        ) -> Response:
            path = request.url.path
            # 仅保护 API 路径，静态壳与资源不参与鉴权
            if not path.startswith("/api/"):
                return await call_next(request)
            if path in _AUTH_EXEMPT_PATHS or any(path.startswith(p) for p in _AUTH_EXEMPT_PREFIXES):
                return await call_next(request)
            if not is_request_authenticated(request, settings.api_key):
                return JSONResponse(
                    status_code=401, content={"detail": "未授权：需要有效的 API Key"}
                )
            return await call_next(request)

    # 注册路由（注意：API/WebSocket 路由必须先注册，确保优先级高于静态文件）
    from nini.api.routes import router as http_router
    from nini.api.websocket import router as ws_router
    from nini.api.cost_routes import router as cost_router
    from nini.api.knowledge_routes import router as knowledge_router
    from nini.api.memory_routes import router as memory_router

    app.include_router(http_router)
    app.include_router(ws_router)
    app.include_router(cost_router)
    app.include_router(knowledge_router)
    app.include_router(memory_router)

    # 挂载前端静态文件（如果已构建）
    if _WEB_DIST.exists() and (_WEB_DIST / "index.html").exists():
        from fastapi.responses import HTMLResponse

        _index_html_content = (_WEB_DIST / "index.html").read_text(encoding="utf-8")

        @app.get("/", response_class=HTMLResponse, include_in_schema=False)
        async def serve_web_index() -> HTMLResponse:
            """返回前端入口页。

            测试环境中的 httpx ASGITransport 与 FileResponse 组合会阻塞，
            这里直接返回 HTML 文本，避免根路径请求卡住。
            """
            return HTMLResponse(_index_html_content)

        # 1. 挂载静态文件（html=True 让 / 自动映射到 index.html）
        app.mount("/", StaticFiles(directory=str(_WEB_DIST), html=True), name="web")

        # 2. SPA fallback 中间件：mounted app 的 404 不会触发 exception_handler，
        #    但中间件可以拦截所有响应，包括子应用返回的 404
        @app.middleware("http")
        async def spa_fallback_middleware(
            request: Request,
            call_next: Callable[[Request], Awaitable[Response]],
        ) -> Response:
            response = await call_next(request)
            path = request.url.path
            # 仅对非 API/WS 路径的 404 返回 index.html（SPA 客户端路由）
            if response.status_code == 404 and not path.startswith("/api/") and path != "/ws":
                return HTMLResponse(_index_html_content)
            return response

        logger.info("前端静态文件已挂载: %s (SPA fallback 已启用)", _WEB_DIST)
    else:
        # 前端未构建时，根路径返回友好提示而非 404
        from fastapi.responses import HTMLResponse

        @app.get("/", response_class=HTMLResponse)
        async def root_fallback():
            return HTMLResponse(
                content=(
                    "<h2>Nini 后端已启动 ✓</h2>"
                    "<p>前端尚未构建，请执行：</p>"
                    "<pre>cd web &amp;&amp; npm install &amp;&amp; npm run build</pre>"
                    "<p>然后重启服务。</p>"
                    '<p>API 文档：<a href="/docs">/docs</a></p>'
                ),
                status_code=200,
            )

        logger.warning("前端构建产物不存在: %s — 根路径将显示提示页面", _WEB_DIST)

    return app
