"""会话记忆沉淀单元测试。

覆盖：
- consolidate_session_memories() 置信度过滤（只沉淀 >= 0.7 的 Finding）
- 统计结果无置信度限制，显著性影响 importance_score
- 方法决策置信度 >= 0.7 才沉淀
- 空会话返回 0
- 异常时不抛出，返回 0
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_store():
    """创建一个模拟的 LongTermMemoryStore。"""
    store = MagicMock()
    store.add_memory = MagicMock()
    return store


@pytest.mark.asyncio
async def test_consolidate_high_confidence_finding_is_saved(mock_store, tmp_path):
    """置信度 >= 0.7 的 Finding 应被写入长期记忆。"""
    from nini.memory.compression import AnalysisMemory, Finding

    memory = AnalysisMemory(session_id="sess1", dataset_name="data.csv")
    memory.findings.append(
        Finding(category="normality", summary="数据近似正态", confidence=0.85)
    )

    # consolidate_session_memories 内部做 from nini.memory.compression import list_session_analysis_memories
    # 因此 patch 路径需指向实际被导入的位置
    with (
        patch(
            "nini.memory.compression.list_session_analysis_memories",
            return_value=[memory],
        ),
        patch(
            "nini.memory.long_term_memory.get_long_term_memory_store",
            return_value=mock_store,
        ),
    ):
        from nini.memory.long_term_memory import consolidate_session_memories

        count = await consolidate_session_memories("sess1")

    assert count >= 1
    mock_store.add_memory.assert_called()


@pytest.mark.asyncio
async def test_consolidate_low_confidence_finding_is_skipped(mock_store, tmp_path):
    """置信度 < 0.7 的 Finding 不应写入长期记忆。"""
    from nini.memory.compression import AnalysisMemory, Finding

    memory = AnalysisMemory(session_id="sess2", dataset_name="data.csv")
    memory.findings.append(
        Finding(category="outlier", summary="可能存在异常值", confidence=0.5)
    )

    with (
        patch(
            "nini.memory.compression.list_session_analysis_memories",
            return_value=[memory],
        ),
        patch(
            "nini.memory.long_term_memory.get_long_term_memory_store",
            return_value=mock_store,
        ),
    ):
        from nini.memory.long_term_memory import consolidate_session_memories

        count = await consolidate_session_memories("sess2")

    # 低置信度 Finding 不写入，统计为 0
    assert count == 0


@pytest.mark.asyncio
async def test_consolidate_statistic_significant_has_higher_importance(mock_store):
    """显著统计结果的 importance_score 应高于不显著结果。"""
    from nini.memory.compression import AnalysisMemory, StatisticResult

    memory = AnalysisMemory(session_id="sess3", dataset_name="data.csv")
    memory.statistics.append(
        StatisticResult(test_name="t_test", significant=True, p_value=0.02)
    )
    memory.statistics.append(
        StatisticResult(test_name="anova", significant=False, p_value=0.45)
    )

    importance_scores = []
    mock_store.add_memory = MagicMock(
        side_effect=lambda **kw: importance_scores.append(kw.get("importance_score", 0))
    )

    with (
        patch(
            "nini.memory.compression.list_session_analysis_memories",
            return_value=[memory],
        ),
        patch(
            "nini.memory.long_term_memory.get_long_term_memory_store",
            return_value=mock_store,
        ),
    ):
        from nini.memory.long_term_memory import consolidate_session_memories

        await consolidate_session_memories("sess3")

    # 显著结果的分值应高于不显著结果
    assert len(importance_scores) == 2
    assert importance_scores[0] > importance_scores[1]


@pytest.mark.asyncio
async def test_consolidate_empty_session_returns_zero():
    """无分析记忆的会话应返回 0。"""
    with patch(
        "nini.memory.compression.list_session_analysis_memories",
        return_value=[],
    ):
        from nini.memory.long_term_memory import consolidate_session_memories

        count = await consolidate_session_memories("empty-session")

    assert count == 0


@pytest.mark.asyncio
async def test_consolidate_exception_does_not_raise():
    """内部异常时应静默返回 0，不抛出。"""
    with patch(
        "nini.memory.compression.list_session_analysis_memories",
        side_effect=RuntimeError("模拟错误"),
    ):
        from nini.memory.long_term_memory import consolidate_session_memories

        count = await consolidate_session_memories("bad-session")

    assert count == 0
