"""长期记忆注入上下文单元测试（基于 SQLite MemoryStore / MemoryManager）。

覆盖：
- build_long_term_memory_context() MemoryManager 有记忆时返回非空字符串
- build_long_term_memory_context() 无记忆时返回空字符串
- build_long_term_memory_context() 空 query 时返回空字符串
- MemoryManager 未初始化时静默返回空字符串
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_build_long_term_memory_context_with_results():
    """MemoryManager.prefetch_all 返回内容时，应返回含不可信上下文标签的字符串。"""
    mock_mm = MagicMock()
    mock_mm.prefetch_all = AsyncMock(
        return_value="[FINDING] t 检验结果显著（来源：experiment.csv）"
    )

    # 在 context_memory.py 中，get_memory_manager 通过懒导入调用
    # 需要 patch 到实际被调用的 nini.memory.manager.get_memory_manager
    with patch("nini.memory.manager.get_memory_manager", return_value=mock_mm):
        from nini.agent.components.context_memory import build_long_term_memory_context

        result = await build_long_term_memory_context("比较两组的差异")

    assert len(result) > 0


@pytest.mark.asyncio
async def test_build_long_term_memory_context_no_results():
    """MemoryManager.prefetch_all 返回空字符串时，应返回空字符串。"""
    mock_mm = MagicMock()
    mock_mm.prefetch_all = AsyncMock(return_value="")

    with patch("nini.memory.manager.get_memory_manager", return_value=mock_mm):
        from nini.agent.components.context_memory import build_long_term_memory_context

        result = await build_long_term_memory_context("任意查询")

    assert result == ""


@pytest.mark.asyncio
async def test_build_long_term_memory_context_empty_query():
    """空 query 时应直接返回空字符串，不触发检索。"""
    mock_mm = MagicMock()
    mock_mm.prefetch_all = AsyncMock(return_value="some content")

    with patch("nini.memory.manager.get_memory_manager", return_value=mock_mm):
        from nini.agent.components.context_memory import build_long_term_memory_context

        result = await build_long_term_memory_context("")

    # 空 query 直接 early-return
    assert result == ""
    mock_mm.prefetch_all.assert_not_called()


@pytest.mark.asyncio
async def test_build_long_term_memory_context_manager_none_returns_empty():
    """get_memory_manager() 返回 None 时应静默返回空字符串。"""
    with patch("nini.memory.manager.get_memory_manager", return_value=None):
        from nini.agent.components.context_memory import build_long_term_memory_context

        result = await build_long_term_memory_context("查询某个主题")

    assert result == ""


@pytest.mark.asyncio
async def test_build_long_term_memory_context_exception_returns_empty():
    """prefetch_all 抛出异常时应静默返回空字符串。"""
    mock_mm = MagicMock()
    mock_mm.prefetch_all = AsyncMock(side_effect=RuntimeError("存储不可用"))

    with patch("nini.memory.manager.get_memory_manager", return_value=mock_mm):
        from nini.agent.components.context_memory import build_long_term_memory_context

        result = await build_long_term_memory_context("查询某个主题")

    assert result == ""
