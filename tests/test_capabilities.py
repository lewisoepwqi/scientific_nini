"""Capabilities 模块测试。"""

from pathlib import Path

import pytest

from nini.agent.session import session_manager
from nini.app import create_app
from nini.capabilities import (
    Capability,
    CapabilityExecutorNotConfiguredError,
    CapabilityNotExecutableError,
    CapabilityRegistry,
    create_default_capabilities,
)
from nini.config import settings
from tests.client_utils import LocalASGIClient


class TestCapability:
    """测试 Capability 基类。"""

    def test_capability_creation(self):
        """测试创建 Capability 实例。"""
        cap = Capability(
            name="test_cap",
            display_name="测试能力",
            description="用于测试的能力",
            icon="🧪",
            required_tools=["tool1", "tool2"],
            suggested_workflow=["tool1", "tool2"],
        )

        assert cap.name == "test_cap"
        assert cap.display_name == "测试能力"
        assert cap.icon == "🧪"
        assert len(cap.required_tools) == 2
        assert cap.is_executable is False

    def test_capability_to_dict(self):
        """测试转换为字典。"""
        cap = Capability(
            name="test_cap",
            display_name="测试能力",
            description="测试",
        )

        data = cap.to_dict()
        assert data["name"] == "test_cap"
        assert data["display_name"] == "测试能力"
        assert "required_tools" in data
        assert data["is_executable"] is False


class TestCapabilityRegistry:
    """测试 CapabilityRegistry。"""

    def test_register_and_get(self):
        """测试注册和获取能力。"""
        registry = CapabilityRegistry()
        cap = Capability(name="test", display_name="测试", description="测试能力")

        registry.register(cap)
        retrieved = registry.get("test")

        assert retrieved is cap

    def test_list_capabilities(self):
        """测试列出所有能力。"""
        registry = CapabilityRegistry()
        registry.register(Capability(name="cap1", display_name="能力1", description=""))
        registry.register(Capability(name="cap2", display_name="能力2", description=""))

        caps = registry.list_capabilities()
        assert len(caps) == 2

    def test_suggest_for_intent(self):
        """测试基于意图推荐能力。"""
        registry = CapabilityRegistry()
        registry.register(
            Capability(
                name="difference_analysis",
                display_name="差异分析",
                description="比较两组数据差异",
            )
        )
        registry.register(
            Capability(
                name="correlation_analysis",
                display_name="相关性分析",
                description="分析变量相关性",
            )
        )

        # 测试精确匹配
        suggested = registry.suggest_for_intent("差异分析")
        assert len(suggested) > 0
        assert suggested[0].name == "difference_analysis"

    def test_to_catalog(self):
        """测试生成目录。"""
        registry = CapabilityRegistry()
        registry.register(Capability(name="test", display_name="测试", description=""))

        catalog = registry.to_catalog()
        assert len(catalog) == 1
        assert catalog[0]["name"] == "test"

    @pytest.mark.asyncio
    async def test_execute_uses_registered_executor_factory(self):
        """执行应通过注册表里的执行器工厂完成。"""
        registry = CapabilityRegistry()

        class _ExecutableCapability:
            async def execute(self, session, **kwargs):
                return type(
                    "_Result",
                    (),
                    {
                        "success": True,
                        "message": "ok",
                        "to_dict": lambda self: {"echo": kwargs, "session_id": session.id},
                    },
                )()

        registry.register(
            Capability(
                name="demo",
                display_name="演示能力",
                description="测试执行器工厂",
                is_executable=True,
                executor_factory=lambda tool_registry: _ExecutableCapability(),
            )
        )
        session = session_manager.get_or_create("cap-registry-exec")

        result = await registry.execute("demo", session, {"dataset_name": "demo"})

        assert result.success is True
        assert result.to_dict()["echo"]["dataset_name"] == "demo"

    @pytest.mark.asyncio
    async def test_execute_non_executable_capability_raises(self):
        """未接入执行器的能力应抛出明确异常。"""
        registry = CapabilityRegistry()
        registry.register(Capability(name="demo", display_name="演示能力", description="测试"))
        session = session_manager.get_or_create("cap-non-exec")

        with pytest.raises(CapabilityNotExecutableError):
            await registry.execute("demo", session, {})

    @pytest.mark.asyncio
    async def test_execute_without_executor_factory_raises(self):
        """错误标记为可执行但缺少工厂时应抛出配置异常。"""
        registry = CapabilityRegistry()
        registry.register(
            Capability(
                name="broken",
                display_name="异常能力",
                description="缺少执行器工厂",
                is_executable=True,
            )
        )
        session = session_manager.get_or_create("cap-broken")

        with pytest.raises(CapabilityExecutorNotConfiguredError):
            await registry.execute("broken", session, {})


class TestDefaultCapabilities:
    """测试默认能力集。"""

    def test_create_default_capabilities(self):
        """测试创建默认能力集。"""
        caps = create_default_capabilities()
        assert len(caps) > 0

        # 验证必需字段
        for cap in caps:
            assert cap.name
            assert cap.display_name
            assert cap.description
            # 对话驱动型能力（is_executable=False）可以不需要 required_tools
            if cap.is_executable:
                assert len(cap.required_tools) > 0

    def test_default_execute_flags_are_explicit(self):
        """默认能力目录应明确标注哪些能力可直接执行。"""
        caps = {cap.name: cap for cap in create_default_capabilities()}

        assert caps["difference_analysis"].is_executable is True
        assert caps["correlation_analysis"].is_executable is True
        assert caps["data_exploration"].is_executable is False
        assert caps["data_exploration"].execution_message

    def test_default_capabilities_cover_common_needs(self):
        """测试默认能力覆盖常见需求。"""
        caps = create_default_capabilities()
        names = {cap.name for cap in caps}

        expected = {
            "difference_analysis",
            "correlation_analysis",
            "data_exploration",
        }

        assert expected.issubset(names)

    def test_default_capabilities_executor_factory_points_to_executors(self):
        """默认能力应直接装配到 executors，而不是旧兼容层。"""
        from nini.capabilities.executors import DifferenceAnalysisCapability
        from nini.tools.registry import create_default_tool_registry

        caps = {cap.name: cap for cap in create_default_capabilities()}
        registry = create_default_tool_registry()

        executor = caps["difference_analysis"].create_executor(registry)

        assert isinstance(executor, DifferenceAnalysisCapability)

    def test_implementations_module_remains_backward_compatible(self):
        """旧 implementations 导入路径仍应导出同名执行器。"""
        from nini.capabilities.executors import CorrelationAnalysisCapability as ExecutorClass
        from nini.capabilities.implementations import (
            CorrelationAnalysisCapability as CompatibilityClass,
        )

        assert CompatibilityClass is ExecutorClass


@pytest.fixture(autouse=True)
def isolate_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()
    session_manager._sessions.clear()
    yield
    session_manager._sessions.clear()


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """创建能力 API 测试客户端。"""
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()
    session_manager._sessions.clear()
    app = create_app()
    client = LocalASGIClient(app)
    yield client
    client.close()
    session_manager._sessions.clear()


def test_capabilities_api_exposes_execute_contract(client: LocalASGIClient):
    """能力目录 API 应暴露直接执行状态。"""
    resp = client.get("/api/capabilities")
    assert resp.status_code == 200

    data = resp.json()["data"]["capabilities"]
    items = {item["name"]: item for item in data}
    assert items["difference_analysis"]["is_executable"] is True
    assert items["report_generation"]["is_executable"] is False
    assert items["report_generation"]["execution_message"]


def test_capability_to_dict_requires_executor_factory_for_direct_execution():
    """目录层的直接执行标记应与执行器接入状态一致。"""
    cap = Capability(
        name="test_cap",
        display_name="测试能力",
        description="测试",
        is_executable=True,
    )

    assert cap.supports_direct_execution() is False
    assert cap.to_dict()["is_executable"] is False


def test_execute_unsupported_capability_returns_409(client: LocalASGIClient):
    """未实现执行器的能力应返回明确的 409。"""
    resp = client.post(
        "/api/capabilities/report_generation/execute",
        params={"session_id": "cap-test"},
        json={"dataset_name": "demo"},
    )
    assert resp.status_code == 409
    assert "暂未提供" in resp.text or "暂不支持" in resp.text


def test_execute_difference_analysis_capability(client: LocalASGIClient):
    """差异分析能力执行接口应可正常返回结果。"""
    session = session_manager.get_or_create("cap-exec")
    import numpy as np
    import pandas as pd

    np.random.seed(7)
    session.datasets["demo"] = pd.DataFrame(
        {
            "value": np.concatenate([np.random.normal(5, 1, 20), np.random.normal(6, 1, 20)]),
            "group": ["A"] * 20 + ["B"] * 20,
        }
    )

    resp = client.post(
        "/api/capabilities/difference_analysis/execute",
        params={"session_id": "cap-exec"},
        json={
            "dataset_name": "demo",
            "value_column": "value",
            "group_column": "group",
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["success"] is True
    assert payload["data"]["selected_method"] in {"t_test", "mann_whitney"}


def test_execute_capability_api_passes_through_extra_params(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """能力执行 API 应透传注册能力所需的额外参数。"""
    from nini import api as api_package
    from nini.api import routes as routes_module

    registry = CapabilityRegistry()

    class _ExecutableCapability:
        async def execute(self, session, **kwargs):
            return type(
                "_Result",
                (),
                {
                    "success": True,
                    "message": "ok",
                    "to_dict": lambda self: {"session_id": session.id, "echo": kwargs},
                },
            )()

    registry.register(
        Capability(
            name="demo_capability",
            display_name="演示能力",
            description="验证参数透传",
            is_executable=True,
            executor_factory=lambda tool_registry: _ExecutableCapability(),
        )
    )

    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()
    monkeypatch.setattr(routes_module, "_capability_registry", registry)
    monkeypatch.setattr(api_package.routes, "_capability_registry", registry)
    session_manager._sessions.clear()

    app = create_app()
    with LocalASGIClient(app) as client:
        resp = client.post(
            "/api/capabilities/demo_capability/execute",
            params={"session_id": "cap-extra"},
            json={
                "dataset_name": "demo",
                "custom_flag": "keep-me",
                "nested": {"mode": "extended"},
            },
        )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["data"]["echo"]["custom_flag"] == "keep-me"
    assert payload["data"]["echo"]["nested"] == {"mode": "extended"}
