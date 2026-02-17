"""FastAPI 应用工厂。

一个进程同时提供：
- HTTP API（文件上传/下载/会话管理）
- WebSocket（Agent 实时交互）
- 静态文件（前端页面）
"""

from __future__ import annotations

import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Awaitable, Callable

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.responses import Response

from nini.config import settings
from nini.models.database import init_db
from nini.tools.registry import create_default_registry
from nini.api.websocket import set_skill_registry

logger = logging.getLogger(__name__)

# 前端构建产物目录
_WEB_DIST = Path(__file__).resolve().parent.parent.parent / "web" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动/关闭时执行。"""
    # 启动
    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger.info("Nini 启动中 ...")

    # 初始化数据库
    await init_db()

    # 从数据库加载用户保存的模型配置，合并 .env 后重载客户端
    try:
        from nini.agent.model_resolver import reload_model_resolver

        await reload_model_resolver()
        logger.info("已从数据库加载模型配置")
    except Exception as e:
        logger.warning("加载数据库模型配置失败（将使用 .env 配置）: %s", e)

    # 初始化工具注册中心
    registry = create_default_registry()
    set_skill_registry(registry)
    logger.info("已注册 %d 个工具", len(registry.list_skills()))

    logger.info("Nini 启动完成 ✓")

    yield

    # 关闭
    logger.info("Nini 关闭中 ...")


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例。"""
    app = FastAPI(
        title="Nini - 科研数据分析 AI Agent",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS（开发模式允许所有来源）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request ID 中间件：为每个请求生成唯一标识
    @app.middleware("http")
    async def request_id_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # 优先使用客户端传入的 X-Request-ID，否则生成新的
        request_id = request.headers.get("X-Request-ID") or secrets.token_hex(8)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    # 注册路由（注意：API/WebSocket 路由必须先注册，确保优先级高于静态文件）
    from nini.api.routes import router as http_router
    from nini.api.websocket import router as ws_router

    app.include_router(http_router)
    app.include_router(ws_router)

    # 挂载前端静态文件（如果已构建）
    if _WEB_DIST.exists() and (_WEB_DIST / "index.html").exists():
        from starlette.requests import Request
        from starlette.responses import Response
        from fastapi.responses import FileResponse

        _index_html = str(_WEB_DIST / "index.html")

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
                return FileResponse(_index_html)
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
