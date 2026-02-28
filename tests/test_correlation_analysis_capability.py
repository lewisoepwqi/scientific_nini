"""相关性分析 Capability 测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nini.agent.session import Session
from nini.capabilities.implementations import (
    CorrelationAnalysisCapability,
    CorrelationAnalysisResult,
)


@pytest.fixture
def corr_session():
    """创建包含相关性数据的会话。"""
    np.random.seed(42)
    n = 50

    x = np.random.normal(0, 1, n)
    y = 0.8 * x + np.random.normal(0, 0.5, n)  # 强正相关
    z = -0.5 * x + np.random.normal(0, 0.8, n)  # 中等负相关
    w = np.random.normal(0, 1, n)  # 无相关

    df = pd.DataFrame({"x": x, "y": y, "z": z, "w": w})
    session = Session()
    session.datasets["corr_data"] = df
    return session


@pytest.fixture
def capability():
    """创建相关性分析能力实例。"""
    from nini.tools.registry import create_default_tool_registry

    registry = create_default_tool_registry()
    return CorrelationAnalysisCapability(registry=registry)


class TestCorrelationAnalysisCapability:
    """测试相关性分析能力。"""

    @pytest.mark.asyncio
    async def test_basic_analysis(self, capability, corr_session):
        """测试基本相关性分析。"""
        result = await capability.execute(
            corr_session,
            dataset_name="corr_data",
            columns=["x", "y", "z"],
        )

        assert isinstance(result, CorrelationAnalysisResult)
        assert result.success
        assert result.method in ["pearson", "spearman", "kendall"]
        assert result.n_variables == 3
        assert result.sample_size == 50
        assert len(result.correlation_matrix) > 0
        assert len(result.all_pairs) == 3  # C(3,2) = 3

    @pytest.mark.asyncio
    async def test_auto_column_selection(self, capability, corr_session):
        """测试自动选择数值列。"""
        result = await capability.execute(
            corr_session,
            dataset_name="corr_data",
        )
        assert result.success
        assert result.n_variables == 4  # x, y, z, w

    @pytest.mark.asyncio
    async def test_significant_pairs_detected(self, capability, corr_session):
        """测试显著相关对被检出。"""
        result = await capability.execute(
            corr_session,
            dataset_name="corr_data",
            columns=["x", "y", "z", "w"],
            correction="bonferroni",
        )
        assert result.success

        # x-y (强正相关) 应该被检出
        sig_names = [(p.var1, p.var2) for p in result.significant_pairs]
        assert ("x", "y") in sig_names or ("y", "x") in sig_names

    @pytest.mark.asyncio
    async def test_method_selection_auto(self, capability, corr_session):
        """测试自动方法选择。"""
        result = await capability.execute(
            corr_session,
            dataset_name="corr_data",
            columns=["x", "y"],
            method="auto",
        )
        assert result.success
        assert result.method in ["pearson", "spearman"]
        assert result.method_reason
        assert len(result.normality_tests) > 0

    @pytest.mark.asyncio
    async def test_explicit_method(self, capability, corr_session):
        """测试指定方法。"""
        result = await capability.execute(
            corr_session,
            dataset_name="corr_data",
            columns=["x", "y"],
            method="spearman",
        )
        assert result.success
        assert result.method == "spearman"

    @pytest.mark.asyncio
    async def test_data_validation_nonexistent_dataset(self, capability, corr_session):
        """测试不存在的数据集。"""
        result = await capability.execute(
            corr_session,
            dataset_name="nonexistent",
            columns=["x", "y"],
        )
        assert not result.success
        assert "不存在" in result.message

    @pytest.mark.asyncio
    async def test_data_validation_nonexistent_column(self, capability, corr_session):
        """测试不存在的列。"""
        result = await capability.execute(
            corr_session,
            dataset_name="corr_data",
            columns=["x", "nonexistent"],
        )
        assert not result.success
        assert "不存在" in result.message

    @pytest.mark.asyncio
    async def test_insufficient_columns(self, capability, corr_session):
        """测试不足 2 列。"""
        result = await capability.execute(
            corr_session,
            dataset_name="corr_data",
            columns=["x"],
        )
        assert not result.success
        assert "至少" in result.message

    @pytest.mark.asyncio
    async def test_bonferroni_correction(self, capability, corr_session):
        """测试 Bonferroni 校正。"""
        result = await capability.execute(
            corr_session,
            dataset_name="corr_data",
            columns=["x", "y", "z", "w"],
            correction="bonferroni",
        )
        assert result.success
        assert result.correction_method == "bonferroni"
        # 校正后的 p 值应该 >= 原始 p 值
        for pair in result.all_pairs:
            if pair.p_adjusted is not None:
                assert pair.p_adjusted >= pair.p_value - 1e-10

    @pytest.mark.asyncio
    async def test_no_correction(self, capability, corr_session):
        """测试无校正。"""
        result = await capability.execute(
            corr_session,
            dataset_name="corr_data",
            columns=["x", "y"],
            correction="none",
        )
        assert result.success
        for pair in result.all_pairs:
            assert pair.p_adjusted == pair.p_value

    def test_strength_classification(self):
        """测试相关强度分类。"""
        assert CorrelationAnalysisCapability._classify_strength(0.9) == "strong"
        assert CorrelationAnalysisCapability._classify_strength(0.5) == "moderate"
        assert CorrelationAnalysisCapability._classify_strength(0.3) == "weak"
        assert CorrelationAnalysisCapability._classify_strength(0.1) == "negligible"
        assert CorrelationAnalysisCapability._classify_strength(-0.8) == "strong"

    def test_result_to_dict(self):
        """测试结果序列化。"""
        result = CorrelationAnalysisResult(
            success=True,
            message="测试完成",
            method="pearson",
            n_variables=3,
            sample_size=50,
        )
        data = result.to_dict()
        assert data["success"] is True
        assert data["method"] == "pearson"
        assert data["n_variables"] == 3

    def test_interpretation_generation(self, capability):
        """测试解释生成。"""
        from nini.capabilities.implementations.correlation_analysis import CorrelationPair

        result = CorrelationAnalysisResult(
            success=True,
            method="pearson",
            method_reason="所有变量通过正态性检验",
            n_variables=3,
            sample_size=50,
            correction_method="bonferroni",
            all_pairs=[
                CorrelationPair("x", "y", 0.85, 0.001, 0.003, True, "strong"),
                CorrelationPair("x", "z", -0.45, 0.02, 0.06, False, "moderate"),
                CorrelationPair("y", "z", 0.1, 0.5, 1.0, False, "negligible"),
            ],
            significant_pairs=[
                CorrelationPair("x", "y", 0.85, 0.001, 0.003, True, "strong"),
            ],
        )

        interpretation = capability._generate_interpretation(result)
        assert "分析方法" in interpretation
        assert "显著相关" in interpretation
        assert "结论" in interpretation
        assert "x" in interpretation and "y" in interpretation
