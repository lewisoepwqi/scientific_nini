"""试用模式状态计算逻辑单元测试（按次数限额）。"""

from __future__ import annotations

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


async def _call_get_trial_status(
    rows: list[tuple[str, str]],
    *,
    fast_limit: int = 50,
    deep_limit: int = 20,
    usage: tuple[int, int] = (0, 0),
) -> dict:
    """辅助：以指定行数据和用量限额调用 get_trial_status()。"""
    db = _build_db_mock(rows)

    async def fake_get_db():
        return db

    with (
        patch("nini._config_trial.get_db", fake_get_db),
        patch("nini._config_trial.settings") as mock_settings,
        patch(
            "nini._config_trial.get_builtin_usage",
            AsyncMock(return_value={"fast": usage[0], "deep": usage[1]}),
        ),
    ):
        mock_settings.builtin_fast_limit = fast_limit
        mock_settings.builtin_deep_limit = deep_limit
        # 延迟导入确保 patch 生效
        from nini.config_manager import get_trial_status

        return await get_trial_status()


# ---- 测试用例 ----


@pytest.mark.asyncio
async def test_trial_not_activated():
    """DB 无记录时：未激活，且试用未耗尽。"""
    result = await _call_get_trial_status(rows=[], usage=(0, 0))
    assert result["activated"] is False
    assert result["expired"] is False
    assert result["fast_calls_used"] == 0
    assert result["deep_calls_used"] == 0


@pytest.mark.asyncio
async def test_trial_activated_within_usage_limits():
    """已激活且两种模式仍有剩余次数：未耗尽。"""
    rows = [("trial_activated", "true")]
    result = await _call_get_trial_status(rows=rows, fast_limit=10, deep_limit=5, usage=(2, 1))
    assert result["activated"] is True
    assert result["expired"] is False
    assert result["fast_calls_remaining"] == 8
    assert result["deep_calls_remaining"] == 4


@pytest.mark.asyncio
async def test_trial_expired_when_all_builtin_modes_exhausted():
    """仅当 fast/deep 都达到上限时，试用视为耗尽。"""
    rows = [("trial_activated", "true")]
    result = await _call_get_trial_status(rows=rows, fast_limit=10, deep_limit=5, usage=(10, 5))
    assert result["activated"] is True
    assert result["expired"] is True
    assert result["fast_calls_remaining"] == 0
    assert result["deep_calls_remaining"] == 0


@pytest.mark.asyncio
async def test_trial_not_expired_when_one_mode_still_available():
    """一个模式耗尽但另一个模式仍可用时，不应阻断试用。"""
    rows = [("trial_activated", "true")]
    result = await _call_get_trial_status(rows=rows, fast_limit=10, deep_limit=5, usage=(10, 4))
    assert result["expired"] is False
    assert result["fast_calls_remaining"] == 0
    assert result["deep_calls_remaining"] == 1
