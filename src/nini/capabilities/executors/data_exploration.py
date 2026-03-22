"""数据探索能力实现。

执行全面的数据探索流程：
1. 数据预览和基本信息
2. 数据质量评估（缺失值、异常值）
3. 描述性统计分析
4. 变量分布分析
5. 数据类型推断
6. 生成探索性报告
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:
    from nini.agent.session import Session
    from nini.tools.base import ToolResult


@dataclass
class ColumnProfile:
    """单列数据画像。"""

    name: str
    dtype: str
    null_count: int
    null_pct: float
    unique_count: int
    unique_pct: float
    sample_values: list[Any] = field(default_factory=list)

    # 数值列特有
    min: float | None = None
    max: float | None = None
    mean: float | None = None
    median: float | None = None
    std: float | None = None
    q25: float | None = None
    q75: float | None = None

    # 分类列特有
    top_values: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class DataExplorationResult:
    """数据探索结果。"""

    success: bool = False
    message: str = ""

    # 基本信息
    dataset_name: str = ""
    n_rows: int = 0
    n_cols: int = 0
    memory_usage: str = ""

    # 列画像
    column_profiles: list[ColumnProfile] = field(default_factory=list)

    # 数据质量
    total_missing: int = 0
    missing_pct: float = 0.0
    duplicate_rows: int = 0
    duplicate_pct: float = 0.0

    # 异常值检测
    outlier_summary: dict[str, int] = field(default_factory=dict)

    # 相关性概览
    high_correlations: list[dict[str, Any]] = field(default_factory=list)

    # 可视化产物
    chart_artifacts: list[dict[str, Any]] = field(default_factory=list)

    # 建议
    recommendations: list[str] = field(default_factory=list)

    # 解释性报告
    interpretation: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "success": self.success,
            "message": self.message,
            "dataset_name": self.dataset_name,
            "n_rows": self.n_rows,
            "n_cols": self.n_cols,
            "memory_usage": self.memory_usage,
            "column_profiles": [
                {
                    "name": p.name,
                    "dtype": p.dtype,
                    "null_count": p.null_count,
                    "null_pct": p.null_pct,
                    "unique_count": p.unique_count,
                    "unique_pct": p.unique_pct,
                    "sample_values": p.sample_values[:5],
                    "min": p.min,
                    "max": p.max,
                    "mean": p.mean,
                    "median": p.median,
                    "std": p.std,
                    "q25": p.q25,
                    "q75": p.q75,
                    "top_values": p.top_values[:5],
                }
                for p in self.column_profiles
            ],
            "total_missing": self.total_missing,
            "missing_pct": self.missing_pct,
            "duplicate_rows": self.duplicate_rows,
            "duplicate_pct": self.duplicate_pct,
            "outlier_summary": self.outlier_summary,
            "high_correlations": self.high_correlations,
            "chart_artifacts": self.chart_artifacts,
            "recommendations": self.recommendations,
            "interpretation": self.interpretation,
        }


class DataExplorationCapability:
    """
    数据探索能力。

    自动执行全面的数据探索流程，包括：
    - 数据预览和基本信息
    - 数据质量评估
    - 描述性统计分析
    - 变量分布分析
    - 异常值检测
    - 生成探索性报告和建议

    使用方法：
        capability = DataExplorationCapability()
        result = await capability.execute(
            session,
            dataset_name="my_data"
        )
    """

    def __init__(self, registry: Any | None = None) -> None:
        """初始化数据探索能力。

        Args:
            registry: ToolRegistry 实例，如果为 None 则尝试获取全局 registry
        """
        self.name = "data_exploration"
        self.display_name = "数据探索"
        self.description = "全面了解数据特征：分布、缺失值、异常值等"
        self.icon = "🔍"
        self._registry = registry

    async def execute(
        self,
        session: Session,
        *,
        dataset_name: str,
        generate_charts: bool = True,
        detect_outliers: bool = True,
        **kwargs: Any,
    ) -> DataExplorationResult:
        """执行数据探索。

        Args:
            session: 会话对象
            dataset_name: 数据集名称
            generate_charts: 是否生成可视化图表
            detect_outliers: 是否检测异常值

        Returns:
            数据探索结果
        """
        result = DataExplorationResult()
        result.dataset_name = dataset_name

        # Step 1: 数据验证
        if not await self._validate_data(session, dataset_name, result):
            return result

        df_raw = session.datasets.get(dataset_name)
        if df_raw is None:
            result.message = f"数据集 '{dataset_name}' 不存在"
            return result
        df = df_raw
        result.n_rows = len(df)
        result.n_cols = len(df.columns)
        result.memory_usage = f"{df.memory_usage(deep=True).sum() / 1024:.2f} KB"

        # Step 2: 生成列画像
        result.column_profiles = self._generate_column_profiles(df)

        # Step 3: 数据质量评估
        await self._assess_data_quality(session, dataset_name, result)

        # Step 4: 异常值检测
        if detect_outliers:
            result.outlier_summary = self._detect_outliers(df)

        # Step 5: 高相关性检测
        result.high_correlations = self._find_high_correlations(df)

        # Step 6: 生成可视化
        if generate_charts:
            result.chart_artifacts = await self._generate_charts(session, dataset_name, df)

        # Step 7: 生成建议
        result.recommendations = self._generate_recommendations(result)

        # Step 8: 生成解释报告
        result.interpretation = self._generate_interpretation(result)
        result.success = True
        result.message = (
            f"成功探索数据集 '{dataset_name}'，发现 {len(result.column_profiles)} 个变量"
        )

        return result

    async def _validate_data(
        self,
        session: Session,
        dataset_name: str,
        result: DataExplorationResult,
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

    def _generate_column_profiles(self, df: pd.DataFrame) -> list[ColumnProfile]:
        """为每列生成画像。"""
        profiles = []
        for col in df.columns:
            series = df[col]
            null_count = series.isnull().sum()
            unique_count = series.nunique()

            profile = ColumnProfile(
                name=col,
                dtype=str(series.dtype),
                null_count=int(null_count),
                null_pct=round(null_count / len(df) * 100, 2),
                unique_count=int(unique_count),
                unique_pct=round(unique_count / len(df) * 100, 2),
                sample_values=series.dropna().head(3).tolist(),
            )

            # 数值列统计
            if pd.api.types.is_numeric_dtype(series):
                desc = series.describe()
                profile.min = float(desc.get("min", 0))
                profile.max = float(desc.get("max", 0))
                profile.mean = float(desc.get("mean", 0))
                profile.median = float(series.median())
                profile.std = float(desc.get("std", 0))
                profile.q25 = float(desc.get("25%", 0))
                profile.q75 = float(desc.get("75%", 0))
            else:
                # 分类列统计
                vc = series.value_counts().head(5)
                profile.top_values = [{"value": str(v), "count": int(c)} for v, c in vc.items()]

            profiles.append(profile)
        return profiles

    async def _assess_data_quality(
        self,
        session: Session,
        dataset_name: str,
        result: DataExplorationResult,
    ) -> None:
        """评估数据质量。"""
        df_raw = session.datasets.get(dataset_name)
        if df_raw is None:
            return
        df = df_raw
        total_cells = df.shape[0] * df.shape[1]
        missing_cells = df.isnull().sum().sum()
        result.total_missing = int(missing_cells)
        result.missing_pct = round(missing_cells / total_cells * 100, 2)

        # 重复行
        dupes = df.duplicated().sum()
        result.duplicate_rows = int(dupes)
        result.duplicate_pct = round(dupes / len(df) * 100, 2)

    def _detect_outliers(self, df: pd.DataFrame) -> dict[str, int]:
        """使用 IQR 方法检测异常值。"""
        outlier_counts = {}
        for col in df.select_dtypes(include=["number"]).columns:
            series = df[col].dropna()
            if len(series) < 10:
                continue
            q1 = series.quantile(0.25)
            q3 = series.quantile(0.75)
            iqr = q3 - q1
            lower = q1 - 1.5 * iqr
            upper = q3 + 1.5 * iqr
            outliers = ((series < lower) | (series > upper)).sum()
            if outliers > 0:
                outlier_counts[col] = int(outliers)
        return outlier_counts

    def _find_high_correlations(
        self, df: pd.DataFrame, threshold: float = 0.8
    ) -> list[dict[str, Any]]:
        """查找高相关性变量对。"""
        numeric_df = df.select_dtypes(include=["number"])
        if len(numeric_df.columns) < 2:
            return []

        corr_matrix = numeric_df.corr().abs()
        high_corr = []

        for i, col1 in enumerate(corr_matrix.columns):
            for j, col2 in enumerate(corr_matrix.columns):
                if i >= j:
                    continue
                corr_raw: Any = corr_matrix.loc[col1, col2]
                corr_val = float(corr_raw)
                if corr_val >= threshold:
                    high_corr.append(
                        {
                            "var1": col1,
                            "var2": col2,
                            "correlation": round(corr_val, 3),
                        }
                    )

        return sorted(high_corr, key=lambda x: x["correlation"], reverse=True)

    async def _generate_charts(
        self,
        session: Session,
        dataset_name: str,
        df: pd.DataFrame,
    ) -> list[dict[str, Any]]:
        """生成探索性可视化。"""
        artifacts: list[dict[str, Any]] = []
        registry = self._get_registry()
        if registry is None:
            return artifacts

        # 数值列的分布图
        numeric_cols = df.select_dtypes(include=["number"]).columns[:3]  # 最多3个
        for col in numeric_cols:
            try:
                chart_result = await registry.execute(
                    "create_chart",
                    session=session,
                    dataset_name=dataset_name,
                    chart_type="histogram",
                    x_column=col,
                    title=f"{col} 分布",
                )
                if chart_result and chart_result.artifact:
                    artifacts.append(
                        {
                            "type": "histogram",
                            "column": col,
                            "artifact": chart_result.artifact,
                        }
                    )
            except Exception:
                pass  # 忽略图表生成错误

        return artifacts

    def _generate_recommendations(self, result: DataExplorationResult) -> list[str]:
        """生成数据改进建议。"""
        recommendations = []

        # 缺失值建议
        if result.missing_pct > 20:
            recommendations.append(
                f"数据集缺失值比例较高 ({result.missing_pct}%)，建议检查数据收集流程"
            )
        elif result.missing_pct > 0:
            recommendations.append(f"存在 {result.total_missing} 个缺失值，建议进行缺失值处理")

        # 重复行建议
        if result.duplicate_pct > 5:
            recommendations.append(
                f"存在 {result.duplicate_rows} 行重复数据 ({result.duplicate_pct}%)，建议去重"
            )

        # 异常值建议
        if result.outlier_summary:
            cols_with_outliers = list(result.outlier_summary.keys())
            recommendations.append(
                f"以下列存在异常值: {', '.join(cols_with_outliers)}，建议检查或处理"
            )

        # 高相关性建议
        if result.high_correlations:
            pairs = [f"{c['var1']}-{c['var2']}" for c in result.high_correlations[:3]]
            recommendations.append(f"发现高相关性变量对: {', '.join(pairs)}，可能存在多重共线性")

        # 列级别建议
        for profile in result.column_profiles:
            if profile.null_pct > 50:
                recommendations.append(f"列 '{profile.name}' 缺失值超过 50%，建议检查或删除")
            if profile.unique_pct == 100 and profile.dtype in ["int64", "float64"]:
                recommendations.append(f"列 '{profile.name}' 可能为 ID 列（唯一值 100%）")

        return recommendations

    def _generate_interpretation(self, result: DataExplorationResult) -> str:
        """生成探索性报告。"""
        lines = [
            f"## 数据探索报告: {result.dataset_name}",
            "",
            f"数据集包含 **{result.n_rows}** 行、**{result.n_cols}** 列，内存占用 {result.memory_usage}。",
            "",
        ]

        # 数据质量概述
        lines.extend(
            [
                "### 数据质量",
                f"- 缺失值: {result.total_missing} 个 ({result.missing_pct}%)",
                f"- 重复行: {result.duplicate_rows} 行 ({result.duplicate_pct}%)",
                "",
            ]
        )

        # 变量类型分布
        dtypes: dict[str, int] = {}
        for p in result.column_profiles:
            dtype_cat = "数值" if p.dtype in ["int64", "float64"] else "分类"
            dtypes[dtype_cat] = dtypes.get(dtype_cat, 0) + 1

        lines.extend(
            [
                "### 变量类型",
                *[f"- {k}: {v} 列" for k, v in dtypes.items()],
                "",
            ]
        )

        # 异常值
        if result.outlier_summary:
            lines.extend(
                [
                    "### 异常值检测",
                    *[
                        f"- {col}: {count} 个异常值"
                        for col, count in result.outlier_summary.items()
                    ],
                    "",
                ]
            )

        # 高相关性
        if result.high_correlations:
            lines.extend(
                [
                    "### 高相关性变量 (|r| > 0.8)",
                    *[
                        f"- {c['var1']} vs {c['var2']}: r = {c['correlation']}"
                        for c in result.high_correlations[:5]
                    ],
                    "",
                ]
            )

        # 建议
        if result.recommendations:
            lines.extend(
                [
                    "### 改进建议",
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
            from nini.tools.registry import create_default_tool_registry

            return create_default_tool_registry()
        except Exception:
            return None
