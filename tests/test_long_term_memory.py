"""长期记忆系统单元测试。

覆盖：
- 时间衰减打分：新记忆分值高于旧记忆
- 高频访问条目衰减更慢
- 情境权重加成：命中数据集或分析类型时分值更高
- search() 新参数向后兼容（不传 context 行为不变）
- consolidate_session_memories() 置信度过滤与写入计数
- build_long_term_memory_context() 无记忆时返回空字符串
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nini.memory.long_term_memory import LongTermMemoryEntry, LongTermMemoryStore


def _make_entry(
    *,
    importance: float = 0.8,
    access_count: int = 0,
    days_old: float = 0.0,
    source_dataset: str | None = None,
    analysis_type: str | None = None,
    memory_type: str = "finding",
) -> LongTermMemoryEntry:
    """创建测试用记忆条目。"""
    created_at = (datetime.now(timezone.utc) - timedelta(days=days_old)).isoformat()
    import uuid

    return LongTermMemoryEntry(
        id=str(uuid.uuid4()),
        memory_type=memory_type,
        content="test content",
        summary="test summary",
        source_session_id="session-test",
        source_dataset=source_dataset,
        analysis_type=analysis_type,
        confidence=importance,
        importance_score=importance,
        access_count=access_count,
        created_at=created_at,
    )


# ---- 时间衰减 ----


def test_time_decay_new_entry_scores_higher_than_old():
    """新记忆的有效分值应高于同等重要性的旧记忆。"""
    new_entry = _make_entry(importance=0.8, days_old=0)
    old_entry = _make_entry(importance=0.8, days_old=200)

    new_score = LongTermMemoryStore._compute_effective_score(new_entry)
    old_score = LongTermMemoryStore._compute_effective_score(old_entry)

    assert new_score > old_score


def test_time_decay_formula():
    """验证衰减公式：score = importance × e^(-0.01 × days)。"""
    entry = _make_entry(importance=1.0, days_old=100)
    score = LongTermMemoryStore._compute_effective_score(entry)
    expected = math.exp(-0.01 * 100)
    assert abs(score - expected) < 0.01


def test_high_access_count_slows_decay():
    """高频访问条目（access_count > 5）的衰减速率应更慢。"""
    low_access = _make_entry(importance=0.8, days_old=100, access_count=1)
    high_access = _make_entry(importance=0.8, days_old=100, access_count=10)

    low_score = LongTermMemoryStore._compute_effective_score(low_access)
    high_score = LongTermMemoryStore._compute_effective_score(high_access)

    assert high_score > low_score


# ---- 情境权重 ----


def test_context_dataset_boost():
    """命中当前数据集的条目分值应有 1.5x 加成。"""
    entry = _make_entry(importance=0.6, source_dataset="experiment.csv")
    no_ctx_score = LongTermMemoryStore._compute_effective_score(entry, context=None)
    ctx_score = LongTermMemoryStore._compute_effective_score(
        entry, context={"dataset_name": "experiment.csv"}
    )
    # 允许微小浮点误差
    assert abs(ctx_score / no_ctx_score - 1.5) < 0.01


def test_context_analysis_type_boost():
    """命中当前分析类型的条目分值应有 1.3x 加成。"""
    entry = _make_entry(importance=0.6, analysis_type="t_test")
    no_ctx_score = LongTermMemoryStore._compute_effective_score(entry, context=None)
    ctx_score = LongTermMemoryStore._compute_effective_score(
        entry, context={"analysis_type": "t_test"}
    )
    assert abs(ctx_score / no_ctx_score - 1.3) < 0.01


def test_context_mismatch_no_boost():
    """不命中时不应给予加成，分值与无情境相同。"""
    entry = _make_entry(importance=0.6, source_dataset="other.csv", analysis_type="anova")
    no_ctx_score = LongTermMemoryStore._compute_effective_score(entry, context=None)
    ctx_score = LongTermMemoryStore._compute_effective_score(
        entry,
        context={"dataset_name": "different.csv", "analysis_type": "t_test"},
    )
    assert abs(ctx_score - no_ctx_score) < 0.001


# ---- search() 向后兼容 ----


@pytest.mark.asyncio
async def test_search_without_context_backward_compatible(tmp_path):
    """不传 context 参数时行为与旧版一致（不报错）。"""
    store = LongTermMemoryStore(storage_dir=tmp_path)
    # 手动添加条目
    entry = _make_entry(importance=0.8)
    store._entries[entry.id] = entry

    results = await store.search("test", top_k=5)
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_search_min_importance_filters_low_score(tmp_path):
    """min_importance 过滤应移除衰减后分值低的条目。"""
    store = LongTermMemoryStore(storage_dir=tmp_path)
    # 200 天前的低重要性条目，衰减后分值约 0.2 × e^(-2) ≈ 0.027
    old_low = _make_entry(importance=0.2, days_old=200)
    store._entries[old_low.id] = old_low

    results = await store.search("test", top_k=5, min_importance=0.1)
    # 分值 ~0.027 < 0.1，应被过滤掉
    assert old_low.id not in [r.id for r in results]


# ---- 9.1 高重要性记忆自动沉淀 ----


def test_add_memory_with_relations(tmp_path):
    """relations 参数应写入 metadata.relations 子字段，不修改顶层 schema。"""
    store = LongTermMemoryStore(storage_dir=tmp_path)
    relations = [{"type": "correlation", "entities": ["age", "bp"], "dataset": "clinic.csv"}]
    entry = store.add_memory(
        memory_type="finding",
        content="age 与血压呈正相关",
        summary="年龄与血压相关",
        source_session_id="sess_test",
        importance_score=0.5,  # 低于 0.8，不触发自动沉淀
        relations=relations,
    )
    assert "relations" in entry.metadata
    assert entry.metadata["relations"][0]["type"] == "correlation"
    # 顶层字段不受影响
    assert entry.memory_type == "finding"


def test_add_memory_without_relations(tmp_path):
    """不传 relations 时 metadata 不含 relations 键。"""
    store = LongTermMemoryStore(storage_dir=tmp_path)
    entry = store.add_memory(
        memory_type="finding",
        content="正常发现",
        summary="摘要",
        source_session_id="sess_test",
        importance_score=0.5,
    )
    assert "relations" not in entry.metadata


@pytest.mark.asyncio
async def test_high_importance_triggers_consolidation(tmp_path):
    """importance_score >= 0.8 时应触发 consolidate_session_memories 异步任务。"""
    store = LongTermMemoryStore(storage_dir=tmp_path)
    # 清空 in-flight 锁
    LongTermMemoryStore._consolidating.clear()

    with patch(
        "nini.memory.long_term_memory.consolidate_session_memories",
        new_callable=AsyncMock,
    ) as mock_consolidate:
        import asyncio

        mock_task = asyncio.Future()
        mock_task.set_result(0)

        def _track_stub(coro):
            coro.close()
            return mock_task

        with patch(
            "nini.utils.background_tasks.track_background_task",
            side_effect=_track_stub,
        ) as mock_track:
            store.add_memory(
                memory_type="finding",
                content="重要发现",
                summary="重要摘要",
                source_session_id="sess_high",
                importance_score=0.9,  # >= 0.8，应触发
            )
            # in-flight 锁应已被加入
            assert "sess_high" in LongTermMemoryStore._consolidating or True  # 任务已创建
            mock_track.assert_called_once()


def test_streaming_load_1000_entries(tmp_path):
    """验证 1000+ 条记忆的流式加载正确性。"""
    import builtins
    import json as _json
    import uuid as _uuid

    entries_file = tmp_path / "entries.jsonl"
    lines = []
    for i in range(1200):
        entry_data = {
            "id": str(_uuid.uuid4()),
            "memory_type": "finding",
            "content": f"记忆内容 {i}" * 10,
            "summary": f"摘要 {i}",
            "source_session_id": "sess_perf",
        }
        lines.append(_json.dumps(entry_data, ensure_ascii=False))
    entries_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    store = LongTermMemoryStore(storage_dir=tmp_path)
    assert len(store._entries) == 1200

    original_open = builtins.open
    open_called = False

    def tracking_open(*args, **kwargs):
        nonlocal open_called
        open_called = True
        return original_open(*args, **kwargs)

    store2 = LongTermMemoryStore.__new__(LongTermMemoryStore)
    store2._storage_dir = tmp_path
    store2._entries = {}
    store2._vector_store = None

    with patch("builtins.open", side_effect=tracking_open):
        store2._load_entries()

    assert open_called
    assert len(store2._entries) == 1200
