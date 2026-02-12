"""数据诊断模块。

提供数据问题诊断和修复建议功能。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from nini.agent.session import Session

logger = logging.getLogger(__name__)


@dataclass
class DataIssue:
    """数据问题定义。"""

    type: str
    severity: str  # high, medium, low
    message: str
    column: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class DiagnosisResult:
    """诊断结果。"""

    dataset_name: str
    issues: list[DataIssue] = field(default_factory=list)
    suggestions: list[DataIssue] = field(default_factory=list)
    quality_score: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式。"""
        return {
            "dataset_name": self.dataset_name,
            "issues": [
                {
                    "type": i.type,
                    "severity": i.severity,
                    "message": i.message,
                    "column": i.column,
                    "details": i.details,
                }
                for i in self.issues
            ],
            "suggestions": [
                {
                    "type": s.type,
                    "severity": s.severity,
                    "message": s.message,
                    "column": s.column,
                    "details": s.details,
                }
                for s in self.suggestions
            ],
            "quality_score": self.quality_score,
            "metadata": self.metadata,
        }


class DataDiagnostics:
    """数据诊断器。

    提供数据质量问题的检测和诊断建议。
    """

    def __init__(self, include_quality_score: bool = True):
        self.include_quality_score = include_quality_score

    async def diagnose(
        self,
        session: "Session",
        dataset_name: str,
        target_column: str | None = None,
    ) -> DiagnosisResult:
        """诊断数据问题。

        Args:
            session: 会话对象
            dataset_name: 数据集名称
            target_column: 目标列名（可选）

        Returns:
            DiagnosisResult 对象
        """
        result = DiagnosisResult(dataset_name=dataset_name)

        df = session.datasets.get(dataset_name)
        if df is None:
            result.issues.append(
                DataIssue(
                    type="dataset_not_found",
                    severity="high",
                    message="数据集不存在",
                )
            )
            return result

        # 集成质量评分
        if self.include_quality_score:
            try:
                from nini.skills.data_quality import evaluate_data_quality

                quality_report = evaluate_data_quality(df, dataset_name)
                result.quality_score = {
                    "overall_score": round(quality_report.overall_score, 2),
                    "grade": quality_report.summary.get("grade", "未知"),
                    "dimension_scores": {
                        ds.dimension.value: round(ds.score, 2)
                        for ds in quality_report.dimension_scores
                    },
                }
                # 将质量问题的建议添加到诊断建议中
                for ds in quality_report.dimension_scores:
                    for suggestion in ds.suggestions:
                        result.suggestions.append(
                            DataIssue(
                                type=f"quality_{ds.dimension.value}",
                                severity="medium" if ds.score >= 70 else "high",
                                message=suggestion,
                            )
                        )
            except Exception as e:
                logger.warning("质量评分计算失败: %s", e)

        # 分析列
        columns_to_analyze = [target_column] if target_column else df.columns.tolist()

        for col in columns_to_analyze:
            if col not in df.columns:
                continue

            col_data = df[col]

            # 检查缺失值
            self._check_missing_values(result, col, col_data)

            # 检查数据类型（仅对数值列）
            if pd.api.types.is_numeric_dtype(col_data):
                self._check_outliers(result, col, col_data)
                self._check_sample_size(result, col, col_data)
            else:
                self._check_type_conversion(result, col, col_data)

        return result

    def _check_missing_values(
        self,
        result: DiagnosisResult,
        col: str,
        col_data: pd.Series,
    ) -> None:
        """检查缺失值问题。"""
        missing_count = col_data.isna().sum()
        if missing_count > 0:
            missing_ratio = missing_count / len(col_data)
            result.metadata.setdefault("missing_values", {})
            result.metadata["missing_values"][col] = {
                "count": int(missing_count),
                "ratio": float(missing_ratio),
            }

            if missing_ratio > 0.5:
                result.suggestions.append(
                    DataIssue(
                        type="missing_values",
                        severity="high",
                        message=f"列 '{col}' 缺失值超过 50%，建议删除该列或使用插补方法",
                        column=col,
                        details={
                            "missing_ratio": float(missing_ratio),
                            "count": int(missing_count),
                        },
                    )
                )
            elif missing_ratio > 0.1:
                result.suggestions.append(
                    DataIssue(
                        type="missing_values",
                        severity="medium",
                        message=f"列 '{col}' 有 {missing_count} 个缺失值，考虑使用均值/中位数填充",
                        column=col,
                        details={
                            "missing_ratio": float(missing_ratio),
                            "count": int(missing_count),
                        },
                    )
                )

    def _check_outliers(
        self,
        result: DiagnosisResult,
        col: str,
        col_data: pd.Series,
    ) -> None:
        """检查异常值问题（使用 IQR 方法）。"""
        clean_data = col_data.dropna()
        if len(clean_data) < 4:
            return

        Q1 = clean_data.quantile(0.25)
        Q3 = clean_data.quantile(0.75)
        IQR = Q3 - Q1
        lower_bound = Q1 - 1.5 * IQR
        upper_bound = Q3 + 1.5 * IQR

        outliers = clean_data[(clean_data < lower_bound) | (clean_data > upper_bound)]
        if len(outliers) > 0:
            result.metadata.setdefault("outliers", {})
            result.metadata["outliers"][col] = {
                "count": len(outliers),
                "values": outliers.tolist()[:10],  # 最多返回 10 个
            }

            if len(outliers) > len(clean_data) * 0.05:
                result.suggestions.append(
                    DataIssue(
                        type="outliers",
                        severity="medium",
                        message=f"列 '{col}' 有 {len(outliers)} 个异常值，建议检查数据质量",
                        column=col,
                        details={"count": len(outliers), "ratio": len(outliers) / len(clean_data)},
                    )
                )

    def _check_sample_size(
        self,
        result: DiagnosisResult,
        col: str,
        col_data: pd.Series,
    ) -> None:
        """检查样本量问题。"""
        clean_data = col_data.dropna()
        if len(clean_data) < 30:
            result.metadata.setdefault("sample_size", {})
            result.metadata["sample_size"][col] = {
                "count": len(clean_data),
                "warning": True,
            }
            if len(clean_data) < 10:
                result.suggestions.append(
                    DataIssue(
                        type="sample_size",
                        severity="high",
                        message=f"列 '{col}' 样本量过小（n={len(clean_data)}），统计结果可能不可靠",
                        column=col,
                        details={"count": len(clean_data)},
                    )
                )

    def _check_type_conversion(
        self,
        result: DiagnosisResult,
        col: str,
        col_data: pd.Series,
    ) -> None:
        """检查是否可以转换为数值类型。"""
        try:
            pd.to_numeric(col_data, errors="coerce")
            result.metadata.setdefault("type_conversion", {})
            result.metadata["type_conversion"][col] = {
                "current_type": str(col_data.dtype),
                "suggested_type": "numeric",
                "can_convert": True,
            }
            result.suggestions.append(
                DataIssue(
                    type="type_conversion",
                    severity="low",
                    message=f"列 '{col}' 可以转换为数值类型以进行数值分析",
                    column=col,
                    details={"current_type": str(col_data.dtype)},
                )
            )
        except Exception:
            pass


# 便捷函数


async def diagnose_data(
    session: "Session",
    dataset_name: str,
    target_column: str | None = None,
    include_quality_score: bool = True,
) -> dict[str, Any]:
    """诊断数据问题的便捷函数。

    Args:
        session: 会话对象
        dataset_name: 数据集名称
        target_column: 目标列名（可选）
        include_quality_score: 是否包含质量评分

    Returns:
        诊断结果字典
    """
    diagnostics = DataDiagnostics(include_quality_score=include_quality_score)
    result = await diagnostics.diagnose(session, dataset_name, target_column)
    return result.to_dict()
