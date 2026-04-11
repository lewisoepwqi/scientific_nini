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
