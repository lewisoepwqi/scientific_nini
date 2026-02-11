"""图表导出技能。"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import plotly.graph_objects as go

from nini.agent.session import Session
from nini.config import settings
from nini.memory.storage import ArtifactStorage
from nini.skills.base import Skill, SkillResult
from nini.utils.chart_fonts import apply_plotly_cjk_font_fallback
from nini.workspace import WorkspaceManager

logger = logging.getLogger(__name__)

# 需要 kaleido + Chrome 的格式
_KALEIDO_FORMATS = {"png", "jpeg", "svg"}


class ExportChartSkill(Skill):
    """导出最近生成的图表。"""

    _formats = ["png", "jpeg", "svg", "html", "json"]

    @property
    def name(self) -> str:
        return "export_chart"

    @property
    def category(self) -> str:
        return "export"

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
        apply_plotly_cjk_font_fallback(fig)
        base = self._build_filename(filename, latest)
        full_name = f"{base}.{fmt}"

        storage = ArtifactStorage(session.id)
        path = storage.get_path(full_name)

        if fmt == "html":
            fig.write_html(str(path))
        elif fmt == "json":
            path.write_text(fig.to_json(), encoding="utf-8")
        elif fmt in _KALEIDO_FORMATS:
            # kaleido 图片导出：在线程池中执行并施加超时保护
            export_timeout = settings.sandbox_image_export_timeout
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(
                        fig.write_image,
                        str(path),
                        width=width,
                        height=height,
                        scale=scale,
                        format=fmt,
                    ),
                    timeout=export_timeout,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "图片导出超时（%ds），格式=%s，尺寸=%dx%d scale=%.1f",
                    export_timeout,
                    fmt,
                    width,
                    height,
                    scale,
                )
                # 降级策略：尝试更小的尺寸/scale
                fallback_result = await self._try_fallback_export(fig, path, fmt, export_timeout)
                if fallback_result is not None:
                    logger.info("图片导出降级成功（降低分辨率）")
                else:
                    # 最终降级：自动切换到 HTML 格式
                    fallback_fmt = "html"
                    full_name = f"{base}.{fallback_fmt}"
                    path = storage.get_path(full_name)
                    fig.write_html(str(path))
                    fmt = fallback_fmt
                    logger.info("图片导出超时，已自动降级为 HTML 格式")
                    return self._build_result(
                        session,
                        storage,
                        fig,
                        fmt,
                        full_name,
                        path,
                        fallback_message=(
                            f"⚠️ {kwargs.get('format', 'png').upper()} 导出超时"
                            f"（>{export_timeout}s），已自动降级为 HTML 格式。\n"
                            "提示：可运行 `nini doctor` 检查 kaleido/Chrome 状态，"
                            "或选择 html/json 格式避免超时。"
                        ),
                    )
            except Exception as exc:
                logger.warning("图片导出失败: %s", exc)
                # 导出失败时降级到 HTML
                fallback_fmt = "html"
                full_name = f"{base}.{fallback_fmt}"
                path = storage.get_path(full_name)
                fig.write_html(str(path))
                fmt = fallback_fmt
                return self._build_result(
                    session,
                    storage,
                    fig,
                    fmt,
                    full_name,
                    path,
                    fallback_message=(
                        f"⚠️ 图片导出失败: {exc}\n"
                        "已自动降级为 HTML 格式。"
                        "PNG/SVG/JPEG 导出需要 kaleido 和 Chrome 浏览器。\n"
                        "请运行 `nini doctor` 查看详情，"
                        '或执行 `python -c "import kaleido; kaleido.get_chrome_sync()"` 安装 Chrome。'
                    ),
                )

        return self._build_result(session, storage, fig, fmt, full_name, path)

    async def _try_fallback_export(
        self,
        fig: go.Figure,
        path: Any,
        fmt: str,
        timeout: int,
    ) -> bool | None:
        """降级尝试：使用更小的尺寸导出图片。"""
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(
                    fig.write_image,
                    str(path),
                    width=800,
                    height=600,
                    scale=1,
                    format=fmt,
                ),
                timeout=timeout,
            )
        except Exception:
            return None

    def _build_result(
        self,
        session: Session,
        storage: ArtifactStorage,
        fig: go.Figure,
        fmt: str,
        full_name: str,
        path: Any,
        fallback_message: str | None = None,
    ) -> SkillResult:
        """构建统一的导出结果。"""
        artifact = {
            "name": full_name,
            "type": "chart",
            "format": fmt,
            "path": str(path),
            "download_url": f"/api/artifacts/{session.id}/{full_name}",
        }
        WorkspaceManager(session.id).add_artifact_record(
            name=full_name,
            artifact_type="chart",
            file_path=path,
            format_hint=fmt,
        )
        session.artifacts["latest_export"] = artifact

        message = fallback_message or f"图表已导出为 `{full_name}`"
        return SkillResult(
            success=True,
            message=message,
            data={"format": fmt, "filename": full_name},
            artifacts=[artifact],
        )

    def _build_filename(self, filename: Any, latest_chart: dict[str, Any]) -> str:
        if isinstance(filename, str) and filename.strip():
            return filename.strip()
        chart_type = str(latest_chart.get("chart_type", "chart"))
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"{chart_type}_{ts}"
