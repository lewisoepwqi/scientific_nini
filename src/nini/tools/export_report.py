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

# 匹配报告中的图片 src：支持旧 /api/artifacts 与新版 /api/workspace/.../files 路径。
_IMG_SRC_PATTERN = re.compile(
    r'(<img\s[^>]*?src=)(["\'])(/api/(?:artifacts/[^"\']+|workspace/[^"\']+/files/[^"\']+))(\2)'
)


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


def _plain_text_to_html(text: str, title: str) -> str:
    """将纯文本包装为可导出的 HTML。"""
    escaped = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    body_html = "<pre>" + escaped + "</pre>"
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


def _normalize_html_document(html_text: str, title: str) -> str:
    """将 HTML 片段规范成完整文档。"""
    if "<html" in html_text.lower():
        return html_text
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
        f"<body>\n{html_text}\n</body>\n"
        "</html>"
    )


def _title_from_document_content(content: str, fallback: str) -> str:
    """从文档内容提取标题。"""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip() or fallback
    return fallback


def _document_to_export_payload(source_path: Path) -> tuple[str, str, str]:
    """读取文档并返回 (raw_text, title, html)。"""
    ext = source_path.suffix.lower()
    raw_text = source_path.read_text(encoding="utf-8")
    fallback_title = source_path.stem or "分析文档"
    title = _title_from_document_content(raw_text, fallback_title)

    if ext in {".md", ".markdown"}:
        return raw_text, title, _md_to_html(raw_text, title)
    if ext in {".txt"}:
        return raw_text, title, _plain_text_to_html(raw_text, title)
    if ext in {".html", ".htm"}:
        return raw_text, title, _normalize_html_document(raw_text, title)
    raise ValueError(f"暂不支持导出此文档类型: {ext or source_path.name}")


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
    workspace_dir = settings.sessions_dir / session_id / "workspace"
    artifacts_root = artifacts_dir.resolve()
    workspace_root = workspace_dir.resolve()
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
        # 从 URL 提取工作区文件路径。
        url_path = urlsplit(src_url).path
        parts = url_path.strip("/").split("/")
        if len(parts) < 4:
            return match.group(0)
        decoded_name = ""
        file_path: Path
        if len(parts) >= 4 and parts[0] == "api" and parts[1] == "artifacts":
            encoded_name = "/".join(parts[3:])  # 支持子路径
            decoded_name = unquote(encoded_name).lstrip("/")
            file_path = (artifacts_dir / decoded_name).resolve()
        elif len(parts) >= 5 and parts[0] == "api" and parts[1] == "workspace" and parts[3] == "files":
            encoded_name = "/".join(parts[4:])
            decoded_name = unquote(encoded_name).lstrip("/")
            file_path = (workspace_dir / decoded_name).resolve()
        else:
            return match.group(0)
        is_plotly_json = decoded_name.lower().endswith(".plotly.json")
        if is_plotly_json:
            stats["plotly_total"] = int(stats.get("plotly_total", 0)) + 1

        # 安全兜底：防止构造路径逃逸到工作区外
        try:
            if url_path.startswith("/api/artifacts/"):
                file_path.relative_to(artifacts_root)
            else:
                file_path.relative_to(workspace_root)
        except ValueError:
            if is_plotly_json:
                stats["plotly_failed"].append(
                    {"name": decoded_name, "error": "图表路径非法，超出工作区目录"}
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


def _default_export_directory(source_path: str) -> str:
    """为导出文件选择默认目录。"""
    rel_path = source_path.strip().strip("/")
    if rel_path.startswith("artifacts/"):
        return "notes/exports"
    parent = str(Path(rel_path).parent)
    return "." if parent in {"", "."} else parent


def _workspace_relative_path_for_candidate(
    manager: WorkspaceManager,
    session_id: str,
    candidate: Path,
) -> str | None:
    """尽量将绝对文件路径映射回工作区相对路径。"""
    try:
        resolved = candidate.resolve()
    except Exception:
        return None

    rel_path = manager._relative_workspace_path(resolved)
    if rel_path:
        return rel_path

    workspace_root = (settings.sessions_dir / session_id / "workspace").resolve()
    try:
        return resolved.relative_to(workspace_root).as_posix()
    except Exception:
        return None


def _resolve_document_source(
    session: Session,
    *,
    source_ref: str | None = None,
    prefer_latest_report: bool = False,
) -> tuple[dict[str, Any] | None, str | None]:
    """定位可导出的工作区文档。"""
    manager = WorkspaceManager(session.id)

    if isinstance(source_ref, str) and source_ref.strip():
        matched = manager.resolve_document_file(source_ref)
        if matched is not None:
            return matched, None

        storage = ArtifactStorage(session.id)
        candidate = storage.get_path(source_ref.strip())
        if candidate.exists():
            rel_path = _workspace_relative_path_for_candidate(manager, session.id, candidate)
            if rel_path:
                matched = manager.resolve_document_file(rel_path)
                if matched is not None:
                    return matched, None
                if candidate.suffix.lower() in {".md", ".txt", ".html", ".htm"}:
                    return {
                        "name": candidate.name,
                        "kind": "document",
                        "path": rel_path,
                        "download_url": manager.build_workspace_file_download_url(rel_path),
                        "meta": {"subtype": "report"},
                    }, None
        return None, f"文档 `{source_ref}` 不存在，或当前不是可导出的文档文件。"

    if prefer_latest_report:
        latest_report = getattr(session, "documents", {}).get("latest_report")
        if isinstance(latest_report, dict):
            path = str(latest_report.get("path", "")).strip()
            if path:
                matched = manager.resolve_document_file(path)
                if matched is not None:
                    return matched, None

    latest_document = getattr(session, "documents", {}).get("latest_document")
    if isinstance(latest_document, dict):
        path = str(latest_document.get("path", "")).strip()
        if path:
            matched = manager.resolve_document_file(path)
            if matched is not None:
                return matched, None

    latest_report = session.artifacts.get("latest_report")
    if isinstance(latest_report, dict):
        report_ref = str(latest_report.get("path") or latest_report.get("name") or "").strip()
        if report_ref:
            matched = manager.resolve_document_file(report_ref)
            if matched is not None:
                return matched, None
            candidate = Path(report_ref)
            if not candidate.is_absolute():
                candidate = ArtifactStorage(session.id).get_path(Path(report_ref).name)
            if candidate.exists():
                rel_path = _workspace_relative_path_for_candidate(manager, session.id, candidate)
                if rel_path and candidate.suffix.lower() in {".md", ".txt", ".html", ".htm"}:
                    return {
                        "name": candidate.name,
                        "kind": "document",
                        "path": rel_path,
                        "download_url": manager.build_workspace_file_download_url(rel_path),
                        "meta": {"subtype": "report"},
                    }, None

    subtype_filter = {"report"} if prefer_latest_report else None
    latest = manager.latest_document_file(subtypes=subtype_filter)
    if latest is not None:
        return latest, None

    return None, "当前会话没有可导出的文档，请先生成或创建 Markdown/文本文件。"


def _build_export_relative_path(
    manager: WorkspaceManager,
    *,
    source_path: str,
    output_format: str,
    filename: str | None = None,
) -> str:
    """为导出文件生成不冲突的工作区相对路径。"""
    source_rel = source_path.strip().strip("/")
    source_name = Path(source_rel).stem or "analysis_document"
    if isinstance(filename, str) and filename.strip():
        raw_name = filename.strip()
    else:
        raw_name = source_name

    safe_name = manager.sanitize_filename(raw_name, default_name=f"{source_name}.{output_format}")
    if not safe_name.lower().endswith(f".{output_format}"):
        safe_name += f".{output_format}"

    target_dir = _default_export_directory(source_rel)
    candidate = safe_name
    stem = Path(safe_name).stem or source_name
    suffix = Path(safe_name).suffix or f".{output_format}"
    counter = 2

    while True:
        rel_path = candidate if target_dir == "." else f"{target_dir}/{candidate}"
        target = manager.resolve_workspace_path(rel_path, allow_missing=True)
        if not target.exists():
            return rel_path
        candidate = f"{stem}_{counter}{suffix}"
        counter += 1


async def export_workspace_document(
    session: Session,
    *,
    source_ref: str | None,
    output_format: str,
    filename: str | None = None,
    prefer_latest_report: bool = False,
) -> SkillResult:
    """将工作区文档导出为 PDF 或 DOCX。"""
    fmt = output_format.strip().lower()
    if fmt not in {"pdf", "docx"}:
        return SkillResult(success=False, message=f"不支持的导出格式: {output_format}")

    source_file, error_message = _resolve_document_source(
        session,
        source_ref=source_ref,
        prefer_latest_report=prefer_latest_report,
    )
    if source_file is None:
        return SkillResult(success=False, message=error_message or "未找到可导出的文档")

    manager = WorkspaceManager(session.id)
    source_path = str(source_file.get("path", "")).strip()
    if not source_path:
        return SkillResult(success=False, message="文档路径缺失，无法导出。")

    source_abs_path = manager.resolve_workspace_path(source_path, allow_missing=False)

    try:
        raw_text, title, html = _document_to_export_payload(source_abs_path)
    except ValueError as exc:
        return SkillResult(success=False, message=str(exc))
    except FileNotFoundError:
        return SkillResult(success=False, message=f"文档 `{source_path}` 不存在。")

    if fmt == "pdf":
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
                        "检测到文档包含 `.plotly.json` 图表，但当前环境缺少 Chrome，"
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
                    "文档中的 `.plotly.json` 图表转换失败，已中止导出以避免 PDF 退化为文本。\n"
                    f"失败图表：{failed_names or '未知'}\n"
                    "请先检查图表文件有效性或运行 `nini doctor` 后重试。"
                ),
            )
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
        try:
            output_bytes: bytes = await asyncio.to_thread(
                weasyprint.HTML(string=html).write_pdf,  # type: ignore[union-attr]
            )
        except Exception as exc:
            logger.error("PDF 生成失败: %s", exc, exc_info=True)
            return SkillResult(success=False, message=f"PDF 生成失败: {exc}")
    else:
        try:
            from nini.tools.report_exporter import export_report as export_markdown_report

            output_bytes = await asyncio.to_thread(
                export_markdown_report,
                raw_text,
                "docx",
                title,
            )
        except ImportError as exc:
            return SkillResult(success=False, message=f"DOCX 导出依赖缺失: {exc}")
        except Exception as exc:
            logger.error("DOCX 生成失败: %s", exc, exc_info=True)
            return SkillResult(success=False, message=f"DOCX 生成失败: {exc}")

    output_relative_path = _build_export_relative_path(
        manager,
        source_path=source_path,
        output_format=fmt,
        filename=filename,
    )
    output_path = manager.resolve_workspace_path(output_relative_path, allow_missing=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(output_bytes)
    manager.sync_text_document_record(output_relative_path)

    subtype = "pdf_export" if fmt == "pdf" else "docx_export"
    document = manager.resolve_document_file(output_relative_path)
    download_url = (
        str(document.get("download_url"))
        if isinstance(document, dict)
        else manager.build_workspace_file_download_url(output_relative_path)
    )
    artifact = {
        "name": output_path.name,
        "type": subtype,
        "format": fmt,
        "path": str(output_path),
        "download_url": download_url,
        "kind": "document",
        "source_path": source_path,
    }

    if not hasattr(session, "documents") or not isinstance(session.documents, dict):
        session.documents = {}
    session.documents["latest_document"] = {
        "name": output_path.name,
        "path": output_relative_path,
        "type": subtype,
        "download_url": download_url,
    }
    session.artifacts["latest_export"] = artifact

    return SkillResult(
        success=True,
        message=f"文档已导出为 {fmt.upper()}: `{output_path.name}`",
        data={
            "filename": output_path.name,
            "format": fmt,
            "source_path": source_path,
            "output_path": output_relative_path,
            "document_type": subtype,
        },
        artifacts=[artifact],
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
            "将分析报告或兼容的工作区 Markdown 文档导出为 PDF 文件。"
            "优先兼容 generate_report 生成的报告，也支持按文件名或路径导出已有文档。"
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
        result = await export_workspace_document(
            session,
            source_ref=str(report_name).strip() if isinstance(report_name, str) else None,
            output_format="pdf",
            filename=str(filename).strip() if isinstance(filename, str) else None,
            prefer_latest_report=True,
        )
        if result.success and isinstance(result.data, dict):
            source_path = str(result.data.get("source_path", "")).strip()
            result.data["source_report"] = source_path or (
                str(report_name).strip() if isinstance(report_name, str) else ""
            )
        elif not result.success and "可导出的文档" in result.message:
            result.message = "当前会话没有已生成的报告，请先调用 generate_report 生成报告。"
        return result
