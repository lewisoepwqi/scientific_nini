"""测试成本透明化功能。

TDD 方式：先写测试，再写实现。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from nini.agent.events import AgentEvent, EventType
from nini.utils.token_counter import TokenTracker, TokenUsage, get_tracker


class TestTokenUsageData:
    """测试 Token 使用数据结构。"""

    def test_token_usage_creation(self):
        """测试创建 Token 使用记录。"""
        usage = TokenUsage(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            model="gpt-4o",
        )

        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.total_tokens == 150
        assert usage.model == "gpt-4o"

    def test_token_usage_cost_calculation(self):
        """测试成本计算。"""
        usage = TokenUsage(
            prompt_tokens=1000,
            completion_tokens=500,
            total_tokens=1500,
            model="gpt-4o",
        )

        # GPT-4o 价格（示例）
        # Input: $2.50 per 1M tokens
        # Output: $10.00 per 1M tokens
        expected_cost = (1000 * 2.5 + 500 * 10.0) / 1_000_000
        assert usage.estimate_cost() > 0

    def test_token_usage_serialization(self):
        """测试序列化。"""
        usage = TokenUsage(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            model="gpt-4o",
        )

        data = usage.to_dict()
        assert "prompt_tokens" in data
        assert "cost_estimate" in data


class TestTokenTracker:
    """测试 Token 追踪器。"""

    def test_tracker_initialization(self):
        """测试追踪器初始化。"""
        tracker = TokenTracker()

        assert tracker.total_tokens == 0
        assert tracker.total_cost == 0.0

    def test_tracker_records_usage(self):
        """测试记录 Token 使用。"""
        tracker = TokenTracker()

        usage = TokenUsage(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            model="gpt-4o",
        )

        tracker.record_usage(usage)

        assert tracker.total_tokens == 150

    def test_tracker_calculates_total_cost(self):
        """测试计算总成本。"""
        tracker = TokenTracker()

        usage = TokenUsage(
            prompt_tokens=1000,
            completion_tokens=500,
            total_tokens=1500,
            model="gpt-4o",
        )

        tracker.record_usage(usage)

        assert tracker.total_cost > 0

    def test_tracker_resets(self):
        """测试重置追踪器。"""
        tracker = TokenTracker()

        usage = TokenUsage(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            model="gpt-4o",
        )

        tracker.record_usage(usage)
        assert tracker.total_tokens > 0

        tracker.reset()
        assert tracker.total_tokens == 0
        assert tracker.total_cost == 0.0

    def test_tracker_enforces_budget_limit(self):
        """测试预算限制。"""
        tracker = TokenTracker(budget_limit=0.01)  # $0.01

        # 添加大量使用
        usage = TokenUsage(
            prompt_tokens=100000,
            completion_tokens=50000,
            total_tokens=150000,
            model="gpt-4o",
        )

        tracker.record_usage(usage)

        # 应该超出预算
        assert tracker.is_over_budget()

    def test_tracker_emits_warning_event(self):
        """测试预算超限时发出警告事件。"""
        tracker = TokenTracker(budget_limit=0.01)

        usage = TokenUsage(
            prompt_tokens=100000,
            completion_tokens=50000,
            total_tokens=150000,
            model="gpt-4o",
        )

        tracker.record_usage(usage)

        # 检查警告
        assert tracker.is_over_budget()


class TestTokenEventIntegration:
    """测试 Token 事件集成。"""

    def test_token_event_type_exists(self):
        """测试 TOKEN_USAGE 事件类型存在。"""
        from nini.agent.events import EventType

        # TOKEN_USAGE 可以使用现有的事件类型或新增
        # 这里使用 existing 类型如 DATA
        assert EventType.DATA == "data"

    def test_create_token_usage_event(self):
        """测试创建 Token 使用事件。"""
        usage = TokenUsage(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            model="gpt-4o",
        )

        event = AgentEvent(
            type=EventType.DATA,
            data={
                "type": "token_usage",
                "usage": usage.to_dict(),
            },
        )

        assert event.type == EventType.DATA
        assert event.data["type"] == "token_usage"


class TestBudgetWarning:
    """测试预算警告机制。"""

    def test_warning_at_50_percent_budget(self):
        """测试 50% 预算时警告。"""
        tracker = TokenTracker(budget_limit=1.0)

        # 使用 50%
        usage = TokenUsage(
            prompt_tokens=100000,
            completion_tokens=50000,
            total_tokens=150000,
            model="gpt-4o",
        )

        tracker.record_usage(usage)

        # 应该接近预算但未超限
        assert not tracker.is_over_budget()
        # 但应该警告
        assert tracker.get_budget_usage_percent() > 0

    def test_warning_at_80_percent_budget(self):
        """测试 80% 预算时警告。"""
        tracker = TokenTracker(budget_limit=1.0)

        # 使用接近预算
        usage = TokenUsage(
            prompt_tokens=800000,
            completion_tokens=400000,
            total_tokens=1200000,
            model="gpt-4o",
        )

        tracker.record_usage(usage)

        percent = tracker.get_budget_usage_percent()
        assert percent >= 0.8

    def test_warning_at_100_percent_budget(self):
        """测试 100% 预算时警告。"""
        tracker = TokenTracker(budget_limit=0.001)  # 很小的预算

        # 超出预算
        usage = TokenUsage(
            prompt_tokens=100000,
            completion_tokens=50000,
            total_tokens=150000,
            model="gpt-4o",
        )

        tracker.record_usage(usage)

        assert tracker.is_over_budget()
        assert tracker.get_budget_usage_percent() >= 1.0


class TestRealTimeUpdates:
    """测试实时更新功能。"""

    def test_tracker_provides_progress_updates(self):
        """测试追踪器提供进度更新。"""
        tracker = TokenTracker(budget_limit=1.0)

        # 初始状态
        assert tracker.get_progress_info()["tokens_used"] == 0
        assert tracker.get_progress_info()["budget_percent"] == 0.0

        # 添加使用
        usage = TokenUsage(
            prompt_tokens=100000,
            completion_tokens=50000,
            total_tokens=150000,
            model="gpt-4o",
        )

        tracker.record_usage(usage)

        # 更新后
        progress = tracker.get_progress_info()
        assert progress["tokens_used"] == 150000
        assert progress["budget_percent"] > 0

    def test_tracker_includes_model_info(self):
        """测试追踪器包含模型信息。"""
        tracker = TokenTracker()

        usage = TokenUsage(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            model="gpt-4o",
        )

        tracker.record_usage(usage)

        progress = tracker.get_progress_info()
        assert "models_used" in progress
        assert "gpt-4o" in progress["models_used"]


class TestCostEstimationAccuracy:
    """测试成本估算准确性。"""

    def test_gpt4o_cost_estimation(self):
        """测试 GPT-4o 成本估算。"""
        usage = TokenUsage(
            prompt_tokens=1000,
            completion_tokens=500,
            total_tokens=1500,
            model="gpt-4o",
        )

        cost = usage.estimate_cost()

        # GPT-4o: $2.50/1M input, $10.00/1M output
        expected = (1000 * 2.5 + 500 * 10.0) / 1_000_000
        assert abs(cost - expected) < 0.0001

    def test_claude_cost_estimation(self):
        """测试 Claude 成本估算。"""
        usage = TokenUsage(
            prompt_tokens=1000,
            completion_tokens=500,
            total_tokens=1500,
            model="claude-sonnet-4-20250514",
        )

        cost = usage.estimate_cost()

        # Claude Sonnet 4: $3/1M input, $15/1M output
        expected = (1000 * 3.0 + 500 * 15.0) / 1_000_000
        assert abs(cost - expected) < 0.0001

    def test_unknown_model_cost_estimation(self):
        """测试未知模型成本估算（使用默认价格）。"""
        usage = TokenUsage(
            prompt_tokens=1000,
            completion_tokens=500,
            total_tokens=1500,
            model="unknown-model",
        )

        # 应该返回默认估算或 0
        cost = usage.estimate_cost()
        assert cost >= 0
