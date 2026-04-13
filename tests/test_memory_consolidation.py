"""会话记忆沉淀单元测试（基于 SQLite MemoryStore）。

覆盖：
- ScientificMemoryProvider.on_session_end() 置信度过滤（只沉淀 >= 0.7 的 Finding）
- 统计结果显著性影响 importance 映射
- 方法决策置信度 >= 0.7 才沉淀
- 空会话写入 0 条
- 异常时不抛出
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_consolidate_high_confidence_finding_is_saved(tmp_path):
    """置信度 >= 0.7 的 Finding 应被写入 SQLite MemoryStore。"""
    from nini.memory.compression import AnalysisMemory, Finding
    from nini.memory.memory_store import MemoryStore
    from nini.memory.scientific_provider import ScientificMemoryProvider

    db = tmp_path / "test.db"
    provider = ScientificMemoryProvider(db_path=db)
    provider._session_id = "sess1"
    provider._store = MemoryStore(db)

    memory = AnalysisMemory(session_id="sess1", dataset_name="data.csv")
    memory.findings.append(Finding(category="normality", summary="数据近似正态", confidence=0.85))

    with patch(
        "nini.memory.compression.list_session_analysis_memories",
        return_value=[memory],
    ):
        await provider.on_session_end([])

    rows = provider._store.search_fts("数据近似正态", top_k=10)
    assert any("数据近似正态" in r.get("content", "") for r in rows)


@pytest.mark.asyncio
async def test_consolidate_low_confidence_finding_is_skipped(tmp_path):
    """置信度 < 0.7 的 Finding 不应写入。"""
    from nini.memory.compression import AnalysisMemory, Finding
    from nini.memory.memory_store import MemoryStore
    from nini.memory.scientific_provider import ScientificMemoryProvider

    db = tmp_path / "test.db"
    provider = ScientificMemoryProvider(db_path=db)
    provider._session_id = "sess2"
    provider._store = MemoryStore(db)

    memory = AnalysisMemory(session_id="sess2", dataset_name="data.csv")
    memory.findings.append(Finding(category="outlier", summary="可能存在异常值", confidence=0.5))

    with patch(
        "nini.memory.compression.list_session_analysis_memories",
        return_value=[memory],
    ):
        await provider.on_session_end([])

    rows = provider._store.search_fts("可能存在异常值", top_k=10)
    assert len(rows) == 0


@pytest.mark.asyncio
async def test_consolidate_statistic_significant_has_higher_importance(tmp_path):
    """显著统计结果的 importance 应高于不显著结果。"""
    from nini.memory.compression import AnalysisMemory, StatisticResult
    from nini.memory.memory_store import MemoryStore
    from nini.memory.scientific_provider import ScientificMemoryProvider

    db = tmp_path / "test.db"
    provider = ScientificMemoryProvider(db_path=db)
    provider._session_id = "sess3"
    provider._store = MemoryStore(db)

    memory = AnalysisMemory(session_id="sess3", dataset_name="data.csv")
    memory.statistics.append(StatisticResult(test_name="t_test", significant=True, p_value=0.02))
    memory.statistics.append(StatisticResult(test_name="anova", significant=False, p_value=0.45))

    with patch(
        "nini.memory.compression.list_session_analysis_memories",
        return_value=[memory],
    ):
        await provider.on_session_end([])

    rows = provider._store.search_fts("", top_k=50)
    t_test_rows = [r for r in rows if "t_test" in r.get("content", "")]
    anova_rows = [r for r in rows if "anova" in r.get("content", "")]

    assert len(t_test_rows) > 0
    assert len(anova_rows) > 0
    assert t_test_rows[0].get("importance", 0) > anova_rows[0].get("importance", 0)


@pytest.mark.asyncio
async def test_consolidate_statistic_with_unknown_significance_does_not_claim_not_significant(
    tmp_path,
):
    """显著性未知时，记忆摘要不应被写成"不显著"。"""
    from nini.memory.compression import AnalysisMemory, StatisticResult
    from nini.memory.memory_store import MemoryStore
    from nini.memory.scientific_provider import ScientificMemoryProvider

    db = tmp_path / "test.db"
    provider = ScientificMemoryProvider(db_path=db)
    provider._session_id = "sess_unknown"
    provider._store = MemoryStore(db)

    memory = AnalysisMemory(session_id="sess_unknown", dataset_name="data.csv")
    memory.statistics.append(StatisticResult(test_name="spearman", p_value=None, significant=None))

    with patch(
        "nini.memory.compression.list_session_analysis_memories",
        return_value=[memory],
    ):
        await provider.on_session_end([])

    rows = provider._store.search_fts("spearman", top_k=10)
    # 确认存在不显著内容不被强制写为 "不显著"（使用 None 作为 significant）
    for r in rows:
        content = r.get("content", "")
        # content 中不应出现"不显著"字样（significant=None，不应被断言为 False）
        assert "不显著" not in content, f"不应出现'不显著'，实际 content={content!r}"


@pytest.mark.asyncio
async def test_consolidate_empty_session_writes_nothing(tmp_path):
    """无分析记忆的会话不应向 MemoryStore 写入任何数据。"""
    from nini.memory.memory_store import MemoryStore
    from nini.memory.scientific_provider import ScientificMemoryProvider

    db = tmp_path / "test.db"
    provider = ScientificMemoryProvider(db_path=db)
    provider._session_id = "empty-session"
    provider._store = MemoryStore(db)

    with patch(
        "nini.memory.compression.list_session_analysis_memories",
        return_value=[],
    ):
        await provider.on_session_end([])

    rows = provider._store.search_fts("", top_k=50)
    assert len(rows) == 0


@pytest.mark.asyncio
async def test_consolidate_exception_does_not_raise(tmp_path):
    """内部异常时应静默，不向调用方抛出。"""
    from nini.memory.memory_store import MemoryStore
    from nini.memory.scientific_provider import ScientificMemoryProvider

    db = tmp_path / "test.db"
    provider = ScientificMemoryProvider(db_path=db)
    provider._session_id = "bad-session"
    provider._store = MemoryStore(db)

    with patch(
        "nini.memory.compression.list_session_analysis_memories",
        side_effect=RuntimeError("模拟错误"),
    ):
        # 不应抛出
        await provider.on_session_end([])
