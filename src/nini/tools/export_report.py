"""报告导出技能：Markdown → PDF。"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
from pathlib import Path
from typing import Any

from nini.agent.session import Session
from nini.config import settings
from nini.memory.storage import ArtifactStorage
from nini.tools.base import Skill, SkillResult
from nini.utils.chart_fonts import CJK_FONT_FAMILY, apply_plotly_cjk_font_fallback
from nini.workspace import WorkspaceManager

logger = logging.getLogger(__name__)

# A4 科研论文风格 CSS
_PDF_CSS_TEMPLATE = """\
@page {{
    size: A4;
    margin: 2cm;
}}
body {{
    font-family: {font_family}, sans-serif;
    font-size: 11pt;
    line-height: 1.6;
    color: #333;
}}
h1 {{
    font-size: 18pt;
    border-bottom: 2px solid #333;
    padding-bottom: 4pt;
    margin-top: 0;
}}
h2 {{
    font-size: 15pt;
    border-bottom: 1px solid #999;
    padding-bottom: 3pt;
}}
h3 {{
    font-size: 13pt;
}}
blockquote {{
    border-left: 3px solid #ccc;
    padding-left: 12px;
    color: #666;
    margin-left: 0;
}}
table {{
    border-collapse: collapse;
    width: 100%;
    margin: 1em 0;
    page-break-inside: auto;
}}
td, th {{
    border: 1px solid #ddd;
    padding: 6px 8px;
    text-align: left;
}}
th {{
    background-color: #f5f5f5;
    font-weight: bold;
}}
tr {{
    page-break-inside: avoid;
}}
img {{
    max-width: 100%;
    page-break-inside: avoid;
}}
pre {{
    background: #f8f8f8;
    border: 1px solid #e0e0e0;
    padding: 8px 12px;
    border-radius: 4px;
    font-size: 9pt;
    overflow-x: auto;
    white-space: pre-wrap;
    word-wrap: break-word;
}}
code {{
    font-size: 9pt;
    background: #f0f0f0;
    padding: 1px 4px;
    border-radius: 2px;
}}
"""

# 匹配报告中的图片 src：/api/artifacts/{session_id}/filename
_IMG_SRC_PATTERN = re.compile(r'(<img\s[^>]*?src=")(/api/artifacts/[^"]+)(")')


def _md_to_html(md_text: str, title: str) -> str:
    """将 Markdown 转换为完整的 HTML 文档。"""
    import markdown as md_lib

    body_html = md_lib.markdown(
        md_text,
        extensions=["tables", "fenced_code", "toc"],
        output_format="html",
    )
    css = _PDF_CSS_TEMPLATE.format(font_family=CJK_FONT_FAMILY)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="zh-CN">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        f"<title>{title}</title>\n"
        f"<style>{css}</style>\n"
        "</head>\n"
        f"<body>\n{body_html}\n</body>\n"
        "</html>"
    )


def _plotly_json_to_png_bytes(json_path: Path) -> bytes | None:
    """将 Plotly JSON 文件转换为 PNG 字节。失败返回 None。"""
    try:
        import plotly.graph_objects as go

        chart_data = json.loads(json_path.read_text(encoding="utf-8"))
        fig = go.Figure(chart_data)
        apply_plotly_cjk_font_fallback(fig)
        png_data: bytes = fig.to_image(format="png", width=1400, height=900, scale=2)  # type: ignore[assignment]
        return png_data
    except Exception as exc:
        logger.debug("Plotly PNG 转换失败 (%s): %s", json_path.name, exc)
        return None


def _resolve_images_to_base64(html: str, session_id: str) -> str:
    """将 HTML 中的 /api/artifacts/ 图片引用替换为 base64 内联数据。"""
    artifacts_dir = settings.sessions_dir / session_id / "workspace" / "artifacts"

    def _replace_match(match: re.Match[str]) -> str:
        prefix, src_url, suffix = match.group(1), match.group(2), match.group(3)
        # 从 URL 提取文件名：/api/artifacts/{session_id}/{filename}
        parts = src_url.strip("/").split("/")
        if len(parts) < 4:
            return match.group(0)
        filename = "/".join(parts[3:])  # 支持子路径
        file_path = artifacts_dir / filename

        if not file_path.exists():
            return match.group(0)

        try:
            if filename.lower().endswith(".plotly.json"):
                png_data = _plotly_json_to_png_bytes(file_path)
                if png_data is None:
                    return match.group(0)
                b64 = base64.b64encode(png_data).decode("ascii")
                return f"{prefix}data:image/png;base64,{b64}{suffix}"

            # 普通图片文件
            raw = file_path.read_bytes()
            ext = file_path.suffix.lower().lstrip(".")
            mime_map = {
                "png": "image/png",
                "jpg": "image/jpeg",
                "jpeg": "image/jpeg",
                "gif": "image/gif",
                "svg": "image/svg+xml",
                "webp": "image/webp",
            }
            mime = mime_map.get(ext, "application/octet-stream")
            b64 = base64.b64encode(raw).decode("ascii")
            return f"{prefix}data:{mime};base64,{b64}{suffix}"
        except Exception as exc:
            logger.debug("图片 base64 转换失败 (%s): %s", filename, exc)
            return match.group(0)

    return _IMG_SRC_PATTERN.sub(_replace_match, html)


class ExportReportSkill(Skill):
    """将 Markdown 报告导出为 PDF 文件。"""

    @property
    def name(self) -> str:
        return "export_report"

    @property
    def category(self) -> str:
        return "export"

    @property
    def description(self) -> str:
        return (
            "将已生成的 Markdown 分析报告导出为 PDF 文件。"
            "需要先调用 generate_report 生成报告，或指定 report_name 参数。"
            "依赖可选包 weasyprint（pip install nini[pdf]）。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "report_name": {
                    "type": "string",
                    "description": "要导出的报告文件名（.md）。不指定则使用最近生成的报告。",
                },
                "filename": {
                    "type": "string",
                    "description": "输出 PDF 文件名（不含扩展名）。不指定则自动从报告名生成。",
                },
            },
            "required": [],
        }

    @property
    def is_idempotent(self) -> bool:
        return False

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        report_name = kwargs.get("report_name")
        filename = kwargs.get("filename")

        # 1. 定位报告文件
        storage = ArtifactStorage(session.id)

        if not report_name:
            latest = session.artifacts.get("latest_report")
            if not isinstance(latest, dict) or "name" not in latest:
                return SkillResult(
                    success=False,
                    message="当前会话没有已生成的报告，请先调用 generate_report 生成报告。",
                )
            report_name = str(latest["name"])

        report_path = storage.get_path(report_name)
        if not report_path.exists():
            return SkillResult(
                success=False,
                message=f"报告文件 `{report_name}` 不存在。",
            )

        md_text = report_path.read_text(encoding="utf-8")
        if not md_text.strip():
            return SkillResult(success=False, message="报告内容为空，无法导出。")

        # 2. 提取标题
        title = "分析报告"
        for line in md_text.splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                title = stripped[2:].strip()
                break

        # 3. MD → HTML → 图片内联
        html = _md_to_html(md_text, title)
        html = _resolve_images_to_base64(html, session.id)

        # 4. HTML → PDF（weasyprint 懒导入）
        try:
            import weasyprint  # type: ignore[import-not-found,import-untyped]
        except ImportError:
            return SkillResult(
                success=False,
                message=(
                    "PDF 导出需要 weasyprint 库，当前未安装。\n"
                    "请执行 `pip install nini[pdf]` 安装后重试。"
                ),
            )

        # 生成输出文件名
        if isinstance(filename, str) and filename.strip():
            pdf_name = filename.strip()
        else:
            pdf_name = Path(report_name).stem
        if not pdf_name.lower().endswith(".pdf"):
            pdf_name += ".pdf"

        pdf_path = storage.get_path(pdf_name)

        try:
            pdf_bytes: bytes = await asyncio.to_thread(
                weasyprint.HTML(string=html).write_pdf,  # type: ignore[union-attr]
            )
            pdf_path.write_bytes(pdf_bytes)
        except Exception as exc:
            logger.error("PDF 生成失败: %s", exc, exc_info=True)
            return SkillResult(
                success=False,
                message=f"PDF 生成失败: {exc}",
            )

        # 5. 注册产物
        ws = WorkspaceManager(session.id)
        artifact = {
            "name": pdf_name,
            "type": "report",
            "format": "pdf",
            "path": str(pdf_path),
            "download_url": ws.build_artifact_download_url(pdf_name),
        }
        ws.add_artifact_record(
            name=pdf_name,
            artifact_type="report",
            file_path=pdf_path,
            format_hint="pdf",
        )
        session.artifacts["latest_export"] = artifact

        return SkillResult(
            success=True,
            message=f"报告已导出为 PDF: `{pdf_name}`",
            data={"filename": pdf_name, "source_report": report_name},
            artifacts=[artifact],
        )
