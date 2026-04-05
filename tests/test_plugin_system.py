"""插件系统测试：Plugin 接口约束、Registry 注册/查询/生命周期、失败隔离。"""

from __future__ import annotations

import asyncio

import pytest

from nini.plugins.base import DegradationInfo, Plugin
from nini.plugins.registry import PluginRegistry

# ---- 测试辅助插件 ----


class _AlwaysAvailablePlugin(Plugin):
    """可用插件桩：始终可用，记录 initialize/shutdown 调用次数。"""

    name = "always_available"
    version = "1.0"
    description = "测试用可用插件"

    def __init__(self) -> None:
        self.init_count = 0
        self.shutdown_count = 0

    async def is_available(self) -> bool:
        return True

    async def initialize(self) -> None:
        self.init_count += 1

    async def shutdown(self) -> None:
        self.shutdown_count += 1

    def get_degradation_info(self) -> DegradationInfo | None:
        return None


class _UnavailablePlugin(Plugin):
    """不可用插件桩：始终不可用，返回降级信息。"""

    name = "unavailable"
    version = "1.0"
    description = "测试用不可用插件"

    async def is_available(self) -> bool:
        return False

    async def initialize(self) -> None:
        pass

    def get_degradation_info(self) -> DegradationInfo:
        return DegradationInfo(
            plugin_name=self.name,
            reason="测试：无可用服务",
            impact="无法执行相关操作",
            alternatives=["使用替代方案 A"],
        )


class _FailingPlugin(Plugin):
    """初始化失败插件桩：initialize() 抛出异常。"""

    name = "failing"
    version = "1.0"
    description = "测试用初始化失败插件"

    async def is_available(self) -> bool:
        return True

    async def initialize(self) -> None:
        raise RuntimeError("故意抛出的初始化异常")


class _SlowPlugin(Plugin):
    """超时插件桩：initialize() 阻塞超过超时阈值。"""

    name = "slow"
    version = "1.0"
    description = "测试用超时插件"

    async def is_available(self) -> bool:
        return True

    async def initialize(self) -> None:
        # 阻塞远超 5 秒超时，由测试用 monkeypatch 缩短超时
        await asyncio.sleep(100)


# ---- DegradationInfo 测试 ----


def test_degradation_info_instantiation() -> None:
    """DegradationInfo 可实例化，alternatives 默认为空列表。"""
    info = DegradationInfo(
        plugin_name="network",
        reason="无网络连接",
        impact="无法在线检索文献",
    )
    assert info.plugin_name == "network"
    assert info.reason == "无网络连接"
    assert info.impact == "无法在线检索文献"
    assert info.alternatives == []


def test_degradation_info_with_alternatives() -> None:
    """DegradationInfo 可携带替代建议列表。"""
    info = DegradationInfo(
        plugin_name="network",
        reason="网络超时",
        impact="联网功能不可用",
        alternatives=["手动上传 PDF", "粘贴文本"],
    )
    assert len(info.alternatives) == 2


# ---- Plugin 接口约束测试 ----


def test_plugin_subclass_missing_abstract_methods_raises_type_error() -> None:
    """未实现 is_available() 或 initialize() 的子类实例化时抛出 TypeError。"""

    class _IncompletePlugin(Plugin):
        name = "incomplete"
        version = "1.0"
        description = "不完整的插件"

        async def is_available(self) -> bool:
            return True

        # 故意不实现 initialize()

    with pytest.raises(TypeError):
        _IncompletePlugin()


def test_plugin_default_shutdown_does_not_raise() -> None:
    """未覆写 shutdown() 的子类调用不报错（默认空操作）。"""

    class _MinimalPlugin(Plugin):
        name = "minimal"
        version = "1.0"
        description = "最小插件"

        async def is_available(self) -> bool:
            return True

        async def initialize(self) -> None:
            pass

    plugin = _MinimalPlugin()
    asyncio.run(plugin.shutdown())  # 不应抛出异常


def test_plugin_default_get_degradation_info_returns_none() -> None:
    """未覆写 get_degradation_info() 的子类默认返回 None。"""

    class _MinimalPlugin(Plugin):
        name = "minimal"
        version = "1.0"
        description = "最小插件"

        async def is_available(self) -> bool:
            return True

        async def initialize(self) -> None:
            pass

    plugin = _MinimalPlugin()
    assert plugin.get_degradation_info() is None


# ---- PluginRegistry 注册与查询测试 ----


def test_registry_register_and_get() -> None:
    """注册插件后可通过名称查询到。"""
    registry = PluginRegistry()
    plugin = _AlwaysAvailablePlugin()
    registry.register(plugin)
    assert registry.get("always_available") is plugin


def test_registry_get_nonexistent_returns_none() -> None:
    """查询不存在的插件返回 None。"""
    registry = PluginRegistry()
    assert registry.get("nonexistent") is None


# ---- PluginRegistry 生命周期测试 ----


@pytest.mark.asyncio
async def test_initialize_all_marks_available_plugin() -> None:
    """可用插件初始化后出现在 list_available() 中。"""
    registry = PluginRegistry()
    plugin = _AlwaysAvailablePlugin()
    registry.register(plugin)
    await registry.initialize_all()
    assert plugin in registry.list_available()
    assert plugin.init_count == 1


@pytest.mark.asyncio
async def test_initialize_all_marks_unavailable_plugin() -> None:
    """不可用插件不出现在 list_available()，出现在 list_unavailable()。"""
    registry = PluginRegistry()
    plugin = _UnavailablePlugin()
    registry.register(plugin)
    await registry.initialize_all()
    assert plugin not in registry.list_available()
    unavailable = registry.list_unavailable()
    names = [p.name for p, _ in unavailable]
    assert "unavailable" in names


@pytest.mark.asyncio
async def test_initialize_all_failure_isolation() -> None:
    """单个插件初始化失败不阻断其他插件。"""
    registry = PluginRegistry()
    failing_plugin = _FailingPlugin()
    ok_plugin = _AlwaysAvailablePlugin()
    registry.register(failing_plugin)
    registry.register(ok_plugin)

    # 不抛出异常
    await registry.initialize_all()

    # failing 标记为不可用
    assert failing_plugin not in registry.list_available()
    # ok 正常初始化
    assert ok_plugin in registry.list_available()
    assert ok_plugin.init_count == 1


@pytest.mark.asyncio
async def test_initialize_all_timeout_marks_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """初始化超时的插件被标记为不可用。"""
    import nini.plugins.registry as registry_module

    # 将超时阈值缩短为 0.1 秒，避免测试等待 5 秒
    monkeypatch.setattr(registry_module, "_PLUGIN_INIT_TIMEOUT", 0.1)

    registry = PluginRegistry()
    slow_plugin = _SlowPlugin()
    registry.register(slow_plugin)

    await registry.initialize_all()

    assert slow_plugin not in registry.list_available()


@pytest.mark.asyncio
async def test_shutdown_all_calls_shutdown_on_all_plugins() -> None:
    """shutdown_all() 调用所有已注册插件的 shutdown()。"""
    registry = PluginRegistry()
    p1 = _AlwaysAvailablePlugin()
    p1.name = "plugin_1"  # type: ignore[assignment]
    p2 = _AlwaysAvailablePlugin()
    p2.name = "plugin_2"  # type: ignore[assignment]
    registry.register(p1)
    registry.register(p2)
    await registry.initialize_all()
    await registry.shutdown_all()
    assert p1.shutdown_count == 1
    assert p2.shutdown_count == 1


# ---- 降级信息查询测试 ----


@pytest.mark.asyncio
async def test_list_unavailable_returns_degradation_info() -> None:
    """list_unavailable() 返回插件及其降级信息。"""
    registry = PluginRegistry()
    plugin = _UnavailablePlugin()
    registry.register(plugin)
    await registry.initialize_all()

    unavailable = registry.list_unavailable()
    assert len(unavailable) == 1
    p, info = unavailable[0]
    assert p is plugin
    assert info is not None
    assert "测试" in info.reason
    assert len(info.alternatives) > 0
