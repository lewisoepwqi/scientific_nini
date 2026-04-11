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

    # ---- 读操作 ----

    def search_fts(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        """全文检索；FTS5 不可用时降级为 LIKE 匹配（特殊字符已转义）。"""
        if not query or not query.strip():
            rows = self._conn.execute(
                "SELECT * FROM facts ORDER BY importance DESC, trust_score DESC LIMIT ?",
                (top_k,),
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]

        # LIKE 降级路径：转义 % 和 _ 特殊字符
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like_q = f"%{escaped}%"
        rows = self._conn.execute(
            "SELECT * FROM facts WHERE content LIKE ? ESCAPE '\\' "
            "OR summary LIKE ? ESCAPE '\\' ORDER BY importance DESC, trust_score DESC LIMIT ?",
            (like_q, like_q, top_k),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def filter_by_sci(
        self,
        *,
        dataset_name: str | None = None,
        analysis_type: str | None = None,
        max_p_value: float | None = None,
        min_effect_size: float | None = None,
    ) -> list[dict[str, Any]]:
        """按 sci_metadata JSON 字段过滤。JSON1 不可用时降级为全表扫描内存过滤。"""
        # 先尝试 json_extract 路径
        try:
            return self._filter_by_sci_sql(
                dataset_name=dataset_name,
                analysis_type=analysis_type,
                max_p_value=max_p_value,
                min_effect_size=min_effect_size,
            )
        except sqlite3.OperationalError:
            # JSON1 不可用，降级为全表扫描+内存过滤
            return self._filter_by_sci_memory(
                dataset_name=dataset_name,
                analysis_type=analysis_type,
                max_p_value=max_p_value,
                min_effect_size=min_effect_size,
            )

    def _filter_by_sci_sql(
        self,
        *,
        dataset_name: str | None,
        analysis_type: str | None,
        max_p_value: float | None,
        min_effect_size: float | None,
    ) -> list[dict[str, Any]]:
        """json_extract 路径（JSON1 可用时）。"""
        conditions: list[str] = []
        params: list[Any] = []

        if dataset_name is not None:
            conditions.append("json_extract(sci_metadata, '$.dataset_name') = ?")
            params.append(dataset_name)
        if analysis_type is not None:
            conditions.append("json_extract(sci_metadata, '$.analysis_type') = ?")
            params.append(analysis_type)
        if max_p_value is not None:
            conditions.append(
                "json_extract(sci_metadata, '$.p_value') IS NOT NULL "
                "AND CAST(json_extract(sci_metadata, '$.p_value') AS REAL) <= ?"
            )
            params.append(max_p_value)
        if min_effect_size is not None:
            conditions.append(
                "json_extract(sci_metadata, '$.effect_size') IS NOT NULL "
                "AND CAST(json_extract(sci_metadata, '$.effect_size') AS REAL) >= ?"
            )
            params.append(min_effect_size)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        rows = self._conn.execute(  # noqa: S608
            f"SELECT * FROM facts {where} ORDER BY importance DESC",
            params,
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def _filter_by_sci_memory(
        self,
        *,
        dataset_name: str | None,
        analysis_type: str | None,
        max_p_value: float | None,
        min_effect_size: float | None,
    ) -> list[dict[str, Any]]:
        """全表扫描+内存过滤降级路径（JSON1 不可用时）。"""
        rows = self._conn.execute("SELECT * FROM facts ORDER BY importance DESC").fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            d = self._row_to_dict(row)
            sci = d.get("sci_metadata") or {}
            if not isinstance(sci, dict):
                try:
                    sci = json.loads(sci)
                except Exception:
                    continue
            if dataset_name is not None and sci.get("dataset_name") != dataset_name:
                continue
            if analysis_type is not None and sci.get("analysis_type") != analysis_type:
                continue
            if max_p_value is not None:
                p = sci.get("p_value")
                if p is None:
                    continue
                try:
                    if float(p) > max_p_value:
                        continue
                except (TypeError, ValueError):
                    continue
            if min_effect_size is not None:
                e = sci.get("effect_size")
                if e is None:
                    continue
                try:
                    if float(e) < min_effect_size:
                        continue
                except (TypeError, ValueError):
                    continue
            results.append(d)
        return results

    # ---- 旧数据迁移 ----

    def migrate_from_jsonl(self, jsonl_path: Path) -> int:
        """将旧 entries.jsonl 迁移到 facts 表。返回实际写入条数（幂等）。

        字段映射：
        - source_dataset → sci_metadata.dataset_name
        - importance_score → importance
        - analysis_type → sci_metadata.analysis_type
        - metadata.dedup_key → dedup_key（无则重新计算 MD5）
        """
        jsonl_path = Path(jsonl_path)
        if not jsonl_path.exists():
            logger.debug("JSONL 迁移文件不存在，跳过：%s", jsonl_path)
            return 0
        count = 0
        with open(jsonl_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    sci: dict[str, Any] = {}
                    if d.get("source_dataset"):
                        sci["dataset_name"] = d["source_dataset"]
                    if d.get("analysis_type"):
                        sci["analysis_type"] = d["analysis_type"]
                    meta = d.get("metadata") or {}
                    for key in ("p_value", "effect_size", "significant", "sample_size"):
                        if key in meta:
                            sci[key] = meta[key]

                    dedup_key = hashlib.md5(
                        f"{d.get('memory_type', '')}|{sci.get('dataset_name', '')}|"
                        f"{d.get('content', '')}".encode()
                    ).hexdigest()
                    existing = self._conn.execute(
                        "SELECT id FROM facts WHERE dedup_key = ?", (dedup_key,)
                    ).fetchone()
                    if existing:
                        continue

                    created_ts = time.time()
                    created_str = str(d.get("created_at", ""))
                    if created_str:
                        try:
                            from datetime import datetime, timezone  # noqa: F401

                            created_ts = datetime.fromisoformat(created_str).timestamp()
                        except Exception:
                            pass

                    fact_id = str(d.get("id") or uuid.uuid4())
                    with self._conn:
                        self._conn.execute(
                            """INSERT OR IGNORE INTO facts
                               (id, content, memory_type, summary, tags, importance,
                                source_session_id, created_at, updated_at, dedup_key,
                                sci_metadata)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                fact_id,
                                str(d.get("content", "")),
                                str(d.get("memory_type", "insight")),
                                str(d.get("summary", "")),
                                json.dumps(d.get("tags") or [], ensure_ascii=False),
                                float(d.get("importance_score", 0.5)),
                                str(d.get("source_session_id", "")),
                                created_ts,
                                created_ts,
                                dedup_key,
                                json.dumps(sci, ensure_ascii=False),
                            ),
                        )
                    count += 1
                except Exception as exc:
                    logger.warning("迁移 JSONL 条目失败: %s", exc)
        return count

    def migrate_profile_json(self, json_path: Path, narrative_path: Path | None = None) -> None:
        """将旧 profiles/*.json + *_profile.md 迁移到 research_profiles 表。

        已存在的 profile 不覆盖（保护新数据）。
        """
        json_path = Path(json_path)
        if not json_path.exists():
            return
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            profile_id = str(data.get("user_id", json_path.stem))
            existing = self._conn.execute(
                "SELECT profile_id FROM research_profiles WHERE profile_id = ?",
                (profile_id,),
            ).fetchone()
            if existing:
                return
            narrative = ""
            if narrative_path is not None:
                narrative_path = Path(narrative_path)
                if narrative_path.exists():
                    narrative = narrative_path.read_text(encoding="utf-8")
            self.upsert_profile(profile_id, data, narrative)
        except Exception as exc:
            logger.warning("迁移 profile JSON 失败 %s: %s", json_path, exc)

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
