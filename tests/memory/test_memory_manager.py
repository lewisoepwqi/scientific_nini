"""MemoryManager 编排层测试。"""

from nini.memory.manager import MemoryManager, build_memory_context_block, sanitize_context
from nini.memory.provider import MemoryProvider


class StubProvider(MemoryProvider):
    """测试用 stub，记录调用次数。"""

    def __init__(self, name_val: str, schemas: list | None = None) -> None:
        self._name = name_val
        self._schemas = schemas or []
        self.prefetch_calls: list[str] = []
        self.sync_calls: int = 0
        self.session_end_calls: int = 0

    @property
    def name(self) -> str:
        return self._name

    async def initialize(self, session_id: str, **kwargs) -> None:
        pass

    def get_tool_schemas(self) -> list:
        return self._schemas

    async def prefetch(self, query: str, *, session_id: str = "") -> str:
        self.prefetch_calls.append(query)
        return f"[{self._name}] context for: {query}"

    async def sync_turn(
        self, user_content: str, assistant_content: str, *, session_id: str = ""
    ) -> None:
        self.sync_calls += 1

    async def on_session_end(self, messages: list) -> None:
        self.session_end_calls += 1


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


# ---- MemoryManager 注册规则 ----


def test_manager_accepts_builtin_provider():
    mgr = MemoryManager()
    builtin = StubProvider("builtin")
    mgr.add_provider(builtin)
    assert len(mgr.providers) == 1


def test_manager_accepts_multiple_external_providers():
    """允许注册任意数量外部 provider。"""
    mgr = MemoryManager()
    mgr.add_provider(StubProvider("builtin"))
    mgr.add_provider(StubProvider("ext1"))
    mgr.add_provider(StubProvider("ext2"))
    assert len(mgr.providers) == 3
    assert mgr.providers[1].name == "ext1"
    assert mgr.providers[2].name == "ext2"


def test_manager_tool_routing():
    mgr = MemoryManager()
    mgr.add_provider(StubProvider("builtin", schemas=[{"name": "tool_a"}]))
    assert mgr.has_tool("tool_a")
    assert not mgr.has_tool("tool_b")


# ---- 生命周期调用 ----


async def test_prefetch_all_combines_results():
    mgr = MemoryManager()
    mgr.add_provider(StubProvider("builtin"))
    mgr.add_provider(StubProvider("ext1"))
    result = await mgr.prefetch_all("查询内容")
    assert "[builtin]" in result
    assert "[ext1]" in result


async def test_sync_all_calls_all_providers():
    mgr = MemoryManager()
    p1 = StubProvider("builtin")
    p2 = StubProvider("ext1")
    mgr.add_provider(p1)
    mgr.add_provider(p2)
    await mgr.sync_all("用户消息", "助手回复")
    assert p1.sync_calls == 1
    assert p2.sync_calls == 1


async def test_on_session_end_calls_all_providers():
    mgr = MemoryManager()
    p1 = StubProvider("builtin")
    mgr.add_provider(p1)
    await mgr.on_session_end([])
    assert p1.session_end_calls == 1


async def test_failing_provider_does_not_block_others():
    """Provider 异常不应阻塞其他 Provider。"""

    class BrokenProvider(MemoryProvider):
        @property
        def name(self) -> str:
            return "broken"

        async def initialize(self, session_id: str, **kwargs) -> None:
            pass

        async def prefetch(self, query: str, *, session_id: str = "") -> str:
            raise RuntimeError("故意失败")

        def get_tool_schemas(self) -> list:
            return []

    mgr = MemoryManager()
    broken = BrokenProvider()
    good = StubProvider("builtin")
    mgr.add_provider(broken)
    mgr.add_provider(good)
    result = await mgr.prefetch_all("查询")
    assert "[builtin]" in result


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
