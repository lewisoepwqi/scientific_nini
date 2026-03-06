"""试用模式状态计算逻辑单元测试。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest


def _build_db_mock(key_value_pairs: list[tuple[str, str]]) -> AsyncMock:
    """构造模拟 DB：SELECT 返回指定的 key-value 行列表。"""
    db = AsyncMock()
    cursor = AsyncMock()
    cursor.fetchall = AsyncMock(return_value=key_value_pairs)
    db.execute = AsyncMock(return_value=cursor)
    db.commit = AsyncMock()
    db.close = AsyncMock()
    return db


async def _call_get_trial_status(rows: list[tuple[str, str]], trial_days: int = 14) -> dict:
    """辅助：以指定行数据和 trial_days 调用 get_trial_status()。"""
    db = _build_db_mock(rows)

    async def fake_get_db():
        return db

    with (
        patch("nini.config_manager.get_db", fake_get_db),
        patch("nini.config_manager.settings") as mock_settings,
    ):
        mock_settings.trial_days = trial_days
        # 延迟导入确保 patch 生效
        from nini.config_manager import get_trial_status
        return await get_trial_status()


# ---- 测试用例 ----


@pytest.mark.asyncio
async def test_trial_not_activated():
    """DB 无记录时：未激活，days_remaining = trial_days，expired = False。"""
    result = await _call_get_trial_status(rows=[], trial_days=14)
    assert result["activated"] is False
    assert result["days_remaining"] == 14
    assert result["expired"] is False


@pytest.mark.asyncio
async def test_trial_active_within_period():
    """安装 5 天后：激活，剩余 9 天，未到期。"""
    install_date = (datetime.now(timezone.utc).date() - timedelta(days=5)).isoformat()
    rows = [
        ("trial_install_date", install_date),
        ("trial_activated", "true"),
    ]
    result = await _call_get_trial_status(rows=rows, trial_days=14)
    assert result["activated"] is True
    assert result["days_remaining"] == 9
    assert result["expired"] is False


@pytest.mark.asyncio
async def test_trial_expired():
    """安装 20 天后：已到期，days_remaining = 0，expired = True。"""
    install_date = (datetime.now(timezone.utc).date() - timedelta(days=20)).isoformat()
    rows = [
        ("trial_install_date", install_date),
        ("trial_activated", "true"),
    ]
    result = await _call_get_trial_status(rows=rows, trial_days=14)
    assert result["activated"] is True
    assert result["days_remaining"] == 0
    assert result["expired"] is True


@pytest.mark.asyncio
async def test_trial_exactly_on_last_day():
    """恰好第 14 天（elapsed=14）：expired = True，days_remaining = 0。"""
    install_date = (datetime.now(timezone.utc).date() - timedelta(days=14)).isoformat()
    rows = [
        ("trial_install_date", install_date),
        ("trial_activated", "true"),
    ]
    result = await _call_get_trial_status(rows=rows, trial_days=14)
    assert result["expired"] is True
    assert result["days_remaining"] == 0
