"""MemoryStore SQLite 存储层测试。"""

from pathlib import Path

import pytest

from nini.memory.memory_store import MemoryStore


@pytest.fixture
def store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(tmp_path / "test.db")


def test_store_creates_facts_table(store: MemoryStore):
    """facts 表和 research_profiles 表应被创建。"""
    tables = {
        row[0]
        for row in store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "facts" in tables
    assert "research_profiles" in tables


def test_store_enables_wal_mode(store: MemoryStore):
    """应启用 WAL 模式。"""
    row = store._conn.execute("PRAGMA journal_mode").fetchone()
    assert row[0] == "wal"


def test_store_facts_has_required_columns(store: MemoryStore):
    """facts 表必须包含所有必要列。"""
    cols = {row[1] for row in store._conn.execute("PRAGMA table_info(facts)").fetchall()}
    required = {
        "id",
        "content",
        "memory_type",
        "summary",
        "tags",
        "importance",
        "trust_score",
        "source_session_id",
        "created_at",
        "updated_at",
        "access_count",
        "dedup_key",
        "sci_metadata",
    }
    assert required <= cols


# ---- 写操作测试 ----


def test_upsert_fact_returns_uuid(store: MemoryStore):
    """首次写入返回 36 字符 UUID。"""
    fact_id = store.upsert_fact(content="t(58)=3.14, p=0.002", memory_type="statistic")
    assert len(fact_id) == 36


def test_upsert_fact_dedup_returns_same_id(store: MemoryStore):
    """相同内容+类型+dataset 的 fact 不重复写入，返回已有 id。"""
    id1 = store.upsert_fact(
        content="正偏斜分布",
        memory_type="finding",
        sci_metadata={"dataset_name": "data.csv"},
    )
    id2 = store.upsert_fact(
        content="正偏斜分布",
        memory_type="finding",
        sci_metadata={"dataset_name": "data.csv"},
    )
    assert id1 == id2


def test_upsert_fact_different_content_creates_new_entry(store: MemoryStore):
    """不同内容创建独立条目。"""
    id1 = store.upsert_fact(content="发现 A", memory_type="finding")
    id2 = store.upsert_fact(content="发现 B", memory_type="finding")
    assert id1 != id2


def test_upsert_profile_and_get(store: MemoryStore):
    """upsert_profile 后 get_profile 可读取。"""
    store.upsert_profile(
        "default",
        data_json={"domain": "psychology", "significance_level": 0.05},
        narrative_md="## 研究偏好摘要\n- 心理学",
    )
    profile = store.get_profile("default")
    assert profile is not None
    assert profile["data_json"]["domain"] == "psychology"
    assert "心理学" in profile["narrative_md"]


def test_upsert_profile_overwrites_existing(store: MemoryStore):
    """二次写入覆盖原有数据。"""
    store.upsert_profile("default", data_json={"domain": "old"}, narrative_md="")
    store.upsert_profile("default", data_json={"domain": "new"}, narrative_md="")
    profile = store.get_profile("default")
    assert profile["data_json"]["domain"] == "new"


def test_get_profile_returns_none_for_missing(store: MemoryStore):
    """不存在的 profile 返回 None。"""
    assert store.get_profile("nonexistent") is None


# ---- 读操作测试 ----


def test_search_fts_finds_matching_facts(store: MemoryStore):
    """FTS 检索应命中含关键词的条目。"""
    store.upsert_fact(
        content="独立样本 t 检验结果显著 p=0.002", memory_type="statistic", summary="t检验"
    )
    store.upsert_fact(
        content="相关性分析 r=0.75 强正相关", memory_type="statistic", summary="相关性"
    )
    results = store.search_fts("t 检验")
    assert any("t 检验" in r["content"] for r in results)


def test_search_fts_empty_query_returns_all(store: MemoryStore):
    """空查询返回所有条目（按重要性排序）。"""
    store.upsert_fact(content="内容 A", memory_type="finding")
    store.upsert_fact(content="内容 B", memory_type="finding")
    results = store.search_fts("", top_k=10)
    assert len(results) >= 2


def test_filter_by_sci_p_value(store: MemoryStore):
    """max_p_value 过滤应只返回显著结果。"""
    store.upsert_fact(
        content="显著结果",
        memory_type="statistic",
        sci_metadata={"p_value": 0.001, "dataset_name": "data.csv"},
    )
    store.upsert_fact(
        content="不显著结果",
        memory_type="statistic",
        sci_metadata={"p_value": 0.3, "dataset_name": "data.csv"},
    )
    results = store.filter_by_sci(max_p_value=0.05)
    assert len(results) == 1
    assert results[0]["content"] == "显著结果"


def test_filter_by_sci_dataset_name(store: MemoryStore):
    """按 dataset_name 过滤。"""
    store.upsert_fact(
        content="数据集 A 的发现",
        memory_type="finding",
        sci_metadata={"dataset_name": "dataset_a.csv"},
    )
    store.upsert_fact(
        content="数据集 B 的发现",
        memory_type="finding",
        sci_metadata={"dataset_name": "dataset_b.csv"},
    )
    results = store.filter_by_sci(dataset_name="dataset_a.csv")
    assert len(results) == 1
    assert "数据集 A" in results[0]["content"]


def test_filter_by_sci_min_effect_size(store: MemoryStore):
    """min_effect_size 过滤。"""
    store.upsert_fact(
        content="大效应量",
        memory_type="statistic",
        sci_metadata={"effect_size": 0.8},
    )
    store.upsert_fact(
        content="小效应量",
        memory_type="statistic",
        sci_metadata={"effect_size": 0.1},
    )
    results = store.filter_by_sci(min_effect_size=0.5)
    assert len(results) == 1
    assert "大效应量" in results[0]["content"]
