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


# ---- sync_turn 测试 ----


async def test_sync_turn_extracts_statistical_values(provider: ScientificMemoryProvider):
    """含统计数值的回复应被提取为 statistic 记忆。"""
    extracted = provider._extract_from_text(
        "独立样本 t 检验：t(58)=3.14, p=0.002, Cohen's d=0.45，差异显著。",
        "sess001",
    )
    assert len(extracted) >= 1
    assert any("p" in item["content"].lower() for item in extracted)


async def test_sync_turn_ignores_no_stat_content(provider: ScientificMemoryProvider):
    """普通对话不应触发统计提取。"""
    extracted = provider._extract_from_text("你好！今天天气怎么样？", "sess001")
    assert extracted == []


async def test_sync_turn_extracts_conclusion(provider: ScientificMemoryProvider):
    """含结论标记的文本应提取为 finding 记忆。"""
    extracted = provider._extract_from_text(
        "结论：两组之间存在统计学上的显著差异，建议进一步分析。",
        "sess001",
    )
    assert any(item["memory_type"] == "finding" for item in extracted)


async def test_sync_turn_does_not_raise(provider: ScientificMemoryProvider):
    """sync_turn 异常不应向外抛出。"""
    # 关闭 store 后调用，模拟内部错误
    provider._store.close()
    provider._store._conn = None  # type: ignore[assignment]
    await provider.sync_turn("用户", "p=0.001 显著", session_id="sess001")  # 不抛出


# ---- on_session_end 测试 ----


async def test_on_session_end_consolidates_statistics(provider: ScientificMemoryProvider):
    """显著统计结果应被沉淀到 facts 表。"""
    from unittest.mock import patch

    from nini.memory.compression import AnalysisMemory, StatisticResult

    memory = AnalysisMemory(
        session_id="sess001",
        dataset_name="survey_2024.csv",
        statistics=[
            StatisticResult(
                test_name="独立样本t检验",
                test_statistic=3.14,
                p_value=0.002,
                effect_size=0.45,
                effect_type="cohen_d",
                significant=True,
            )
        ],
    )
    with patch(
        "nini.memory.compression.list_session_analysis_memories",
        return_value=[memory],
    ):
        await provider.on_session_end([])

    results = provider._store.filter_by_sci(max_p_value=0.05)
    assert len(results) >= 1


async def test_on_session_end_consolidates_findings(provider: ScientificMemoryProvider):
    """高置信度 Finding 应被沉淀到 facts 表。"""
    from unittest.mock import patch

    from nini.memory.compression import AnalysisMemory, Finding

    memory = AnalysisMemory(
        session_id="sess001",
        dataset_name="data.csv",
        findings=[Finding(category="distribution", summary="正偏斜分布", confidence=0.85)],
    )
    with patch(
        "nini.memory.compression.list_session_analysis_memories",
        return_value=[memory],
    ):
        await provider.on_session_end([])

    results = provider._store.search_fts("正偏斜")
    assert any("正偏斜" in r["content"] or "正偏斜" in r.get("summary", "") for r in results)


async def test_on_session_end_skips_low_confidence(provider: ScientificMemoryProvider):
    """置信度不足 0.7 的 finding 不应沉淀。"""
    from unittest.mock import patch

    from nini.memory.compression import AnalysisMemory, Finding

    memory = AnalysisMemory(
        session_id="sess001",
        dataset_name="data.csv",
        findings=[Finding(category="noise", summary="不确定的发现低置信度", confidence=0.3)],
    )
    with patch(
        "nini.memory.compression.list_session_analysis_memories",
        return_value=[memory],
    ):
        await provider.on_session_end([])

    results = provider._store.search_fts("不确定的发现低置信度")
    assert len(results) == 0


async def test_on_session_end_is_graceful_on_error(provider: ScientificMemoryProvider):
    """on_session_end 遇到异常不应向外抛出。"""
    from unittest.mock import patch

    with patch(
        "nini.memory.compression.list_session_analysis_memories",
        side_effect=RuntimeError("故意失败"),
    ):
        await provider.on_session_end([])  # 不应抛出


# ---- on_pre_compress 测试 ----


def test_on_pre_compress_extracts_stat_lines(provider: ScientificMemoryProvider):
    """含统计数值的 assistant 消息应触发保留提示。"""
    messages = [
        {"role": "user", "content": "分析这个数据集"},
        {"role": "assistant", "content": "t(58)=3.14, p=0.002, Cohen's d=0.45，差异显著。"},
    ]
    result = provider.on_pre_compress(messages)
    assert "p=0.002" in result or "3.14" in result
    assert "保留" in result or "必须" in result


def test_on_pre_compress_empty_when_no_stats(provider: ScientificMemoryProvider):
    """无统计数值的消息应返回空字符串。"""
    messages = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好！有什么我可以帮你的？"},
    ]
    result = provider.on_pre_compress(messages)
    assert result == ""


# ---- 工具调用测试 ----


async def test_tool_find_returns_results(provider: ScientificMemoryProvider):
    """nini_memory_find 应返回含 success=True 和 results 的 JSON。"""
    import json as _json

    provider._store.upsert_fact(
        content="t(58)=3.14, p=0.002",
        memory_type="statistic",
        summary="t检验显著",
        importance=0.8,
    )
    result = await provider.handle_tool_call("nini_memory_find", {"query": "t检验"})
    data = _json.loads(result)
    assert data["success"] is True
    assert "results" in data


async def test_tool_save_stores_fact(provider: ScientificMemoryProvider):
    """nini_memory_save 应写入 facts 并返回含 id 的 JSON。"""
    import json as _json

    result = await provider.handle_tool_call(
        "nini_memory_save",
        {
            "content": "数据正态性不满足，应使用非参数检验",
            "memory_type": "decision",
            "importance": 0.8,
        },
    )
    data = _json.loads(result)
    assert data["success"] is True
    assert "id" in data


async def test_tool_save_empty_content_returns_error(provider: ScientificMemoryProvider):
    """nini_memory_save 空 content 应返回 success=False。"""
    import json as _json

    result = await provider.handle_tool_call("nini_memory_save", {"content": ""})
    data = _json.loads(result)
    assert data["success"] is False


async def test_tool_find_with_p_value_filter(provider: ScientificMemoryProvider):
    """nini_memory_find 的 max_p_value 过滤应只返回显著结果。"""
    import json as _json

    provider._store.upsert_fact(
        content="显著结果",
        memory_type="statistic",
        sci_metadata={"p_value": 0.001},
    )
    provider._store.upsert_fact(
        content="不显著结果",
        memory_type="statistic",
        sci_metadata={"p_value": 0.4},
    )
    result = await provider.handle_tool_call(
        "nini_memory_find", {"query": "结果", "max_p_value": 0.05}
    )
    data = _json.loads(result)
    assert data["success"] is True
    contents = [r["content"] for r in data["results"]]
    assert any("显著结果" in c for c in contents)
    assert not any("不显著结果" in c for c in contents)


async def test_tool_returns_error_when_not_initialized():
    """未初始化时工具调用应返回 success=False 而非抛出异常。"""
    import json as _json
    from pathlib import Path

    p = ScientificMemoryProvider(db_path=Path(":memory:"))
    result = await p.handle_tool_call("nini_memory_find", {"query": "test"})
    data = _json.loads(result)
    assert data["success"] is False


def test_system_prompt_block_contains_tool_names():
    """system_prompt_block 应包含 nini_memory_find 和 nini_memory_save。"""
    from pathlib import Path

    p = ScientificMemoryProvider(db_path=Path(":memory:"))
    block = p.system_prompt_block()
    assert "nini_memory_find" in block
    assert "nini_memory_save" in block
