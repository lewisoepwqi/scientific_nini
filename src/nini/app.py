"""FastAPI 应用工厂。

一个进程同时提供：
- HTTP API（文件上传/下载/会话管理）
- WebSocket（Agent 实时交互）
- 静态文件（前端页面）
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from nini.config import settings
from nini.models.database import init_db
from nini.skills.registry import create_default_registry
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

    # 初始化技能注册中心
    registry = create_default_registry()
    set_skill_registry(registry)
    logger.info("已注册 %d 个技能", len(registry.list_skills()))

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

    # 注册路由（注意：API/WebSocket 路由必须先注册，确保优先级高于静态文件）
    from nini.api.routes import router as http_router
    from nini.api.websocket import router as ws_router

    app.include_router(http_router)
    app.include_router(ws_router)

    # 挂载前端静态文件（如果已构建）
    # 策略：先挂载静态文件，再添加 SPA fallback 路由
    # 这样可以确保 /api 和 /ws 优先于静态文件
    if _WEB_DIST.exists() and (_WEB_DIST / "index.html").exists():
        from starlette.exceptions import HTTPException as StarletteHTTPException
        from fastapi.responses import FileResponse

        # 1. 挂载静态文件（不含 html=True）
        app.mount("/", StaticFiles(directory=str(_WEB_DIST)), name="web")

        # 2. 添加 SPA fallback：非 API 路径的 404 返回 index.html
        @app.exception_handler(StarletteHTTPException)
        async def spa_fallback_handler(request, exc):
            # 如果是 API 或 WebSocket 路径，或者非 404 错误，让 FastAPI 默认处理器处理
            path = request.url.path
            if path.startswith("/api/") or path == "/ws" or exc.status_code != 404:
                # 对于 API 路径，直接返回 None 让其他处理器处理
                # 但由于 FastAPI 不允许返回 None，我们需要重新抛出并由框架处理
                from fastapi.exception_handlers import http_exception_handler

                return await http_exception_handler(request, exc)
            # 其他 404 返回 index.html（SPA 路由）
            return FileResponse(str(_WEB_DIST / "index.html"))

        logger.info("前端静态文件已挂载: %s (SPA fallback 已启用)", _WEB_DIST)

    return app
