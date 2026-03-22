"""SQLite 统一会话存储层。

每个会话在其目录下维护一个 session.db 文件，包含：
- messages 表：消息历史（与 memory.jsonl 双写）
- session_meta 表：会话元数据键值对（与 meta.json 双写）
- archived_messages 表：压缩归档消息
- archived_fts 虚拟表：FTS5 全文索引（若 SQLite 支持）

首次打开旧格式会话时，自动将 memory.jsonl + meta.json + archive/*.json
迁移到 session.db，原文件保留不删除。
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# FTS5 可用性缓存（进程级）
_FTS5_AVAILABLE: bool | None = None

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS messages (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    role     TEXT    NOT NULL,
    content  TEXT,
    raw_json TEXT    NOT NULL,
    ts       REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS session_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS archived_messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    archive_file TEXT    NOT NULL,
    role         TEXT    NOT NULL,
    content      TEXT,
    raw_json     TEXT    NOT NULL
);
"""

_FTS5_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS archived_fts USING fts5(
    content,
    role UNINDEXED,
    archive_file UNINDEXED,
    tokenize='unicode61'
);
"""


def is_fts5_available() -> bool:
    """检测 SQLite 是否支持 FTS5。结果缓存以避免重复探测。"""
    global _FTS5_AVAILABLE
    if _FTS5_AVAILABLE is not None:
        return _FTS5_AVAILABLE
    try:
        probe = sqlite3.connect(":memory:")
        probe.execute("CREATE VIRTUAL TABLE _fts5_probe USING fts5(x)")
        probe.close()
        _FTS5_AVAILABLE = True
    except sqlite3.OperationalError:
        _FTS5_AVAILABLE = False
    return _FTS5_AVAILABLE


def _init_schema(conn: sqlite3.Connection) -> None:
    """初始化数据库 schema。FTS5 不可用时静默跳过虚拟表。"""
    conn.executescript(_SCHEMA_SQL)
    if is_fts5_available():
        try:
            conn.executescript(_FTS5_SQL)
        except sqlite3.OperationalError as exc:
            logger.warning("[DB] FTS5 虚拟表创建失败，归档检索将使用 LIKE 降级路径: %s", exc)
    conn.commit()


# ---- 迁移辅助函数 ----


def _migrate_memory_jsonl(memory_path: Path, conn: sqlite3.Connection) -> None:
    """将 memory.jsonl 内容迁移到 messages 表。"""
    from datetime import datetime, timezone

    rows: list[tuple] = []
    try:
        with memory_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    if not isinstance(msg, dict):
                        continue
                    role = str(msg.get("role", ""))
                    content_raw = msg.get("content", "")
                    content = str(content_raw) if content_raw is not None else ""
                    ts_str = msg.get("_ts", "")
                    try:
                        ts = (
                            datetime.fromisoformat(str(ts_str)).timestamp()
                            if ts_str
                            else time.time()
                        )
                    except Exception:
                        ts = time.time()
                    rows.append((role, content, json.dumps(msg, ensure_ascii=False), ts))
                except json.JSONDecodeError:
                    continue
    except OSError as exc:
        logger.warning("[DB] 读取 memory.jsonl 失败: %s", exc)
        return

    if rows:
        conn.executemany(
            "INSERT INTO messages (role, content, raw_json, ts) VALUES (?, ?, ?, ?)",
            rows,
        )
    logger.debug("[DB] 迁移 %d 条消息到 messages 表", len(rows))


def _migrate_meta_json(meta_path: Path, conn: sqlite3.Connection) -> None:
    """将 meta.json 内容迁移到 session_meta 表。"""
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("[DB] 读取 meta.json 失败: %s", exc)
        return
    if not isinstance(data, dict):
        return
    rows = [(str(k), json.dumps(v, ensure_ascii=False)) for k, v in data.items()]
    if rows:
        conn.executemany(
            "INSERT OR REPLACE INTO session_meta (key, value) VALUES (?, ?)",
            rows,
        )
    logger.debug("[DB] 迁移 %d 个元数据字段到 session_meta 表", len(rows))


def _migrate_archive_file(archive_file: Path, conn: sqlite3.Connection) -> None:
    """将单个归档文件内容迁移到 archived_messages 表（及 FTS5 索引）。"""
    try:
        raw = archive_file.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("[DB] 读取归档文件失败 %s: %s", archive_file.name, exc)
        return

    messages = data if isinstance(data, list) else data.get("messages", [])
    if not messages:
        return

    rows: list[tuple] = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role", "unknown"))
        content_raw = msg.get("content", "")
        content = str(content_raw) if content_raw is not None else ""
        rows.append((archive_file.name, role, content, json.dumps(msg, ensure_ascii=False)))

    if not rows:
        return

    conn.executemany(
        "INSERT INTO archived_messages (archive_file, role, content, raw_json) VALUES (?, ?, ?, ?)",
        rows,
    )

    # 同步 FTS5 索引
    if is_fts5_available():
        fts_rows = [(row[0], row[1], row[2]) for row in rows]  # archive_file, role, content
        try:
            conn.executemany(
                "INSERT INTO archived_fts (archive_file, role, content) VALUES (?, ?, ?)",
                fts_rows,
            )
        except sqlite3.OperationalError:
            pass  # FTS5 表不存在时静默跳过

    logger.debug("[DB] 迁移归档文件 %s: %d 条消息", archive_file.name, len(rows))


def _migrate_legacy(session_dir: Path, conn: sqlite3.Connection) -> None:
    """将旧格式文件迁移到 SQLite（单一事务，失败时回滚）。

    迁移内容：
    - memory.jsonl → messages 表
    - meta.json → session_meta 表
    - archive/*.json → archived_messages + archived_fts
    """
    logger.info("[DB] 开始迁移旧格式会话: %s", session_dir.name)
    try:
        with conn:  # 事务块，异常时自动 rollback
            memory_path = session_dir / "memory.jsonl"
            if memory_path.exists():
                _migrate_memory_jsonl(memory_path, conn)

            meta_path = session_dir / "meta.json"
            if meta_path.exists():
                _migrate_meta_json(meta_path, conn)

            archive_dir = session_dir / "archive"
            if archive_dir.exists():
                for archive_file in sorted(archive_dir.glob("compressed_*.json")):
                    _migrate_archive_file(archive_file, conn)

        logger.info("[DB] 迁移完成: %s", session_dir.name)
    except Exception as exc:
        logger.error("[DB] 迁移失败，已回滚: %s", exc)
        raise


# ---- 公共接口 ----


def get_session_db(session_dir: Path, *, create: bool = True) -> sqlite3.Connection | None:
    """获取会话 SQLite 连接。

    Args:
        session_dir: 会话目录路径（settings.sessions_dir / session_id）
        create: 若 DB 不存在是否创建。False 时不存在返回 None。

    Returns:
        sqlite3.Connection（行工厂 = Row，WAL 模式），失败时返回 None。
        调用方负责关闭连接。
    """
    from nini.config import settings

    db_filename = getattr(settings, "session_db_filename", "session.db")
    db_path = session_dir / db_filename

    if not create and not db_path.exists():
        return None

    # 检查是否需要迁移（DB 不存在但有旧格式文件）
    archive_dir = session_dir / "archive"
    has_archive_files = archive_dir.is_dir() and any(archive_dir.glob("compressed_*.json"))
    needs_migration = not db_path.exists() and (
        (session_dir / "memory.jsonl").exists()
        or (session_dir / "meta.json").exists()
        or has_archive_files
    )

    try:
        session_dir.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=NORMAL")

        _init_schema(conn)

        if needs_migration:
            try:
                _migrate_legacy(session_dir, conn)
            except Exception as exc:
                logger.error("[DB] 迁移失败，继续使用空数据库: %s", exc)

        return conn
    except Exception as exc:
        logger.error("[DB] 无法打开 SQLite 数据库 %s: %s", db_path, exc)
        return None


def insert_message(conn: sqlite3.Connection, msg: dict[str, Any]) -> None:
    """插入一条消息到 messages 表。"""
    role = str(msg.get("role", ""))
    content_raw = msg.get("content", "")
    content = str(content_raw) if content_raw is not None else ""
    raw_json = json.dumps(msg, ensure_ascii=False, default=str)
    ts_str = msg.get("_ts", "")
    try:
        from datetime import datetime

        ts = datetime.fromisoformat(str(ts_str)).timestamp() if ts_str else time.time()
    except Exception:
        ts = time.time()

    with conn:
        conn.execute(
            "INSERT INTO messages (role, content, raw_json, ts) VALUES (?, ?, ?, ?)",
            (role, content, raw_json, ts),
        )


def load_messages_from_db(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """从 messages 表加载所有消息，按插入顺序排列。"""
    rows = conn.execute("SELECT raw_json FROM messages ORDER BY id ASC").fetchall()
    entries: list[dict[str, Any]] = []
    for row in rows:
        try:
            entry = json.loads(row[0])
            if isinstance(entry, dict):
                entries.append(entry)
        except json.JSONDecodeError:
            pass
    return entries


def upsert_meta_fields(conn: sqlite3.Connection, fields: dict[str, Any]) -> None:
    """将 fields 字典中的字段 upsert 到 session_meta 表。"""
    rows = [(str(k), json.dumps(v, ensure_ascii=False)) for k, v in fields.items()]
    if rows:
        with conn:
            conn.executemany(
                "INSERT OR REPLACE INTO session_meta (key, value) VALUES (?, ?)",
                rows,
            )


def load_meta_from_db(conn: sqlite3.Connection) -> dict[str, Any]:
    """从 session_meta 表加载所有元数据，返回 Python dict。"""
    rows = conn.execute("SELECT key, value FROM session_meta").fetchall()
    meta: dict[str, Any] = {}
    for row in rows:
        try:
            meta[str(row[0])] = json.loads(row[1])
        except (json.JSONDecodeError, TypeError):
            meta[str(row[0])] = str(row[1])
    return meta


def insert_archived_message(
    conn: sqlite3.Connection, archive_file: str, msg: dict[str, Any]
) -> None:
    """插入一条归档消息到 archived_messages 和 archived_fts 表。"""
    role = str(msg.get("role", "unknown"))
    content_raw = msg.get("content", "")
    content = str(content_raw) if content_raw is not None else ""
    raw_json = json.dumps(msg, ensure_ascii=False, default=str)

    with conn:
        conn.execute(
            "INSERT INTO archived_messages (archive_file, role, content, raw_json) VALUES (?, ?, ?, ?)",
            (archive_file, role, content, raw_json),
        )
        if is_fts5_available():
            try:
                conn.execute(
                    "INSERT INTO archived_fts (archive_file, role, content) VALUES (?, ?, ?)",
                    (archive_file, role, content),
                )
            except sqlite3.OperationalError:
                pass


def insert_archived_messages_bulk(
    conn: sqlite3.Connection, archive_file: str, messages: list[dict[str, Any]]
) -> None:
    """批量插入归档消息（单一事务）。"""
    rows: list[tuple] = []
    fts_rows: list[tuple] = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role", "unknown"))
        content_raw = msg.get("content", "")
        content = str(content_raw) if content_raw is not None else ""
        raw_json = json.dumps(msg, ensure_ascii=False, default=str)
        rows.append((archive_file, role, content, raw_json))
        fts_rows.append((archive_file, role, content))

    if not rows:
        return

    with conn:
        conn.executemany(
            "INSERT INTO archived_messages (archive_file, role, content, raw_json) VALUES (?, ?, ?, ?)",
            rows,
        )
        if is_fts5_available() and fts_rows:
            try:
                conn.executemany(
                    "INSERT INTO archived_fts (archive_file, role, content) VALUES (?, ?, ?)",
                    fts_rows,
                )
            except sqlite3.OperationalError:
                pass


def get_indexed_archive_files(conn: sqlite3.Connection) -> set[str]:
    """返回 archived_messages 表中已索引的归档文件名集合。"""
    rows = conn.execute("SELECT DISTINCT archive_file FROM archived_messages").fetchall()
    return {str(row[0]) for row in rows}
