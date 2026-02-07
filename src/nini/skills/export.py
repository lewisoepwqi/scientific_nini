"""图表导出技能。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import plotly.graph_objects as go

from nini.agent.session import Session
from nini.memory.storage import ArtifactStorage
from nini.skills.base import Skill, SkillResult


class ExportChartSkill(Skill):
    """导出最近生成的图表。"""

    _formats = ["png", "jpeg", "svg", "html", "json"]

    @property
    def name(self) -> str:
        return "export_chart"

    @property
    def description(self) -> str:
        return "将最近生成的图表导出为 PNG/JPEG/SVG/HTML/JSON 文件。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "enum": self._formats,
                    "default": "png",
                    "description": "导出格式",
                },
                "filename": {
                    "type": "string",
                    "description": "可选，不含扩展名的文件名",
                },
                "width": {"type": "integer", "default": 1200},
                "height": {"type": "integer", "default": 800},
                "scale": {"type": "number", "default": 2.0},
            },
            "required": [],
        }

    @property
    def is_idempotent(self) -> bool:
        return False

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        fmt = str(kwargs.get("format", "png")).lower().strip()
        filename = kwargs.get("filename")
        width = int(kwargs.get("width", 1200))
        height = int(kwargs.get("height", 800))
        scale = float(kwargs.get("scale", 2.0))

        if fmt not in self._formats:
            return SkillResult(success=False, message=f"不支持的导出格式: {fmt}")

        latest = session.artifacts.get("latest_chart")
        if not isinstance(latest, dict) or "chart_data" not in latest:
            return SkillResult(
                success=False, message="当前会话没有可导出的图表，请先调用 create_chart"
            )

        chart_data = latest.get("chart_data")
        if not isinstance(chart_data, dict):
            return SkillResult(success=False, message="图表数据无效，无法导出")

        fig = go.Figure(chart_data)
        base = self._build_filename(filename, latest)
        full_name = f"{base}.{fmt}"

        storage = ArtifactStorage(session.id)
        path = storage.get_path(full_name)

        if fmt == "html":
            fig.write_html(str(path))
        elif fmt == "json":
            path.write_text(fig.to_json(), encoding="utf-8")
        else:
            fig.write_image(
                str(path),
                width=width,
                height=height,
                scale=scale,
                format=fmt,
            )

        artifact = {
            "name": full_name,
            "type": "chart",
            "format": fmt,
            "path": str(path),
            "download_url": f"/api/artifacts/{session.id}/{full_name}",
        }
        session.artifacts["latest_export"] = artifact

        return SkillResult(
            success=True,
            message=f"图表已导出为 `{full_name}`",
            data={"format": fmt, "filename": full_name},
            artifacts=[artifact],
        )

    def _build_filename(self, filename: Any, latest_chart: dict[str, Any]) -> str:
        if isinstance(filename, str) and filename.strip():
            return filename.strip()
        chart_type = str(latest_chart.get("chart_type", "chart"))
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"{chart_type}_{ts}"
