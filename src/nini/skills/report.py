"""分析报告生成技能。"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import pandas as pd

from nini.agent.session import Session
from nini.memory.storage import ArtifactStorage
from nini.skills.base import Skill, SkillResult
from nini.workspace import WorkspaceManager


def _dataset_overview(session: Session, dataset_names: list[str] | None = None) -> str:
    targets = dataset_names or list(session.datasets.keys())
    if not targets:
        return "当前会话无已加载数据集。"

    lines: list[str] = []
    for name in targets:
        df = session.datasets.get(name)
        if df is None:
            continue
        numeric_cols = df.select_dtypes(include="number").columns.tolist()
        missing_total = int(df.isna().sum().sum())
        lines.append(
            f"- **{name}**: {len(df)} 行 × {len(df.columns)} 列，"
            f"数值列 {len(numeric_cols)}，缺失值总计 {missing_total}"
        )
    return "\n".join(lines) if lines else "目标数据集不存在。"


_NOISE_PATTERNS = (
    "stdout:",
    "stderr:",
    "kaleido",
    "chromium",
    "chrome",
    "timed out",
    "超时",
    "traceback",
    "error installing",
    "npm warn",
    "deprecationwarning",
)


def _collect_chart_artifacts(session_id: str, max_items: int = 12) -> list[dict[str, str]]:
    """收集会话图表产物（去重，按时间倒序）。"""
    manager = WorkspaceManager(session_id)
    artifacts = manager.list_artifacts()
    results: list[dict[str, str]] = []
    seen_names: set[str] = set()

    for item in artifacts:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue

        name_lower = name.lower()
        artifact_type = str(item.get("type", "")).lower()
        fmt_hint = str(item.get("format", "")).lower().strip()
        ext = Path(name).suffix.lower().lstrip(".")
        fmt = fmt_hint or ext or "unknown"
        is_chart = artifact_type == "chart" or name_lower.endswith(".plotly.json")
        if not is_chart:
            continue

        dedupe_key = name_lower
        if dedupe_key in seen_names:
            continue
        seen_names.add(dedupe_key)

        url = str(item.get("download_url", "")).strip() or f"/api/artifacts/{session_id}/{name}"
        results.append(
            {
                "name": name,
                "format": fmt,
                "download_url": url,
            }
        )
        if len(results) >= max_items:
            break

    return results


def _chart_artifacts_markdown(session_id: str) -> str:
    """生成图表清单 Markdown。"""
    charts = _collect_chart_artifacts(session_id)
    if not charts:
        return ""

    lines = [
        "| 图表文件 | 格式 | 链接 |",
        "|---|---|---|",
    ]
    for chart in charts:
        name = chart["name"]
        fmt = chart["format"].upper()
        url = chart["download_url"]
        lines.append(f"| `{name}` | {fmt} | [查看/下载]({url}) |")
    lines.append("")
    lines.append("注：`PLOTLY.JSON/JSON` 可在工作区预览或下载后继续复用。")
    return "\n".join(lines)


def _chart_preview_markdown(session_id: str) -> str:
    """生成图表预览 Markdown。"""
    charts = _collect_chart_artifacts(session_id)
    if not charts:
        return ""

    lines: list[str] = []
    for idx, chart in enumerate(charts, 1):
        name = chart["name"]
        fmt = chart["format"].lower()
        url = chart["download_url"]
        suffix = Path(name).suffix.lower()

        lines.append(f"### 图 {idx}：{name}")
        # 统一使用 Markdown 图片语法：图片文件直接显示；
        # .plotly.json 由前端自定义渲染器转为交互图。
        if suffix in {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}:
            lines.append(f"![{name}]({url})")
        elif name.lower().endswith(".plotly.json") or fmt == "json":
            lines.append(f"![{name}]({url})")
            lines.append(f"[下载图表数据]({url})")
        elif suffix in {".html", ".htm"} or fmt in {"html", "htm"}:
            lines.append(f"[打开交互图表（HTML）]({url})")
        else:
            lines.append(f"[查看图表文件]({url})")
        lines.append("")
    return "\n".join(lines).strip()


def _is_noise(text: str) -> bool:
    """判断文本是否为技术噪声（不应出现在报告中）。"""
    lower = text.lower()
    return any(p in lower for p in _NOISE_PATTERNS)


def _recent_findings(messages: list[dict[str, Any]], max_items: int = 12) -> str:
    """从工具执行结果中提取有意义的分析发现，过滤噪声。"""
    findings: list[str] = []
    for msg in reversed(messages):
        role = msg.get("role")
        if role != "tool":
            continue

        content = msg.get("content")
        parsed = None
        if isinstance(content, str):
            try:
                parsed = json.loads(content)
            except Exception:
                parsed = None

        if isinstance(parsed, dict):
            # 跳过失败的工具执行
            if parsed.get("success") is False or parsed.get("error"):
                continue
            message = parsed.get("message")
            if isinstance(message, str) and message.strip() and not _is_noise(message):
                truncated = message.strip()[:120]
                findings.append(f"- {truncated}")
        # 非 JSON 格式的原始输出不再提取，避免 DataFrame dump 等噪声

        if len(findings) >= max_items:
            break

    if not findings:
        return ""
    findings.reverse()
    return "\n".join(findings)


def _build_markdown(
    session: Session,
    *,
    title: str,
    dataset_names: list[str] | None,
    summary_text: str,
    methods: str,
    conclusions: str,
    include_recent_messages: bool,
    include_charts: bool,
) -> str:
    """构建结构化 Markdown 报告。无内容的 section 自动跳过。"""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sections = [
        f"# {title}",
        "",
        f"> 会话 ID: `{session.id}` | 生成时间: {now}",
        "",
        "## 数据集概览",
        _dataset_overview(session, dataset_names),
    ]

    # 分析方法（可选）
    if methods and methods.strip():
        sections.extend(["", "## 分析方法", methods.strip()])

    # 分析摘要
    if summary_text and summary_text.strip():
        sections.extend(["", "## 分析摘要", summary_text.strip()])

    # 图表清单（可选）
    if include_charts:
        chart_preview_md = _chart_preview_markdown(session.id)
        if chart_preview_md:
            sections.extend(["", "## 图表预览", chart_preview_md])
        chart_md = _chart_artifacts_markdown(session.id)
        if chart_md:
            sections.extend(["", "## 图表清单", chart_md])

    # 关键发现（从工具结果提取，过滤噪声）
    if include_recent_messages:
        findings = _recent_findings(session.messages)
        if findings:
            sections.extend(["", "## 关键发现", findings])

    # 结论与建议（可选）
    if conclusions and conclusions.strip():
        sections.extend(["", "## 结论与建议", conclusions.strip()])

    return "\n".join(sections).strip() + "\n"


def _resolve_output_name(
    session: Session,
    storage: ArtifactStorage,
    *,
    filename: Any,
) -> str:
    """解析并去重报告文件名，避免覆盖历史报告。"""
    manager = WorkspaceManager(session.id)

    if isinstance(filename, str) and filename.strip():
        raw_name = filename.strip()
    else:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        raw_name = f"analysis_report_{ts}.md"

    if not raw_name.endswith(".md"):
        raw_name += ".md"

    safe_name = manager.sanitize_filename(raw_name, default_name="analysis_report.md")
    if not safe_name.lower().endswith(".md"):
        safe_name += ".md"

    candidate = safe_name
    stem = Path(safe_name).stem or "analysis_report"
    suffix = Path(safe_name).suffix or ".md"
    counter = 2
    while storage.get_path(candidate).exists():
        candidate = f"{stem}_{counter}{suffix}"
        counter += 1
    return candidate


class GenerateReportSkill(Skill):
    """生成 Markdown 分析报告并保存为产物。"""

    @property
    def name(self) -> str:
        return "generate_report"

    @property
    def category(self) -> str:
        return "export"

    @property
    def description(self) -> str:
        return (
            "生成结构化 Markdown 分析报告。请传入详细的 methods（使用了哪些统计方法及选择理由）、"
            "summary_text（核心结果摘要）和 conclusions（结论与下一步建议），"
            "工具会自动从执行历史中提取关键发现。报告保存为会话产物并同步写入知识记忆。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string", "default": "科研数据分析报告"},
                "summary_text": {
                    "type": "string",
                    "description": "分析结果的核心摘要，包含关键统计量、p值、效应量等",
                },
                "methods": {
                    "type": "string",
                    "description": "分析方法说明：使用了哪些统计方法、为何选择、前提假设是否满足",
                },
                "conclusions": {
                    "type": "string",
                    "description": "结论与建议：基于结果的解释、局限性、下一步建议",
                },
                "dataset_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "可选。仅包含这些数据集",
                },
                "include_recent_messages": {
                    "type": "boolean",
                    "default": True,
                    "description": "是否附带近期工具分析结论",
                },
                "include_charts": {
                    "type": "boolean",
                    "default": True,
                    "description": "是否在报告中附加图表清单（从工作空间图表产物自动提取）",
                },
                "save_to_knowledge": {
                    "type": "boolean",
                    "default": True,
                    "description": "是否写入 knowledge.md",
                },
                "filename": {
                    "type": "string",
                    "description": "可选。产物文件名（.md）",
                },
            },
            "required": [],
        }

    @property
    def is_idempotent(self) -> bool:
        return False

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        title = str(kwargs.get("title", "科研数据分析报告")).strip() or "科研数据分析报告"
        summary_text = str(kwargs.get("summary_text", "") or "")
        methods = str(kwargs.get("methods", "") or "")
        conclusions = str(kwargs.get("conclusions", "") or "")
        dataset_names = kwargs.get("dataset_names") or None
        include_recent_messages = bool(kwargs.get("include_recent_messages", True))
        include_charts = bool(kwargs.get("include_charts", True))
        save_to_knowledge = bool(kwargs.get("save_to_knowledge", True))
        filename = kwargs.get("filename")

        markdown = _build_markdown(
            session,
            title=title,
            dataset_names=dataset_names,
            summary_text=summary_text,
            methods=methods,
            conclusions=conclusions,
            include_recent_messages=include_recent_messages,
            include_charts=include_charts,
        )

        storage = ArtifactStorage(session.id)
        output_name = _resolve_output_name(
            session,
            storage,
            filename=filename,
        )
        path = storage.save_text(markdown, output_name)

        if save_to_knowledge:
            session.knowledge_memory.append(title, markdown)

        artifact = {
            "name": output_name,
            "type": "report",
            "path": str(path),
            "download_url": f"/api/artifacts/{session.id}/{output_name}",
        }
        WorkspaceManager(session.id).add_artifact_record(
            name=output_name,
            artifact_type="report",
            file_path=path,
            format_hint="md",
        )
        session.artifacts["latest_report"] = artifact

        return SkillResult(
            success=True,
            message=f"报告已生成并保存为 `{output_name}`",
            data={
                "title": title,
                "filename": output_name,
                "report_markdown": markdown,
            },
            artifacts=[artifact],
        )
