"""可视化技能：生成 Plotly 图表。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.utils import PlotlyJSONEncoder

from nini.agent.session import Session
from nini.memory.storage import ArtifactStorage
from nini.skills.base import Skill, SkillResult
from nini.skills.templates import get_template
from nini.workspace import WorkspaceManager

JOURNAL_PALETTES: dict[str, list[str]] = {
    "nature": ["#E64B35", "#4DBBD5", "#00A087", "#3C5488", "#F39B7F", "#8491B4"],
    "science": ["#1F77B4", "#FF7F0E", "#2CA02C", "#D62728", "#9467BD", "#8C564B"],
    "cell": ["#E41A1C", "#377EB8", "#4DAF4A", "#984EA3", "#FF7F00", "#FFFF33"],
    "nejm": ["#BC3C29", "#0072B5", "#E18727", "#20854E", "#7876B1", "#6F99AD"],
    "lancet": ["#00468B", "#ED0000", "#42B540", "#0099B4", "#925E9F", "#FDAF91"],
    "default": px.colors.qualitative.Plotly,
}


def _to_plotly_json(fig: go.Figure) -> dict[str, Any]:
    """将 Figure 转换为 JSON 可序列化字典。"""
    return json.loads(json.dumps(fig, cls=PlotlyJSONEncoder))


def _assert_columns(df: pd.DataFrame, *columns: str | None) -> None:
    """校验列名存在性。"""
    for col in columns:
        if col and col not in df.columns:
            raise ValueError(f"列 '{col}' 不存在")


def _apply_style(fig: go.Figure, journal_style: str, title: str | None) -> None:
    """统一应用期刊风格布局。"""
    template = get_template(journal_style)
    fig.update_layout(
        title=title,
        font={
            "family": template["font"],
            "size": template["font_size"],
            "color": "#111827",
        },
        paper_bgcolor="white",
        plot_bgcolor="white",
        legend={"title": None},
        margin={"l": 56, "r": 24, "t": 56, "b": 48},
    )
    fig.update_xaxes(showgrid=True, gridcolor="#E5E7EB", zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor="#E5E7EB", zeroline=False)


class CreateChartSkill(Skill):
    """生成科研图表。"""

    _chart_types = ["scatter", "line", "bar", "box", "violin", "histogram", "heatmap"]
    _journal_styles = ["default", "nature", "science", "cell", "nejm", "lancet"]

    @property
    def name(self) -> str:
        return "create_chart"

    @property
    def description(self) -> str:
        return (
            "创建图表并返回 Plotly JSON。"
            "支持 scatter/line/bar/box/violin/histogram/heatmap，"
            "支持 default/nature/science/cell/nejm/lancet 风格。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "dataset_name": {"type": "string", "description": "数据集名称"},
                "chart_type": {
                    "type": "string",
                    "enum": self._chart_types,
                    "description": "图表类型",
                },
                "x_column": {"type": "string", "description": "X 轴列名"},
                "y_column": {"type": "string", "description": "Y 轴列名"},
                "group_column": {"type": "string", "description": "分组列名"},
                "color_column": {"type": "string", "description": "颜色映射列名"},
                "columns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "热力图列集合（仅 heatmap）",
                },
                "title": {"type": "string", "description": "图表标题"},
                "journal_style": {
                    "type": "string",
                    "enum": self._journal_styles,
                    "default": "default",
                    "description": "期刊风格",
                },
                "bins": {
                    "type": "integer",
                    "default": 20,
                    "description": "直方图分箱数量（仅 histogram）",
                },
            },
            "required": ["dataset_name", "chart_type"],
        }

    @property
    def is_idempotent(self) -> bool:
        return False

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        dataset_name = kwargs["dataset_name"]
        chart_type = str(kwargs["chart_type"]).lower().strip()
        title = kwargs.get("title")
        journal_style = str(kwargs.get("journal_style", "default")).lower().strip()

        df = session.datasets.get(dataset_name)
        if df is None:
            return SkillResult(success=False, message=f"数据集 '{dataset_name}' 不存在")
        if chart_type not in self._chart_types:
            return SkillResult(success=False, message=f"不支持的图表类型: {chart_type}")
        if journal_style not in self._journal_styles:
            journal_style = "default"

        try:
            fig = self._create_figure(df, chart_type, kwargs)
            _apply_style(fig, journal_style, title)
            chart_data = _to_plotly_json(fig)
            # 保存最近一次图表，供 export_chart 等技能复用
            session.artifacts["latest_chart"] = {
                "chart_data": chart_data,
                "chart_type": chart_type,
                "journal_style": journal_style,
                "dataset_name": dataset_name,
                "title": title,
            }

            # 自动保存图表 JSON 到工作空间，便于会话成果管理与复用
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            output_name = WorkspaceManager(session.id).sanitize_filename(
                f"{chart_type}_{ts}.plotly.json",
                default_name="chart.plotly.json",
            )
            storage = ArtifactStorage(session.id)
            path = storage.save_text(
                json.dumps(chart_data, ensure_ascii=False),
                output_name,
            )
            WorkspaceManager(session.id).add_artifact_record(
                name=output_name,
                artifact_type="chart",
                file_path=path,
                format_hint="json",
            )
            artifact = {
                "name": output_name,
                "type": "chart",
                "format": "json",
                "path": str(path),
                "download_url": f"/api/artifacts/{session.id}/{output_name}",
            }

            message = f"已生成 {chart_type} 图（{journal_style} 风格）"
            return SkillResult(
                success=True,
                message=message,
                data={
                    "chart_type": chart_type,
                    "journal_style": journal_style,
                    "dataset_name": dataset_name,
                },
                has_chart=True,
                chart_data=chart_data,
                artifacts=[artifact],
            )
        except ValueError as exc:
            return SkillResult(success=False, message=str(exc))
        except Exception as exc:
            return SkillResult(success=False, message=f"图表生成失败: {exc}")

    def _create_figure(
        self, df: pd.DataFrame, chart_type: str, kwargs: dict[str, Any]
    ) -> go.Figure:
        x_col = kwargs.get("x_column")
        y_col = kwargs.get("y_column")
        group_col = kwargs.get("group_column")
        color_col = kwargs.get("color_column")
        palette = JOURNAL_PALETTES.get(
            str(kwargs.get("journal_style", "default")).lower(), JOURNAL_PALETTES["default"]
        )

        if chart_type == "scatter":
            _assert_columns(df, x_col, y_col, color_col)
            if not x_col or not y_col:
                raise ValueError("scatter 需要 x_column 和 y_column")
            return px.scatter(
                df, x=x_col, y=y_col, color=color_col, color_discrete_sequence=palette
            )

        if chart_type == "line":
            _assert_columns(df, x_col, y_col, color_col)
            if not x_col or not y_col:
                raise ValueError("line 需要 x_column 和 y_column")
            plot_df = df.sort_values(by=x_col)
            return px.line(
                plot_df, x=x_col, y=y_col, color=color_col, color_discrete_sequence=palette
            )

        if chart_type == "bar":
            _assert_columns(df, x_col, y_col, group_col)
            if not x_col:
                raise ValueError("bar 需要 x_column")
            if y_col:
                group_keys = [x_col] + ([group_col] if group_col else [])
                grouped = (
                    df[group_keys + [y_col]]
                    .dropna()
                    .groupby(group_keys, as_index=False)[y_col]
                    .mean()
                )
                return px.bar(
                    grouped,
                    x=x_col,
                    y=y_col,
                    color=group_col,
                    barmode="group",
                    color_discrete_sequence=palette,
                )
            count_df = (
                df[x_col].dropna().value_counts().rename_axis(x_col).reset_index(name="count")
            )
            return px.bar(count_df, x=x_col, y="count", color_discrete_sequence=palette)

        if chart_type == "box":
            _assert_columns(df, x_col, y_col, group_col)
            value_col = y_col or x_col
            category_col = group_col if group_col else (x_col if x_col != value_col else None)
            if not value_col:
                raise ValueError("box 需要 y_column 或 x_column 作为数值列")
            return px.box(
                df,
                x=category_col,
                y=value_col,
                points="all",
                color=group_col,
                color_discrete_sequence=palette,
            )

        if chart_type == "violin":
            _assert_columns(df, x_col, y_col, group_col)
            value_col = y_col or x_col
            category_col = group_col if group_col else (x_col if x_col != value_col else None)
            if not value_col:
                raise ValueError("violin 需要 y_column 或 x_column 作为数值列")
            return px.violin(
                df,
                x=category_col,
                y=value_col,
                box=True,
                points=False,
                color=group_col,
                color_discrete_sequence=palette,
            )

        if chart_type == "histogram":
            _assert_columns(df, x_col, color_col)
            if not x_col:
                raise ValueError("histogram 需要 x_column")
            nbins = int(kwargs.get("bins", 20))
            return px.histogram(
                df, x=x_col, color=color_col, nbins=nbins, color_discrete_sequence=palette
            )

        if chart_type == "heatmap":
            columns = kwargs.get("columns") or []
            if not columns:
                columns = df.select_dtypes(include="number").columns.tolist()[:20]
            if len(columns) < 2:
                raise ValueError("heatmap 至少需要两列数值列")
            _assert_columns(df, *columns)
            corr = df[columns].corr(numeric_only=True)
            return px.imshow(
                corr,
                text_auto=".2f",
                color_continuous_scale="RdBu",
                zmin=-1,
                zmax=1,
            )

        raise ValueError(f"不支持的图表类型: {chart_type}")
