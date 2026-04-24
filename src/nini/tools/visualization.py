"""可视化技能：支持 Plotly / Matplotlib 双渲染。

实际绘图通过 code_templates 生成 Python 脚本并 exec 执行，
保证"代码档案中的代码"与"实际渲染产物"字节等价，无漂移。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import pandas as pd
import plotly.graph_objects as go
from plotly.utils import PlotlyJSONEncoder

from nini.agent.session import Session
from nini.charts import build_style_spec, normalize_render_engine
from nini.charts.code_templates import render_matplotlib_script, render_plotly_script
from nini.memory.storage import ArtifactStorage
from nini.tools.base import Tool, ToolResult
from nini.tools.templates.journal_styles import get_template_names
from nini.workspace import WorkspaceManager


def _to_plotly_json(fig: go.Figure) -> dict[str, Any]:
    """将 Figure 转换为 JSON 可序列化字典。"""
    payload = json.loads(json.dumps(fig, cls=PlotlyJSONEncoder))
    return cast(dict[str, Any], payload) if isinstance(payload, dict) else {}


def _exec_template(code: str, df: pd.DataFrame) -> Any:
    """在受控 namespace 中执行模板脚本，返回 namespace。"""
    namespace: dict[str, Any] = {"df": df}
    exec(compile(code, "<chart_template>", "exec"), namespace)
    return namespace


class CreateChartTool(Tool):
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

    async def execute(self, session: Session, **kwargs: Any) -> ToolResult:
        dataset_name = kwargs["dataset_name"]
        chart_type = str(kwargs["chart_type"]).lower().strip()
        title = kwargs.get("title")
        journal_style = str(kwargs.get("journal_style", "default")).lower().strip()
        render_engine = normalize_render_engine(str(kwargs.get("render_engine", "auto")))
        resolved_engine = "plotly" if render_engine == "auto" else render_engine

        df = session.datasets.get(dataset_name)
        if df is None:
            return ToolResult(success=False, message=f"数据集 '{dataset_name}' 不存在")
        if chart_type not in self._chart_types:
            return ToolResult(success=False, message=f"不支持的图表类型: {chart_type}")
        if journal_style not in self._journal_styles:
            journal_style = "default"

        try:
            style_spec = build_style_spec(journal_style)

            plotly_code = render_plotly_script(chart_type, kwargs, style_spec, title=title)
            plotly_ns = _exec_template(plotly_code, df)
            plotly_fig = plotly_ns["fig"]
            chart_data = _to_plotly_json(plotly_fig)

            ws = WorkspaceManager(session)
            storage = ArtifactStorage(session)
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
                "download_url": ws.build_artifact_file_download_url(output_name),
                "render_engine": "plotly",
                "style_key": style_spec.style_key,
            }
            artifacts: list[dict[str, Any]] = [artifact]

            # 保存最近一次图表：沙箱子 Agent 模式下存储 ArtifactRef，否则存储内容（供 export_chart 复用）
            if getattr(session, "workspace_root", None) is not None:
                from nini.agent.artifact_ref import ArtifactRef

                session.artifacts["latest_chart"] = ArtifactRef(
                    path=output_name,
                    type="chart",
                    summary=f"{chart_type} 图（{style_spec.style_key} 风格）",
                    agent_id="",
                )
            else:
                session.artifacts["latest_chart"] = {
                    "chart_data": chart_data,
                    "chart_type": chart_type,
                    "journal_style": style_spec.style_key,
                    "dataset_name": dataset_name,
                    "title": title,
                    "render_engine": resolved_engine,
                    "style_key": style_spec.style_key,
                }

            # matplotlib 模式额外导出发表级文件，保证双实现方式可用
            matplotlib_code: str | None = None
            if resolved_engine == "matplotlib":
                matplot_base = Path(output_name).stem.replace(".plotly", "") or "chart"
                mpl_code = render_matplotlib_script(
                    chart_type, kwargs, style_spec, title=title
                )
                matplotlib_code = mpl_code
                matplotlib_artifacts = self._save_matplotlib_artifacts(
                    storage=storage,
                    ws=ws,
                    df=df,
                    code=mpl_code,
                    base_name=matplot_base,
                    style_spec=style_spec,
                )
                artifacts.extend(matplotlib_artifacts)

            message = (
                f"已生成 {chart_type} 图（{style_spec.style_key} 风格，{resolved_engine} 渲染）"
            )
            # 生成的代码用于代码档案入库；chart_session 会把主引擎代码写入 save_code_execution。
            generated_code: dict[str, str] = {"plotly": plotly_code}
            if matplotlib_code is not None:
                generated_code["matplotlib"] = matplotlib_code
            return ToolResult(
                success=True,
                message=message,
                data={
                    "chart_type": chart_type,
                    "journal_style": style_spec.style_key,
                    "dataset_name": dataset_name,
                    "render_engine": resolved_engine,
                    "generated_code": generated_code,
                },
                has_chart=True,
                chart_data=chart_data,
                artifacts=artifacts,
            )
        except ValueError as exc:
            return ToolResult(success=False, message=str(exc))
        except Exception as exc:
            return ToolResult(success=False, message=f"图表生成失败: {exc}")

    def _save_matplotlib_artifacts(
        self,
        *,
        storage: ArtifactStorage,
        ws: WorkspaceManager,
        df: pd.DataFrame,
        code: str,
        base_name: str,
        style_spec: Any,
    ) -> list[dict[str, Any]]:
        """执行 matplotlib 模板并保存多格式产物。"""
        import matplotlib.pyplot as plt

        ns = _exec_template(code, df)
        fig = ns["fig"]
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
                    "download_url": ws.build_artifact_file_download_url(filename),
                    "render_engine": "matplotlib",
                    "style_key": style_spec.style_key,
                }
            )
        plt.close(fig)
        return artifacts
