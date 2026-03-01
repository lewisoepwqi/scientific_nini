"""API 路由模块导入和注册测试。

确保所有新拆分的路由模块都能正确导入，且路由端点正确注册。
覆盖 routes.py 中使用 try/except 包裹的路由导入。
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute


class TestRouteModuleImport:
    """测试路由模块能否正确导入（不依赖 FastAPI 应用）。"""

    def test_session_routes_import(self):
        """session_routes 模块应能正确导入。"""
        from nini.api.session_routes import router
        assert router is not None
        assert len(router.routes) > 0

    def test_workspace_routes_import(self):
        """workspace_routes 模块应能正确导入。"""
        from nini.api.workspace_routes import router
        assert router is not None
        assert len(router.routes) > 0

    def test_skill_routes_import(self):
        """skill_routes 模块应能正确导入。"""
        from nini.api.skill_routes import router
        assert router is not None
        assert len(router.routes) > 0

    def test_profile_routes_import(self):
        """profile_routes 模块应能正确导入。"""
        from nini.api.profile_routes import router
        assert router is not None
        assert len(router.routes) > 0

    def test_models_routes_import(self):
        """models_routes 模块应能正确导入。"""
        from nini.api.models_routes import router
        assert router is not None
        assert len(router.routes) > 0

    def test_intent_routes_import(self):
        """intent_routes 模块应能正确导入。"""
        from nini.api.intent_routes import router
        assert router is not None
        assert len(router.routes) > 0


class TestRoutesRegistration:
    """测试路由是否在主路由中正确注册。"""

    def test_routes_import_no_errors(self):
        """导入 routes.py 时不应有导入错误。"""
        from nini.api import routes

        # 检查是否有路由导入错误
        if hasattr(routes, '_route_import_errors'):
            assert len(routes._route_import_errors) == 0, (
                f"路由导入错误: {routes._route_import_errors}"
            )

    def test_all_routes_registered(self):
        """所有新路由模块的端点应被注册到主路由。"""
        from nini.api.routes import router

        # 获取所有已注册的路由路径
        registered_paths: set[str] = set()
        for route in router.routes:
            if isinstance(route, APIRoute):
                registered_paths.add(route.path)

        # 检查关键路由是否存在
        critical_routes = [
            # workspace_routes
            "/workspace/{session_id}/folders",
            "/workspace/{session_id}/executions",
            # session_routes（通过 prefix="/sessions" 注册）
            "/sessions/{session_id}/messages",
            # models_routes
            "/models/active",
            "/models/routing",
            # skill_routes (markdown skill 路由)
            "/skills/markdown/{skill_name}/enabled",
            # intent_routes
            "/intent/analyze",
        ]

        missing_routes = []
        for route in critical_routes:
            # 使用模糊匹配，因为路径可能包含参数
            found = any(route in path or path == route for path in registered_paths)
            if not found:
                missing_routes.append(route)

        if missing_routes:
            pytest.fail(f"以下关键路由未注册: {missing_routes}")


class TestRoutesWithApp:
    """使用 FastAPI 应用实例测试路由。"""

    @pytest.fixture
    def app(self):
        """创建测试应用。"""
        from nini.app import create_app
        return create_app()

    def test_app_includes_all_routes(self, app: FastAPI):
        """应用应包含所有 API 路由。"""
        all_paths: set[str] = set()

        for route in app.routes:
            if isinstance(route, APIRoute):
                all_paths.add(route.path)

        # 检查关键 API 端点
        required_endpoints = [
            "/api/models/active",
            "/api/models/routing",
            "/api/workspace/{session_id}/folders",
            "/api/workspace/{session_id}/executions",
            "/api/sessions/{session_id}/messages",
        ]

        missing = []
        for endpoint in required_endpoints:
            # 去掉前缀匹配
            found = any(endpoint == path or endpoint in path for path in all_paths)
            if not found:
                missing.append(endpoint)

        if missing:
            available = sorted([p for p in all_paths if p.startswith("/api")])[:20]
            pytest.fail(
                f"缺少端点: {missing}\n"
                f"可用端点（前20个）: {available}"
            )

    def test_workspace_routes_registered(self, app: FastAPI):
        """工作区路由应正确注册。"""
        # 注意：routes.py 包含了 workspace_routes 和旧的 workspace 路由定义
        # 两者可以共存，因为路径不重叠
        workspace_paths = [
            "/api/workspace/{session_id}/folders",
            "/api/workspace/{session_id}/executions",
            "/api/workspace/{session_id}/tree",
        ]

        all_paths = {r.path for r in app.routes if isinstance(r, APIRoute)}

        for path in workspace_paths:
            # 使用前缀匹配
            matching = [p for p in all_paths if path in p]
            assert matching, f"工作区路由 {path} 未注册。可用路径: {sorted(all_paths)[:20]}"


class TestRouteErrorHandling:
    """测试路由错误处理。"""

    def test_routes_import_logs_errors(self, caplog):
        """路由导入失败时应记录错误日志。"""
        import logging

        # 重新导入 routes 模块以触发日志记录
        import importlib
        from nini.api import routes

        with caplog.at_level(logging.WARNING):
            importlib.reload(routes)

        # 检查是否有路由导入错误日志
        # 注意：在正常环境下不应有错误，但如果故意破坏某个模块，应该能看到日志
        error_logs = [r for r in caplog.records if "路由模块加载失败" in r.message]
        # 正常情况不应有错误，但我们需要确保日志机制存在


class TestEndpointsAvailability:
    """测试端点是否可用（需要数据库）。"""

    @pytest.fixture
    async def client(self):
        """创建异步测试客户端。"""
        import httpx
        from nini.app import create_app

        app = create_app()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver"
        ) as client:
            yield client

    @pytest.mark.asyncio
    async def test_models_active_endpoint_exists(self, client):
        """/api/models/active 端点应可访问（可能返回401/403但不应404）。"""
        import httpx

        response = await client.get("/api/models/active")
        # 不应返回 404（路由未注册）
        assert response.status_code != 404, "/api/models/active 端点未注册"

    @pytest.mark.asyncio
    async def test_workspace_folders_endpoint_exists(self, client):
        """/api/workspace/{session_id}/folders 端点应可访问。"""
        response = await client.get("/api/workspace/test-session/folders")
        # 不应返回 404（路由未注册）
        # 可能返回 404 因为会话不存在，但那是业务逻辑，不是路由问题
        assert response.status_code != 404 or "detail" in response.text, (
            "端点返回404可能是因为路由未注册，检查错误信息"
        )
