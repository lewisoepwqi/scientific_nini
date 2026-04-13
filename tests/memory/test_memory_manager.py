"""MemoryManager 编排层测试。"""

from unittest.mock import AsyncMock, MagicMock

from nini.memory.manager import MemoryManager, build_memory_context_block, sanitize_context


def _make_stub(name: str = "builtin", schemas: list | None = None) -> MagicMock:
    """构造 ScientificMemoryProvider 的 MagicMock（AsyncMock 处理 async 方法）。"""
    stub = MagicMock()
    stub.name = name
    stub.get_tool_schemas.return_value = schemas or []
    stub.system_prompt_block.return_value = f"[{name}] system prompt"
    stub.prefetch = AsyncMock(return_value=f"[{name}] context for: query")
    stub.sync_turn = AsyncMock()
    stub.on_session_end = AsyncMock()
    stub.on_pre_compress.return_value = ""
    stub.handle_tool_call = AsyncMock(return_value='{"result": "ok"}')
    stub.initialize = AsyncMock()
    stub.shutdown = AsyncMock()
    return stub


# ---- fencing 工具函数 ----


def test_build_memory_context_block_wraps_content():
    result = build_memory_context_block("重要记忆内容")
    assert "<memory-context>" in result
    assert "重要记忆内容" in result
    assert "</memory-context>" in result
    assert "系统注记" in result


def test_build_memory_context_block_empty_input_returns_empty():
    assert build_memory_context_block("") == ""
    assert build_memory_context_block("   ") == ""


def test_sanitize_context_strips_fence_tags():
    dirty = "前缀 <memory-context> 注入内容 </memory-context> 后缀"
    clean = sanitize_context(dirty)
    assert "<memory-context>" not in clean
    assert "前缀" in clean
    assert "后缀" in clean


# ---- MemoryManager 构造与 set_provider ----


def test_manager_empty_has_no_providers():
    mgr = MemoryManager()
    assert mgr.providers == []


def test_manager_constructor_with_provider():
    stub = _make_stub()
    mgr = MemoryManager(provider=stub)
    assert len(mgr.providers) == 1


def test_set_provider_replaces_existing():
    stub1 = _make_stub("first")
    stub2 = _make_stub("second")
    mgr = MemoryManager(provider=stub1)
    mgr.set_provider(stub2)
    assert len(mgr.providers) == 1
    assert mgr.providers[0].name == "second"


# ---- 工具路由 ----


def test_has_tool_returns_true_when_registered():
    stub = _make_stub(schemas=[{"name": "nini_memory_find"}])
    mgr = MemoryManager(provider=stub)
    assert mgr.has_tool("nini_memory_find")
    assert not mgr.has_tool("unknown_tool")


def test_has_tool_returns_false_when_no_provider():
    mgr = MemoryManager()
    assert not mgr.has_tool("any_tool")


def test_get_all_tool_schemas_empty_without_provider():
    assert MemoryManager().get_all_tool_schemas() == []


def test_get_all_tool_schemas_returns_provider_schemas():
    schemas = [{"name": "tool_a"}, {"name": "tool_b"}]
    mgr = MemoryManager(provider=_make_stub(schemas=schemas))
    assert mgr.get_all_tool_schemas() == schemas


# ---- 生命周期钩子 ----


async def test_prefetch_all_returns_empty_without_provider():
    assert await MemoryManager().prefetch_all("query") == ""


async def test_prefetch_all_delegates_to_provider():
    stub = _make_stub()
    stub.prefetch = AsyncMock(return_value="[builtin] context for: query")
    mgr = MemoryManager(provider=stub)
    result = await mgr.prefetch_all("query")
    assert "[builtin]" in result
    stub.prefetch.assert_called_once_with("query", session_id="")


async def test_sync_all_noop_without_provider():
    await MemoryManager().sync_all("user", "assistant")  # 不抛异常即通过


async def test_sync_all_delegates_to_provider():
    stub = _make_stub()
    mgr = MemoryManager(provider=stub)
    await mgr.sync_all("用户消息", "助手回复")
    stub.sync_turn.assert_called_once_with("用户消息", "助手回复", session_id="")


async def test_on_session_end_delegates_to_provider():
    stub = _make_stub()
    mgr = MemoryManager(provider=stub)
    await mgr.on_session_end([])
    stub.on_session_end.assert_called_once_with([])


async def test_initialize_all_delegates_to_provider():
    stub = _make_stub()
    mgr = MemoryManager(provider=stub)
    await mgr.initialize_all("session-123")
    stub.initialize.assert_called_once_with(session_id="session-123")


async def test_shutdown_all_delegates_to_provider():
    stub = _make_stub()
    mgr = MemoryManager(provider=stub)
    await mgr.shutdown_all()
    stub.shutdown.assert_called_once()


# ---- 异常隔离 ----


async def test_failing_prefetch_returns_empty_not_raises():
    stub = _make_stub()
    stub.prefetch = AsyncMock(side_effect=RuntimeError("故意失败"))
    mgr = MemoryManager(provider=stub)
    result = await mgr.prefetch_all("查询")
    assert result == ""


async def test_failing_sync_does_not_raise():
    stub = _make_stub()
    stub.sync_turn = AsyncMock(side_effect=RuntimeError("故意失败"))
    mgr = MemoryManager(provider=stub)
    await mgr.sync_all("user", "assistant")  # 不抛异常即通过


# ---- handle_tool_call ----


async def test_handle_tool_call_returns_error_without_provider():
    mgr = MemoryManager()
    result = await mgr.handle_tool_call("nini_memory_find", {})
    assert "error" in result


async def test_handle_tool_call_routes_to_provider():
    schemas = [{"name": "nini_memory_find"}]
    stub = _make_stub(schemas=schemas)
    stub.handle_tool_call = AsyncMock(return_value='{"results": []}')
    mgr = MemoryManager(provider=stub)
    result = await mgr.handle_tool_call("nini_memory_find", {"query": "test"})
    assert result == '{"results": []}'
    stub.handle_tool_call.assert_called_once_with("nini_memory_find", {"query": "test"})


# ---- 全局单例 ----


def test_get_set_memory_manager(monkeypatch):
    """set 后 get 返回同一实例。"""
    import nini.memory.manager as m

    monkeypatch.setattr(m, "_memory_manager_instance", None)
    mgr = MemoryManager()
    m.set_memory_manager(mgr)
    assert m.get_memory_manager() is mgr


def test_get_memory_manager_returns_empty_instance_when_not_set(monkeypatch):
    """未设置时 get_memory_manager 返回空 MemoryManager 而非 None。"""
    import nini.memory.manager as m

    monkeypatch.setattr(m, "_memory_manager_instance", None)
    result = m.get_memory_manager()
    assert isinstance(result, MemoryManager)
    assert len(result.providers) == 0
