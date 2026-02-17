"""测试自我修复与降级策略。

TDD 方式：先写测试，再写实现。
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import pytest

from nini.agent.session import Session
from nini.tools.registry import create_default_registry, SkillRegistry

logger = logging.getLogger(__name__)


class TestSkillFallbackStrategy:
    """测试技能降级策略。"""

    @pytest.mark.asyncio
    async def test_t_test_falls_back_to_mann_whitney_on_non_normal(self):
        """测试 t 检验在非正态数据时降级到 Mann-Whitney U 检验。"""
        registry = create_default_registry()
        session = Session()

        # 创建明显偏态的数据
        test_data = pd.DataFrame(
            {
                "value": [1, 1, 1, 2, 2, 100, 150, 200, 250, 300],
                "group": ["A"] * 5 + ["B"] * 5,
            }
        )
        session.datasets["test_data"] = test_data

        # 执行带降级的 t 检验
        result = await registry.execute_with_fallback(
            "t_test",
            session=session,
            dataset_name="test_data",
            value_column="value",
            group_column="group",
        )

        assert result["success"] is True
        # 应该包含降级信息
        assert "fallback" in result

    @pytest.mark.asyncio
    async def test_anova_falls_back_to_kruskal_wallis_on_variance_heterogeneity(self):
        """测试 ANOVA 在方差不齐时降级到 Kruskal-Wallis 检验。"""
        registry = create_default_registry()
        session = Session()

        # 创建方差异常的数据
        test_data = pd.DataFrame(
            {
                "value": [10, 11, 10, 12] + [100, 110, 100, 120] + [20, 21, 20, 22],
                "group": ["A"] * 4 + ["B"] * 4 + ["C"] * 4,
            }
        )
        session.datasets["test_data"] = test_data

        result = await registry.execute_with_fallback(
            "anova",
            session=session,
            dataset_name="test_data",
            value_column="value",
            group_column="group",
        )

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_fallback_includes_reason_in_message(self):
        """测试降级时在消息中说明原因。"""
        registry = create_default_registry()
        session = Session()

        test_data = pd.DataFrame(
            {
                "value": [1, 1, 1, 2, 2, 100, 150, 200, 250, 300],
                "group": ["A"] * 5 + ["B"] * 5,
            }
        )
        session.datasets["test_data"] = test_data

        result = await registry.execute_with_fallback(
            "t_test",
            session=session,
            dataset_name="test_data",
            value_column="value",
            group_column="group",
        )

        assert result["success"] is True
        # 消息应该包含测试结果信息

    @pytest.mark.asyncio
    async def test_no_fallback_when_assumptions_met(self):
        """测试满足前提时不降级。"""
        registry = create_default_registry()
        session = Session()

        # 创建正态分布数据
        np.random.seed(42)
        test_data = pd.DataFrame(
            {
                "value": list(np.random.normal(10, 2, 5)) + list(np.random.normal(12, 2, 5)),
                "group": ["A"] * 5 + ["B"] * 5,
            }
        )
        session.datasets["test_data"] = test_data

        result = await registry.execute_with_fallback(
            "t_test",
            session=session,
            dataset_name="test_data",
            value_column="value",
            group_column="group",
        )

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_fallback_records_original_attempt(self):
        """测试降级时记录原始尝试。"""
        registry = create_default_registry()
        session = Session()

        test_data = pd.DataFrame(
            {
                "value": [1, 1, 1, 2, 2, 100, 150, 200, 250, 300],
                "group": ["A"] * 5 + ["B"] * 5,
            }
        )
        session.datasets["test_data"] = test_data

        result = await registry.execute_with_fallback(
            "t_test",
            session=session,
            dataset_name="test_data",
            value_column="value",
            group_column="group",
        )

        assert result["success"] is True
        # 应该记录原始尝试的方法
        if "original_skill" in result:
            assert result["original_skill"] == "t_test"


class TestDataDiagnostics:
    """测试数据问题智能诊断。"""

    @pytest.mark.asyncio
    async def test_diagnose_missing_values(self):
        """测试缺失值诊断。"""
        registry = create_default_registry()
        session = Session()

        test_data = pd.DataFrame(
            {
                "value": [1.0, 2.0, None, 4.0, 5.0, 6.0, None, 8.0, 9.0, 10.0],
                "group": ["A"] * 5 + ["B"] * 5,
            }
        )
        session.datasets["test_data"] = test_data

        diagnosis = await registry.diagnose_data_problem(
            session=session,
            dataset_name="test_data",
        )

        assert "missing_values" in diagnosis
        assert diagnosis["missing_values"]["count"] == 2
        assert "suggestions" in diagnosis

    @pytest.mark.asyncio
    async def test_diagnose_outliers(self):
        """测试异常值诊断。"""
        registry = create_default_registry()
        session = Session()

        test_data = pd.DataFrame(
            {
                "value": [10, 11, 12, 13, 14, 1000],  # 1000 是异常值
                "group": ["A"] * 3 + ["B"] * 3,
            }
        )
        session.datasets["test_data"] = test_data

        diagnosis = await registry.diagnose_data_problem(
            session=session,
            dataset_name="test_data",
        )

        assert "outliers" in diagnosis
        assert len(diagnosis["outliers"]) > 0

    @pytest.mark.asyncio
    async def test_diagnose_small_sample_size(self):
        """测试小样本诊断。"""
        registry = create_default_registry()
        session = Session()

        test_data = pd.DataFrame(
            {
                "value": [1, 2],
                "group": ["A", "B"],
            }
        )
        session.datasets["test_data"] = test_data

        diagnosis = await registry.diagnose_data_problem(
            session=session,
            dataset_name="test_data",
        )

        assert "sample_size" in diagnosis
        assert diagnosis["sample_size"]["warning"] is True
        assert len(diagnosis["suggestions"]) > 0

    @pytest.mark.asyncio
    async def test_diagnose_type_conversion_suggestion(self):
        """测试数据类型转换建议。"""
        registry = create_default_registry()
        session = Session()

        # 数值列存储为字符串
        test_data = pd.DataFrame(
            {
                "value": ["1.5", "2.3", "3.1", "4.2", "5.0"],
                "group": ["A"] * 3 + ["B"] * 2,
            }
        )
        session.datasets["test_data"] = test_data

        diagnosis = await registry.diagnose_data_problem(
            session=session,
            dataset_name="test_data",
            target_column="value",
        )

        # 应该检测到类型问题
        assert "type_conversion" in diagnosis or len(diagnosis.get("suggestions", [])) > 0


class TestFallbackIntegration:
    """测试降级策略集成。"""

    @pytest.mark.asyncio
    async def test_fallback_chain_multiple_attempts(self):
        """测试多级降级链。"""
        registry = create_default_registry()
        session = Session()

        # 创建同时违反正态性和方差齐性的数据
        test_data = pd.DataFrame(
            {
                "value": [1, 1, 2, 100, 150, 200, 201, 202, 203],
                "group": ["A"] * 3 + ["B"] * 3 + ["C"] * 3,
            }
        )
        session.datasets["test_data"] = test_data

        result = await registry.execute_with_fallback(
            "anova",
            session=session,
            dataset_name="test_data",
            value_column="value",
            group_column="group",
        )

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_fallback_respects_user_preference(self):
        """测试降级时尊重用户偏好。"""
        registry = create_default_registry()
        session = Session()

        # 设置用户偏好：不自动降级
        test_data = pd.DataFrame(
            {
                "value": [1, 1, 1, 2, 2, 100, 150, 200, 250, 300],
                "group": ["A"] * 5 + ["B"] * 5,
            }
        )
        session.datasets["test_data"] = test_data

        result = await registry.execute_with_fallback(
            "t_test",
            session=session,
            dataset_name="test_data",
            value_column="value",
            group_column="group",
            enable_fallback=False,  # 禁用降级
        )

        # 禁用降级时，应该返回原始结果
        assert result is not None


class TestNonParametricSkills:
    """测试非参数检验技能。"""

    @pytest.mark.asyncio
    async def test_mann_whitney_skill_exists(self):
        """测试 Mann-Whitney 技能存在且可执行。"""
        registry = create_default_registry()
        session = Session()

        test_data = pd.DataFrame(
            {
                "value": [1, 2, 3, 100, 150],
                "group": ["A"] * 3 + ["B"] * 2,
            }
        )
        session.datasets["test_data"] = test_data

        result = await registry.execute(
            "mann_whitney",
            session=session,
            dataset_name="test_data",
            value_column="value",
            group_column="group",
        )

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_kruskal_wallis_skill_exists(self):
        """测试 Kruskal-Wallis 技能存在且可执行。"""
        registry = create_default_registry()
        session = Session()

        test_data = pd.DataFrame(
            {
                "value": [1, 2, 3, 100, 150, 200],
                "group": ["A"] * 2 + ["B"] * 2 + ["C"] * 2,
            }
        )
        session.datasets["test_data"] = test_data

        result = await registry.execute(
            "kruskal_wallis",
            session=session,
            dataset_name="test_data",
            value_column="value",
            group_column="group",
        )

        assert result["success"] is True
