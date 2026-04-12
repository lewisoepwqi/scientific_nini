"""回归分析 Capability 测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nini.agent.session import Session
from nini.capabilities.executors import (
    RegressionAnalysisCapability,
    RegressionAnalysisResult,
)


@pytest.fixture
def regr_session():
    """创建包含回归数据的会话。"""
    np.random.seed(42)
    n = 100

    # 创建具有线性关系的数据
    x1 = np.random.normal(0, 1, n)
    x2 = np.random.normal(0, 1, n)
    # y = 2 + 3*x1 + 1.5*x2 + 噪声
    y = 2 + 3 * x1 + 1.5 * x2 + np.random.normal(0, 0.5, n)

    df = pd.DataFrame({"x1": x1, "x2": x2, "y": y})
    session = Session()
    session.datasets["regr_data"] = df
    return session


@pytest.fixture
def multicollinear_session():
    """创建具有多重共线性的数据集。"""
    np.random.seed(42)
    n = 100

    x1 = np.random.normal(0, 1, n)
    x2 = 0.9 * x1 + np.random.normal(0, 0.1, n)  # 与 x1 高度相关
    y = 2 + 3 * x1 + np.random.normal(0, 0.5, n)

    df = pd.DataFrame({"x1": x1, "x2": x2, "y": y})
    session = Session()
    session.datasets["multicol_data"] = df
    return session


@pytest.fixture
def capability():
    """创建回归分析能力实例。"""
    from nini.tools.registry import create_default_tool_registry

    registry = create_default_tool_registry()
    return RegressionAnalysisCapability(registry=registry)


class TestRegressionAnalysisCapability:
    """测试回归分析能力。"""

    @pytest.mark.asyncio
    async def test_basic_linear_regression(self, capability, regr_session):
        """测试基本线性回归分析。"""
        result = await capability.execute(
            regr_session,
            dataset_name="regr_data",
            dependent_var="y",
            independent_vars=["x1", "x2"],
        )

        assert isinstance(result, RegressionAnalysisResult)
        assert result.success
        assert result.dependent_var == "y"
        assert result.independent_vars == ["x1", "x2"]
        assert result.sample_size == 100
        assert result.n_predictors == 2

        # 模型拟合度检查
        assert result.r_squared is not None
        assert result.r_squared > 0.8  # 应该有很好的拟合
        assert result.adj_r_squared is not None
        assert result.f_statistic is not None
        assert result.f_pvalue is not None
        assert result.f_pvalue < 0.05  # 模型应该显著

    @pytest.mark.asyncio
    async def test_coefficients_estimation(self, capability, regr_session):
        """测试系数估计。"""
        result = await capability.execute(
            regr_session,
            dataset_name="regr_data",
            dependent_var="y",
            independent_vars=["x1", "x2"],
        )

        assert result.success
        assert len(result.coefficients) == 2

        # 检查系数名称
        var_names = [c.variable for c in result.coefficients]
        assert "x1" in var_names
        assert "x2" in var_names

        # 检查截距
        assert result.intercept is not None
        assert result.intercept.coefficient is not None

        # x1 的系数应该接近 3
        x1_coef = next(c for c in result.coefficients if c.variable == "x1")
        assert 2.0 < x1_coef.coefficient < 4.0
        assert x1_coef.p_value is not None
        assert x1_coef.p_value < 0.05  # 应该显著

    @pytest.mark.asyncio
    async def test_multicollinearity_detection(self, capability, multicollinear_session):
        """测试多重共线性检测。"""
        result = await capability.execute(
            multicollinear_session,
            dataset_name="multicol_data",
            dependent_var="y",
            independent_vars=["x1", "x2"],
            check_multicollinearity=True,
            vif_threshold=5.0,  # 较低的阈值以触发检测
        )

        assert result.success
        # 应该检测到共线性
        assert result.multicollinearity_detected
        assert len(result.high_vif_vars) > 0

    @pytest.mark.asyncio
    async def test_residual_diagnostics(self, capability, regr_session):
        """测试残差诊断（如果底层工具返回残差数据）。"""
        result = await capability.execute(
            regr_session,
            dataset_name="regr_data",
            dependent_var="y",
            independent_vars=["x1", "x2"],
        )

        assert result.success
        # 注意：残差诊断需要底层工具返回残差数据
        # 如果工具未返回，diagnostics 可能为 None
        if result.diagnostics is not None:
            # 残差正态性检验
            assert result.diagnostics.residual_normality_p is not None
            assert result.diagnostics.residual_normality_passed is not None

            # 异方差性检验
            assert result.diagnostics.heteroscedasticity_p is not None
            assert result.diagnostics.heteroscedasticity_passed is not None

    @pytest.mark.asyncio
    async def test_dataset_not_found(self, capability, regr_session):
        """测试数据集不存在的情况。"""
        result = await capability.execute(
            regr_session,
            dataset_name="nonexistent",
            dependent_var="y",
            independent_vars=["x1", "x2"],
        )

        assert not result.success
        assert "不存在" in result.message

    @pytest.mark.asyncio
    async def test_insufficient_sample_size(self, capability):
        """测试样本量不足的情况。"""
        # 创建小数据集
        df = pd.DataFrame(
            {
                "x1": [1, 2, 3],
                "y": [1, 2, 3],
            }
        )
        session = Session()
        session.datasets["small_data"] = df

        result = await capability.execute(
            session,
            dataset_name="small_data",
            dependent_var="y",
            independent_vars=["x1"],
        )

        assert not result.success
        assert "样本量不足" in result.message

    @pytest.mark.asyncio
    async def test_interpretation_generation(self, capability, regr_session):
        """测试解释性报告生成。"""
        result = await capability.execute(
            regr_session,
            dataset_name="regr_data",
            dependent_var="y",
            independent_vars=["x1", "x2"],
        )

        assert result.success
        assert result.interpretation
        assert len(result.interpretation) > 0
        assert result.model_summary
        assert len(result.model_summary) > 0

    @pytest.mark.asyncio
    async def test_single_predictor(self, capability, regr_session):
        """测试单预测变量回归。"""
        result = await capability.execute(
            regr_session,
            dataset_name="regr_data",
            dependent_var="y",
            independent_vars=["x1"],
        )

        assert result.success
        assert len(result.coefficients) == 1
        assert result.coefficients[0].variable == "x1"
        assert result.r_squared is not None
        assert result.r_squared > 0.5
