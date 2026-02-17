"""数据质量评分体系模块。

提供多维度数据质量评估功能，包括完整性、一致性、准确性等维度。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from nini.agent.session import Session
from nini.tools.base import Skill, SkillResult


class QualityDimension(Enum):
    """数据质量维度枚举。"""

    COMPLETENESS = "completeness"  # 完整性
    CONSISTENCY = "consistency"  # 一致性
    ACCURACY = "accuracy"  # 准确性
    TIMELINESS = "timeliness"  # 及时性
    VALIDITY = "validity"  # 有效性
    UNIQUENESS = "uniqueness"  # 唯一性


@dataclass
class DimensionScore:
    """单个维度的质量评分。"""

    dimension: QualityDimension
    score: float  # 0-100
    weight: float  # 权重
    details: dict[str, Any] = field(default_factory=dict)
    issues: list[dict[str, Any]] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


@dataclass
class QualityReport:
    """数据质量报告。"""

    dataset_name: str
    total_rows: int
    total_columns: int
    overall_score: float  # 综合评分 0-100
    dimension_scores: list[DimensionScore] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式。"""
        return {
            "dataset_name": self.dataset_name,
            "total_rows": self.total_rows,
            "total_columns": self.total_columns,
            "overall_score": round(self.overall_score, 2),
            "dimension_scores": [
                {
                    "dimension": ds.dimension.value,
                    "score": round(ds.score, 2),
                    "weight": ds.weight,
                    "details": ds.details,
                    "issues": ds.issues,
                    "suggestions": ds.suggestions,
                }
                for ds in self.dimension_scores
            ],
            "summary": self.summary,
        }


# ---- 质量评分算法 ----


def calculate_completeness_score(df: pd.DataFrame) -> DimensionScore:
    """计算完整性评分。

    评估数据集中缺失值的情况。
    """
    total_cells = df.size
    missing_cells = df.isna().sum().sum()
    completeness_ratio = (total_cells - missing_cells) / total_cells if total_cells > 0 else 1.0

    # 按列统计缺失情况
    column_missing = {}
    high_missing_columns = []
    for col in df.columns:
        col_missing = df[col].isna().sum()
        col_ratio = col_missing / len(df) if len(df) > 0 else 0
        column_missing[col] = {
            "missing_count": int(col_missing),
            "missing_ratio": round(col_ratio, 4),
        }
        if col_ratio > 0.3:
            high_missing_columns.append(col)

    score = completeness_ratio * 100

    issues = []
    suggestions = []

    if high_missing_columns:
        issues.append(
            {
                "type": "high_missing_columns",
                "columns": high_missing_columns,
                "message": f"以下列缺失率超过 30%: {', '.join(high_missing_columns)}",
            }
        )
        suggestions.append(
            f"考虑删除高缺失率列或采用合适的插补策略: {', '.join(high_missing_columns)}"
        )

    if completeness_ratio < 0.9:
        suggestions.append("数据集整体缺失率较高，建议检查数据收集流程")

    return DimensionScore(
        dimension=QualityDimension.COMPLETENESS,
        score=score,
        weight=0.25,
        details={
            "total_cells": total_cells,
            "missing_cells": int(missing_cells),
            "completeness_ratio": round(completeness_ratio, 4),
            "column_missing": column_missing,
        },
        issues=issues,
        suggestions=suggestions,
    )


def calculate_consistency_score(df: pd.DataFrame) -> DimensionScore:
    """计算一致性评分。

    评估数据格式、类型的一致性。
    """
    issues = []
    suggestions = []

    # 检查数值列的数据类型一致性
    type_consistency_issues = 0
    for col in df.columns:
        if df[col].dtype == object:
            # 检查是否混合了数值和字符串
            try:
                numeric_converted = pd.to_numeric(df[col], errors="coerce")
                non_null_original = df[col].notna().sum()
                non_null_converted = numeric_converted.notna().sum()
                if non_null_converted > 0 and non_null_converted < non_null_original:
                    type_consistency_issues += 1
            except Exception:
                pass

    # 检查分类列的值一致性（大小写、空格等）
    categorical_consistency_issues = 0
    for col in df.select_dtypes(include=["object", "string"]).columns:
        unique_vals = df[col].dropna().unique()
        # 检查大小写不一致
        lower_vals = [str(v).lower().strip() for v in unique_vals]
        if len(lower_vals) != len(set(lower_vals)):
            categorical_consistency_issues += 1

    # 计算评分
    total_checks = len(df.columns)
    failed_checks = type_consistency_issues + categorical_consistency_issues
    score = max(0, (1 - failed_checks / max(total_checks, 1)) * 100)

    if type_consistency_issues > 0:
        issues.append(
            {
                "type": "mixed_types",
                "count": type_consistency_issues,
                "message": f"发现 {type_consistency_issues} 列存在混合数据类型",
            }
        )
        suggestions.append("建议统一数据类型，将数值型数据从字符串转换为数值类型")

    if categorical_consistency_issues > 0:
        issues.append(
            {
                "type": "case_inconsistency",
                "count": categorical_consistency_issues,
                "message": f"发现 {categorical_consistency_issues} 列存在大小写或空格不一致",
            }
        )
        suggestions.append("建议统一分类值的大小写和去除多余空格")

    return DimensionScore(
        dimension=QualityDimension.CONSISTENCY,
        score=score,
        weight=0.20,
        details={
            "type_consistency_issues": type_consistency_issues,
            "categorical_consistency_issues": categorical_consistency_issues,
        },
        issues=issues,
        suggestions=suggestions,
    )


def calculate_accuracy_score(df: pd.DataFrame) -> DimensionScore:
    """计算准确性评分。

    评估异常值、离群点等情况。
    """
    issues = []
    suggestions = []
    total_outliers = 0
    outlier_columns = []

    # 检查数值列的异常值
    for col in df.select_dtypes(include=[np.number]).columns:
        series = df[col].dropna()
        if len(series) < 4:
            continue

        Q1 = series.quantile(0.25)
        Q3 = series.quantile(0.75)
        IQR = Q3 - Q1
        lower_bound = Q1 - 1.5 * IQR
        upper_bound = Q3 + 1.5 * IQR

        outliers = series[(series < lower_bound) | (series > upper_bound)]
        if len(outliers) > 0:
            total_outliers += len(outliers)
            outlier_ratio = len(outliers) / len(series)
            outlier_columns.append(
                {
                    "column": col,
                    "outlier_count": len(outliers),
                    "outlier_ratio": round(outlier_ratio, 4),
                }
            )

            if outlier_ratio > 0.05:
                issues.append(
                    {
                        "type": "high_outlier_ratio",
                        "column": col,
                        "ratio": round(outlier_ratio, 4),
                        "message": f"列 '{col}' 异常值比例过高 ({outlier_ratio:.1%})",
                    }
                )

    # 计算评分
    total_numeric_cells = sum(
        len(df[col].dropna()) for col in df.select_dtypes(include=[np.number]).columns
    )

    if total_numeric_cells > 0:
        outlier_ratio = total_outliers / total_numeric_cells
        score = max(0, (1 - outlier_ratio * 5) * 100)  # 异常值权重放大5倍
    else:
        score = 100.0

    if outlier_columns:
        suggestions.append(f"发现 {len(outlier_columns)} 列存在异常值，建议检查数据录入质量")
        high_outlier_cols = [str(c["column"]) for c in outlier_columns if float(c["outlier_ratio"]) > 0.05]  # type: ignore[arg-type]
        if high_outlier_cols:
            suggestions.append(
                f"列 {', '.join(high_outlier_cols)} 异常值比例较高，建议使用缩尾或截断处理"
            )

    return DimensionScore(
        dimension=QualityDimension.ACCURACY,
        score=score,
        weight=0.25,
        details={
            "total_outliers": total_outliers,
            "outlier_columns": outlier_columns,
        },
        issues=issues,
        suggestions=suggestions,
    )


def calculate_validity_score(df: pd.DataFrame) -> DimensionScore:
    """计算有效性评分。

    评估数据是否符合预期的范围和格式。
    """
    issues = []
    suggestions = []
    invalid_count = 0

    # 检查数值列的范围有效性
    range_issues = []
    for col in df.select_dtypes(include=[np.number]).columns:
        series = df[col].dropna()
        if len(series) == 0:
            continue

        # 检查极端值（可能是数据录入错误）
        min_val = series.min()
        max_val = series.max()

        # 检测可能的无效值（如负数年龄、超过合理范围的值等）
        if col.lower() in ["age", "年龄"] and (min_val < 0 or max_val > 150):
            invalid_count += len(series[(series < 0) | (series > 150)])
            range_issues.append(
                {
                    "column": col,
                    "issue": "invalid_age_range",
                    "min": float(min_val),
                    "max": float(max_val),
                }
            )

    # 检查日期有效性
    date_issues = []
    for col in df.select_dtypes(include=["datetime64"]).columns:
        series = df[col]
        future_dates = series > pd.Timestamp.now()
        if future_dates.any():
            date_issues.append(
                {
                    "column": col,
                    "issue": "future_dates",
                    "count": int(future_dates.sum()),
                }
            )
            invalid_count += int(future_dates.sum())

    # 计算评分
    total_cells = df.size
    if total_cells > 0:
        score = max(0, (1 - invalid_count / total_cells) * 100)
    else:
        score = 100.0

    if range_issues:
        issues.append(
            {
                "type": "range_violations",
                "details": range_issues,
                "message": f"发现 {len(range_issues)} 列存在范围违规",
            }
        )

    if date_issues:
        issues.append(
            {
                "type": "invalid_dates",
                "details": date_issues,
                "message": f"发现 {len(date_issues)} 列包含未来日期",
            }
        )

    if issues:
        suggestions.append("建议检查数据范围约束，设置合理的数据验证规则")

    return DimensionScore(
        dimension=QualityDimension.VALIDITY,
        score=score,
        weight=0.15,
        details={
            "invalid_count": invalid_count,
            "range_issues": range_issues,
            "date_issues": date_issues,
        },
        issues=issues,
        suggestions=suggestions,
    )


def calculate_uniqueness_score(df: pd.DataFrame) -> DimensionScore:
    """计算唯一性评分。

    评估重复数据的情况。
    """
    # 检查完全重复的行
    total_rows = len(df)
    duplicate_rows = df.duplicated().sum()
    duplicate_ratio = duplicate_rows / total_rows if total_rows > 0 else 0

    # 检查潜在的ID列重复
    id_column_issues = []
    for col in df.columns:
        if any(keyword in col.lower() for keyword in ["id", "编号", "code", "代码", "key"]):
            unique_count = df[col].nunique()
            total_count = len(df[col].dropna())
            if unique_count < total_count:
                id_column_issues.append(
                    {
                        "column": col,
                        "unique_count": unique_count,
                        "total_count": total_count,
                        "duplicate_count": total_count - unique_count,
                    }
                )

    # 计算评分
    score = max(0, (1 - duplicate_ratio) * 100)

    issues = []
    suggestions = []

    if duplicate_rows > 0:
        issues.append(
            {
                "type": "duplicate_rows",
                "count": int(duplicate_rows),
                "ratio": round(duplicate_ratio, 4),
                "message": f"发现 {duplicate_rows} 行完全重复的数据",
            }
        )
        suggestions.append("建议删除重复行或使用去重策略")

    if id_column_issues:
        issues.append(
            {
                "type": "id_column_duplicates",
                "columns": [i["column"] for i in id_column_issues],
                "message": f"ID 列存在重复值: {', '.join(str(i['column']) for i in id_column_issues)}",
            }
        )
        suggestions.append("ID 列应该具有唯一性，请检查数据完整性")

    return DimensionScore(
        dimension=QualityDimension.UNIQUENESS,
        score=score,
        weight=0.15,
        details={
            "total_rows": total_rows,
            "duplicate_rows": int(duplicate_rows),
            "duplicate_ratio": round(duplicate_ratio, 4),
            "id_column_issues": id_column_issues,
        },
        issues=issues,
        suggestions=suggestions,
    )


def calculate_overall_score(dimension_scores: list[DimensionScore]) -> float:
    """计算综合质量评分（加权平均）。"""
    if not dimension_scores:
        return 0.0

    total_weight = sum(ds.weight for ds in dimension_scores)
    if total_weight == 0:
        return 0.0

    weighted_sum = sum(ds.score * ds.weight for ds in dimension_scores)
    return weighted_sum / total_weight


def generate_quality_summary(report: QualityReport) -> dict[str, Any]:
    """生成质量报告摘要。"""
    all_issues = []
    all_suggestions = []

    for ds in report.dimension_scores:
        all_issues.extend(ds.issues)
        all_suggestions.extend(ds.suggestions)

    # 确定质量等级
    if report.overall_score >= 90:
        grade = "优秀"
        status = "数据质量良好，可以直接使用"
    elif report.overall_score >= 75:
        grade = "良好"
        status = "数据质量较好，建议处理发现的问题"
    elif report.overall_score >= 60:
        grade = "一般"
        status = "数据质量一般，需要进行清洗处理"
    else:
        grade = "较差"
        status = "数据质量较差，建议重新收集或进行深度清洗"

    return {
        "grade": grade,
        "status": status,
        "total_issues": len(all_issues),
        "total_suggestions": len(all_suggestions),
        "critical_issues": [i for i in all_issues if i.get("severity") == "high"],
        "top_suggestions": all_suggestions[:5] if all_suggestions else [],
    }


def evaluate_data_quality(df: pd.DataFrame, dataset_name: str) -> QualityReport:
    """评估数据质量并生成完整报告。

    Args:
        df: 要评估的数据集
        dataset_name: 数据集名称

    Returns:
        QualityReport 对象
    """
    # 计算各维度评分
    dimension_scores = [
        calculate_completeness_score(df),
        calculate_consistency_score(df),
        calculate_accuracy_score(df),
        calculate_validity_score(df),
        calculate_uniqueness_score(df),
    ]

    # 计算综合评分
    overall_score = calculate_overall_score(dimension_scores)

    # 创建报告
    report = QualityReport(
        dataset_name=dataset_name,
        total_rows=len(df),
        total_columns=len(df.columns),
        overall_score=overall_score,
        dimension_scores=dimension_scores,
    )

    # 生成摘要
    report.summary = generate_quality_summary(report)

    return report


# ---- 技能实现 ----


class DataQualitySkill(Skill):
    """数据质量评估技能。

    从完整性、一致性、准确性、有效性、唯一性等维度评估数据质量。
    """

    @property
    def name(self) -> str:
        return "evaluate_data_quality"

    @property
    def category(self) -> str:
        return "data"

    @property
    def description(self) -> str:
        return (
            "评估数据集的质量，从完整性、一致性、准确性、有效性、唯一性等维度进行评分，"
            "生成综合质量报告和改进建议。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "dataset_name": {
                    "type": "string",
                    "description": "要评估的数据集名称",
                },
            },
            "required": ["dataset_name"],
        }

    @property
    def is_idempotent(self) -> bool:
        return True

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        dataset_name = kwargs.get("dataset_name")

        if not dataset_name:
            return SkillResult(
                success=False,
                message="请提供数据集名称",
            )

        df = session.datasets.get(dataset_name)
        if df is None:
            return SkillResult(
                success=False,
                message=f"数据集 '{dataset_name}' 不存在",
            )

        try:
            # 执行质量评估
            report = evaluate_data_quality(df, dataset_name)

            # 构建消息
            summary = report.summary
            message = (
                f"数据集 '{dataset_name}' 质量评估完成。"
                f"综合评分: {report.overall_score:.1f}/100 ({summary['grade']})\n"
                f"发现 {summary['total_issues']} 个问题，"
                f"{summary['total_suggestions']} 条改进建议。"
            )

            return SkillResult(
                success=True,
                data=report.to_dict(),
                message=message,
            )

        except Exception as e:
            return SkillResult(
                success=False,
                message=f"质量评估失败: {e}",
            )


class DataQualityReportSkill(Skill):
    """生成详细数据质量报告技能。"""

    @property
    def name(self) -> str:
        return "generate_quality_report"

    @property
    def category(self) -> str:
        return "data"

    @property
    def description(self) -> str:
        return "生成详细的数据质量报告，包含所有维度的详细分析和改进建议。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "dataset_name": {
                    "type": "string",
                    "description": "要评估的数据集名称",
                },
                "include_recommendations": {
                    "type": "boolean",
                    "default": True,
                    "description": "是否包含清洗建议",
                },
            },
            "required": ["dataset_name"],
        }

    @property
    def is_idempotent(self) -> bool:
        return True

    @property
    def expose_to_llm(self) -> bool:
        # 此技能与 evaluate_data_quality 功能类似，不暴露给 LLM 以减少工具数量
        return False

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        dataset_name = kwargs.get("dataset_name")
        include_recommendations = kwargs.get("include_recommendations", True)

        if not dataset_name:
            return SkillResult(
                success=False,
                message="请提供数据集名称",
            )

        df = session.datasets.get(dataset_name)
        if df is None:
            return SkillResult(
                success=False,
                message=f"数据集 '{dataset_name}' 不存在",
            )

        try:
            report = evaluate_data_quality(df, dataset_name)

            # 构建详细报告
            report_data = report.to_dict()

            if include_recommendations:
                # 生成清洗建议
                cleaning_recommendations = _generate_cleaning_recommendations(report)
                report_data["cleaning_recommendations"] = cleaning_recommendations

            return SkillResult(
                success=True,
                data=report_data,
                message=f"已生成 '{dataset_name}' 的详细质量报告",
            )

        except Exception as e:
            return SkillResult(
                success=False,
                message=f"报告生成失败: {e}",
            )


def _generate_cleaning_recommendations(report: QualityReport) -> list[dict[str, Any]]:
    """基于质量报告生成清洗建议。"""
    recommendations = []

    for ds in report.dimension_scores:
        if ds.dimension == QualityDimension.COMPLETENESS and ds.score < 90:
            # 完整性建议
            high_missing_cols = [
                col
                for col, info in ds.details.get("column_missing", {}).items()
                if info.get("missing_ratio", 0) > 0.3
            ]
            if high_missing_cols:
                recommendations.append(
                    {
                        "priority": "high",
                        "type": "missing_values",
                        "target_columns": high_missing_cols,
                        "action": "考虑删除高缺失率列或使用高级插补方法",
                        "reason": "缺失率超过 30% 的列难以提供有效信息",
                    }
                )

        elif ds.dimension == QualityDimension.ACCURACY and ds.score < 85:
            # 准确性建议
            outlier_cols = [
                c["column"]
                for c in ds.details.get("outlier_columns", [])
                if c.get("outlier_ratio", 0) > 0.05
            ]
            if outlier_cols:
                recommendations.append(
                    {
                        "priority": "medium",
                        "type": "outliers",
                        "target_columns": outlier_cols,
                        "action": "使用缩尾法或截断法处理异常值",
                        "reason": "异常值比例较高，可能影响统计分析结果",
                    }
                )

        elif ds.dimension == QualityDimension.UNIQUENESS and ds.score < 95:
            # 唯一性建议
            if ds.details.get("duplicate_rows", 0) > 0:
                recommendations.append(
                    {
                        "priority": "medium",
                        "type": "duplicates",
                        "action": "删除重复行",
                        "reason": f"发现 {ds.details['duplicate_rows']} 行重复数据",
                    }
                )

        elif ds.dimension == QualityDimension.CONSISTENCY and ds.score < 90:
            # 一致性建议
            recommendations.append(
                {
                    "priority": "low",
                    "type": "consistency",
                    "action": "统一数据格式和分类值的大小写",
                    "reason": "发现数据格式不一致或大小写混用",
                }
            )

    return recommendations
