"""数据清洗能力实现。

执行智能数据清洗流程：
1. 评估数据质量问题
2. 生成清洗策略建议
3. 执行清洗操作（缺失值、异常值、格式标准化）
4. 验证清洗效果
5. 生成清洗报告
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pandas as pd
import numpy as np

if TYPE_CHECKING:
    from nini.agent.session import Session
    from nini.tools.base import SkillResult


@dataclass
class CleaningOperation:
    """单次清洗操作记录。"""

    operation_type: str  # missing_value, outlier, duplicate, format
    column: str
    method: str
    rows_affected: int
    details: str = ""


@dataclass
class DataCleaningResult:
    """数据清洗结果。"""

    success: bool = False
    message: str = ""

    # 清洗前后统计
    original_rows: int = 0
    final_rows: int = 0
    rows_removed: int = 0
    rows_modified: int = 0

    # 操作记录
    operations: list[CleaningOperation] = field(default_factory=list)

    # 质量改善
    quality_before: dict[str, Any] = field(default_factory=dict)
    quality_after: dict[str, Any] = field(default_factory=dict)

    # 清洗后的数据集名称
    cleaned_dataset_name: str = ""

    # 建议
    recommendations: list[str] = field(default_factory=list)

    # 解释性报告
    interpretation: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "success": self.success,
            "message": self.message,
            "original_rows": self.original_rows,
            "final_rows": self.final_rows,
            "rows_removed": self.rows_removed,
            "rows_modified": self.rows_modified,
            "operations": [
                {
                    "operation_type": op.operation_type,
                    "column": op.column,
                    "method": op.method,
                    "rows_affected": op.rows_affected,
                    "details": op.details,
                }
                for op in self.operations
            ],
            "quality_before": self.quality_before,
            "quality_after": self.quality_after,
            "cleaned_dataset_name": self.cleaned_dataset_name,
            "recommendations": self.recommendations,
            "interpretation": self.interpretation,
        }


class DataCleaningCapability:
    """
    数据清洗能力。

    自动执行智能数据清洗流程，包括：
    - 数据质量评估
    - 缺失值处理（删除/填充/插值）
    - 异常值处理（删除/截尾/转换）
    - 重复值处理
    - 格式标准化
    - 清洗效果验证

    使用方法：
        capability = DataCleaningCapability()
        result = await capability.execute(
            session,
            dataset_name="my_data",
            strategy="auto"
        )
    """

    def __init__(self, registry: Any | None = None) -> None:
        """初始化数据清洗能力。

        Args:
            registry: ToolRegistry 实例，如果为 None 则尝试获取全局 registry
        """
        self.name = "data_cleaning"
        self.display_name = "数据清洗"
        self.description = "处理缺失值、异常值，提升数据质量"
        self.icon = "🧹"
        self._registry = registry

    async def execute(
        self,
        session: Session,
        *,
        dataset_name: str,
        output_name: str | None = None,
        strategy: str = "auto",
        missing_threshold: float = 0.5,
        outlier_method: str = "iqr",
        outlier_action: str = "clip",
        **kwargs: Any,
    ) -> DataCleaningResult:
        """执行数据清洗。

        Args:
            session: 会话对象
            dataset_name: 数据集名称
            output_name: 输出数据集名称（默认: {dataset_name}_cleaned）
            strategy: 清洗策略 (auto, conservative, aggressive)
            missing_threshold: 缺失值比例阈值，超过则删除列
            outlier_method: 异常值检测方法 (iqr, zscore)
            outlier_action: 异常值处理方式 (remove, clip, none)

        Returns:
            数据清洗结果
        """
        result = DataCleaningResult()
        result.cleaned_dataset_name = output_name or f"{dataset_name}_cleaned"

        # Step 1: 数据验证
        if not await self._validate_data(session, dataset_name, result):
            return result

        df = session.datasets.get(dataset_name).copy()
        result.original_rows = len(df)

        # Step 2: 评估清洗前质量
        result.quality_before = self._assess_quality(df)

        # Step 3: 根据策略执行清洗
        if strategy == "auto":
            operations = await self._auto_clean(
                session, df, dataset_name, missing_threshold, outlier_method, outlier_action
            )
        elif strategy == "conservative":
            operations = await self._conservative_clean(
                session, df, dataset_name, missing_threshold, outlier_method
            )
        elif strategy == "aggressive":
            operations = await self._aggressive_clean(session, df, dataset_name, outlier_method)
        else:
            result.message = f"未知清洗策略: {strategy}"
            return result

        result.operations = operations

        # Step 4: 计算影响
        result.final_rows = len(df)
        result.rows_removed = result.original_rows - result.final_rows
        result.rows_modified = sum(
            op.rows_affected for op in operations if op.operation_type != "duplicate"
        )

        # Step 5: 评估清洗后质量
        result.quality_after = self._assess_quality(df)

        # Step 6: 保存清洗后的数据
        session.datasets[result.cleaned_dataset_name] = df

        # Step 7: 生成建议
        result.recommendations = self._generate_recommendations(result)

        # Step 8: 生成报告
        result.interpretation = self._generate_interpretation(result)
        result.success = True
        result.message = f"清洗完成: 移除 {result.rows_removed} 行, 修改 {result.rows_modified} 行"

        return result

    async def _validate_data(
        self,
        session: Session,
        dataset_name: str,
        result: DataCleaningResult,
    ) -> bool:
        """验证数据是否存在。"""
        if dataset_name not in session.datasets:
            result.message = f"数据集 '{dataset_name}' 不存在"
            return False
        df = session.datasets.get(dataset_name)
        if df is None or df.empty:
            result.message = f"数据集 '{dataset_name}' 为空"
            return False
        return True

    def _assess_quality(self, df: pd.DataFrame) -> dict[str, Any]:
        """评估数据质量。"""
        total_cells = df.shape[0] * df.shape[1]
        missing_cells = df.isnull().sum().sum()
        duplicate_rows = df.duplicated().sum()

        return {
            "total_rows": len(df),
            "total_cols": len(df.columns),
            "missing_cells": int(missing_cells),
            "missing_pct": round(missing_cells / total_cells * 100, 2) if total_cells > 0 else 0,
            "duplicate_rows": int(duplicate_rows),
            "duplicate_pct": round(duplicate_rows / len(df) * 100, 2) if len(df) > 0 else 0,
        }

    async def _auto_clean(
        self,
        session: Session,
        df: pd.DataFrame,
        dataset_name: str,
        missing_threshold: float,
        outlier_method: str,
        outlier_action: str,
    ) -> list[CleaningOperation]:
        """自动清洗策略。"""
        operations = []

        # 1. 删除缺失值比例过高的列
        missing_pcts = df.isnull().mean()
        high_missing_cols = missing_pcts[missing_pcts > missing_threshold].index.tolist()
        if high_missing_cols:
            original_cols = len(df.columns)
            df.drop(columns=high_missing_cols, inplace=True)
            for col in high_missing_cols:
                operations.append(
                    CleaningOperation(
                        operation_type="missing_value",
                        column=col,
                        method="drop_column",
                        rows_affected=0,
                        details=f"缺失值比例 {missing_pcts[col]:.1%} 超过阈值 {missing_threshold:.1%}",
                    )
                )

        # 2. 删除完全重复的行
        duplicates = df.duplicated().sum()
        if duplicates > 0:
            df.drop_duplicates(inplace=True)
            operations.append(
                CleaningOperation(
                    operation_type="duplicate",
                    column="*",
                    method="drop_duplicates",
                    rows_affected=int(duplicates),
                )
            )

        # 3. 处理缺失值（按列类型智能选择方法）
        for col in df.columns:
            if df[col].isnull().sum() == 0:
                continue

            missing_count = df[col].isnull().sum()

            if pd.api.types.is_numeric_dtype(df[col]):
                # 数值列：用中位数填充
                fill_value = df[col].median()
                df[col].fillna(fill_value, inplace=True)
                operations.append(
                    CleaningOperation(
                        operation_type="missing_value",
                        column=col,
                        method="median_imputation",
                        rows_affected=int(missing_count),
                    )
                )
            else:
                # 分类列：用众数填充
                mode_val = df[col].mode()
                if len(mode_val) > 0:
                    fill_value = mode_val[0]
                    df[col].fillna(fill_value, inplace=True)
                    operations.append(
                        CleaningOperation(
                            operation_type="missing_value",
                            column=col,
                            method="mode_imputation",
                            rows_affected=int(missing_count),
                        )
                    )

        # 4. 处理异常值
        if outlier_action != "none":
            for col in df.select_dtypes(include=[np.number]).columns:
                outliers = self._detect_outliers(df[col], outlier_method)
                if len(outliers) == 0:
                    continue

                if outlier_action == "remove":
                    df.drop(index=outliers.index, inplace=True)
                    operations.append(
                        CleaningOperation(
                            operation_type="outlier",
                            column=col,
                            method="remove",
                            rows_affected=len(outliers),
                        )
                    )
                elif outlier_action == "clip":
                    q1, q3 = df[col].quantile([0.25, 0.75])
                    iqr = q3 - q1
                    lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
                    clipped = ((df[col] < lower) | (df[col] > upper)).sum()
                    df[col] = df[col].clip(lower, upper)
                    operations.append(
                        CleaningOperation(
                            operation_type="outlier",
                            column=col,
                            method="clip",
                            rows_affected=int(clipped),
                        )
                    )

        return operations

    async def _conservative_clean(
        self,
        session: Session,
        df: pd.DataFrame,
        dataset_name: str,
        missing_threshold: float,
        outlier_method: str,
    ) -> list[CleaningOperation]:
        """保守清洗策略：只做最安全的操作。"""
        operations = []

        # 只删除完全重复的行
        duplicates = df.duplicated().sum()
        if duplicates > 0:
            df.drop_duplicates(inplace=True)
            operations.append(
                CleaningOperation(
                    operation_type="duplicate",
                    column="*",
                    method="drop_duplicates",
                    rows_affected=int(duplicates),
                )
            )

        # 只处理缺失值比例非常高的列（删除）
        missing_pcts = df.isnull().mean()
        very_high_missing = missing_pcts[missing_pcts > 0.8].index.tolist()
        if very_high_missing:
            df.drop(columns=very_high_missing, inplace=True)
            for col in very_high_missing:
                operations.append(
                    CleaningOperation(
                        operation_type="missing_value",
                        column=col,
                        method="drop_column",
                        rows_affected=0,
                        details="缺失值比例超过 80%",
                    )
                )

        return operations

    async def _aggressive_clean(
        self,
        session: Session,
        df: pd.DataFrame,
        dataset_name: str,
        outlier_method: str,
    ) -> list[CleaningOperation]:
        """激进清洗策略：移除所有有问题的数据。"""
        operations = []

        # 删除任何有缺失值的行
        rows_with_missing = df.isnull().any(axis=1).sum()
        if rows_with_missing > 0:
            df.dropna(inplace=True)
            operations.append(
                CleaningOperation(
                    operation_type="missing_value",
                    column="*",
                    method="drop_rows",
                    rows_affected=int(rows_with_missing),
                )
            )

        # 删除重复行
        duplicates = df.duplicated().sum()
        if duplicates > 0:
            df.drop_duplicates(inplace=True)
            operations.append(
                CleaningOperation(
                    operation_type="duplicate",
                    column="*",
                    method="drop_duplicates",
                    rows_affected=int(duplicates),
                )
            )

        # 删除包含异常值的行
        for col in df.select_dtypes(include=[np.number]).columns:
            outliers = self._detect_outliers(df[col], outlier_method)
            if len(outliers) > 0:
                df.drop(index=outliers.index, inplace=True)
                operations.append(
                    CleaningOperation(
                        operation_type="outlier",
                        column=col,
                        method="remove",
                        rows_affected=len(outliers),
                    )
                )

        return operations

    def _detect_outliers(self, series: pd.Series, method: str = "iqr") -> pd.Series:
        """检测异常值。"""
        series_clean = series.dropna()

        if method == "iqr":
            q1, q3 = series_clean.quantile([0.25, 0.75])
            iqr = q3 - q1
            lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            return series[(series < lower) | (series > upper)]
        elif method == "zscore":
            z_scores = (series_clean - series_clean.mean()) / series_clean.std()
            outlier_idx = z_scores[abs(z_scores) > 3].index
            return series.loc[outlier_idx]

        return pd.Series(dtype=series.dtype)

    def _generate_recommendations(self, result: DataCleaningResult) -> list[str]:
        """生成后续建议。"""
        recommendations = []

        # 检查清洗效果
        missing_before = result.quality_before.get("missing_pct", 0)
        missing_after = result.quality_after.get("missing_pct", 0)

        if missing_after > 0:
            recommendations.append(f"清洗后仍有 {missing_after:.1f}% 缺失值，建议手动检查")
        elif missing_before > 0:
            recommendations.append("所有缺失值已成功处理")

        # 数据损失评估
        loss_pct = (
            (result.rows_removed / result.original_rows * 100) if result.original_rows > 0 else 0
        )
        if loss_pct > 20:
            recommendations.append(
                f"数据损失率较高 ({loss_pct:.1f}%)，建议检查清洗策略是否过于激进"
            )
        elif loss_pct > 5:
            recommendations.append(f"数据损失率在合理范围内 ({loss_pct:.1f}%)")
        else:
            recommendations.append("数据保留率良好")

        return recommendations

    def _generate_interpretation(self, result: DataCleaningResult) -> str:
        """生成清洗报告。"""
        lines = [
            f"## 数据清洗报告: {result.cleaned_dataset_name}",
            "",
            f"原始数据: **{result.original_rows}** 行",
            f"清洗后: **{result.final_rows}** 行",
            f"移除: **{result.rows_removed}** 行 ({result.original_rows and result.rows_removed/result.original_rows*100:.1f}%)",
            "",
        ]

        # 清洗操作
        if result.operations:
            lines.extend(
                [
                    "### 执行的操作",
                    "",
                ]
            )
            for op in result.operations:
                lines.append(
                    f"- **{op.operation_type}** | {op.column}: {op.method} ({op.rows_affected} 行)"
                )
            lines.append("")

        # 质量改善
        lines.extend(
            [
                "### 质量改善",
                f"- 缺失值: {result.quality_before.get('missing_pct', 0):.1f}% → {result.quality_after.get('missing_pct', 0):.1f}%",
                f"- 重复行: {result.quality_before.get('duplicate_rows', 0)} → {result.quality_after.get('duplicate_rows', 0)}",
                "",
            ]
        )

        # 建议
        if result.recommendations:
            lines.extend(
                [
                    "### 建议",
                    *[f"- {r}" for r in result.recommendations],
                    "",
                ]
            )

        return "\n".join(lines)

    def _get_registry(self) -> Any | None:
        """获取 ToolRegistry。"""
        if self._registry is not None:
            return self._registry
        try:
            from nini.tools.registry import get_default_registry

            return get_default_registry()
        except Exception:
            return None
