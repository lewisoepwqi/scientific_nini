"""SQLite 统一记忆存储层（data/nini_memory.db）。"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS facts (
    id                TEXT PRIMARY KEY,
    content           TEXT NOT NULL,
    memory_type       TEXT NOT NULL,
    summary           TEXT DEFAULT '',
    tags              TEXT DEFAULT '[]',
    importance        REAL DEFAULT 0.5,
    trust_score       REAL DEFAULT 0.5,
    source_session_id TEXT DEFAULT '',
    created_at        REAL NOT NULL,
    updated_at        REAL NOT NULL,
    access_count      INTEGER DEFAULT 0,
    last_accessed_at  REAL,
    dedup_key         TEXT UNIQUE,
    sci_metadata      TEXT DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS research_profiles (
    profile_id   TEXT PRIMARY KEY,
    data_json    TEXT NOT NULL,
    narrative_md TEXT DEFAULT '',
    updated_at   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_facts_session ON facts(source_session_id);
CREATE INDEX IF NOT EXISTS idx_facts_type    ON facts(memory_type);
CREATE INDEX IF NOT EXISTS idx_facts_trust   ON facts(trust_score DESC);
CREATE INDEX IF NOT EXISTS idx_facts_dedup   ON facts(dedup_key);
"""

_FTS5_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
    content, summary, tags,
    content=facts, content_rowid=rowid,
    tokenize='unicode61'
);
CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
    INSERT INTO facts_fts(rowid, content, summary, tags)
    VALUES (new.rowid, new.content, new.summary, new.tags);
END;
CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, content, summary, tags)
    VALUES ('delete', old.rowid, old.content, old.summary, old.tags);
END;
CREATE TRIGGER IF NOT EXISTS facts_au AFTER UPDATE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, content, summary, tags)
    VALUES ('delete', old.rowid, old.content, old.summary, old.tags);
    INSERT INTO facts_fts(rowid, content, summary, tags)
    VALUES (new.rowid, new.content, new.summary, new.tags);
END;
"""


def _check_fts5() -> bool:
    """探测当前 SQLite 是否支持 FTS5。"""
    try:
        probe = sqlite3.connect(":memory:")
        probe.execute("CREATE VIRTUAL TABLE _p USING fts5(x)")
        probe.close()
        return True
    except sqlite3.OperationalError:
        return False


class MemoryStore:
    """SQLite 统一记忆存储层。WAL 模式，支持多会话并发写入。"""

    def __init__(self, db_path: Path) -> None:
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._fts5 = _check_fts5()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=10.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        with self._conn:
            self._conn.executescript(_SCHEMA_SQL)
            if self._fts5:
                try:
                    self._conn.executescript(_FTS5_SQL)
                except sqlite3.OperationalError:
                    self._fts5 = False
        # json_extract 索引（JSON1 扩展存在时生效，否则静默跳过）
        try:
            with self._conn:
                self._conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_facts_dataset "
                    "ON facts(json_extract(sci_metadata, '$.dataset_name'))"
                )
        except sqlite3.OperationalError:
            pass

    # ---- 写操作 ----

    def upsert_fact(
        self,
        *,
        content: str,
        memory_type: str,
        summary: str = "",
        tags: list[str] | None = None,
        importance: float = 0.5,
        trust_score: float = 0.5,
        source_session_id: str = "",
        sci_metadata: dict[str, Any] | None = None,
    ) -> str:
        """插入 fact；相同 dedup_key 时更新访问计数并返回已有 id（幂等）。"""
        sci = sci_metadata or {}
        dedup_key = hashlib.md5(
            f"{memory_type}|{sci.get('dataset_name', '')}|{content}".encode()
        ).hexdigest()

        existing = self._conn.execute(
            "SELECT id FROM facts WHERE dedup_key = ?", (dedup_key,)
        ).fetchone()
        if existing:
            now = time.time()
            with self._conn:
                self._conn.execute(
                    "UPDATE facts SET access_count = access_count + 1, last_accessed_at = ? "
                    "WHERE id = ?",
                    (now, existing[0]),
                )
            return str(existing[0])

        fact_id = str(uuid.uuid4())
        now = time.time()
        with self._conn:
            self._conn.execute(
                """INSERT INTO facts
                   (id, content, memory_type, summary, tags, importance, trust_score,
                    source_session_id, created_at, updated_at, dedup_key, sci_metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    fact_id,
                    content,
                    memory_type,
                    summary,
                    json.dumps(tags or [], ensure_ascii=False),
                    importance,
                    trust_score,
                    source_session_id,
                    now,
                    now,
                    dedup_key,
                    json.dumps(sci, ensure_ascii=False),
                ),
            )
        return fact_id

    def upsert_profile(self, profile_id: str, data_json: dict[str, Any], narrative_md: str) -> None:
        """更新研究画像（ON CONFLICT 覆盖）。"""
        with self._conn:
            self._conn.execute(
                """INSERT INTO research_profiles (profile_id, data_json, narrative_md, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(profile_id) DO UPDATE SET
                       data_json    = excluded.data_json,
                       narrative_md = excluded.narrative_md,
                       updated_at   = excluded.updated_at""",
                (
                    profile_id,
                    json.dumps(data_json, ensure_ascii=False),
                    narrative_md,
                    time.time(),
                ),
            )

    def get_profile(self, profile_id: str) -> dict[str, Any] | None:
        """获取研究画像，不存在时返回 None。"""
        row = self._conn.execute(
            "SELECT * FROM research_profiles WHERE profile_id = ?", (profile_id,)
        ).fetchone()
        if not row:
            return None
        return {
            "profile_id": row["profile_id"],
            "data_json": json.loads(row["data_json"]),
            "narrative_md": row["narrative_md"],
            "updated_at": row["updated_at"],
        }

    def close(self) -> None:
        """关闭数据库连接。"""
        try:
            self._conn.close()
        except Exception:
            pass

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        """将 SQLite Row 转为 Python dict，解析 JSON 列。"""
        d = dict(row)
        try:
            d["tags"] = json.loads(d.get("tags") or "[]")
        except Exception:
            d["tags"] = []
        try:
            d["sci_metadata"] = json.loads(d.get("sci_metadata") or "{}")
        except Exception:
            d["sci_metadata"] = {}
        return d
