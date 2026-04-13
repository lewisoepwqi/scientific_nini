"""试用模式管理。

负责记录试用激活状态，并结合内置用量计算剩余调用额度。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from nini.config import settings
from nini.models.database import get_db

from nini._config_model_crud import _ensure_app_settings_table
from nini._config_usage import get_builtin_usage

logger = logging.getLogger(__name__)

_TRIAL_INSTALL_DATE_KEY = "trial_install_date"
_TRIAL_ACTIVATED_KEY = "trial_activated"


async def get_trial_status() -> dict[str, Any]:
    """读取试用状态并计算剩余调用次数（按次数限额）。

    Returns:
        包含 activated、expired、内置模型用量与剩余额度的字典
    """
    fast_limit = max(0, int(settings.builtin_fast_limit))
    deep_limit = max(0, int(settings.builtin_deep_limit))
    usage = await get_builtin_usage()
    fast_remaining = max(0, fast_limit - usage["fast"]) if fast_limit > 0 else 10**9
    deep_remaining = max(0, deep_limit - usage["deep"]) if deep_limit > 0 else 10**9

    # 仅当两个模式都达到上限时才视为试用耗尽
    expired = (fast_limit > 0 and fast_remaining <= 0) and (deep_limit > 0 and deep_remaining <= 0)

    db = await get_db()
    try:
        await _ensure_app_settings_table(db)
        cursor = await db.execute(
            "SELECT key, value FROM app_settings WHERE key IN (?)", (_TRIAL_ACTIVATED_KEY,)
        )
        rows = await cursor.fetchall()
        row_map = {r[0]: r[1] for r in rows}

        activated = row_map.get(_TRIAL_ACTIVATED_KEY) == "true"
        # 向后兼容：若历史数据未激活但已有调用次数，视为已激活。
        if not activated and (usage["fast"] > 0 or usage["deep"] > 0):
            activated = True

        return {
            "activated": activated,
            "expired": expired,
            "fast_calls_used": usage["fast"],
            "deep_calls_used": usage["deep"],
            "fast_calls_remaining": fast_remaining if fast_limit > 0 else None,
            "deep_calls_remaining": deep_remaining if deep_limit > 0 else None,
        }
    finally:
        await db.close()


async def activate_trial() -> None:
    """激活试用模式，记录当前日期到本地存储。"""
    today_str = datetime.now(timezone.utc).date().isoformat()
    db = await get_db()
    try:
        await _ensure_app_settings_table(db)
        await db.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(key) DO NOTHING
            """,
            (_TRIAL_INSTALL_DATE_KEY, today_str),
        )
        await db.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, 'true', datetime('now'))
            ON CONFLICT(key) DO UPDATE SET value = 'true', updated_at = datetime('now')
            """,
            (_TRIAL_ACTIVATED_KEY,),
        )
        await db.commit()
        logger.info("试用模式已激活，安装日期: %s", today_str)
    finally:
        await db.close()
