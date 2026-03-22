"""Fresh Tail 保护回归测试。

验证压缩函数正确保留最近 N 条消息，修复 archive_count 语义 Bug。
"""

from __future__ import annotations

import pytest

from nini.agent.session import Session
from nini.memory.compression import compress_session_history, compress_session_history_with_llm


def _make_session_with_messages(n: int) -> Session:
    """创建包含 n 条消息的测试会话（不持久化）。"""
    session = Session()
    for i in range(n):
        role = "user" if i % 2 == 0 else "assistant"
        session.messages.append({"role": role, "content": f"消息 {i}"})
    return session


class TestFreshTailProtection:
    """验证 Fresh Tail 保护：保留最近 N 条消息。"""

    def test_bug_regression_total25_keep20(self):
        """精确复现 Bug：total=25, keep_recent=20 时应保留 20 条而非 5 条。"""
        session = _make_session_with_messages(25)
        result = compress_session_history(session, ratio=0.2, min_messages=20)
        assert result["success"] is True
        assert len(session.messages) == 20, (
            f"应保留 20 条，实际保留 {len(session.messages)} 条 (Bug 未修复)"
        )

    def test_keep_recent_respected_various_totals(self):
        """不同消息总数下，保留数量均符合 min_messages 约束。"""
        cases = [
            (25, 20, 0.5),
            (50, 20, 0.5),
            (30, 10, 0.6),
            (40, 15, 0.4),
        ]
        for total, keep, ratio in cases:
            session = _make_session_with_messages(total)
            result = compress_session_history(session, ratio=ratio, min_messages=keep)
            assert result["success"] is True
            assert len(session.messages) >= keep, (
                f"total={total}, keep={keep}, ratio={ratio}: "
                f"应保留 >={keep} 条，实际 {len(session.messages)} 条"
            )

    def test_ratio_limits_single_pass_archive(self):
        """ratio 仍限制单次归档比例，不超过 ratio 倍。"""
        session = _make_session_with_messages(100)
        result = compress_session_history(session, ratio=0.3, min_messages=20)
        assert result["success"] is True
        archived = result["archived_count"]
        assert archived <= int(100 * 0.3) + 1, (
            f"单次归档不应超过 ratio=0.3 的 30 条，实际归档 {archived} 条"
        )
        assert len(session.messages) >= 20

    def test_archive_at_least_one(self):
        """即使保留数等于总数减一，也应归档至少 1 条。"""
        session = _make_session_with_messages(10)
        result = compress_session_history(session, ratio=0.1, min_messages=9)
        assert result["success"] is True
        assert result["archived_count"] >= 1
        assert len(session.messages) == 10 - result["archived_count"]

    def test_insufficient_messages_returns_failure(self):
        """消息数不足时应返回 success=False，不进行压缩。"""
        session = _make_session_with_messages(5)
        result = compress_session_history(session, ratio=0.5, min_messages=10)
        assert result["success"] is False
        assert len(session.messages) == 5  # 消息不变

    def test_archived_messages_are_oldest(self):
        """归档的应该是最旧的消息，保留的应该是最新的。"""
        n = 20
        session = _make_session_with_messages(n)
        original_messages = list(session.messages)

        result = compress_session_history(session, ratio=0.5, min_messages=10)
        assert result["success"] is True

        archived_count = result["archived_count"]
        remaining_count = result["remaining_count"]

        # 保留的消息应该是原来的最后 remaining_count 条
        assert session.messages == original_messages[archived_count:]
        assert len(session.messages) == remaining_count


class TestFreshTailProtectionLLM:
    """验证 LLM 压缩函数也正确保留 Fresh Tail。"""

    async def test_llm_compress_keeps_recent(self, monkeypatch):
        """LLM 压缩函数同样遵守 min_messages 保留约束。"""
        # mock _llm_summarize 避免真实 LLM 调用
        from unittest.mock import AsyncMock, patch

        with patch(
            "nini.memory.compression._llm_summarize",
            new_callable=AsyncMock,
            return_value="摘要内容",
        ):
            session = _make_session_with_messages(30)
            result = await compress_session_history_with_llm(
                session, ratio=0.5, min_messages=20
            )

        assert result["success"] is True
        assert len(session.messages) >= 20, (
            f"LLM 压缩后应保留 >=20 条，实际 {len(session.messages)} 条"
        )
