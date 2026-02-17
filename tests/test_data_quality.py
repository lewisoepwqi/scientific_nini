"""数据质量评分体系测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nini.agent.session import Session
from nini.tools.data_quality import (
    DataQualityReportSkill,
    DataQualitySkill,
    DimensionScore,
    QualityDimension,
    QualityReport,
    calculate_accuracy_score,
    calculate_completeness_score,
    calculate_consistency_score,
    calculate_overall_score,
    calculate_uniqueness_score,
    calculate_validity_score,
    evaluate_data_quality,
    generate_quality_summary,
)
from nini.tools.registry import create_default_registry


class TestCompletenessScore:
    """测试完整性评分。"""

    def test_perfect_completeness(self):
        df = pd.DataFrame({"a": [1, 2, 3, 4, 5], "b": ["x", "y", "z", "w", "v"]})
        score = calculate_completeness_score(df)

        assert score.dimension == QualityDimension.COMPLETENESS
        assert score.score == 100.0
        assert score.weight == 0.25
        assert len(score.issues) == 0

    def test_partial_missing(self):
        df = pd.DataFrame({"a": [1, None, 3, None, 5], "b": ["x", "y", None, "w", None]})
        score = calculate_completeness_score(df)

        assert score.score == 60.0  # 6/10 cells filled
        # 每列都是 2/5=40% 缺失，超过30%阈值
        assert len(score.issues) == 1
        assert score.issues[0]["type"] == "high_missing_columns"

    def test_high_missing_columns(self):
        df = pd.DataFrame(
            {
                "normal": [1, 2, 3, 4, 5],
                "mostly_missing": [1, None, None, None, None],  # 80% missing
            }
        )
        score = calculate_completeness_score(df)

        assert score.score == 60.0  # 6/10 cells filled (5+1)
        assert len(score.issues) == 1
        assert score.issues[0]["type"] == "high_missing_columns"
        assert "mostly_missing" in score.issues[0]["columns"]


class TestConsistencyScore:
    """测试一致性评分。"""

    def test_perfect_consistency(self):
        df = pd.DataFrame(
            {
                "numeric": [1, 2, 3, 4, 5],
                "category": ["a", "b", "a", "b", "a"],
            }
        )
        score = calculate_consistency_score(df)

        assert score.dimension == QualityDimension.CONSISTENCY
        assert score.score == 100.0

    def test_case_inconsistency(self):
        df = pd.DataFrame(
            {
                "category": ["Apple", "apple", "APPLE", "banana", "Banana"],
            }
        )
        score = calculate_consistency_score(df)

        assert score.score < 100.0
        assert any(i["type"] == "case_inconsistency" for i in score.issues)


class TestAccuracyScore:
    """测试准确性评分。"""

    def test_no_outliers(self):
        df = pd.DataFrame({"value": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]})
        score = calculate_accuracy_score(df)

        assert score.dimension == QualityDimension.ACCURACY
        assert score.score == 100.0

    def test_with_outliers(self):
        np.random.seed(42)
        normal_data = np.random.normal(0, 1, 100)
        df = pd.DataFrame({"value": list(normal_data) + [100, -100]})  # 添加异常值
        score = calculate_accuracy_score(df)

        assert score.score < 100.0
        assert len(score.details["outlier_columns"]) == 1

    def test_high_outlier_ratio(self):
        np.random.seed(42)
        normal_data = np.random.normal(0, 1, 50)
        extreme_data = [100] * 10  # 20% 异常值
        df = pd.DataFrame({"value": list(normal_data) + extreme_data})
        score = calculate_accuracy_score(df)

        assert score.score < 80.0
        assert any(i["type"] == "high_outlier_ratio" for i in score.issues)


class TestValidityScore:
    """测试有效性评分。"""

    def test_valid_data(self):
        df = pd.DataFrame(
            {
                "age": [20, 30, 40, 50, 60],
                "score": [80, 90, 70, 85, 95],
            }
        )
        score = calculate_validity_score(df)

        assert score.dimension == QualityDimension.VALIDITY
        assert score.score == 100.0

    def test_invalid_age_range(self):
        df = pd.DataFrame(
            {
                "age": [20, 30, -5, 200, 40],  # 包含负数年龄和超范围年龄
            }
        )
        score = calculate_validity_score(df)

        assert score.score < 100.0
        assert any(i["type"] == "range_violations" for i in score.issues)


class TestUniquenessScore:
    """测试唯一性评分。"""

    def test_no_duplicates(self):
        df = pd.DataFrame(
            {
                "id": [1, 2, 3, 4, 5],
                "value": ["a", "b", "c", "d", "e"],
            }
        )
        score = calculate_uniqueness_score(df)

        assert score.dimension == QualityDimension.UNIQUENESS
        assert score.score == 100.0

    def test_duplicate_rows(self):
        df = pd.DataFrame(
            {
                "a": [1, 2, 3, 1, 2],  # 第1、4行和第2、5行重复
                "b": ["x", "y", "z", "x", "y"],
            }
        )
        score = calculate_uniqueness_score(df)

        assert score.score == 60.0  # 3/5 unique rows
        assert any(i["type"] == "duplicate_rows" for i in score.issues)

    def test_id_column_duplicates(self):
        df = pd.DataFrame(
            {
                "user_id": [1, 2, 3, 1, 2],  # ID 列有重复
                "name": ["a", "b", "c", "d", "e"],
            }
        )
        score = calculate_uniqueness_score(df)

        assert any(i["type"] == "id_column_duplicates" for i in score.issues)


class TestOverallScoreCalculation:
    """测试综合评分计算。"""

    def test_weighted_average(self):
        dimensions = [
            DimensionScore(QualityDimension.COMPLETENESS, 80, 0.25),
            DimensionScore(QualityDimension.CONSISTENCY, 90, 0.20),
            DimensionScore(QualityDimension.ACCURACY, 70, 0.25),
            DimensionScore(QualityDimension.VALIDITY, 100, 0.15),
            DimensionScore(QualityDimension.UNIQUENESS, 85, 0.15),
        ]

        overall = calculate_overall_score(dimensions)
        expected = 80 * 0.25 + 90 * 0.20 + 70 * 0.25 + 100 * 0.15 + 85 * 0.15

        assert overall == pytest.approx(expected, rel=1e-5)

    def test_empty_dimensions(self):
        overall = calculate_overall_score([])
        assert overall == 0.0


class TestQualitySummary:
    """测试质量摘要生成。"""

    def test_excellent_grade(self):
        report = QualityReport(
            dataset_name="test",
            total_rows=100,
            total_columns=5,
            overall_score=95,
            dimension_scores=[],
        )
        summary = generate_quality_summary(report)

        assert summary["grade"] == "优秀"
        assert "良好" in summary["status"]

    def test_poor_grade(self):
        report = QualityReport(
            dataset_name="test",
            total_rows=100,
            total_columns=5,
            overall_score=50,
            dimension_scores=[],
        )
        summary = generate_quality_summary(report)

        assert summary["grade"] == "较差"
        assert "较差" in summary["status"]


class TestEvaluateDataQuality:
    """测试完整质量评估流程。"""

    def test_complete_evaluation(self):
        df = pd.DataFrame(
            {
                "numeric": [1, 2, 3, 4, 5],
                "category": ["a", "b", "a", "b", "a"],
            }
        )
        report = evaluate_data_quality(df, "test_dataset")

        assert report.dataset_name == "test_dataset"
        assert report.total_rows == 5
        assert report.total_columns == 2
        assert len(report.dimension_scores) == 5
        assert report.overall_score >= 0
        assert report.overall_score <= 100
        assert "grade" in report.summary

    def test_report_to_dict(self):
        df = pd.DataFrame({"a": [1, 2, 3]})
        report = evaluate_data_quality(df, "test")
        data = report.to_dict()

        assert data["dataset_name"] == "test"
        assert "overall_score" in data
        assert "dimension_scores" in data
        assert len(data["dimension_scores"]) == 5


@pytest.mark.asyncio
class TestDataQualitySkill:
    """测试数据质量评估技能。"""

    async def test_skill_execution(self):
        registry = create_default_registry()
        session = Session()
        session.datasets["test.csv"] = pd.DataFrame(
            {
                "value": [1, 2, 3, 4, 5],
                "category": ["a", "b", "a", "b", "a"],
            }
        )

        result = await registry.execute(
            "evaluate_data_quality",
            session=session,
            dataset_name="test.csv",
        )

        assert result["success"] is True
        assert "data" in result
        assert "overall_score" in result["data"]
        assert "dimension_scores" in result["data"]
        assert "summary" in result["data"]

    async def test_skill_with_invalid_dataset(self):
        registry = create_default_registry()
        session = Session()

        result = await registry.execute(
            "evaluate_data_quality",
            session=session,
            dataset_name="nonexistent.csv",
        )

        assert result["success"] is False
        assert "不存在" in result["message"]

    async def test_skill_with_missing_dataset_name(self):
        registry = create_default_registry()
        session = Session()

        result = await registry.execute(
            "evaluate_data_quality",
            session=session,
        )

        assert result["success"] is False
        assert "数据集名称" in result["message"] or "请提供" in result["message"]


@pytest.mark.asyncio
class TestDataQualityReportSkill:
    """测试详细质量报告技能。"""

    async def test_detailed_report(self):
        registry = create_default_registry()
        session = Session()
        session.datasets["test.csv"] = pd.DataFrame(
            {
                "value": [1, 2, None, 4, 100],  # 有缺失值和异常值
                "category": ["a", "b", "a", None, "b"],
            }
        )

        result = await registry.execute(
            "generate_quality_report",
            session=session,
            dataset_name="test.csv",
            include_recommendations=True,
        )

        assert result["success"] is True
        assert "cleaning_recommendations" in result["data"]

    async def test_report_without_recommendations(self):
        registry = create_default_registry()
        session = Session()
        session.datasets["test.csv"] = pd.DataFrame({"a": [1, 2, 3]})

        result = await registry.execute(
            "generate_quality_report",
            session=session,
            dataset_name="test.csv",
            include_recommendations=False,
        )

        assert result["success"] is True
        assert "cleaning_recommendations" not in result["data"]


@pytest.mark.asyncio
class TestDiagnoseWithQualityScore:
    """测试诊断功能集成质量评分。"""

    async def test_diagnose_includes_quality_score(self):
        registry = create_default_registry()
        session = Session()
        session.datasets["test.csv"] = pd.DataFrame(
            {
                "value": [1, 2, 3, 4, 5],
                "category": ["a", "b", "a", "b", "a"],
            }
        )

        diagnosis = await registry.diagnose_data_problem(
            session=session,
            dataset_name="test.csv",
            include_quality_score=True,
        )

        assert "quality_score" in diagnosis
        assert "overall_score" in diagnosis["quality_score"]
        assert "grade" in diagnosis["quality_score"]
        assert "dimension_scores" in diagnosis["quality_score"]

    async def test_diagnose_without_quality_score(self):
        registry = create_default_registry()
        session = Session()
        session.datasets["test.csv"] = pd.DataFrame({"a": [1, 2, 3]})

        diagnosis = await registry.diagnose_data_problem(
            session=session,
            dataset_name="test.csv",
            include_quality_score=False,
        )

        assert "quality_score" not in diagnosis
