"""内置用量追踪。

负责跟踪内置模型的调用次数，同时写入数据库与系统文件以防止 DB 重置绕过限额。
"""

from __future__ import annotations

import json
import logging
import os
import platform
from pathlib import Path
from typing import Any

from nini.models.database import get_db

from nini._config_model_crud import _ensure_app_settings_table

logger = logging.getLogger(__name__)

_BUILTIN_FAST_USAGE_KEY = "builtin_fast_calls_used"
_BUILTIN_DEEP_USAGE_KEY = "builtin_deep_calls_used"


def _get_system_usage_path() -> Path:
    """获取系统级内置用量文件路径（跨重装持久化）。

    - macOS/Linux: ~/.config/nini/builtin_usage.json
    - Windows:     %APPDATA%\\nini\\builtin_usage.json
    """
    if platform.system() == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "nini" / "builtin_usage.json"


def _read_system_usage() -> dict[str, int]:
    """从系统文件读取内置用量计数。"""
    path = _get_system_usage_path()
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return {
                "fast": max(0, int(data.get("fast", 0))),
                "deep": max(0, int(data.get("deep", 0))),
            }
    except Exception as e:
        logger.warning("读取系统用量文件失败: %s", e)
    return {"fast": 0, "deep": 0}


def _write_system_usage(fast: int, deep: int) -> None:
    """将内置用量计数写入系统文件。"""
    path = _get_system_usage_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"fast": fast, "deep": deep}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("写入系统用量文件失败: %s", e)


async def _read_db_usage() -> dict[str, int]:
    """从数据库读取内置用量计数。"""
    db = await get_db()
    try:
        await _ensure_app_settings_table(db)
        cursor = await db.execute(
            "SELECT key, value FROM app_settings WHERE key IN (?, ?)",
            (_BUILTIN_FAST_USAGE_KEY, _BUILTIN_DEEP_USAGE_KEY),
        )
        rows = await cursor.fetchall()
        row_map = {r[0]: r[1] for r in rows}
        return {
            "fast": max(0, int(row_map.get(_BUILTIN_FAST_USAGE_KEY, 0) or 0)),
            "deep": max(0, int(row_map.get(_BUILTIN_DEEP_USAGE_KEY, 0) or 0)),
        }
    except Exception as e:
        logger.warning("读取数据库用量失败: %s", e)
        return {"fast": 0, "deep": 0}
    finally:
        await db.close()


async def get_builtin_usage() -> dict[str, int]:
    """获取内置用量（取 DB 与系统文件的最大值，防止 DB 重置绕过限额）。

    Returns:
        {"fast": <已用快速次数>, "deep": <已用深度次数>}
    """
    db_usage = await _read_db_usage()
    sys_usage = _read_system_usage()
    return {
        "fast": max(db_usage["fast"], sys_usage["fast"]),
        "deep": max(db_usage["deep"], sys_usage["deep"]),
    }


async def increment_builtin_usage(mode: str) -> None:
    """递增内置用量计数（同时写入 DB 和系统文件）。

    Args:
        mode: "fast" 或 "deep"
    """
    if mode not in ("fast", "deep"):
        return

    key = _BUILTIN_FAST_USAGE_KEY if mode == "fast" else _BUILTIN_DEEP_USAGE_KEY
    db = await get_db()
    try:
        await _ensure_app_settings_table(db)
        await db.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, '1', datetime('now'))
            ON CONFLICT(key) DO UPDATE SET
                value = CAST(COALESCE(app_settings.value, '0') AS INTEGER) + 1,
                updated_at = datetime('now')
            """,
            (key,),
        )
        cursor = await db.execute(
            "SELECT key, value FROM app_settings WHERE key IN (?, ?)",
            (_BUILTIN_FAST_USAGE_KEY, _BUILTIN_DEEP_USAGE_KEY),
        )
        rows = await cursor.fetchall()
        await db.commit()
    except Exception as e:
        logger.warning("写入数据库用量失败: %s", e)
        rows = []
    finally:
        await db.close()

    row_map = {r[0]: r[1] for r in rows}
    db_usage: dict[str, Any] = {
        "fast": max(0, int(row_map.get(_BUILTIN_FAST_USAGE_KEY, 0) or 0)),
        "deep": max(0, int(row_map.get(_BUILTIN_DEEP_USAGE_KEY, 0) or 0)),
    }
    sys_usage = _read_system_usage()
    merged_fast = max(db_usage["fast"], sys_usage["fast"])
    merged_deep = max(db_usage["deep"], sys_usage["deep"])
    _write_system_usage(fast=merged_fast, deep=merged_deep)
    logger.debug(
        "内置用量更新: mode=%s, 累计=%d",
        mode,
        merged_fast if mode == "fast" else merged_deep,
    )


async def is_builtin_exhausted(mode: str) -> bool:
    """检查指定模式的内置用量是否已耗尽。

    Args:
        mode: "fast" 或 "deep"

    Returns:
        True 表示已耗尽（不可再用内置模型）
    """
    from nini.config import settings

    if mode not in ("fast", "deep"):
        return False

    usage = await get_builtin_usage()
    limit = settings.builtin_fast_limit if mode == "fast" else settings.builtin_deep_limit
    return usage[mode] >= limit
