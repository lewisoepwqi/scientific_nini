"""可视化技能：支持 Plotly / Matplotlib 双渲染。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.utils import PlotlyJSONEncoder

from nini.agent.session import Session
from nini.charts import build_style_spec, normalize_render_engine
from nini.charts.renderers import (
    apply_matplotlib_axes_style,
    apply_plotly_style,
)
from nini.memory.storage import ArtifactStorage
from nini.skills.base import Skill, SkillResult
from nini.skills.templates.journal_styles import get_template_names
from nini.workspace import WorkspaceManager


def _to_plotly_json(fig: go.Figure) -> dict[str, Any]:
    """将 Figure 转换为 JSON 可序列化字典。"""
    payload = json.loads(json.dumps(fig, cls=PlotlyJSONEncoder))
    return cast(dict[str, Any], payload) if isinstance(payload, dict) else {}


def _assert_columns(df: pd.DataFrame, *columns: str | None) -> None:
    """校验列名存在性。"""
    for col in columns:
        if col and col not in df.columns:
            raise ValueError(f"列 '{col}' 不存在")


def _prepare_line_dataframe(df: pd.DataFrame, x_col: str) -> pd.DataFrame:
    """为折线图准备可排序的数据，兼容混合类型时间列。"""
    plot_df = df.copy()

    # 常规路径：直接按 x 排序
    try:
        return plot_df.sort_values(by=x_col, kind="mergesort")
    except TypeError:
        pass

    # 回退路径 1：优先尝试将 x 列整体解析为 datetime
    coerced = pd.to_datetime(plot_df[x_col], errors="coerce")
    non_null = int(plot_df[x_col].notna().sum())
    parsed_non_null = int(coerced.notna().sum())
    if non_null > 0 and (parsed_non_null / non_null) >= 0.8:
        return plot_df.assign(**{x_col: coerced}).sort_values(by=x_col, kind="mergesort")

    # 回退路径 2：按字符串排序，确保不会因类型不一致崩溃
    sort_key = plot_df[x_col].map(lambda v: "" if pd.isna(v) else str(v))
    return (
        plot_df.assign(__x_sort_key=sort_key)
        .sort_values(by="__x_sort_key", kind="mergesort")
        .drop(columns=["__x_sort_key"])
    )


class CreateChartSkill(Skill):
    """生成科研图表。"""

    _chart_types = ["scatter", "line", "bar", "box", "violin", "histogram", "heatmap"]
    _journal_styles = get_template_names()
    _render_engines = ["auto", "plotly", "matplotlib"]

    @property
    def name(self) -> str:
        return "create_chart"

    @property
    def category(self) -> str:
        return "visualization"

    @property
    def description(self) -> str:
        return (
            "快速创建简单标准图表。支持 scatter/line/bar/box/violin/histogram/heatmap，"
            "支持 default/nature/science/cell/nejm/lancet 风格。"
            "如需复杂自定义图表、子图布局、统计标注等，请使用 run_code。"
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
                "render_engine": {
                    "type": "string",
                    "enum": self._render_engines,
                    "default": "auto",
                    "description": "渲染引擎：auto|plotly|matplotlib",
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
        render_engine = normalize_render_engine(str(kwargs.get("render_engine", "auto")))
        resolved_engine = "plotly" if render_engine == "auto" else render_engine

        df = session.datasets.get(dataset_name)
        if df is None:
            return SkillResult(success=False, message=f"数据集 '{dataset_name}' 不存在")
        if chart_type not in self._chart_types:
            return SkillResult(success=False, message=f"不支持的图表类型: {chart_type}")
        if journal_style not in self._journal_styles:
            journal_style = "default"

        try:
            style_spec = build_style_spec(journal_style)
            plotly_fig = self._create_plotly_figure(df, chart_type, kwargs, list(style_spec.colors))
            apply_plotly_style(plotly_fig, style_spec, title)
            chart_data = _to_plotly_json(plotly_fig)
            # 保存最近一次图表，供 export_chart 等技能复用
            session.artifacts["latest_chart"] = {
                "chart_data": chart_data,
                "chart_type": chart_type,
                "journal_style": style_spec.style_key,
                "dataset_name": dataset_name,
                "title": title,
                "render_engine": resolved_engine,
                "style_key": style_spec.style_key,
            }

            ws = WorkspaceManager(session.id)
            storage = ArtifactStorage(session.id)
            # 默认保持兼容：先保存 plotly json 产物
            if title and title.strip():
                base_name = ws.sanitize_filename(
                    f"{title.strip()}.plotly.json",
                    default_name="chart.plotly.json",
                )
            else:
                ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
                base_name = ws.sanitize_filename(
                    f"{chart_type}_{ts}.plotly.json",
                    default_name="chart.plotly.json",
                )
            output_name = base_name
            stem = Path(base_name).stem or "chart"
            suffix = Path(base_name).suffix or ".json"
            counter = 2
            while storage.get_path(output_name).exists():
                output_name = f"{stem}_{counter}{suffix}"
                counter += 1
            path = storage.save_text(
                json.dumps(chart_data, ensure_ascii=False),
                output_name,
            )
            ws.add_artifact_record(
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
                "render_engine": "plotly",
                "style_key": style_spec.style_key,
            }
            artifacts: list[dict[str, Any]] = [artifact]

            # matplotlib 模式额外导出发表级文件，保证双实现方式可用
            if resolved_engine == "matplotlib":
                matplot_base = Path(output_name).stem.replace(".plotly", "") or "chart"
                matplotlib_artifacts = self._save_matplotlib_artifacts(
                    session=session,
                    storage=storage,
                    ws=ws,
                    df=df,
                    chart_type=chart_type,
                    kwargs=kwargs,
                    title=title,
                    base_name=matplot_base,
                    style_spec=style_spec,
                )
                artifacts.extend(matplotlib_artifacts)

            message = (
                f"已生成 {chart_type} 图（{style_spec.style_key} 风格，{resolved_engine} 渲染）"
            )
            return SkillResult(
                success=True,
                message=message,
                data={
                    "chart_type": chart_type,
                    "journal_style": style_spec.style_key,
                    "dataset_name": dataset_name,
                    "render_engine": resolved_engine,
                },
                has_chart=True,
                chart_data=chart_data,
                artifacts=artifacts,
            )
        except ValueError as exc:
            return SkillResult(success=False, message=str(exc))
        except Exception as exc:
            return SkillResult(success=False, message=f"图表生成失败: {exc}")

    def _create_plotly_figure(
        self,
        df: pd.DataFrame,
        chart_type: str,
        kwargs: dict[str, Any],
        palette: list[str],
    ) -> go.Figure:
        x_col = kwargs.get("x_column")
        y_col = kwargs.get("y_column")
        group_col = kwargs.get("group_column")
        color_col = kwargs.get("color_column")

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
            plot_df = _prepare_line_dataframe(df, x_col)
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

    def _save_matplotlib_artifacts(
        self,
        *,
        session: Session,
        storage: ArtifactStorage,
        ws: WorkspaceManager,
        df: pd.DataFrame,
        chart_type: str,
        kwargs: dict[str, Any],
        title: str | None,
        base_name: str,
        style_spec: Any,
    ) -> list[dict[str, Any]]:
        """保存 Matplotlib 多格式产物。"""
        import matplotlib.pyplot as plt

        fig = self._create_matplotlib_figure(
            df=df,
            chart_type=chart_type,
            kwargs=kwargs,
            title=title,
            style_spec=style_spec,
        )
        artifacts: list[dict[str, Any]] = []
        export_formats = [fmt for fmt in style_spec.export_formats if fmt in {"pdf", "svg", "png"}]
        if not export_formats:
            export_formats = ["pdf", "svg", "png"]
        for fmt in export_formats:
            filename = f"{base_name}.{fmt}"
            path = storage.get_path(filename)
            save_kwargs: dict[str, Any] = {
                "bbox_inches": "tight",
                "pad_inches": 0.05,
                "facecolor": "white",
                "format": fmt,
            }
            if fmt == "png":
                save_kwargs["dpi"] = style_spec.dpi
            fig.savefig(path, **save_kwargs)
            ws.add_artifact_record(
                name=filename,
                artifact_type="chart",
                file_path=path,
                format_hint=fmt,
            )
            artifacts.append(
                {
                    "name": filename,
                    "type": "chart",
                    "format": fmt,
                    "path": str(path),
                    "download_url": f"/api/artifacts/{session.id}/{filename}",
                    "render_engine": "matplotlib",
                    "style_key": style_spec.style_key,
                }
            )
        plt.close(fig)
        return artifacts

    def _create_matplotlib_figure(
        self,
        *,
        df: pd.DataFrame,
        chart_type: str,
        kwargs: dict[str, Any],
        title: str | None,
        style_spec: Any,
    ) -> Any:
        """按统一风格契约生成 Matplotlib 图表。"""
        import matplotlib.pyplot as plt
        import numpy as np

        x_col = kwargs.get("x_column")
        y_col = kwargs.get("y_column")
        group_col = kwargs.get("group_column")
        color_col = kwargs.get("color_column")
        palette = list(style_spec.colors)

        fig, ax = plt.subplots(figsize=style_spec.figure_size)
        plt.rcParams["font.family"] = "sans-serif"
        plt.rcParams["font.sans-serif"] = [
            part.strip() for part in style_spec.font_family.split(",")
        ]
        plt.rcParams["font.size"] = style_spec.font_size

        if chart_type == "scatter":
            _assert_columns(df, x_col, y_col, color_col)
            if not x_col or not y_col:
                raise ValueError("scatter 需要 x_column 和 y_column")
            if color_col:
                for idx, (label, part) in enumerate(df.groupby(color_col, dropna=False)):
                    ax.scatter(
                        part[x_col],
                        part[y_col],
                        s=20,
                        alpha=0.9,
                        label=str(label),
                        color=palette[idx % len(palette)],
                    )
                ax.legend(frameon=False)
            else:
                ax.scatter(df[x_col], df[y_col], s=20, alpha=0.9, color=palette[0])
            ax.set_xlabel(str(x_col))
            ax.set_ylabel(str(y_col))

        elif chart_type == "line":
            _assert_columns(df, x_col, y_col, color_col)
            if not x_col or not y_col:
                raise ValueError("line 需要 x_column 和 y_column")
            plot_df = _prepare_line_dataframe(df, x_col)
            if color_col:
                for idx, (label, part) in enumerate(plot_df.groupby(color_col, dropna=False)):
                    ax.plot(
                        part[x_col],
                        part[y_col],
                        marker="o",
                        linewidth=style_spec.line_width,
                        markersize=4,
                        label=str(label),
                        color=palette[idx % len(palette)],
                    )
                ax.legend(frameon=False)
            else:
                ax.plot(
                    plot_df[x_col],
                    plot_df[y_col],
                    marker="o",
                    linewidth=style_spec.line_width,
                    markersize=4,
                    color=palette[0],
                )
            ax.set_xlabel(str(x_col))
            ax.set_ylabel(str(y_col))

        elif chart_type == "bar":
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
                if group_col:
                    pivot = grouped.pivot(index=x_col, columns=group_col, values=y_col).fillna(0)
                    x = np.arange(len(pivot.index))
                    groups = list(pivot.columns)
                    width = 0.8 / max(1, len(groups))
                    for idx, label in enumerate(groups):
                        offset = (idx - (len(groups) - 1) / 2.0) * width
                        ax.bar(
                            x + offset,
                            pivot[label].values,
                            width=width,
                            color=palette[idx % len(palette)],
                            label=str(label),
                        )
                    ax.set_xticks(x)
                    ax.set_xticklabels([str(v) for v in pivot.index.tolist()])
                    ax.legend(frameon=False)
                else:
                    ax.bar(
                        grouped[x_col].astype(str),
                        grouped[y_col],
                        color=palette[0],
                    )
                ax.set_ylabel(str(y_col))
            else:
                count_df = (
                    df[x_col].dropna().value_counts().rename_axis(x_col).reset_index(name="count")
                )
                ax.bar(count_df[x_col].astype(str), count_df["count"], color=palette[0])
                ax.set_ylabel("count")
            ax.set_xlabel(str(x_col))

        elif chart_type == "box":
            _assert_columns(df, x_col, y_col, group_col)
            value_col = y_col or x_col
            category_col = group_col if group_col else (x_col if x_col != value_col else None)
            if not value_col:
                raise ValueError("box 需要 y_column 或 x_column 作为数值列")
            if category_col:
                grouped_values = [
                    part[value_col].dropna().to_list()
                    for _, part in df.groupby(category_col, dropna=False)
                ]
                labels = [str(label) for label, _ in df.groupby(category_col, dropna=False)]
                bp = ax.boxplot(grouped_values, patch_artist=True, tick_labels=labels)
                for idx, patch in enumerate(bp["boxes"]):
                    patch.set_facecolor(palette[idx % len(palette)])
                    patch.set_alpha(0.8)
            else:
                bp = ax.boxplot(
                    [df[value_col].dropna().to_list()],
                    patch_artist=True,
                    tick_labels=[value_col],
                )
                bp["boxes"][0].set_facecolor(palette[0])
            ax.set_ylabel(str(value_col))
            ax.set_xlabel(str(category_col or "group"))

        elif chart_type == "violin":
            _assert_columns(df, x_col, y_col, group_col)
            value_col = y_col or x_col
            category_col = group_col if group_col else (x_col if x_col != value_col else None)
            if not value_col:
                raise ValueError("violin 需要 y_column 或 x_column 作为数值列")
            if category_col:
                grouped_values = [
                    part[value_col].dropna().to_list()
                    for _, part in df.groupby(category_col, dropna=False)
                ]
                labels = [str(label) for label, _ in df.groupby(category_col, dropna=False)]
                positions = list(range(1, len(grouped_values) + 1))
                vp = ax.violinplot(
                    grouped_values, positions=positions, showmeans=False, showextrema=True
                )
                bodies = cast(list[Any], vp["bodies"])
                for idx, body in enumerate(bodies):
                    body.set_facecolor(palette[idx % len(palette)])
                    body.set_alpha(0.7)
                ax.set_xticks(positions)
                ax.set_xticklabels(labels)
            else:
                vp = ax.violinplot(
                    [df[value_col].dropna().to_list()], showmeans=False, showextrema=True
                )
                bodies = cast(list[Any], vp["bodies"])
                for body in bodies:
                    body.set_facecolor(palette[0])
                    body.set_alpha(0.7)
                ax.set_xticks([1])
                ax.set_xticklabels([value_col])
            ax.set_ylabel(str(value_col))
            ax.set_xlabel(str(category_col or "group"))

        elif chart_type == "histogram":
            _assert_columns(df, x_col, color_col)
            if not x_col:
                raise ValueError("histogram 需要 x_column")
            bins = int(kwargs.get("bins", 20))
            if color_col:
                for idx, (label, part) in enumerate(df.groupby(color_col, dropna=False)):
                    ax.hist(
                        part[x_col].dropna(),
                        bins=bins,
                        alpha=0.55,
                        label=str(label),
                        color=palette[idx % len(palette)],
                    )
                ax.legend(frameon=False)
            else:
                ax.hist(df[x_col].dropna(), bins=bins, color=palette[0], alpha=0.85)
            ax.set_xlabel(str(x_col))
            ax.set_ylabel("frequency")

        elif chart_type == "heatmap":
            columns = kwargs.get("columns") or []
            if not columns:
                columns = df.select_dtypes(include="number").columns.tolist()[:20]
            if len(columns) < 2:
                raise ValueError("heatmap 至少需要两列数值列")
            _assert_columns(df, *columns)
            corr = df[columns].corr(numeric_only=True)
            im = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1)
            ax.set_xticks(range(len(columns)))
            ax.set_yticks(range(len(columns)))
            ax.set_xticklabels(columns, rotation=45, ha="right")
            ax.set_yticklabels(columns)
            fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        else:
            raise ValueError(f"不支持的图表类型: {chart_type}")

        if title:
            ax.set_title(str(title))
        apply_matplotlib_axes_style(ax, style_spec)
        fig.tight_layout()
        return fig
