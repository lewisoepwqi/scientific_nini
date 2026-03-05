"""长期记忆注入上下文单元测试。

覆盖：
- build_long_term_memory_context() 有记忆时返回包含 long_term_memory 标签的字符串
- build_long_term_memory_context() 无记忆时返回空字符串
- build_long_term_memory_context() 空 query 时返回空字符串
- 异常时静默返回空字符串
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_build_long_term_memory_context_with_results():
    """有检索结果时应返回包含 long_term_memory 标签的字符串。"""
    from nini.memory.long_term_memory import LongTermMemoryEntry

    entry = LongTermMemoryEntry(
        id=str(uuid.uuid4()),
        memory_type="finding",
        content="实验组平均值显著高于对照组（t=3.2, p=0.002, d=0.78）",
        summary="t 检验结果显著",
        source_session_id="prev-session",
    )

    mock_store = MagicMock()
    mock_store.search = AsyncMock(return_value=[entry])

    # context_memory.py 内部做懒导入，patch 路径指向实际模块
    with (
        patch("nini.memory.long_term_memory.get_long_term_memory_store", return_value=mock_store),
        patch(
            "nini.memory.long_term_memory.format_memories_for_context",
            return_value="## 历史分析记忆\n\n1. [FINDING] t 检验结果显著",
        ),
    ):
        from nini.agent.components.context_memory import build_long_term_memory_context

        result = await build_long_term_memory_context("比较两组的差异")

    # 实际输出为中文不可信标签包裹，验证非空且包含记忆内容
    assert len(result) > 0
    assert "不可信上下文" in result or "历史分析记忆" in result


@pytest.mark.asyncio
async def test_build_long_term_memory_context_no_results():
    """无检索结果时应返回空字符串。"""
    mock_store = MagicMock()
    mock_store.search = AsyncMock(return_value=[])

    with patch("nini.memory.long_term_memory.get_long_term_memory_store", return_value=mock_store):
        from nini.agent.components.context_memory import build_long_term_memory_context

        result = await build_long_term_memory_context("任意查询")

    assert result == ""


@pytest.mark.asyncio
async def test_build_long_term_memory_context_empty_query():
    """空 query 时应直接返回空字符串，不触发检索。"""
    mock_store = MagicMock()
    mock_store.search = AsyncMock(return_value=[])

    with patch("nini.memory.long_term_memory.get_long_term_memory_store", return_value=mock_store):
        from nini.agent.components.context_memory import build_long_term_memory_context

        result = await build_long_term_memory_context("")

    assert result == ""
    mock_store.search.assert_not_called()


@pytest.mark.asyncio
async def test_build_long_term_memory_context_exception_returns_empty():
    """检索抛出异常时应静默返回空字符串。"""
    mock_store = MagicMock()
    mock_store.search = AsyncMock(side_effect=RuntimeError("向量存储不可用"))

    with patch("nini.memory.long_term_memory.get_long_term_memory_store", return_value=mock_store):
        from nini.agent.components.context_memory import build_long_term_memory_context

        result = await build_long_term_memory_context("查询某个主题")

    assert result == ""
