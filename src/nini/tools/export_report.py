"""报告导出技能：Markdown → PDF。"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from nini.agent.session import Session
from nini.config import settings
from nini.memory.storage import ArtifactStorage
from nini.tools.base import Skill, SkillResult
from nini.utils.chart_fonts import CJK_FONT_FAMILY, apply_plotly_cjk_font_fallback
from nini.workspace import WorkspaceManager

logger = logging.getLogger(__name__)

# A4 科研论文风格 CSS
_PDF_CSS_TEMPLATE = """\
{font_face}
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

# 匹配报告中的图片 src：/api/artifacts/{session_id}/filename（支持单双引号）
_IMG_SRC_PATTERN = re.compile(r'(<img\s[^>]*?src=)(["\'])(/api/artifacts/[^"\']+)(\2)')


def _build_pdf_font_css() -> tuple[str, str]:
    """构建 PDF 导出的字体 CSS 与字体链。"""
    fallback_font = settings.data_dir / "fonts" / "NotoSansCJKsc-Regular.otf"
    if not fallback_font.exists():
        return "", CJK_FONT_FAMILY

    # 显式声明本地 CJK 字体，避免系统未安装中文字体时出现方框。
    font_uri = fallback_font.resolve().as_uri()
    font_face_css = (
        "@font-face {\n"
        "    font-family: 'Nini CJK';\n"
        f"    src: url('{font_uri}') format('opentype');\n"
        "    font-weight: normal;\n"
        "    font-style: normal;\n"
        "}\n"
    )
    return font_face_css, "'Nini CJK', " + CJK_FONT_FAMILY


def _md_to_html(md_text: str, title: str) -> str:
    """将 Markdown 转换为完整的 HTML 文档。"""
    import markdown as md_lib

    body_html = md_lib.markdown(
        md_text,
        extensions=["tables", "fenced_code", "toc"],
        output_format="html",
    )
    font_face_css, font_family = _build_pdf_font_css()
    css = _PDF_CSS_TEMPLATE.format(font_face=font_face_css, font_family=font_family)
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


def _normalize_plotly_figure_payload(chart_data: Any) -> dict[str, Any] | None:
    """归一化 Plotly JSON 载荷，兼容 {figure, config, schema_version} 包装格式。"""
    if not isinstance(chart_data, dict):
        return None

    figure: Any = chart_data.get("figure")
    candidate = figure if isinstance(figure, dict) else chart_data
    if not isinstance(candidate, dict):
        return None

    normalized: dict[str, Any] = {}
    data = candidate.get("data")
    layout = candidate.get("layout")
    frames = candidate.get("frames")
    if isinstance(data, list):
        normalized["data"] = data
    if isinstance(layout, dict):
        normalized["layout"] = layout
    if isinstance(frames, list):
        normalized["frames"] = frames

    return normalized or None


def _plotly_json_to_png_bytes(json_path: Path) -> tuple[bytes | None, str | None]:
    """将 Plotly JSON 文件转换为 PNG 字节。失败时返回错误原因。"""
    try:
        import plotly.graph_objects as go

        raw_chart_data = json.loads(json_path.read_text(encoding="utf-8"))
        chart_data = _normalize_plotly_figure_payload(raw_chart_data)
        if chart_data is None:
            logger.debug("Plotly JSON 结构无法识别 (%s)", json_path.name)
            return None, "Plotly JSON 结构无法识别"
        fig = go.Figure(chart_data)
        apply_plotly_cjk_font_fallback(fig)
        png_data: bytes = fig.to_image(format="png", width=1400, height=900, scale=2)  # type: ignore[assignment]
        return png_data, None
    except Exception as exc:
        logger.debug("Plotly PNG 转换失败 (%s): %s", json_path.name, exc)
        error_text = str(exc).strip() or exc.__class__.__name__
        return None, error_text


def _resolve_images_to_base64(html: str, session_id: str) -> str:
    """将 HTML 中的 /api/artifacts/ 图片引用替换为 base64 内联数据。"""
    resolved_html, _ = _resolve_images_to_base64_with_stats(html, session_id)
    return resolved_html


def _resolve_images_to_base64_with_stats(
    html: str,
    session_id: str,
) -> tuple[str, dict[str, Any]]:
    """将 HTML 中的 /api/artifacts/ 图片内联，并返回转换统计。"""
    artifacts_dir = settings.sessions_dir / session_id / "workspace" / "artifacts"
    artifacts_root = artifacts_dir.resolve()
    stats: dict[str, Any] = {
        "plotly_total": 0,
        "plotly_converted": 0,
        "plotly_failed": [],
    }

    def _replace_match(match: re.Match[str]) -> str:
        prefix, quote, src_url, suffix = (
            match.group(1),
            match.group(2),
            match.group(3),
            match.group(4),
        )
        # 从 URL 提取文件名：/api/artifacts/{session_id}/{filename}
        url_path = urlsplit(src_url).path
        parts = url_path.strip("/").split("/")
        if len(parts) < 4:
            return match.group(0)
        encoded_name = "/".join(parts[3:])  # 支持子路径
        decoded_name = unquote(encoded_name).lstrip("/")
        file_path = (artifacts_dir / decoded_name).resolve()
        is_plotly_json = decoded_name.lower().endswith(".plotly.json")
        if is_plotly_json:
            stats["plotly_total"] = int(stats.get("plotly_total", 0)) + 1

        # 安全兜底：防止构造路径逃逸到 artifacts 目录外
        try:
            file_path.relative_to(artifacts_root)
        except ValueError:
            if is_plotly_json:
                stats["plotly_failed"].append(
                    {"name": decoded_name, "error": "图表路径非法，超出 artifacts 目录"}
                )
            return match.group(0)

        if not file_path.exists():
            if is_plotly_json:
                stats["plotly_failed"].append({"name": decoded_name, "error": "图表文件不存在"})
            return match.group(0)

        try:
            if is_plotly_json:
                png_data, error_text = _plotly_json_to_png_bytes(file_path)
                if png_data is None:
                    stats["plotly_failed"].append(
                        {
                            "name": decoded_name,
                            "error": error_text or "Plotly 转 PNG 失败",
                        }
                    )
                    return match.group(0)
                b64 = base64.b64encode(png_data).decode("ascii")
                stats["plotly_converted"] = int(stats.get("plotly_converted", 0)) + 1
                return f"{prefix}{quote}data:image/png;base64,{b64}{suffix}"

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
            return f"{prefix}{quote}data:{mime};base64,{b64}{suffix}"
        except Exception as exc:
            logger.debug("图片 base64 转换失败 (%s): %s", decoded_name, exc)
            return match.group(0)

    return _IMG_SRC_PATTERN.sub(_replace_match, html), stats


def _is_chrome_missing_error(error_text: str | None) -> bool:
    if not error_text:
        return False
    normalized = error_text.lower()
    return (
        "requires google chrome" in normalized
        or "kaleido requires google chrome" in normalized
        or ("chrome" in normalized and "not found" in normalized)
    )


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
            "依赖可选包 weasyprint（源码环境: pip install -e .[dev] 或 pip install -e .[pdf]；发布包环境: pip install nini[pdf]）。"
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
        html, image_stats = _resolve_images_to_base64_with_stats(html, session.id)
        plotly_failed = image_stats.get("plotly_failed", [])
        if isinstance(plotly_failed, list) and plotly_failed:
            failed_items = [
                item for item in plotly_failed if isinstance(item, dict) and item.get("name")
            ]
            failed_names = "、".join(str(item["name"]) for item in failed_items[:3])
            if len(failed_items) > 3:
                failed_names += " 等"
            has_chrome_missing = any(
                _is_chrome_missing_error(str(item.get("error", ""))) for item in failed_items
            )
            if has_chrome_missing:
                return SkillResult(
                    success=False,
                    message=(
                        "检测到报告包含 `.plotly.json` 图表，但当前环境缺少 Chrome，"
                        "无法转换为 PDF 可嵌入图片。\n"
                        "请先在当前 Python 环境安装 Chrome 后重试：\n"
                        "- `plotly_get_chrome -y`\n"
                        '- 或 `python -c "import plotly.io as pio; pio.get_chrome()"`\n'
                        f"失败图表：{failed_names or '未知'}"
                    ),
                )
            return SkillResult(
                success=False,
                message=(
                    "报告中的 `.plotly.json` 图表转换失败，已中止导出以避免 PDF 退化为文本。\n"
                    f"失败图表：{failed_names or '未知'}\n"
                    "请先检查图表文件有效性或运行 `nini doctor` 后重试。"
                ),
            )

        # 4. HTML → PDF（weasyprint 懒导入）
        try:
            import weasyprint  # type: ignore[import-not-found,import-untyped]
        except ImportError:
            return SkillResult(
                success=False,
                message=(
                    "PDF 导出需要 weasyprint 库，当前未安装。\n"
                    "请执行以下命令之一安装后重试：\n"
                    "- `pip install -e .[dev]`（源码开发环境，推荐）\n"
                    "- `pip install -e .[pdf]`（源码开发环境，仅补装 PDF）\n"
                    "- `pip install nini[pdf]`（已发布包环境）"
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
