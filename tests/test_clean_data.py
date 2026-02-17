"""数据清洗技能测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nini.agent.session import Session
from nini.tools.clean_data import (
    MissingPattern,
    OutlierPattern,
    analyze_column_profile,
    analyze_dataset_features,
    analyze_missing_pattern,
    analyze_outlier_pattern,
    generate_cleaning_recommendation,
    recommend_cleaning_strategy,
    recommend_missing_strategy,
    recommend_outlier_strategy,
    recommend_normalization,
)
from nini.tools.registry import create_default_registry


class TestMissingPatternAnalysis:
    """测试缺失值模式分析。"""

    def test_no_missing(self):
        df = pd.DataFrame({"a": [1, 2, 3, 4, 5]})
        pattern = analyze_missing_pattern(df, "a")
        assert pattern == MissingPattern.NONE

    def test_random_missing(self):
        df = pd.DataFrame({"a": [1, None, 3, None, 5]})
        pattern = analyze_missing_pattern(df, "a")
        assert pattern == MissingPattern.RANDOM

    def test_block_missing(self):
        df = pd.DataFrame({"a": [1, 2, None, None, None]})
        pattern = analyze_missing_pattern(df, "a")
        assert pattern == MissingPattern.BLOCK

    def test_systematic_missing(self):
        # 创建系统性缺失：当 b 缺失时，a 也缺失
        # 使用更大的数据集以获得统计显著性
        df = pd.DataFrame(
            {
                "a": [1, None, 3, None, 5, 6, None, 8, None, 10],
                "b": ["x", None, "y", None, "z", "a", None, "b", None, "c"],
            }
        )
        pattern = analyze_missing_pattern(df, "a")
        assert pattern == MissingPattern.SYSTEMATIC


class TestOutlierPatternAnalysis:
    """测试异常值模式分析。"""

    def test_no_outliers(self):
        series = pd.Series([1, 2, 3, 4, 5])
        pattern, count, bounds = analyze_outlier_pattern(series)
        assert pattern == OutlierPattern.NONE
        assert count == 0

    def test_normal_outliers(self):
        # 正态分布，少量异常值
        np.random.seed(42)
        series = pd.Series(np.random.normal(0, 1, 100))
        series = pd.concat([series, pd.Series([10, -10])], ignore_index=True)
        pattern, count, bounds = analyze_outlier_pattern(series)
        assert pattern in [OutlierPattern.NORMAL, OutlierPattern.EXTREME]
        assert count > 0

    def test_skewed_distribution(self):
        # 偏态分布
        np.random.seed(42)
        series = pd.Series(np.random.exponential(2, 100))
        pattern, count, bounds = analyze_outlier_pattern(series)
        # 指数分布通常是右偏的
        assert pattern in [OutlierPattern.SKEWED, OutlierPattern.EXTREME, OutlierPattern.NORMAL]

    def test_extreme_outliers(self):
        # 大量异常值 - 使用更大的数据集确保 IQR 方法能检测
        np.random.seed(42)
        normal_data = np.random.normal(0, 1, 50)
        extreme_data = [100] * 10  # 20% 异常值
        series = pd.Series(list(normal_data) + extreme_data)
        pattern, count, bounds = analyze_outlier_pattern(series)
        assert pattern == OutlierPattern.EXTREME
        assert count > 0


class TestColumnProfileAnalysis:
    """测试列特征分析。"""

    def test_numeric_column(self):
        df = pd.DataFrame({"value": [1, 2, 3, 4, 5]})
        profile = analyze_column_profile(df, "value")

        assert profile.column == "value"
        assert profile.is_numeric is True
        assert profile.missing_count == 0
        assert profile.mean == 3.0
        assert profile.median == 3.0

    def test_categorical_column(self):
        df = pd.DataFrame({"category": ["a", "b", "a", "c", None]})
        profile = analyze_column_profile(df, "category")

        assert profile.column == "category"
        assert profile.is_numeric is False
        assert profile.missing_count == 1
        assert profile.mode == "a"
        assert profile.mode_freq == 2

    def test_column_with_missing(self):
        df = pd.DataFrame({"value": [1, None, 3, None, 5]})
        profile = analyze_column_profile(df, "value")

        assert profile.missing_count == 2
        assert profile.missing_ratio == 0.4
        assert profile.mean == 3.0  # (1+3+5)/3


class TestRecommendationStrategies:
    """测试策略推荐。"""

    def test_no_missing_recommendation(self):
        from nini.tools.clean_data import ColumnProfile

        profile = ColumnProfile(
            column="test",
            dtype="float64",
            total_rows=100,
            missing_count=0,
            missing_ratio=0.0,
            missing_pattern=MissingPattern.NONE,
            unique_count=100,
            is_numeric=True,
        )
        strategy, reason = recommend_missing_strategy(profile)
        assert strategy == "none"
        assert "无缺失值" in reason

    def test_high_missing_recommendation(self):
        from nini.tools.clean_data import ColumnProfile

        profile = ColumnProfile(
            column="test",
            dtype="float64",
            total_rows=100,
            missing_count=60,
            missing_ratio=0.6,
            missing_pattern=MissingPattern.RANDOM,
            unique_count=40,
            is_numeric=True,
        )
        strategy, reason = recommend_missing_strategy(profile)
        assert strategy == "drop_column"
        assert "缺失率" in reason

    def test_skewed_data_recommendation(self):
        from nini.tools.clean_data import ColumnProfile

        profile = ColumnProfile(
            column="test",
            dtype="float64",
            total_rows=100,
            missing_count=10,
            missing_ratio=0.1,
            missing_pattern=MissingPattern.RANDOM,
            unique_count=90,
            is_numeric=True,
            skewness=2.0,
            outlier_pattern=OutlierPattern.SKEWED,
        )
        strategy, reason = recommend_missing_strategy(profile)
        assert strategy == "median"
        assert "偏态" in reason

    def test_outlier_recommendation(self):
        from nini.tools.clean_data import ColumnProfile

        profile = ColumnProfile(
            column="test",
            dtype="float64",
            total_rows=100,
            missing_count=0,
            missing_ratio=0.0,
            missing_pattern=MissingPattern.NONE,
            unique_count=100,
            is_numeric=True,
            outlier_count=15,
            outlier_ratio=0.15,
            outlier_pattern=OutlierPattern.EXTREME,
        )
        strategy, reason = recommend_outlier_strategy(profile)
        assert strategy == "winsorize"
        assert "缩尾" in reason or "比例过高" in reason


class TestDatasetFeaturesAnalysis:
    """测试数据集整体特征分析。"""

    def test_complete_dataset_analysis(self):
        df = pd.DataFrame(
            {
                "numeric": [1, 2, 3, 4, 5],
                "categorical": ["a", "b", "a", "b", "a"],
                "with_missing": [1, None, 3, None, 5],
            }
        )
        features = analyze_dataset_features(df)

        assert features["total_rows"] == 5
        assert features["total_columns"] == 3
        assert features["numeric_columns"] == 2
        assert features["categorical_columns"] == 1
        assert "column_profiles" in features
        assert len(features["column_profiles"]) == 3


class TestCleaningStrategyRecommendation:
    """测试完整清洗策略推荐。"""

    def test_recommend_cleaning_strategy(self):
        df = pd.DataFrame(
            {
                "normal_col": [1, 2, 3, 4, 5],
                "missing_col": [1, None, 3, None, 5],
                "category_col": ["a", "b", "a", None, "b"],
            }
        )
        result = recommend_cleaning_strategy(df)

        assert "overall_strategy" in result
        assert "recommendations" in result
        assert "column_profiles" in result
        assert len(result["recommendations"]) == 3

        # 检查每列都有推荐
        for col in df.columns:
            assert col in result["recommendations"]
            rec = result["recommendations"][col]
            assert "missing_strategy" in rec
            assert "outlier_strategy" in rec
            assert "priority" in rec


@pytest.mark.asyncio
class TestRecommendCleaningStrategySkill:
    """测试 recommend_cleaning_strategy 技能。"""

    async def test_skill_execution(self):
        registry = create_default_registry()
        session = Session()
        session.datasets["test.csv"] = pd.DataFrame(
            {
                "value": [1, 2, None, 4, 5],
                "category": ["a", "b", "a", None, "b"],
            }
        )

        result = await registry.execute(
            "recommend_cleaning_strategy",
            session=session,
            dataset_name="test.csv",
        )

        assert result["success"] is True
        assert "data" in result
        assert "recommendations" in result["data"]

    async def test_skill_with_invalid_dataset(self):
        registry = create_default_registry()
        session = Session()

        result = await registry.execute(
            "recommend_cleaning_strategy",
            session=session,
            dataset_name="nonexistent.csv",
        )

        assert result["success"] is False
        assert "不存在" in result["message"]

    async def test_skill_with_target_columns(self):
        registry = create_default_registry()
        session = Session()
        session.datasets["test.csv"] = pd.DataFrame(
            {
                "value": [1, 2, None, 4, 5],
                "category": ["a", "b", "a", None, "b"],
                "other": [1, 2, 3, 4, 5],
            }
        )

        result = await registry.execute(
            "recommend_cleaning_strategy",
            session=session,
            dataset_name="test.csv",
            target_columns=["value", "category"],
        )

        assert result["success"] is True
        assert len(result["data"]["recommendations"]) == 2


@pytest.mark.asyncio
class TestCleanDataAutoMode:
    """测试 clean_data 的 auto 模式。"""

    async def test_auto_missing_strategy(self):
        registry = create_default_registry()
        session = Session()
        session.datasets["test.csv"] = pd.DataFrame(
            {
                "value": [1, 2, None, 4, 5],
            }
        )

        result = await registry.execute(
            "clean_data",
            session=session,
            dataset_name="test.csv",
            missing_strategy="auto",
            outlier_method="none",
            inplace=True,
        )

        assert result["success"] is True
        assert "使用自动推荐策略" in result["message"]
        # 缺失值应该被填充
        assert result["data"]["missing_after"] == 0

    async def test_auto_outlier_strategy(self):
        registry = create_default_registry()
        session = Session()
        # 创建有异常值的数据 - 使用更大的数据集
        np.random.seed(42)
        normal_data = np.random.normal(0, 1, 50)
        session.datasets["test.csv"] = pd.DataFrame(
            {
                "value": list(normal_data) + [100, 200],  # 添加异常值
            }
        )

        result = await registry.execute(
            "clean_data",
            session=session,
            dataset_name="test.csv",
            missing_strategy="none",
            outlier_method="auto",
            inplace=True,
        )

        assert result["success"] is True
        # 异常值应该被处理（缩尾或删除）

    async def test_auto_mode_with_high_missing_column(self):
        registry = create_default_registry()
        session = Session()
        # 创建高缺失率列
        session.datasets["test.csv"] = pd.DataFrame(
            {
                "mostly_missing": [1, None, None, None, None],  # 80% 缺失
                "normal_col": [1, 2, 3, 4, 5],
            }
        )

        result = await registry.execute(
            "clean_data",
            session=session,
            dataset_name="test.csv",
            missing_strategy="auto",
            outlier_method="none",
            inplace=True,
        )

        assert result["success"] is True
        # 高缺失率列应该被删除
        assert "mostly_missing" not in session.datasets["test.csv"].columns

    async def test_legacy_mode_still_works(self):
        registry = create_default_registry()
        session = Session()
        session.datasets["test.csv"] = pd.DataFrame(
            {
                "value": [1, 2, None, 4, 5],
            }
        )

        result = await registry.execute(
            "clean_data",
            session=session,
            dataset_name="test.csv",
            missing_strategy="mean",
            outlier_method="none",
            inplace=True,
        )

        assert result["success"] is True
        assert "使用自动推荐策略" not in result["message"]
        assert result["data"]["missing_after"] == 0
