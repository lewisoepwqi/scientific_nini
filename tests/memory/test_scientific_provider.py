"""ScientificMemoryProvider 生命周期测试。"""
from pathlib import Path

import pytest

from nini.memory.scientific_provider import ScientificMemoryProvider


@pytest.fixture
async def provider(tmp_path: Path) -> ScientificMemoryProvider:
    """已初始化的 provider fixture。"""
    p = ScientificMemoryProvider(db_path=tmp_path / "nini_memory.db")
    await p.initialize(session_id="sess001")
    return p


# ---- 基础属性 ----

def test_provider_name_is_builtin():
    """name 属性必须返回 'builtin'。"""
    p = ScientificMemoryProvider(db_path=Path(":memory:"))
    assert p.name == "builtin"


async def test_initialize_creates_db(tmp_path: Path):
    """initialize 应创建数据库文件。"""
    db_path = tmp_path / "nini_memory.db"
    p = ScientificMemoryProvider(db_path=db_path)
    await p.initialize(session_id="sess001")
    assert db_path.exists()


async def test_provider_has_two_tool_schemas(provider: ScientificMemoryProvider):
    """get_tool_schemas 应返回 nini_memory_find 和 nini_memory_save。"""
    schemas = provider.get_tool_schemas()
    names = {s["name"] for s in schemas}
    assert "nini_memory_find" in names
    assert "nini_memory_save" in names


# ---- system_prompt_block ----

async def test_system_prompt_block_safe_before_initialize():
    """initialize 前调用 system_prompt_block 不应抛出异常。"""
    p = ScientificMemoryProvider(db_path=Path(":memory:"))
    block = p.system_prompt_block()
    assert isinstance(block, str)


async def test_system_prompt_block_includes_profile(provider: ScientificMemoryProvider):
    """有研究画像时，system_prompt_block 应包含画像内容。"""
    provider._store.upsert_profile(
        "default",
        data_json={"domain": "psychology"},
        narrative_md="## 研究偏好摘要\n- 研究领域：心理学\n- α=0.05",
    )
    block = provider.system_prompt_block()
    assert "心理学" in block


# ---- prefetch 测试 ----


async def test_prefetch_returns_empty_when_no_facts(provider: ScientificMemoryProvider):
    """facts 表为空时 prefetch 返回空字符串。"""
    result = await provider.prefetch("t检验")
    assert result == ""


async def test_prefetch_returns_relevant_facts(provider: ScientificMemoryProvider):
    """facts 表有相关记录时 prefetch 应返回包含内容的字符串。"""
    provider._store.upsert_fact(
        content="t(58)=3.14, p=0.002，独立样本 t 检验结果显著",
        memory_type="statistic",
        summary="t检验显著",
        importance=0.8,
        sci_metadata={"p_value": 0.002, "dataset_name": "survey.csv"},
    )
    result = await provider.prefetch("t检验")
    assert "t(58)=3.14" in result or "t检验" in result


async def test_prefetch_applies_fencing(provider: ScientificMemoryProvider):
    """prefetch 返回的内容应包含 memory-context 标签。"""
    provider._store.upsert_fact(
        content="显著性结果 p=0.001",
        memory_type="statistic",
        summary="显著",
        importance=0.9,
    )
    result = await provider.prefetch("显著性")
    if result:
        assert "<memory-context>" in result
        assert "</memory-context>" in result
