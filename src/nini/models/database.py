"""SQLite 数据库模型和初始化。

使用 aiosqlite + 原生 SQL（不依赖 SQLAlchemy ORM），保持轻量。
"""

from __future__ import annotations

import aiosqlite
import logging
from pathlib import Path

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
"""


async def init_db() -> None:
    """初始化数据库（建表 + 迁移）。"""
    db_path = settings.db_path
    logger.info("初始化数据库: %s", db_path)
    async with aiosqlite.connect(str(db_path)) as db:
        await db.executescript(_SCHEMA)
        # 迁移：为旧数据库添加新字段
        await _migrate_model_configs(db)
        await db.commit()


async def _migrate_model_configs(db: aiosqlite.Connection) -> None:
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


async def get_db() -> aiosqlite.Connection:
    """获取数据库连接。"""
    db = await aiosqlite.connect(str(settings.db_path))
    db.row_factory = aiosqlite.Row
    return db
