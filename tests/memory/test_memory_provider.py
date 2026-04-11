"""MemoryProvider ABC 测试。"""

import asyncio

from nini.memory.provider import MemoryProvider


def test_cannot_instantiate_abstract_provider():
    """抽象类不可直接实例化。"""
    try:
        MemoryProvider()  # type: ignore[abstract]
        assert False, "应抛出 TypeError"
    except TypeError:
        pass


def test_incomplete_subclass_cannot_instantiate():
    """未实现全部抽象方法的子类不可实例化。"""

    class Incomplete(MemoryProvider):
        pass

    try:
        Incomplete()
        assert False, "应抛出 TypeError"
    except TypeError:
        pass


def test_minimal_provider_instantiates():
    """实现全部抽象方法的子类可实例化，可选钩子有合理默认值。"""

    class Minimal(MemoryProvider):
        @property
        def name(self) -> str:
            return "test"

        async def initialize(self, session_id: str, **kwargs) -> None:
            pass

        def get_tool_schemas(self) -> list:
            return []

    p = Minimal()
    assert p.name == "test"
    assert p.system_prompt_block() == ""
    assert p.on_pre_compress([]) == ""
    assert asyncio.run(p.prefetch("test query")) == ""
