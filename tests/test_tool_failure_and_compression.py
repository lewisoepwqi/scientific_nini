"""测试工具失败分类修复与压缩摘要保留失败状态。"""

from __future__ import annotations

import json

import pytest

from nini.harness.runner import HarnessRunner
from nini.memory.compression import (
    _append_pending_actions_to_summary,
    _extract_tool_failures,
    _summarize_messages,
)


# ── 改动 1：_classify_tool_failure 通用幂等识别 ──


class TestClassifyToolFailure:
    """测试 _classify_tool_failure 对幂等冲突的分类。"""

    @staticmethod
    def _classify(tool_name: str, message: str, data: dict) -> tuple[str, bool]:
        return HarnessRunner._classify_tool_failure(tool_name=tool_name, message=message, data=data)

    def test_duplicate_dataset_profile_is_nonblocking(self) -> None:
        """DUPLICATE_DATASET_PROFILE_CALL 应被分类为 idempotent_conflict（非阻塞）。"""
        category, blocking = self._classify(
            tool_name="dataset_catalog",
            message="同一轮中已成功调用过相同的 dataset_catalog(profile): test.xlsx",
            data={
                "status": "error",
                "data": {"error_code": "DUPLICATE_DATASET_PROFILE_CALL"},
            },
        )
        assert category == "idempotent_conflict"
        assert blocking is False

    def test_duplicate_prefix_generic(self) -> None:
        """DUPLICATE_* 前缀的 error_code 均应被识别为幂等冲突。"""
        category, blocking = self._classify(
            tool_name="stat_model",
            message="重复请求",
            data={"data": {"error_code": "DUPLICATE_STAT_REQUEST"}},
        )
        assert category == "idempotent_conflict"
        assert blocking is False

    def test_already_prefix_is_nonblocking(self) -> None:
        """ALREADY_* 前缀的 error_code 应被识别为幂等冲突。"""
        category, blocking = self._classify(
            tool_name="code_session",
            message="脚本已在运行",
            data={"data": {"error_code": "ALREADY_RUNNING"}},
        )
        assert category == "idempotent_conflict"
        assert blocking is False

    def test_real_dataset_catalog_error_is_blocking(self) -> None:
        """dataset_catalog 的真实错误（非幂等）应仍为 blocking。"""
        category, blocking = self._classify(
            tool_name="dataset_catalog",
            message="数据集不存在: missing.xlsx",
            data={"status": "error", "data": {"error_code": "DATASET_NOT_FOUND"}},
        )
        assert category == "blocking_failure"
        assert blocking is True

    def test_task_state_noop_is_nonblocking(self) -> None:
        """task_state 的 no-op 应保持原有的非阻塞分类。"""
        category, blocking = self._classify(
            tool_name="task_state",
            message="无变化",
            data={
                "result": {
                    "data": {"no_op_ids": [1, 2], "error_code": None},
                }
            },
        )
        assert blocking is False

    def test_circuit_breaker_is_nonblocking(self) -> None:
        """Agent runner 的 TOOL_CALL_CIRCUIT_BREAKER 应为非阻塞（本质是幂等冲突的升级版）。"""
        category, blocking = self._classify(
            tool_name="dataset_catalog",
            message="检测到相同工具调用已连续失败 3 次，已触发熔断并阻止本次重复调用。",
            data={
                "data": {
                    "error_code": "TOOL_CALL_CIRCUIT_BREAKER",
                    "last_error_code": "DUPLICATE_DATASET_PROFILE_CALL",
                }
            },
        )
        assert category == "idempotent_conflict"
        assert blocking is False

    def test_duplicate_in_result_payload(self) -> None:
        """error_code 在 data.result 中（真实 agent runner 事件结构）。"""
        category, blocking = self._classify(
            tool_name="dataset_catalog",
            message="同一轮中已成功调用过相同的 dataset_catalog(profile): test.xlsx",
            data={
                "status": "error",
                "message": "同一轮中已成功调用过相同的 dataset_catalog(profile): test.xlsx",
                "result": {
                    "success": False,
                    "message": "同一轮中已成功调用过相同的 dataset_catalog(profile): test.xlsx",
                    "error_code": "DUPLICATE_DATASET_PROFILE_CALL",
                    "recovery_hint": "已获取数据概况",
                },
                "data": {
                    "result": {
                        "success": False,
                        "message": "同一轮中已成功调用过相同的 dataset_catalog(profile): test.xlsx",
                        "error_code": "DUPLICATE_DATASET_PROFILE_CALL",
                        "recovery_hint": "已获取数据概况",
                    },
                },
            },
        )
        assert category == "idempotent_conflict"
        assert blocking is False

    def test_duplicate_at_top_level(self) -> None:
        """error_code 在 data 顶层（某些工具直接返回的结构）。"""
        category, blocking = self._classify(
            tool_name="dataset_catalog",
            message="重复调用",
            data={
                "status": "error",
                "error_code": "DUPLICATE_DATASET_PROFILE_CALL",
            },
        )
        assert category == "idempotent_conflict"
        assert blocking is False


# ── 改动 2a：_extract_tool_failures ──


class TestExtractToolFailures:
    """测试 _extract_tool_failures 从消息列表提取失败记录。"""

    def test_extracts_error_tool_result(self) -> None:
        messages = [
            {
                "role": "tool",
                "status": "error",
                "tool_name": "dataset_catalog",
                "content": json.dumps(
                    {
                        "success": False,
                        "message": "同一轮中已成功调用过相同的 dataset_catalog(profile): test.xlsx",
                        "error_code": "DUPLICATE_DATASET_PROFILE_CALL",
                        "metadata": {"duplicate_profile_blocked": True},
                    }
                ),
            }
        ]
        failures = _extract_tool_failures(messages)
        assert len(failures) == 1
        assert "dataset_catalog" in failures[0]
        assert "重复调用" in failures[0]

    def test_extracts_generic_failure(self) -> None:
        messages = [
            {
                "role": "tool",
                "status": "error",
                "tool_name": "stat_model",
                "content": json.dumps(
                    {
                        "success": False,
                        "message": "列不存在: foo",
                        "error_code": "INVALID_COLUMN",
                    }
                ),
            }
        ]
        failures = _extract_tool_failures(messages)
        assert len(failures) == 1
        assert "stat_model 失败" in failures[0]
        assert "[INVALID_COLUMN]" in failures[0]

    def test_no_failures_returns_empty(self) -> None:
        messages = [
            {
                "role": "tool",
                "status": "success",
                "tool_name": "dataset_catalog",
                "content": json.dumps({"success": True}),
            }
        ]
        failures = _extract_tool_failures(messages)
        assert failures == []

    def test_non_tool_messages_ignored(self) -> None:
        messages = [
            {"role": "assistant", "content": "你好"},
            {"role": "user", "content": "开始"},
        ]
        failures = _extract_tool_failures(messages)
        assert failures == []

    def test_deduplication(self) -> None:
        msg = {
            "role": "tool",
            "status": "error",
            "tool_name": "dataset_catalog",
            "content": json.dumps(
                {
                    "success": False,
                    "message": "重复调用",
                    "error_code": "DUPLICATE_DATASET_PROFILE_CALL",
                    "metadata": {"duplicate_profile_blocked": True},
                }
            ),
        }
        failures = _extract_tool_failures([msg, msg])
        assert len(failures) == 1


# ── 改动 2b：_summarize_messages 集成 ──


class TestSummarizeMessagesWithFailures:
    """测试 _summarize_messages 包含工具失败记录。"""

    def test_summary_includes_failure_section(self) -> None:
        messages = [
            {"role": "user", "content": "开始分析"},
            {
                "role": "assistant",
                "content": "调用工具",
                "tool_calls": [
                    {
                        "function": {
                            "name": "dataset_catalog",
                            "arguments": '{"operation":"profile"}',
                        }
                    }
                ],
            },
            {
                "role": "tool",
                "status": "error",
                "tool_name": "dataset_catalog",
                "content": json.dumps(
                    {
                        "success": False,
                        "message": "重复调用",
                        "error_code": "DUPLICATE_DATASET_PROFILE_CALL",
                        "metadata": {"duplicate_profile_blocked": True},
                    }
                ),
            },
        ]
        summary = _summarize_messages(messages)
        assert "工具失败记录" in summary
        assert "dataset_catalog" in summary


# ── 改动 2c：_append_pending_actions_to_summary ──


class TestAppendPendingActions:
    """测试压缩摘要追加 pending_actions。"""

    def test_appends_blocking_action(self) -> None:
        summary = "时间线:\n- [用户] 开始"
        pending = [
            {
                "blocking": True,
                "summary": "dataset_catalog 失败：重复调用",
                "type": "tool_failure_unresolved",
            }
        ]
        result = _append_pending_actions_to_summary(summary, pending)
        assert "当前待处理动作" in result
        assert "[阻塞]" in result
        assert "dataset_catalog" in result

    def test_no_pending_actions_unchanged(self) -> None:
        summary = "原始摘要"
        result = _append_pending_actions_to_summary(summary, [])
        assert result == summary

    def test_nonblocking_action(self) -> None:
        pending = [
            {
                "blocking": False,
                "summary": "提醒：检查数据",
                "type": "user_confirmation_pending",
            }
        ]
        result = _append_pending_actions_to_summary("摘要", pending)
        assert "[非阻塞]" in result
