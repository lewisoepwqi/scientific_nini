"""成本模型测试。"""

import pytest
from datetime import datetime, timezone
from nini.models.cost import (
    ModelTokenUsage,
    TokenUsage,
    ModelPricing,
    PricingConfig,
    SessionCostSummary,
    AggregateCostSummary,
)


class TestModelTokenUsage:
    """ModelTokenUsage 模型测试。"""

    def test_basic_creation(self):
        """测试基本创建。"""
        usage = ModelTokenUsage(
            model_id="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
            total_tokens=1500,
            cost_cny=0.5,
            cost_usd=0.07,
            call_count=2,
        )
        assert usage.model_id == "gpt-4o"
        assert usage.input_tokens == 1000
        assert usage.output_tokens == 500
        assert usage.total_tokens == 1500
        assert usage.cost_cny == 0.5
        assert usage.cost_usd == 0.07
        assert usage.call_count == 2

    def test_default_values(self):
        """测试默认值。"""
        usage = ModelTokenUsage(model_id="gpt-4o")
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0
        assert usage.total_tokens == 0
        assert usage.cost_cny == 0.0
        assert usage.cost_usd == 0.0
        assert usage.call_count == 0


class TestTokenUsage:
    """TokenUsage 模型测试。"""

    def test_basic_creation(self):
        """测试基本创建。"""
        usage = TokenUsage(
            session_id="test-session",
            input_tokens=1000,
            output_tokens=500,
            total_tokens=1500,
            estimated_cost_cny=0.5,
            estimated_cost_usd=0.07,
        )
        assert usage.session_id == "test-session"
        assert usage.input_tokens == 1000
        assert usage.output_tokens == 500
        assert usage.total_tokens == 1500
        assert usage.estimated_cost_cny == 0.5
        assert usage.estimated_cost_usd == 0.07

    def test_to_dict(self):
        """测试转换为字典。"""
        model_usage = ModelTokenUsage(
            model_id="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
            total_tokens=1500,
            cost_cny=0.5,
            cost_usd=0.07,
            call_count=2,
        )
        usage = TokenUsage(
            session_id="test-session",
            input_tokens=1000,
            output_tokens=500,
            total_tokens=1500,
            estimated_cost_cny=0.5,
            estimated_cost_usd=0.07,
            model_breakdown={"gpt-4o": model_usage},
        )
        data = usage.to_dict()
        assert data["session_id"] == "test-session"
        assert data["input_tokens"] == 1000
        assert data["output_tokens"] == 500
        assert data["total_tokens"] == 1500
        assert data["estimated_cost_cny"] == 0.5
        assert data["estimated_cost_usd"] == 0.07
        assert "gpt-4o" in data["model_breakdown"]


class TestModelPricing:
    """ModelPricing 模型测试。"""

    def test_basic_creation(self):
        """测试基本创建。"""
        pricing = ModelPricing(
            input_price=0.0025,
            output_price=0.01,
            currency="USD",
            tier="standard",
        )
        assert pricing.input_price == 0.0025
        assert pricing.output_price == 0.01
        assert pricing.currency == "USD"
        assert pricing.tier == "standard"

    def test_calculate_cost(self):
        """测试成本计算。"""
        pricing = ModelPricing(
            input_price=0.0025,
            output_price=0.01,
            currency="USD",
            tier="standard",
        )
        # (1000 * 0.0025 + 500 * 0.01) / 1000 = 0.0075
        cost = pricing.calculate_cost(1000, 500)
        assert cost == 0.0075


class TestPricingConfig:
    """PricingConfig 模型测试。"""

    def test_get_model_pricing_exact_match(self):
        """测试精确匹配模型定价。"""
        pricing = ModelPricing(input_price=0.0025, output_price=0.01)
        config = PricingConfig(
            models={"gpt-4o": pricing},
            usd_to_cny_rate=7.2,
        )
        result = config.get_model_pricing("gpt-4o")
        assert result is not None
        assert result.input_price == 0.0025

    def test_calculate_cost_cny(self):
        """测试人民币成本计算。"""
        pricing = ModelPricing(input_price=0.0025, output_price=0.01)
        config = PricingConfig(
            models={"gpt-4o": pricing},
            usd_to_cny_rate=7.2,
        )
        # USD cost: 0.0075, CNY cost: 0.0075 * 7.2 = 0.054
        cost_cny = config.calculate_cost_cny("gpt-4o", 1000, 500)
        assert abs(cost_cny - 0.054) < 0.001

    def test_calculate_cost_usd(self):
        """测试美元成本计算。"""
        pricing = ModelPricing(input_price=0.0025, output_price=0.01)
        config = PricingConfig(
            models={"gpt-4o": pricing},
            usd_to_cny_rate=7.2,
        )
        cost_usd = config.calculate_cost_usd("gpt-4o", 1000, 500)
        assert abs(cost_usd - 0.0075) < 0.0001


class TestSessionCostSummary:
    """SessionCostSummary 模型测试。"""

    def test_basic_creation(self):
        """测试基本创建。"""
        summary = SessionCostSummary(
            session_id="test-session",
            title="测试会话",
            total_tokens=1500,
            estimated_cost_cny=0.5,
            model_count=2,
        )
        assert summary.session_id == "test-session"
        assert summary.title == "测试会话"
        assert summary.total_tokens == 1500
        assert summary.estimated_cost_cny == 0.5
        assert summary.model_count == 2


class TestAggregateCostSummary:
    """AggregateCostSummary 模型测试。"""

    def test_basic_creation(self):
        """测试基本创建。"""
        summary = AggregateCostSummary(
            total_sessions=10,
            total_tokens=15000,
            total_input_tokens=10000,
            total_output_tokens=5000,
            total_cost_cny=5.0,
            total_cost_usd=0.7,
            average_cost_per_session=0.5,
            most_used_model="gpt-4o",
        )
        assert summary.total_sessions == 10
        assert summary.total_tokens == 15000
        assert summary.total_input_tokens == 10000
        assert summary.total_output_tokens == 5000
        assert summary.total_cost_cny == 5.0
        assert summary.total_cost_usd == 0.7
        assert summary.average_cost_per_session == 0.5
        assert summary.most_used_model == "gpt-4o"
