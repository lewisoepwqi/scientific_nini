"""测试 agent/loop_guard.py 的循环检测逻辑。

覆盖范围：
  - _hash_tool_calls 哈希函数的正确性
  - NORMAL / WARN / FORCE_STOP 三条决策路径
  - session 隔离
  - LRU 缓存淘汰
  - runner.py 集成（WARN 注入 SystemMessage，FORCE_STOP 终止工具执行）
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nini.agent.loop_guard import (
    LoopGuard,
    LoopGuardDecision,
    _hash_tool_calls,
    build_loop_warn_message,
)

# ---------------------------------------------------------------------------
# 工具函数：构造模拟 tool_call 字典
# ---------------------------------------------------------------------------


def _make_tc(name: str, **kwargs: Any) -> dict[str, Any]:
    """构造模拟的 tool_call 字典（与 runner.py 中的格式一致）。"""
    return {
        "id": f"call_{name}",
        "function": {
            "name": name,
            "arguments": __import__("json").dumps(kwargs),
        },
    }


# ---------------------------------------------------------------------------
# 3.2 _hash_tool_calls 测试
# ---------------------------------------------------------------------------


class TestHashToolCalls:
    """测试 _hash_tool_calls 函数。"""

    def test_same_calls_same_order_produces_same_hash(self):
        """相同工具调用顺序相同 → 相同哈希。"""
        tc = [_make_tc("load_dataset", path="/data/a.csv")]
        assert _hash_tool_calls(tc) == _hash_tool_calls(tc)

    def test_same_calls_different_order_produces_same_hash(self):
        """相同工具调用不同顺序 → 相同哈希（顺序无关）。"""
        tc1 = [
            _make_tc("load_dataset", path="/data/a.csv"),
            _make_tc("t_test", col="x"),
        ]
        tc2 = [
            _make_tc("t_test", col="x"),
            _make_tc("load_dataset", path="/data/a.csv"),
        ]
        assert _hash_tool_calls(tc1) == _hash_tool_calls(tc2)

    def test_different_args_produces_different_hash(self):
        """相同工具名但不同参数 → 不同哈希。"""
        tc1 = [_make_tc("load_dataset", path="/data/a.csv")]
        tc2 = [_make_tc("load_dataset", path="/data/b.csv")]
        assert _hash_tool_calls(tc1) != _hash_tool_calls(tc2)

    def test_different_tool_names_produces_different_hash(self):
        """不同工具名 → 不同哈希。"""
        tc1 = [_make_tc("t_test", col="x")]
        tc2 = [_make_tc("anova", col="x")]
        assert _hash_tool_calls(tc1) != _hash_tool_calls(tc2)

    def test_hash_length_is_12(self):
        """哈希结果应为 12 位字符串。"""
        tc = [_make_tc("run_code", code="print(1)")]
        result = _hash_tool_calls(tc)
        assert len(result) == 12
        assert result.isalnum()

    def test_empty_tool_calls_produces_consistent_hash(self):
        """空列表应返回一致的哈希（不崩溃）。"""
        assert _hash_tool_calls([]) == _hash_tool_calls([])


# ---------------------------------------------------------------------------
# 3.3-3.7 LoopGuard.check 决策路径测试
# ---------------------------------------------------------------------------


class TestLoopGuardDecisions:
    """测试 LoopGuard 三级决策路径。"""

    def setup_method(self):
        """每个测试用例使用独立的 LoopGuard 实例（warn=3, hard=5, window=20）。"""
        self.guard = LoopGuard(warn_threshold=3, hard_limit=5, window_size=20)
        self.session = "session-test"
        self.tc = [_make_tc("load_dataset", path="/data/a.csv")]

    def test_normal_path_first_call(self):
        """第 1 次出现 → NORMAL，工具名列表为空。"""
        decision, tool_names = self.guard.check(self.tc, self.session)
        assert decision == LoopGuardDecision.NORMAL
        assert tool_names == []

    def test_normal_path_second_call(self):
        """第 2 次出现 → NORMAL。"""
        self.guard.check(self.tc, self.session)
        decision, tool_names = self.guard.check(self.tc, self.session)
        assert decision == LoopGuardDecision.NORMAL
        assert tool_names == []

    def test_warn_path_third_call(self):
        """第 3 次出现 → WARN，返回重复工具名。"""
        for _ in range(2):
            self.guard.check(self.tc, self.session)
        decision, tool_names = self.guard.check(self.tc, self.session)
        assert decision == LoopGuardDecision.WARN
        assert tool_names == ["load_dataset"]

    def test_warn_path_fourth_call(self):
        """第 4 次出现（介于 warn 和 hard_limit 之间）→ WARN。"""
        for _ in range(3):
            self.guard.check(self.tc, self.session)
        decision, tool_names = self.guard.check(self.tc, self.session)
        assert decision == LoopGuardDecision.WARN
        assert "load_dataset" in tool_names

    def test_force_stop_path_fifth_call(self):
        """第 5 次出现 → FORCE_STOP，返回重复工具名。"""
        for _ in range(4):
            self.guard.check(self.tc, self.session)
        decision, tool_names = self.guard.check(self.tc, self.session)
        assert decision == LoopGuardDecision.FORCE_STOP
        assert tool_names == ["load_dataset"]

    def test_force_stop_beyond_hard_limit(self):
        """超过 hard_limit 次 → 持续返回 FORCE_STOP。"""
        decision = LoopGuardDecision.NORMAL
        for _ in range(10):
            decision, _ = self.guard.check(self.tc, self.session)
        assert decision == LoopGuardDecision.FORCE_STOP

    def test_different_fingerprint_resets_count(self):
        """不同 fingerprint 的出现次数独立计数。"""
        tc2 = [_make_tc("t_test", col="y")]
        for _ in range(4):
            self.guard.check(self.tc, self.session)
        # tc2 首次出现应为 NORMAL
        decision, tool_names = self.guard.check(tc2, self.session)
        assert decision == LoopGuardDecision.NORMAL
        assert tool_names == []


# ---------------------------------------------------------------------------
# 3.6 Session 隔离测试
# ---------------------------------------------------------------------------


class TestSessionIsolation:
    """测试不同 session 的状态互不干扰。"""

    def test_session_a_state_does_not_affect_session_b(self):
        """session A 中 fingerprint 出现 4 次（WARN 状态）不影响 session B。"""
        guard = LoopGuard()
        tc = [_make_tc("run_code", code="1+1")]
        for _ in range(4):
            guard.check(tc, "session-a")
        # session-b 中相同 fingerprint 首次出现 → 应为 NORMAL
        decision, _ = guard.check(tc, "session-b")
        assert decision == LoopGuardDecision.NORMAL

    def test_multiple_sessions_independent_counts(self):
        """多个 session 各自维护独立计数。"""
        guard = LoopGuard(warn_threshold=3, hard_limit=5)
        tc = [_make_tc("data_summary")]
        sessions = ["s1", "s2", "s3"]
        for sid in sessions:
            for _ in range(2):
                decision, _ = guard.check(tc, sid)
                assert decision == LoopGuardDecision.NORMAL


# ---------------------------------------------------------------------------
# 3.7 LRU 淘汰测试
# ---------------------------------------------------------------------------


class TestLRUEviction:
    """测试超出 max_sessions 时最旧 session 被淘汰。"""

    def test_lru_eviction_oldest_session(self):
        """缓存已满时插入新 session，最旧 session 状态被淘汰并重新初始化。"""
        max_sessions = 5
        guard = LoopGuard(max_sessions=max_sessions)
        tc = [_make_tc("t_test", col="x")]

        # 填满缓存：session-0 是最旧的
        for i in range(max_sessions):
            guard.check(tc, f"session-{i}")

        # session-0 中目前有 1 次记录
        # 访问 session-1 到 session-4，使 session-0 成为最旧
        for i in range(1, max_sessions):
            guard.check(tc, f"session-{i}")

        # 插入第 max_sessions+1 个新 session，触发 LRU 淘汰 session-0
        guard.check(tc, "session-new")
        assert len(guard._cache) == max_sessions

        # session-0 已被淘汰，其计数重置
        # 再次访问 session-0 应返回 NORMAL（第 1 次出现，不是第 2 次）
        decision, _ = guard.check(tc, "session-0")
        assert decision == LoopGuardDecision.NORMAL

    def test_lru_max_sessions_respected(self):
        """缓存内 session 数量不超过 max_sessions。"""
        max_sessions = 10
        guard = LoopGuard(max_sessions=max_sessions)
        tc = [_make_tc("correlation")]
        for i in range(max_sessions * 2):
            guard.check(tc, f"session-{i}")
        assert len(guard._cache) == max_sessions

    def test_sliding_window_evicts_old_fingerprints(self):
        """滑动窗口超出 window_size 时，旧 fingerprint 自动淘汰。"""
        guard = LoopGuard(warn_threshold=3, hard_limit=5, window_size=5)
        tc_a = [_make_tc("t_test", col="x")]
        tc_noise = [_make_tc("run_code", code=f"print({i})") for i in range(1)]  # 不同调用

        # 先触发 3 次 tc_a（第 3 次 = WARN）
        for _ in range(3):
            guard.check(tc_a, "s1")

        # 用 5 次不同的 noise 调用填满窗口，将 tc_a 的记录从窗口中挤出
        for i in range(5):
            tc_noise_i = [_make_tc("run_code", code=f"x={i}")]
            guard.check(tc_noise_i, "s1")

        # tc_a 已被完全挤出滑动窗口（窗口大小=5），再次出现应返回 NORMAL
        decision, _ = guard.check(tc_a, "s1")
        assert decision == LoopGuardDecision.NORMAL


# ---------------------------------------------------------------------------
# 3.8-3.9 Runner 集成测试
# ---------------------------------------------------------------------------


class TestRunnerIntegration:
    """集成测试：验证 runner.py 中 WARN/FORCE_STOP 的实际行为。

    采用直接 mock runner 内部私有方法的策略，避免完整启动 AgentRunner 的复杂依赖链。
    """

    def _make_tool_call_dict(self, name: str = "run_code", args: str = '{"code":"1+1"}') -> dict:
        """构造 runner.py 中实际使用的 tool_call 格式。"""
        return {
            "id": f"call_{name}_1",
            "function": {"name": name, "arguments": args},
        }

    @pytest.mark.asyncio
    async def test_warn_decision_injects_system_message(self):
        """WARN 决策导致下一轮 LLM 请求消息列表中包含循环警告 SystemMessage。"""
        from nini.agent.runner import AgentRunner

        runner = AgentRunner()
        # 预置 _loop_guard，使第一次调用直接返回 WARN，第二次返回 NORMAL
        check_call_count = [0]

        def mock_check(tool_calls, session_id):
            check_call_count[0] += 1
            tool_names = [str(tc.get("function", {}).get("name", "")) for tc in tool_calls]
            if check_call_count[0] == 1:
                return LoopGuardDecision.WARN, tool_names
            return LoopGuardDecision.NORMAL, []

        mock_guard = MagicMock()
        mock_guard.check.side_effect = mock_check
        runner._loop_guard = mock_guard

        # 收集每次 LLM 调用时传入的 messages
        injected_messages_per_call: list[list[dict]] = []

        async def mock_chat(messages, tools, **kwargs):
            injected_messages_per_call.append(list(messages))
            if check_call_count[0] <= 1:
                # 第一轮：返回 tool_calls，触发 WARN 逻辑
                yield MagicMock(
                    text="",
                    reasoning=None,
                    tool_calls=[self._make_tool_call_dict()],
                    usage={},
                    model=None,
                    fallback_used=False,
                    fallback_chain=[],
                )
            else:
                # 第二轮：返回纯文本，结束循环
                yield MagicMock(
                    text="分析完成。",
                    reasoning=None,
                    tool_calls=[],
                    usage={},
                    model=None,
                    fallback_used=False,
                    fallback_chain=[],
                )

        tc = self._make_tool_call_dict()

        session = MagicMock()
        session.id = "test-warn-session"
        session.messages = []
        session.conversation_memory = []
        session.task_manager = MagicMock()
        session.task_manager.has_tasks.return_value = False
        session.task_manager.initialized = False
        session.chart_output_preference = None

        # 直接 mock runner 内部方法，绕过完整依赖链
        with (
            patch.object(
                runner,
                "_build_messages_and_retrieval",
                new_callable=AsyncMock,
                return_value=([], None),
            ),
            patch.object(runner, "_maybe_auto_compress", new_callable=AsyncMock, return_value=None),
            patch.object(runner, "_get_tool_definitions", return_value=[]),
            patch.object(runner, "_maybe_handle_intent_clarification", return_value=aiter([])),
            patch.object(runner._resolver, "chat", side_effect=mock_chat),
            patch.object(
                runner, "_execute_tool", new_callable=AsyncMock, return_value={"result": "ok"}
            ),
            patch.object(
                runner,
                "_resolve_allowed_tool_recommendations",
                return_value=(None, []),
            ),
            patch("nini.agent.runner.session_manager"),
            patch("nini.config_manager.get_active_provider_id", new_callable=AsyncMock) as mock_p,
            patch(
                "nini.config_manager.list_user_configured_provider_ids",
                new_callable=AsyncMock,
            ) as mock_c,
        ):
            mock_p.return_value = "openai"
            mock_c.return_value = ["openai"]

            events = []
            async for evt in runner.run(session, "帮我分析数据", append_user_message=False):
                events.append(evt)

        # 验证：第二轮 LLM 调用的消息列表中包含循环警告 SystemMessage
        assert (
            len(injected_messages_per_call) >= 2
        ), f"LLM 应被调用至少两次，实际: {len(injected_messages_per_call)}"
        second_call_messages = injected_messages_per_call[1]
        warn_msgs = [
            m
            for m in second_call_messages
            if m.get("role") == "system" and "循环" in m.get("content", "")
        ]
        assert (
            len(warn_msgs) >= 1
        ), f"第二轮 LLM 调用未包含循环警告 SystemMessage，消息列表: {second_call_messages}"

    @pytest.mark.asyncio
    async def test_force_stop_does_not_execute_tools(self):
        """FORCE_STOP 决策导致推送 text 事件且不执行任何工具。"""
        from nini.agent.events import EventType
        from nini.agent.runner import AgentRunner

        runner = AgentRunner()
        mock_guard = MagicMock()
        mock_guard.check.return_value = (LoopGuardDecision.FORCE_STOP, ["run_code"])
        runner._loop_guard = mock_guard

        async def mock_chat(messages, tools, **kwargs):
            yield MagicMock(
                text="",
                reasoning=None,
                tool_calls=[self._make_tool_call_dict()],
                usage={},
                model=None,
                fallback_used=False,
                fallback_chain=[],
            )

        session = MagicMock()
        session.id = "test-force-session"
        session.messages = []
        session.conversation_memory = []
        session.task_manager = MagicMock()
        session.task_manager.has_tasks.return_value = False
        session.task_manager.initialized = False
        session.chart_output_preference = None

        tool_executed = []

        with (
            patch.object(
                runner,
                "_build_messages_and_retrieval",
                new_callable=AsyncMock,
                return_value=([], None),
            ),
            patch.object(runner, "_maybe_auto_compress", new_callable=AsyncMock, return_value=None),
            patch.object(runner, "_get_tool_definitions", return_value=[]),
            patch.object(runner, "_maybe_handle_intent_clarification", return_value=aiter([])),
            patch.object(runner._resolver, "chat", side_effect=mock_chat),
            patch(
                "nini.agent.runner.execute_tool",
                side_effect=lambda *a, **kw: tool_executed.append(1),
            ),
            patch("nini.agent.runner.session_manager"),
            patch("nini.config_manager.get_active_provider_id", new_callable=AsyncMock) as mock_p,
            patch(
                "nini.config_manager.list_user_configured_provider_ids",
                new_callable=AsyncMock,
            ) as mock_c,
        ):
            mock_p.return_value = "openai"
            mock_c.return_value = ["openai"]

            events = []
            async for evt in runner.run(session, "帮我分析", append_user_message=False):
                events.append(evt)

        # 验证：工具未被执行
        assert len(tool_executed) == 0, "FORCE_STOP 时不应执行任何工具"

        # 验证：推送了含"循环"关键词的 text 事件
        text_events = [
            e
            for e in events
            if hasattr(e, "type") and e.type == EventType.TEXT and "循环" in str(e.data)
        ]
        assert len(text_events) >= 1, f"未找到 FORCE_STOP text 事件，收到事件: {events}"


# ---------------------------------------------------------------------------
# build_loop_warn_message 测试
# ---------------------------------------------------------------------------


class TestBuildLoopWarnMessage:
    """测试针对性循环警告消息生成。"""

    def test_known_tool_produces_specific_hint(self):
        """已知工具名应生成包含具体建议的警告消息。"""
        msg = build_loop_warn_message(["dataset_catalog"])
        assert "具体建议" in msg
        assert "直接进入分析步骤" in msg

    def test_unknown_tool_produces_generic_hint(self):
        """未知工具名应使用通用反思建议。"""
        msg = build_loop_warn_message(["unknown_tool"])
        assert "换一种方法" in msg
        assert "具体建议" not in msg

    def test_multiple_known_tools(self):
        """多个已知工具名应生成多条具体建议。"""
        msg = build_loop_warn_message(["stat_test", "code_session"])
        assert "统计检验" in msg
        assert "代码反复执行" in msg

    def test_empty_tool_names(self):
        """空工具名列表应使用通用反思建议。"""
        msg = build_loop_warn_message([])
        assert "换一种方法" in msg


def aiter(iterable):
    """将同步可迭代对象包装为异步生成器（用于 mock async for 的方法）。"""

    async def _gen():
        for item in iterable:
            yield item

    return _gen()
