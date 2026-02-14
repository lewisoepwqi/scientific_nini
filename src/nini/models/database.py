"""SQLite 数据库模型和初始化。

使用 sqlite3 + 轻量异步包装（不依赖 SQLAlchemy ORM），保持轻量。
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any, Iterable, cast

from nini.config import settings

logger = logging.getLogger(__name__)

# 建表 SQL
_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    title TEXT DEFAULT '新会话',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    message_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS datasets (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_type TEXT NOT NULL,
    file_size INTEGER DEFAULT 0,
    row_count INTEGER DEFAULT 0,
    column_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    name TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    file_path TEXT NOT NULL,
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS model_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL UNIQUE,
    model TEXT NOT NULL,
    encrypted_api_key TEXT,
    api_key_hint TEXT,
    base_url TEXT,
    priority INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    is_default INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS workflow_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    steps TEXT NOT NULL,
    parameters TEXT DEFAULT '{}',
    source_session_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_datasets_session_created
ON datasets(session_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_artifacts_session_created
ON artifacts(session_id, created_at DESC);
"""


class AsyncSQLiteCursor:
    """sqlite3.Cursor 的最小异步适配层。"""

    def __init__(self, cursor: sqlite3.Cursor):
        self._cursor = cursor

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    async def fetchone(self) -> sqlite3.Row | tuple[Any, ...] | None:
        return cast(sqlite3.Row | tuple[Any, ...] | None, self._cursor.fetchone())

    async def fetchall(self) -> list[sqlite3.Row] | list[tuple[Any, ...]]:
        return self._cursor.fetchall()

    async def close(self) -> None:
        self._cursor.close()


class AsyncSQLiteConnection:
    """sqlite3.Connection 的最小异步适配层。

    说明：
    - 当前执行环境中 aiosqlite 依赖线程回调，可能导致事件循环无法收敛。
    - 这里保持 `await db.execute()/commit()/close()` 调用接口不变，
      但底层使用同步 sqlite3，避免线程桥接阻塞。
    """

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    @property
    def row_factory(self) -> type | None:
        return cast(type | None, self._conn.row_factory)

    @row_factory.setter
    def row_factory(self, factory: type | None) -> None:
        self._conn.row_factory = factory

    async def execute(
        self,
        sql: str,
        parameters: Iterable[Any] | None = None,
    ) -> AsyncSQLiteCursor:
        cursor = self._conn.execute(sql, tuple(parameters or ()))
        return AsyncSQLiteCursor(cursor)

    async def executescript(self, sql_script: str) -> AsyncSQLiteCursor:
        cursor = self._conn.executescript(sql_script)
        return AsyncSQLiteCursor(cursor)

    async def commit(self) -> None:
        self._conn.commit()

    async def rollback(self) -> None:
        self._conn.rollback()

    async def close(self) -> None:
        self._conn.close()

    async def __aenter__(self) -> AsyncSQLiteConnection:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()


async def init_db() -> None:
    """初始化数据库（建表 + 迁移）。"""
    db_path = settings.db_path
    logger.info("初始化数据库: %s", db_path)
    async with await get_db() as db:
        await db.executescript(_SCHEMA)
        # 迁移：为旧数据库添加新字段
        await _migrate_model_configs(db)
        await db.commit()


async def _migrate_model_configs(db: AsyncSQLiteConnection) -> None:
    """为 model_configs 表添加可能缺失的字段和索引（兼容旧数据库）。"""
    cursor = await db.execute("PRAGMA table_info(model_configs)")
    columns = {row[1] for row in await cursor.fetchall()}

    migrations = [
        (
            "encrypted_api_key",
            "ALTER TABLE model_configs ADD COLUMN encrypted_api_key TEXT",
        ),
        (
            "updated_at",
            "ALTER TABLE model_configs ADD COLUMN updated_at TEXT DEFAULT (datetime('now'))",
        ),
        (
            "is_default",
            "ALTER TABLE model_configs ADD COLUMN is_default INTEGER DEFAULT 0",
        ),
    ]
    for col_name, sql in migrations:
        if col_name not in columns:
            try:
                await db.execute(sql)
                logger.info("数据库迁移：已添加 model_configs.%s 字段", col_name)
            except Exception as e:
                logger.debug("迁移字段 %s 跳过: %s", col_name, e)

    # 确保 provider 列有 UNIQUE 约束（旧表可能缺失）
    try:
        await db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_model_configs_provider ON model_configs(provider)"
        )
    except Exception as e:
        logger.debug("创建 provider 唯一索引跳过: %s", e)

    # 创建 app_settings 表（如果不存在）
    try:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
    except Exception as e:
        logger.debug("创建 app_settings 表跳过: %s", e)


async def get_db() -> AsyncSQLiteConnection:
    """获取数据库连接。"""
    conn = sqlite3.connect(str(settings.db_path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    db = AsyncSQLiteConnection(conn)
    return db
