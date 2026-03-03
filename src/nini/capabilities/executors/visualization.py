"""可视化能力实现。

执行智能可视化流程：
1. 分析数据特征和类型
2. 根据分析目的推荐图表类型
3. 自动生成多个相关图表
4. 导出图表产物
5. 生成可视化报告
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:
    from nini.agent.session import Session
    from nini.tools.base import SkillResult


@dataclass
class ChartSpec:
    """图表规格。"""

    chart_type: str
    title: str
    columns: list[str]
    artifact: dict[str, Any] | None = None
    error: str = ""


@dataclass
class VisualizationResult:
    """可视化结果。"""

    success: bool = False
    message: str = ""

    # 生成的图表
    charts: list[ChartSpec] = field(default_factory=list)

    # 按类别分组
    distribution_charts: list[ChartSpec] = field(default_factory=list)
    relationship_charts: list[ChartSpec] = field(default_factory=list)
    composition_charts: list[ChartSpec] = field(default_factory=list)

    # 导出的产物
    exported_files: list[dict[str, Any]] = field(default_factory=list)

    # 解释性报告
    interpretation: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "success": self.success,
            "message": self.message,
            "charts": [
                {
                    "chart_type": c.chart_type,
                    "title": c.title,
                    "columns": c.columns,
                    "artifact": c.artifact,
                    "error": c.error,
                }
                for c in self.charts
            ],
            "exported_files": self.exported_files,
            "interpretation": self.interpretation,
        }


class VisualizationCapability:
    """
    可视化能力。

    自动执行智能可视化流程，包括：
    - 数据特征分析
    - 智能图表推荐
    - 自动生成分布图、关系图、组合图
    - 图表导出
    - 生成可视化报告

    使用方法：
        capability = VisualizationCapability()
        result = await capability.execute(
            session,
            dataset_name="my_data",
            focus="distribution"
        )
    """

    def __init__(self, registry: Any | None = None) -> None:
        """初始化可视化能力。

        Args:
            registry: ToolRegistry 实例，如果为 None 则尝试获取全局 registry
        """
        self.name = "visualization"
        self.display_name = "可视化"
        self.description = "创建各类图表展示数据特征和分析结果"
        self.icon = "📊"
        self._registry = registry

    async def execute(
        self,
        session: Session,
        *,
        dataset_name: str,
        focus: str | None = None,
        columns: list[str] | None = None,
        max_charts: int = 6,
        export_format: str | None = None,
        **kwargs: Any,
    ) -> VisualizationResult:
        """执行可视化。

        Args:
            session: 会话对象
            dataset_name: 数据集名称
            focus: 可视化重点 (distribution, relationship, composition, all)
            columns: 指定列（默认所有列）
            max_charts: 最大生成图表数量
            export_format: 导出格式 (png, svg, pdf)

        Returns:
            可视化结果
        """
        result = VisualizationResult()

        # Step 1: 数据验证
        if not await self._validate_data(session, dataset_name, result):
            return result

        df = session.datasets.get(dataset_name)
        target_cols = columns or df.columns.tolist()

        # Step 2: 分析数据特征
        data_profile = self._analyze_data(df, target_cols)

        # Step 3: 确定可视化重点
        if focus is None:
            focus = self._recommend_focus(data_profile)

        # Step 4: 生成图表
        if focus in ["distribution", "all"]:
            result.distribution_charts = await self._generate_distribution_charts(
                session, dataset_name, df, data_profile, max_charts // 2
            )

        if focus in ["relationship", "all"]:
            result.relationship_charts = await self._generate_relationship_charts(
                session, dataset_name, df, data_profile, max_charts // 2
            )

        if focus in ["composition", "all"]:
            result.composition_charts = await self._generate_composition_charts(
                session, dataset_name, df, data_profile, max_charts // 3
            )

        # 合并所有图表
        result.charts = (
            result.distribution_charts + result.relationship_charts + result.composition_charts
        )

        # Step 5: 导出图表
        if export_format and result.charts:
            result.exported_files = await self._export_charts(session, result.charts, export_format)

        # Step 6: 生成报告
        result.interpretation = self._generate_interpretation(result, data_profile)
        result.success = len(result.charts) > 0
        result.message = f"成功生成 {len(result.charts)} 个图表"

        return result

    async def _validate_data(
        self,
        session: Session,
        dataset_name: str,
        result: VisualizationResult,
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

    def _analyze_data(self, df: pd.DataFrame, columns: list[str]) -> dict[str, Any]:
        """分析数据特征。"""
        numeric_cols = [
            c for c in columns if c in df.columns and pd.api.types.is_numeric_dtype(df[c])
        ]
        categorical_cols = [
            c for c in columns if c in df.columns and not pd.api.types.is_numeric_dtype(df[c])
        ]

        return {
            "n_rows": len(df),
            "n_cols": len(columns),
            "numeric_cols": numeric_cols[:10],  # 限制数量
            "categorical_cols": categorical_cols[:10],
            "has_time_column": any(
                pd.api.types.is_datetime64_any_dtype(df[c]) for c in columns if c in df.columns
            ),
        }

    def _recommend_focus(self, data_profile: dict[str, Any]) -> str:
        """推荐可视化重点。"""
        n_numeric = len(data_profile.get("numeric_cols", []))
        n_categorical = len(data_profile.get("categorical_cols", []))

        if n_numeric >= 2:
            return "all"
        elif n_numeric > 0:
            return "distribution"
        elif n_categorical > 0:
            return "composition"
        return "distribution"

    async def _generate_distribution_charts(
        self,
        session: Session,
        dataset_name: str,
        df: pd.DataFrame,
        data_profile: dict[str, Any],
        max_charts: int,
    ) -> list[ChartSpec]:
        """生成分布图表。"""
        charts = []
        registry = self._get_registry()
        if registry is None:
            return charts

        numeric_cols = data_profile.get("numeric_cols", [])[:max_charts]

        for col in numeric_cols:
            try:
                chart_result = await registry.execute(
                    "create_chart",
                    session=session,
                    dataset_name=dataset_name,
                    chart_type="histogram",
                    x_column=col,
                    title=f"{col} 分布直方图",
                )
                if chart_result and chart_result.artifact:
                    charts.append(
                        ChartSpec(
                            chart_type="histogram",
                            title=f"{col} 分布",
                            columns=[col],
                            artifact=chart_result.artifact,
                        )
                    )
            except Exception as e:
                charts.append(
                    ChartSpec(
                        chart_type="histogram",
                        title=f"{col} 分布",
                        columns=[col],
                        error=str(e),
                    )
                )

        return charts

    async def _generate_relationship_charts(
        self,
        session: Session,
        dataset_name: str,
        df: pd.DataFrame,
        data_profile: dict[str, Any],
        max_charts: int,
    ) -> list[ChartSpec]:
        """生成关系图表。"""
        charts = []
        registry = self._get_registry()
        if registry is None:
            return charts

        numeric_cols = data_profile.get("numeric_cols", [])

        # 散点图矩阵（前3个数值列的两两组合）
        if len(numeric_cols) >= 2:
            for i, col1 in enumerate(numeric_cols[:3]):
                for col2 in numeric_cols[i + 1 : 4]:
                    if len(charts) >= max_charts:
                        break
                    try:
                        chart_result = await registry.execute(
                            "create_chart",
                            session=session,
                            dataset_name=dataset_name,
                            chart_type="scatter",
                            x_column=col1,
                            y_column=col2,
                            title=f"{col1} vs {col2} 散点图",
                        )
                        if chart_result and chart_result.artifact:
                            charts.append(
                                ChartSpec(
                                    chart_type="scatter",
                                    title=f"{col1} vs {col2}",
                                    columns=[col1, col2],
                                    artifact=chart_result.artifact,
                                )
                            )
                    except Exception:
                        pass

        # 相关性热力图
        if len(numeric_cols) >= 2 and len(charts) < max_charts:
            try:
                chart_result = await registry.execute(
                    "create_chart",
                    session=session,
                    dataset_name=dataset_name,
                    chart_type="heatmap",
                    title="数值变量相关性热力图",
                )
                if chart_result and chart_result.artifact:
                    charts.append(
                        ChartSpec(
                            chart_type="heatmap",
                            title="相关性热力图",
                            columns=numeric_cols[:6],
                            artifact=chart_result.artifact,
                        )
                    )
            except Exception:
                pass

        return charts

    async def _generate_composition_charts(
        self,
        session: Session,
        dataset_name: str,
        df: pd.DataFrame,
        data_profile: dict[str, Any],
        max_charts: int,
    ) -> list[ChartSpec]:
        """生成组合图表。"""
        charts = []
        registry = self._get_registry()
        if registry is None:
            return charts

        categorical_cols = data_profile.get("categorical_cols", [])[:max_charts]

        for col in categorical_cols:
            try:
                # 选择前10个最常见的类别
                vc = df[col].value_counts().head(10)
                if len(vc) > 1:
                    chart_result = await registry.execute(
                        "create_chart",
                        session=session,
                        dataset_name=dataset_name,
                        chart_type="pie",
                        x_column=col,
                        title=f"{col} 类别分布",
                    )
                    if chart_result and chart_result.artifact:
                        charts.append(
                            ChartSpec(
                                chart_type="pie",
                                title=f"{col} 类别分布",
                                columns=[col],
                                artifact=chart_result.artifact,
                            )
                        )
            except Exception:
                pass

        return charts

    async def _export_charts(
        self,
        session: Session,
        charts: list[ChartSpec],
        export_format: str,
    ) -> list[dict[str, Any]]:
        """导出图表。"""
        exported = []
        registry = self._get_registry()
        if registry is None:
            return exported

        for chart in charts:
            if chart.artifact is None:
                continue
            try:
                export_result = await registry.execute(
                    "export_chart",
                    session=session,
                    chart_data=chart.artifact,
                    file_format=export_format,
                    filename=f"{chart.title.replace(' ', '_')}.{export_format}",
                )
                if export_result and export_result.artifact:
                    exported.append(
                        {
                            "chart_type": chart.chart_type,
                            "title": chart.title,
                            "file_path": export_result.artifact.get("file_path"),
                            "format": export_format,
                        }
                    )
            except Exception:
                pass

        return exported

    def _generate_interpretation(
        self, result: VisualizationResult, data_profile: dict[str, Any]
    ) -> str:
        """生成可视化报告。"""
        lines = [
            "## 可视化报告",
            "",
            f"共生成 **{len(result.charts)}** 个图表：",
            "",
        ]

        # 分布图表
        if result.distribution_charts:
            lines.extend(
                [
                    "### 分布图表",
                    *[f"- **{c.title}** ({c.chart_type})" for c in result.distribution_charts],
                    "",
                ]
            )

        # 关系图表
        if result.relationship_charts:
            lines.extend(
                [
                    "### 关系图表",
                    *[f"- **{c.title}** ({c.chart_type})" for c in result.relationship_charts],
                    "",
                ]
            )

        # 组合图表
        if result.composition_charts:
            lines.extend(
                [
                    "### 组合图表",
                    *[f"- **{c.title}** ({c.chart_type})" for c in result.composition_charts],
                    "",
                ]
            )

        # 导出文件
        if result.exported_files:
            lines.extend(
                [
                    "### 导出文件",
                    *[f"- {f['file_path']}" for f in result.exported_files],
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
