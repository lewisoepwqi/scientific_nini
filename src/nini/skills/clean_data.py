"""数据清洗技能。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from nini.agent.session import Session
from nini.skills.base import Skill, SkillResult


class MissingPattern(Enum):
    """缺失值模式类型。"""

    RANDOM = "random"  # 完全随机缺失 (MCAR)
    SYSTEMATIC = "systematic"  # 系统性缺失
    BLOCK = "block"  # 整块缺失
    NONE = "none"  # 无缺失


class OutlierPattern(Enum):
    """异常值分布模式。"""

    NORMAL = "normal"  # 正常分布
    SKEWED = "skewed"  # 偏态分布
    EXTREME = "extreme"  # 极端值较多
    NONE = "none"  # 无异常值


@dataclass
class ColumnProfile:
    """单列数据特征分析结果。"""

    column: str
    dtype: str
    total_rows: int
    missing_count: int
    missing_ratio: float
    missing_pattern: MissingPattern
    unique_count: int
    is_numeric: bool
    # 数值列特有
    mean: float | None = None
    median: float | None = None
    std: float | None = None
    skewness: float | None = None
    kurtosis: float | None = None
    outlier_count: int = 0
    outlier_ratio: float = 0.0
    outlier_pattern: OutlierPattern = OutlierPattern.NONE
    outlier_bounds: tuple[float, float] | None = None
    # 分类列特有
    mode: Any | None = None
    mode_freq: int = 0


@dataclass
class CleaningRecommendation:
    """清洗策略推荐结果。"""

    column: str
    missing_strategy: str
    missing_reason: str
    outlier_strategy: str
    outlier_reason: str
    normalize: bool
    normalize_reason: str
    priority: str  # high, medium, low


def analyze_missing_pattern(df: pd.DataFrame, column: str) -> MissingPattern:
    """分析缺失值模式。

    通过检查缺失值的分布来判断是随机缺失还是系统性缺失。
    """
    col_data = df[column]
    missing_mask = col_data.isna()

    if missing_mask.sum() == 0:
        return MissingPattern.NONE

    # 检查是否整块缺失（连续缺失）
    missing_indices = missing_mask[missing_mask].index
    if len(missing_indices) > 1:
        gaps = missing_indices[1:].values - missing_indices[:-1].values
        if np.mean(gaps) < 2.0:  # 平均间隔小于2，说明是连续缺失
            return MissingPattern.BLOCK

    # 检查是否与其他列的缺失相关（系统性缺失）
    other_cols = [c for c in df.columns if c != column]
    if other_cols:
        correlations = []
        for other_col in other_cols:
            other_missing = df[other_col].isna()
            if other_missing.sum() > 0:
                # 使用列联表检验
                try:
                    contingency = pd.crosstab(missing_mask, other_missing)
                    if contingency.shape == (2, 2):
                        _, p_value, _, _ = stats.chi2_contingency(contingency)
                        if p_value < 0.05:
                            correlations.append(True)
                except Exception:
                    pass

        if correlations and len(correlations) > 0:
            return MissingPattern.SYSTEMATIC

    return MissingPattern.RANDOM


def analyze_outlier_pattern(series: pd.Series) -> tuple[OutlierPattern, int, tuple[float, float]]:
    """分析异常值模式。

    返回: (模式, 异常值数量, (下界, 上界))
    """
    clean_data = series.dropna()
    if len(clean_data) < 4:
        return OutlierPattern.NONE, 0, (0.0, 0.0)

    # 使用 IQR 方法检测异常值
    q1 = clean_data.quantile(0.25)
    q3 = clean_data.quantile(0.75)
    iqr = q3 - q1

    if pd.isna(iqr) or iqr == 0:
        return OutlierPattern.NONE, 0, (q1, q3)

    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr

    outliers = clean_data[(clean_data < lower_bound) | (clean_data > upper_bound)]
    outlier_count = len(outliers)
    outlier_ratio = outlier_count / len(clean_data)

    # 判断分布模式（即使无异常值也计算）
    skewness = clean_data.skew()

    if outlier_count == 0:
        return OutlierPattern.NONE, 0, (lower_bound, upper_bound)

    if outlier_ratio > 0.1:
        pattern = OutlierPattern.EXTREME
    elif abs(skewness) > 1.5:
        pattern = OutlierPattern.SKEWED
    else:
        pattern = OutlierPattern.NORMAL

    return pattern, outlier_count, (lower_bound, upper_bound)


def analyze_column_profile(df: pd.DataFrame, column: str) -> ColumnProfile:
    """分析单列数据特征。"""
    col_data = df[column]
    total_rows = len(col_data)
    missing_count = int(col_data.isna().sum())
    missing_ratio = missing_count / total_rows if total_rows > 0 else 0.0
    missing_pattern = analyze_missing_pattern(df, column)
    unique_count = col_data.nunique(dropna=True)
    is_numeric = pd.api.types.is_numeric_dtype(col_data)

    profile = ColumnProfile(
        column=column,
        dtype=str(col_data.dtype),
        total_rows=total_rows,
        missing_count=missing_count,
        missing_ratio=missing_ratio,
        missing_pattern=missing_pattern,
        unique_count=unique_count,
        is_numeric=is_numeric,
    )

    if is_numeric:
        clean_data = col_data.dropna()
        if len(clean_data) > 0:
            profile.mean = float(clean_data.mean())
            profile.median = float(clean_data.median())
            profile.std = float(clean_data.std()) if clean_data.std() is not None else 0.0
            profile.skewness = float(clean_data.skew())
            profile.kurtosis = float(clean_data.kurtosis())

            outlier_pattern, outlier_count, bounds = analyze_outlier_pattern(clean_data)
            profile.outlier_count = outlier_count
            profile.outlier_ratio = outlier_count / len(clean_data)
            profile.outlier_pattern = outlier_pattern
            profile.outlier_bounds = bounds
    else:
        # 分类列：计算众数
        mode_series = col_data.mode(dropna=True)
        if len(mode_series) > 0:
            profile.mode = mode_series.iloc[0]
            profile.mode_freq = int((col_data == profile.mode).sum())

    return profile


def recommend_missing_strategy(profile: ColumnProfile) -> tuple[str, str]:
    """基于数据特征推荐缺失值处理策略。

    返回: (策略, 原因)
    """
    if profile.missing_count == 0:
        return "none", "无缺失值"

    # 高缺失率列（>50%）建议删除
    if profile.missing_ratio > 0.5:
        return "drop_column", f"缺失率 {profile.missing_ratio:.1%} 过高，建议删除该列"

    if not profile.is_numeric:
        # 分类列使用众数填充
        if profile.missing_pattern == MissingPattern.RANDOM:
            return "mode", "分类列随机缺失，使用众数填充"
        else:
            return "mode", "分类列系统性缺失，使用众数填充（建议同时检查数据收集流程）"

    # 数值列策略
    if profile.missing_pattern == MissingPattern.BLOCK:
        # 连续缺失使用时序填充
        return "ffill", "数值列存在连续缺失，使用前向填充"

    if profile.missing_pattern == MissingPattern.SYSTEMATIC:
        # 系统性缺失需要谨慎处理，建议使用中位数（更稳健）
        return "median", "数值列存在系统性缺失，使用中位数填充更稳健"

    # 随机缺失：根据分布特征选择
    if profile.outlier_pattern == OutlierPattern.EXTREME or abs(profile.skewness or 0) > 1.5:
        return "median", f"数据存在偏态（skewness={profile.skewness:.2f}），使用中位数填充更稳健"

    if profile.missing_ratio < 0.05:
        return "mean", "缺失率较低且分布正常，使用均值填充"

    return "median", "默认使用中位数填充以保证稳健性"


def recommend_outlier_strategy(profile: ColumnProfile) -> tuple[str, str]:
    """基于数据特征推荐异常值处理策略。

    返回: (策略, 原因)
    """
    if not profile.is_numeric or profile.outlier_count == 0:
        return "none", "无异常值"

    if profile.outlier_pattern == OutlierPattern.EXTREME:
        return (
            "winsorize",
            f"异常值比例过高（{profile.outlier_ratio:.1%}），建议使用缩尾处理而非删除",
        )

    if profile.outlier_pattern == OutlierPattern.SKEWED:
        return "iqr", f"数据呈偏态分布（skewness={profile.skewness:.2f}），使用 IQR 方法识别异常值"

    if profile.outlier_ratio < 0.01:
        return "iqr", f"异常值比例较低（{profile.outlier_ratio:.1%}），可安全删除"

    return "none", "异常值在可接受范围内，保留原数据"


def recommend_normalization(profile: ColumnProfile) -> tuple[bool, str]:
    """推荐是否需要标准化。

    返回: (是否标准化, 原因)
    """
    if not profile.is_numeric:
        return False, "非数值列无需标准化"

    if profile.std is None or profile.std == 0:
        return False, "标准差为零，无需标准化"

    # 如果数据已经近似标准正态，不需要标准化
    if profile.std and 0.9 < profile.std < 1.1 and profile.mean and -0.1 < profile.mean < 0.1:
        return False, "数据已近似标准正态分布"

    # 如果数据范围差异很大，建议标准化
    if profile.outlier_pattern == OutlierPattern.EXTREME:
        return True, "数据存在极端值，标准化可减少异常值影响"

    return False, "数据分布正常，无需标准化"


def generate_cleaning_recommendation(profile: ColumnProfile) -> CleaningRecommendation:
    """为单列生成完整的清洗策略推荐。"""
    missing_strategy, missing_reason = recommend_missing_strategy(profile)
    outlier_strategy, outlier_reason = recommend_outlier_strategy(profile)
    normalize, normalize_reason = recommend_normalization(profile)

    # 确定优先级
    if profile.missing_ratio > 0.3 or profile.outlier_ratio > 0.1:
        priority = "high"
    elif profile.missing_ratio > 0.1 or profile.outlier_ratio > 0.05:
        priority = "medium"
    else:
        priority = "low"

    return CleaningRecommendation(
        column=profile.column,
        missing_strategy=missing_strategy,
        missing_reason=missing_reason,
        outlier_strategy=outlier_strategy,
        outlier_reason=outlier_reason,
        normalize=normalize,
        normalize_reason=normalize_reason,
        priority=priority,
    )


def analyze_dataset_features(df: pd.DataFrame) -> dict[str, Any]:
    """分析整个数据集的特征。

    返回包含各列特征分析的字典。
    """
    profiles = {}
    for column in df.columns:
        profiles[column] = analyze_column_profile(df, column)

    # 计算数据集整体统计
    total_cells = df.size
    missing_cells = df.isna().sum().sum()
    numeric_cols = df.select_dtypes(include="number").columns.tolist()

    return {
        "total_rows": len(df),
        "total_columns": len(df.columns),
        "total_cells": total_cells,
        "missing_cells": int(missing_cells),
        "missing_ratio": missing_cells / total_cells if total_cells > 0 else 0.0,
        "numeric_columns": len(numeric_cols),
        "categorical_columns": len(df.columns) - len(numeric_cols),
        "column_profiles": profiles,
    }


def recommend_cleaning_strategy(df: pd.DataFrame) -> dict[str, Any]:
    """为整个数据集推荐清洗策略。

    这是对外暴露的主要推荐函数。
    """
    features = analyze_dataset_features(df)
    profiles = features["column_profiles"]

    recommendations = {}
    for column, profile in profiles.items():
        recommendations[column] = generate_cleaning_recommendation(profile)

    # 生成整体策略建议
    high_priority_cols = [r.column for r in recommendations.values() if r.priority == "high"]
    medium_priority_cols = [r.column for r in recommendations.values() if r.priority == "medium"]

    overall_strategy = {
        "high_priority_columns": high_priority_cols,
        "medium_priority_columns": medium_priority_cols,
        "summary": {
            "columns_needing_attention": len(high_priority_cols) + len(medium_priority_cols),
            "total_columns": len(df.columns),
            "dataset_missing_ratio": features["missing_ratio"],
        },
    }

    # 转换为可序列化的字典
    recommendations_dict = {}
    for col, rec in recommendations.items():
        recommendations_dict[col] = {
            "missing_strategy": rec.missing_strategy,
            "missing_reason": rec.missing_reason,
            "outlier_strategy": rec.outlier_strategy,
            "outlier_reason": rec.outlier_reason,
            "normalize": rec.normalize,
            "normalize_reason": rec.normalize_reason,
            "priority": rec.priority,
        }

    # 列特征详情
    profiles_dict = {}
    for col, prof in profiles.items():
        profiles_dict[col] = {
            "dtype": prof.dtype,
            "missing_count": prof.missing_count,
            "missing_ratio": prof.missing_ratio,
            "missing_pattern": prof.missing_pattern.value,
            "unique_count": prof.unique_count,
            "is_numeric": prof.is_numeric,
            "mean": prof.mean,
            "median": prof.median,
            "std": prof.std,
            "skewness": prof.skewness,
            "outlier_count": prof.outlier_count,
            "outlier_ratio": prof.outlier_ratio,
            "outlier_pattern": prof.outlier_pattern.value,
        }

    return {
        "overall_strategy": overall_strategy,
        "recommendations": recommendations_dict,
        "column_profiles": profiles_dict,
    }


def _safe_preview(df: pd.DataFrame, n_rows: int = 20) -> dict[str, Any]:
    preview = df.head(n_rows)
    rows = preview.to_dict(orient="records")
    safe_rows: list[dict[str, Any]] = []
    for row in rows:
        safe_row: dict[str, Any] = {}
        for key, value in row.items():
            if isinstance(value, np.bool_):
                safe_row[key] = bool(value)
            elif isinstance(value, np.integer):
                safe_row[key] = int(value)
            elif isinstance(value, (np.floating, float)):
                if not math.isfinite(value):
                    safe_row[key] = None
                else:
                    safe_row[key] = float(value)
            elif pd.isna(value):
                safe_row[key] = None
            else:
                safe_row[key] = value
        safe_rows.append(safe_row)

    return {
        "data": safe_rows,
        "columns": [{"name": c, "dtype": str(df[c].dtype)} for c in df.columns],
        "total_rows": len(df),
        "preview_rows": min(n_rows, len(df)),
    }


class CleanDataSkill(Skill):
    """对数据集进行缺失值处理、异常值过滤与标准化。"""

    _missing_strategies = [
        "auto",
        "none",
        "drop",
        "mean",
        "median",
        "mode",
        "zero",
        "ffill",
        "bfill",
    ]
    _outlier_methods = ["auto", "none", "iqr", "zscore"]

    @property
    def name(self) -> str:
        return "clean_data"

    @property
    def category(self) -> str:
        return "data"

    @property
    def description(self) -> str:
        return (
            "执行数据清洗：缺失值处理、异常值过滤、标准化。"
            "支持 inplace 覆盖原数据，或输出为新数据集。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "dataset_name": {"type": "string", "description": "输入数据集名称"},
                "missing_strategy": {
                    "type": "string",
                    "enum": self._missing_strategies,
                    "default": "auto",
                    "description": "缺失值处理策略，auto 表示自动推荐",
                },
                "outlier_method": {
                    "type": "string",
                    "enum": self._outlier_methods,
                    "default": "auto",
                    "description": "异常值处理方法，auto 表示自动推荐",
                },
                "outlier_threshold": {
                    "type": "number",
                    "default": 3.0,
                    "description": "zscore 阈值（仅 outlier_method=zscore）",
                },
                "normalize_numeric": {
                    "type": ["boolean", "string"],
                    "enum": [True, False, "auto"],
                    "default": False,
                    "description": "是否对数值列做 Z-score 标准化，auto 表示自动推荐",
                },
                "normalize_columns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "指定要标准化的列（为空则默认所有数值列）",
                },
                "inplace": {
                    "type": "boolean",
                    "default": False,
                    "description": "是否覆盖原数据集",
                },
                "output_dataset_name": {
                    "type": "string",
                    "description": "输出数据集名称（inplace=false 时可选）",
                },
            },
            "required": ["dataset_name"],
        }

    @property
    def is_idempotent(self) -> bool:
        return False

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        dataset_name = kwargs["dataset_name"]
        missing_strategy = str(kwargs.get("missing_strategy", "auto")).lower().strip()
        outlier_method = str(kwargs.get("outlier_method", "auto")).lower().strip()
        outlier_threshold = float(kwargs.get("outlier_threshold", 3.0))
        normalize_numeric = kwargs.get("normalize_numeric", False)
        normalize_columns = kwargs.get("normalize_columns") or []
        inplace = bool(kwargs.get("inplace", False))
        output_dataset_name = kwargs.get("output_dataset_name")

        df = session.datasets.get(dataset_name)
        if df is None:
            return SkillResult(success=False, message=f"数据集 '{dataset_name}' 不存在")
        if missing_strategy not in self._missing_strategies:
            return SkillResult(
                success=False, message=f"不支持的 missing_strategy: {missing_strategy}"
            )
        if outlier_method not in self._outlier_methods:
            return SkillResult(success=False, message=f"不支持的 outlier_method: {outlier_method}")

        # 自动模式：分析数据并应用推荐策略
        auto_recommendations = None
        if missing_strategy == "auto" or outlier_method == "auto":
            auto_recommendations = recommend_cleaning_strategy(df)

        cleaned = df.copy(deep=True)
        before_rows = len(cleaned)
        before_missing = int(cleaned.isna().sum().sum())

        # 处理缺失值
        if missing_strategy == "auto":
            self._handle_missing_auto(cleaned, auto_recommendations)
        else:
            self._handle_missing(cleaned, missing_strategy)

        # 处理异常值
        if outlier_method == "auto":
            removed_outliers = self._handle_outliers_auto(cleaned, auto_recommendations)
        else:
            removed_outliers = self._handle_outliers(cleaned, outlier_method, outlier_threshold)

        # 自动标准化建议
        if normalize_numeric == "auto":
            self._normalize_auto(cleaned, auto_recommendations)
        else:
            self._normalize(cleaned, normalize_numeric, normalize_columns)

        after_rows = len(cleaned)
        after_missing = int(cleaned.isna().sum().sum())

        if inplace:
            target_name = dataset_name
        else:
            target_name = output_dataset_name or self._default_output_name(dataset_name)
        session.datasets[target_name] = cleaned

        summary = {
            "input_dataset": dataset_name,
            "output_dataset": target_name,
            "inplace": inplace,
            "missing_strategy": missing_strategy,
            "outlier_method": outlier_method,
            "rows_before": before_rows,
            "rows_after": after_rows,
            "rows_removed_by_outlier": removed_outliers,
            "missing_before": before_missing,
            "missing_after": after_missing,
        }

        msg = (
            f"数据清洗完成：{dataset_name} -> {target_name}，"
            f"行数 {before_rows}->{after_rows}，缺失值 {before_missing}->{after_missing}"
        )

        # 添加自动策略信息
        if missing_strategy == "auto" or outlier_method == "auto":
            msg += "（使用自动推荐策略）"

        preview = _safe_preview(cleaned)
        result_data = summary
        if auto_recommendations:
            result_data["auto_strategy"] = auto_recommendations["recommendations"]

        return SkillResult(
            success=True,
            message=msg,
            data=result_data,
            has_dataframe=True,
            dataframe_preview=preview,
        )

    def _handle_missing(self, df: pd.DataFrame, strategy: str) -> None:
        if strategy == "none":
            return

        if strategy == "drop":
            df.dropna(inplace=True)
            df.reset_index(drop=True, inplace=True)
            return

        if strategy == "ffill":
            df.fillna(method="ffill", inplace=True)
            return
        if strategy == "bfill":
            df.fillna(method="bfill", inplace=True)
            return

        numeric_cols = df.select_dtypes(include="number").columns.tolist()
        non_numeric_cols = [c for c in df.columns if c not in numeric_cols]

        if strategy == "mean":
            for col in numeric_cols:
                df[col] = df[col].fillna(df[col].mean())
            for col in non_numeric_cols:
                mode = df[col].mode(dropna=True)
                if len(mode) > 0:
                    df[col] = df[col].fillna(mode.iloc[0])
            return

        if strategy == "median":
            for col in numeric_cols:
                df[col] = df[col].fillna(df[col].median())
            for col in non_numeric_cols:
                mode = df[col].mode(dropna=True)
                if len(mode) > 0:
                    df[col] = df[col].fillna(mode.iloc[0])
            return

        if strategy == "mode":
            for col in df.columns:
                mode = df[col].mode(dropna=True)
                if len(mode) > 0:
                    df[col] = df[col].fillna(mode.iloc[0])
            return

        if strategy == "zero":
            for col in numeric_cols:
                df[col] = df[col].fillna(0)
            for col in non_numeric_cols:
                df[col] = df[col].fillna("")

    def _handle_outliers(self, df: pd.DataFrame, method: str, threshold: float) -> int:
        if method == "none":
            return 0

        numeric_cols = df.select_dtypes(include="number").columns.tolist()
        if not numeric_cols:
            return 0

        before = len(df)
        mask = pd.Series([True] * len(df), index=df.index)

        if method == "iqr":
            for col in numeric_cols:
                q1 = df[col].quantile(0.25)
                q3 = df[col].quantile(0.75)
                iqr = q3 - q1
                if pd.isna(iqr) or iqr == 0:
                    continue
                low = q1 - 1.5 * iqr
                high = q3 + 1.5 * iqr
                mask &= df[col].between(low, high) | df[col].isna()

        if method == "zscore":
            for col in numeric_cols:
                std = df[col].std()
                if pd.isna(std) or std == 0:
                    continue
                z = (df[col] - df[col].mean()) / std
                mask &= z.abs().le(threshold) | df[col].isna()

        filtered = df[mask].copy()
        df.drop(df.index, inplace=True)
        if len(filtered) > 0:
            df[filtered.columns] = filtered
        df.reset_index(drop=True, inplace=True)
        return before - len(df)

    def _normalize(self, df: pd.DataFrame, normalize_numeric: bool, columns: list[str]) -> None:
        if not normalize_numeric:
            return
        if columns:
            target_cols = [col for col in columns if col in df.columns]
        else:
            target_cols = df.select_dtypes(include="number").columns.tolist()

        for col in target_cols:
            if not pd.api.types.is_numeric_dtype(df[col]):
                continue
            std = df[col].std()
            if pd.isna(std) or std == 0:
                continue
            df[col] = (df[col] - df[col].mean()) / std

    def _handle_missing_auto(
        self, df: pd.DataFrame, recommendations: dict[str, Any] | None
    ) -> None:
        """基于推荐策略自动处理缺失值。"""
        if recommendations is None:
            return

        recs = recommendations.get("recommendations", {})
        for col in list(df.columns):  # 使用 list 复制，避免在迭代时修改
            if col not in recs:
                continue

            strategy = recs[col].get("missing_strategy", "median")
            if strategy == "none":
                continue
            if strategy == "drop_column":
                # 删除整列
                if col in df.columns:
                    df.drop(columns=[col], inplace=True)
                continue

            # 应用策略
            if strategy == "drop":
                df.dropna(subset=[col], inplace=True)
            elif strategy == "mean" and pd.api.types.is_numeric_dtype(df[col]):
                df[col] = df[col].fillna(df[col].mean())
            elif strategy == "median" and pd.api.types.is_numeric_dtype(df[col]):
                df[col] = df[col].fillna(df[col].median())
            elif strategy == "mode":
                mode = df[col].mode(dropna=True)
                if len(mode) > 0:
                    df[col] = df[col].fillna(mode.iloc[0])
            elif strategy == "ffill":
                df[col] = df[col].fillna(method="ffill")
            elif strategy == "bfill":
                df[col] = df[col].fillna(method="bfill")
            elif strategy == "zero":
                if pd.api.types.is_numeric_dtype(df[col]):
                    df[col] = df[col].fillna(0)
                else:
                    df[col] = df[col].fillna("")

        df.reset_index(drop=True, inplace=True)

    def _handle_outliers_auto(
        self, df: pd.DataFrame, recommendations: dict[str, Any] | None
    ) -> int:
        """基于推荐策略自动处理异常值。"""
        if recommendations is None:
            return 0

        recs = recommendations.get("recommendations", {})
        numeric_cols = df.select_dtypes(include="number").columns.tolist()
        before = len(df)
        mask = pd.Series([True] * len(df), index=df.index)

        for col in numeric_cols:
            if col not in recs or col not in df.columns:
                continue

            strategy = recs[col].get("outlier_strategy", "none")
            if strategy == "none":
                continue

            if strategy == "iqr":
                q1 = df[col].quantile(0.25)
                q3 = df[col].quantile(0.75)
                iqr = q3 - q1
                if pd.isna(iqr) or iqr == 0:
                    continue
                low = q1 - 1.5 * iqr
                high = q3 + 1.5 * iqr
                mask &= df[col].between(low, high) | df[col].isna()
            elif strategy == "zscore":
                std = df[col].std()
                if pd.isna(std) or std == 0:
                    continue
                z = (df[col] - df[col].mean()) / std
                mask &= z.abs().le(3.0) | df[col].isna()
            elif strategy == "winsorize":
                # 缩尾处理：将异常值替换为边界值
                q1 = df[col].quantile(0.25)
                q3 = df[col].quantile(0.75)
                iqr = q3 - q1
                if pd.isna(iqr) or iqr == 0:
                    continue
                low = q1 - 1.5 * iqr
                high = q3 + 1.5 * iqr
                df[col] = df[col].clip(lower=low, upper=high)

        if before > 0:
            filtered = df[mask].copy()
            df.drop(df.index, inplace=True)
            if len(filtered) > 0:
                df[filtered.columns] = filtered
            df.reset_index(drop=True, inplace=True)

        return before - len(df)

    def _normalize_auto(self, df: pd.DataFrame, recommendations: dict[str, Any] | None) -> None:
        """基于推荐策略自动标准化。"""
        if recommendations is None:
            return

        recs = recommendations.get("recommendations", {})
        for col in df.columns:
            if col not in recs:
                continue

            should_normalize = recs[col].get("normalize", False)
            if should_normalize and pd.api.types.is_numeric_dtype(df[col]):
                std = df[col].std()
                if pd.isna(std) or std == 0:
                    continue
                df[col] = (df[col] - df[col].mean()) / std

    def _default_output_name(self, dataset_name: str) -> str:
        if "." in dataset_name:
            base, ext = dataset_name.rsplit(".", 1)
            return f"{base}_cleaned.{ext}"
        return f"{dataset_name}_cleaned"


class RecommendCleaningStrategySkill(Skill):
    """分析数据特征并推荐最优清洗策略。"""

    @property
    def name(self) -> str:
        return "recommend_cleaning_strategy"

    @property
    def category(self) -> str:
        return "data"

    @property
    def description(self) -> str:
        return (
            "智能分析数据特征（缺失值模式、异常值分布、数据类型等），"
            "为每列推荐最优的清洗策略，包括缺失值处理方法、异常值处理建议和标准化建议。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "dataset_name": {
                    "type": "string",
                    "description": "要分析的数据集名称",
                },
                "target_columns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "指定要分析的列（为空则分析所有列）",
                },
            },
            "required": ["dataset_name"],
        }

    @property
    def is_idempotent(self) -> bool:
        return True

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        dataset_name = kwargs["dataset_name"]
        target_columns = kwargs.get("target_columns") or []

        df = session.datasets.get(dataset_name)
        if df is None:
            return SkillResult(success=False, message=f"数据集 '{dataset_name}' 不存在")

        # 如果指定了列，过滤数据
        if target_columns:
            invalid_cols = [c for c in target_columns if c not in df.columns]
            if invalid_cols:
                return SkillResult(
                    success=False, message=f"以下列不存在: {', '.join(invalid_cols)}"
                )
            df = df[target_columns].copy()

        # 生成清洗策略推荐
        recommendation = recommend_cleaning_strategy(df)

        # 构建可读的消息
        overall = recommendation["overall_strategy"]
        summary = overall["summary"]

        high_priority = overall["high_priority_columns"]
        medium_priority = overall["medium_priority_columns"]

        msg_parts = [
            f"数据清洗策略分析完成：{dataset_name}",
            f"共 {summary['total_columns']} 列，"
            f"其中 {summary['columns_needing_attention']} 列需要关注",
        ]

        if high_priority:
            msg_parts.append(f"高优先级列: {', '.join(high_priority)}")
        if medium_priority:
            msg_parts.append(f"中优先级列: {', '.join(medium_priority)}")

        return SkillResult(
            success=True,
            message="；".join(msg_parts),
            data=recommendation,
        )
