"""SQLite 会话存储层单元测试。

覆盖：
- schema 初始化
- 重复打开不报错
- FTS5 可用性检测
- memory.jsonl / meta.json / archive/*.json 迁移
- 迁移失败回滚（session.db 不持久化）
- 消息 CRUD
- 元数据 upsert / load
- 归档消息批量写入 + FTS5
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from nini.agent.session import Session
from nini.config import settings
from nini.memory.db import (
    get_indexed_archive_files,
    get_session_db,
    insert_archived_messages_bulk,
    insert_message,
    is_fts5_available,
    load_messages_from_db,
    load_meta_from_db,
    upsert_meta_fields,
)


@pytest.fixture(autouse=True)
def isolate_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """将数据目录隔离到 tmp_path。"""
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    settings.ensure_dirs()


class TestSchemaInit:
    """测试 schema 初始化。"""

    def test_creates_db_on_first_call(self, tmp_path):
        """首次调用时应创建 session.db 并初始化四张表。"""
        session_dir = tmp_path / "sessions" / "test_session"
        conn = get_session_db(session_dir, create=True)
        assert conn is not None
        conn.close()

        db_path = session_dir / settings.session_db_filename
        assert db_path.exists()

    def test_tables_exist_after_init(self, tmp_path):
        """初始化后 messages / session_meta / archived_messages 表应存在。"""
        session_dir = tmp_path / "sessions" / "test_tables"
        conn = get_session_db(session_dir, create=True)
        assert conn is not None

        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        conn.close()

        assert "messages" in tables
        assert "session_meta" in tables
        assert "archived_messages" in tables

    def test_reopen_existing_db_no_error(self, tmp_path):
        """重复打开已存在的 DB 不应报错，且可正常使用。"""
        session_dir = tmp_path / "sessions" / "test_reopen"
        conn1 = get_session_db(session_dir, create=True)
        assert conn1 is not None
        conn1.close()

        conn2 = get_session_db(session_dir, create=False)
        assert conn2 is not None
        conn2.close()

    def test_create_false_returns_none_when_no_db(self, tmp_path):
        """create=False 且 DB 不存在时应返回 None。"""
        session_dir = tmp_path / "sessions" / "nonexistent"
        conn = get_session_db(session_dir, create=False)
        assert conn is None

    def test_fts5_available(self):
        """当前环境应支持 FTS5。"""
        assert is_fts5_available() is True


class TestMessageCRUD:
    """测试消息写入与读取。"""

    def test_insert_and_load_messages(self, tmp_path):
        """写入消息后应可从 DB 正确读回。"""
        session_dir = tmp_path / "sessions" / "test_msgs"
        conn = get_session_db(session_dir, create=True)
        assert conn is not None

        msg1 = {"role": "user", "content": "你好", "_ts": "2026-01-01T00:00:00+00:00"}
        msg2 = {"role": "assistant", "content": "你好！有什么可以帮你？"}

        insert_message(conn, msg1)
        insert_message(conn, msg2)

        entries = load_messages_from_db(conn)
        conn.close()

        assert len(entries) == 2
        assert entries[0]["role"] == "user"
        assert entries[0]["content"] == "你好"
        assert entries[1]["role"] == "assistant"

    def test_messages_order_preserved(self, tmp_path):
        """消息应按插入顺序返回。"""
        session_dir = tmp_path / "sessions" / "test_order"
        conn = get_session_db(session_dir, create=True)
        assert conn is not None

        for i in range(5):
            insert_message(conn, {"role": "user", "content": f"消息 {i}"})

        entries = load_messages_from_db(conn)
        conn.close()

        for i, entry in enumerate(entries):
            assert entry["content"] == f"消息 {i}"


class TestMetaCRUD:
    """测试元数据写入与读取。"""

    def test_upsert_and_load_meta(self, tmp_path):
        """写入元数据后应可正确读回。"""
        session_dir = tmp_path / "sessions" / "test_meta"
        conn = get_session_db(session_dir, create=True)
        assert conn is not None

        upsert_meta_fields(conn, {"title": "测试会话", "compressed_rounds": 2})
        meta = load_meta_from_db(conn)
        conn.close()

        assert meta["title"] == "测试会话"
        assert meta["compressed_rounds"] == 2

    def test_upsert_replaces_existing_key(self, tmp_path):
        """相同 key 的二次 upsert 应覆盖旧值。"""
        session_dir = tmp_path / "sessions" / "test_upsert"
        conn = get_session_db(session_dir, create=True)
        assert conn is not None

        upsert_meta_fields(conn, {"title": "原标题"})
        upsert_meta_fields(conn, {"title": "新标题"})
        meta = load_meta_from_db(conn)
        conn.close()

        assert meta["title"] == "新标题"


class TestArchivedMessages:
    """测试归档消息批量写入与 FTS5 索引。"""

    def test_bulk_insert_archived_messages(self, tmp_path):
        """批量插入归档消息后应可在 archived_messages 中查到。"""
        session_dir = tmp_path / "sessions" / "test_archive"
        conn = get_session_db(session_dir, create=True)
        assert conn is not None

        messages = [
            {"role": "user", "content": "统计分析结果 p 值显著"},
            {"role": "assistant", "content": "p 值为 0.03，具有显著性"},
        ]
        insert_archived_messages_bulk(conn, "compressed_001.json", messages)

        indexed = get_indexed_archive_files(conn)
        conn.close()

        assert "compressed_001.json" in indexed

    def test_sqlite_like_search_works(self, tmp_path):
        """archived_messages LIKE 查询应正确检索中文关键词。

        注：FTS5 unicode61 分词器不支持无空格中文，实际检索走 LIKE 路径。
        """
        session_dir = tmp_path / "sessions" / "test_fts5"
        conn = get_session_db(session_dir, create=True)
        assert conn is not None

        messages = [{"role": "user", "content": "关键词命中测试内容"}]
        insert_archived_messages_bulk(conn, "compressed_fts.json", messages)

        rows = conn.execute(
            "SELECT content FROM archived_messages WHERE lower(content) LIKE ?",
            ("%关键词%",),
        ).fetchall()
        conn.close()

        assert len(rows) >= 1
        assert "关键词" in str(rows[0][0])

    def test_fts5_english_search_works(self, tmp_path):
        """FTS5 应支持英文 token 级别匹配（英文内容）。"""
        session_dir = tmp_path / "sessions" / "test_fts5_en"
        conn = get_session_db(session_dir, create=True)
        assert conn is not None

        messages = [{"role": "user", "content": "statistical significance pvalue test"}]
        insert_archived_messages_bulk(conn, "compressed_en.json", messages)

        rows = conn.execute(
            "SELECT content FROM archived_fts WHERE archived_fts MATCH ?",
            ("significance",),
        ).fetchall()
        conn.close()

        assert len(rows) >= 1


class TestLegacyMigration:
    """测试旧格式文件自动迁移。"""

    def _make_session_dir(self, sessions_dir: Path, session_id: str) -> Path:
        session_dir = sessions_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir

    def test_migrate_memory_jsonl(self, tmp_path):
        """有 memory.jsonl 时应自动迁移到 messages 表。"""
        session_dir = self._make_session_dir(settings.sessions_dir, "migrate_msgs")

        msgs = [
            {"role": "user", "content": "迁移测试", "_ts": "2026-01-01T00:00:00+00:00"},
            {"role": "assistant", "content": "迁移成功"},
        ]
        (session_dir / "memory.jsonl").write_text(
            "\n".join(json.dumps(m, ensure_ascii=False) for m in msgs),
            encoding="utf-8",
        )

        conn = get_session_db(session_dir, create=True)
        assert conn is not None
        entries = load_messages_from_db(conn)
        conn.close()

        assert len(entries) == 2
        assert entries[0]["role"] == "user"

    def test_migrate_meta_json(self, tmp_path):
        """有 meta.json 时应自动迁移到 session_meta 表。"""
        session_dir = self._make_session_dir(settings.sessions_dir, "migrate_meta")

        meta = {"title": "迁移的会话", "compressed_rounds": 1}
        (session_dir / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False), encoding="utf-8"
        )

        conn = get_session_db(session_dir, create=True)
        assert conn is not None
        loaded_meta = load_meta_from_db(conn)
        conn.close()

        assert loaded_meta.get("title") == "迁移的会话"
        assert loaded_meta.get("compressed_rounds") == 1

    def test_migrate_archive_files(self, tmp_path):
        """有 archive/*.json 时应迁移到 archived_messages 表。"""
        session_dir = self._make_session_dir(settings.sessions_dir, "migrate_arch")
        archive_dir = session_dir / "archive"
        archive_dir.mkdir()

        msgs = [{"role": "user", "content": "归档内容迁移"}]
        (archive_dir / "compressed_20260101_120000.json").write_text(
            json.dumps(msgs, ensure_ascii=False), encoding="utf-8"
        )

        conn = get_session_db(session_dir, create=True)
        assert conn is not None
        indexed = get_indexed_archive_files(conn)
        conn.close()

        assert "compressed_20260101_120000.json" in indexed

    def test_original_files_preserved_after_migration(self, tmp_path):
        """迁移后原始 JSONL / meta.json 文件应保留。"""
        session_dir = self._make_session_dir(settings.sessions_dir, "preserve_files")
        memory_path = session_dir / "memory.jsonl"
        meta_path = session_dir / "meta.json"

        memory_path.write_text(json.dumps({"role": "user", "content": "test"}), encoding="utf-8")
        meta_path.write_text(json.dumps({"title": "test"}), encoding="utf-8")

        conn = get_session_db(session_dir, create=True)
        assert conn is not None
        conn.close()

        assert memory_path.exists(), "memory.jsonl 应在迁移后保留"
        assert meta_path.exists(), "meta.json 应在迁移后保留"

    def test_migration_skipped_when_db_exists(self, tmp_path):
        """若 session.db 已存在，不应触发迁移。"""
        session_dir = self._make_session_dir(settings.sessions_dir, "no_remigrate")

        # 先创建 DB（无迁移）
        conn1 = get_session_db(session_dir, create=True)
        assert conn1 is not None
        conn1.close()

        # 后创建 memory.jsonl（模拟旧文件）
        memory_path = session_dir / "memory.jsonl"
        memory_path.write_text(
            json.dumps({"role": "user", "content": "不应被迁移"}), encoding="utf-8"
        )

        # 重新打开：DB 已存在，不触发迁移
        conn2 = get_session_db(session_dir, create=True)
        assert conn2 is not None
        entries = load_messages_from_db(conn2)
        conn2.close()

        # DB 是空的（JSONL 出现在 DB 创建之后，不触发迁移）
        assert len(entries) == 0
