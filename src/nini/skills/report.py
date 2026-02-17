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


def _sanitize_chinese_filename(title: str, max_bytes: int = 80) -> str:
    """
    将报告标题转换为安全的文件名。

    规则：
    - 移除文件系统禁止字符（<>:"/\\|?*）
    - 保留中文、英文、数字、下划线、连字符
    - 限制字节长度（UTF-8 编码）
    - 去除首尾空格和下划线

    示例：
        "血压与心率的相关性分析" -> "血压与心率的相关性分析"
        "Data Analysis: 2024" -> "Data_Analysis_2024"
        "文件名太长" * 20 -> "文件名太长..." (截断到max_bytes)
    """
    import re
    import unicodedata

    # 1. Unicode 规范化（NFC）
    normalized = unicodedata.normalize("NFC", title)

    # 2. 移除文件系统禁止字符，保留中文、字母、数字、下划线、连字符、空格
    safe = re.sub(r'[<>:"/\\|?*]+', "", normalized)
    safe = re.sub(r"\s+", "_", safe)  # 空格转下划线

    # 3. 字节长度限制（UTF-8）
    safe_bytes = safe.encode("utf-8")
    if len(safe_bytes) > max_bytes:
        # 逐字符截断到目标字节数
        truncated = ""
        for char in safe:
            test = (truncated + char).encode("utf-8")
            if len(test) > max_bytes:
                break
            truncated += char
        safe = truncated

    # 4. 清理首尾下划线
    return safe.strip("_") or "report"


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

# 已知内部技能名称，用于从报告文本中过滤工具提及
_KNOWN_SKILL_NAMES: set[str] = {
    "load_dataset",
    "preview_data",
    "data_summary",
    "clean_data",
    "recommend_cleaning_strategy",
    "evaluate_data_quality",
    "generate_quality_report",
    "create_chart",
    "export_chart",
    "run_code",
    "run_r_code",
    "generate_report",
    "organize_workspace",
    "save_workflow",
    "list_workflows",
    "apply_workflow",
    "fetch_url",
    "image_analysis",
    "interpret_statistical_result",
    "t_test",
    "anova",
    "correlation",
    "regression",
    "mann_whitney",
    "kruskal_wallis",
    "multiple_comparison_correction",
    "complete_comparison",
    "complete_anova",
    "correlation_analysis",
    "export_report",
}


def _strip_tool_mentions(text: str) -> str:
    """移除文本中对内部工具/技能名称的提及。

    匹配模式：
    - "使用 xxx 工具"、"调用 xxx 工具"、"通过 xxx 工具"
    - "使用 xxx 和 yyy 工具"（多工具连用）
    - 工具名出现在反引号中
    """
    import re

    if not text:
        return text

    # 构建工具名正则模式（按长度降序，避免短名称误匹配子串）
    sorted_names = sorted(_KNOWN_SKILL_NAMES, key=len, reverse=True)
    names_pattern = "|".join(re.escape(n) for n in sorted_names)

    # 匹配 "使用/调用/通过 tool_a (和/、/及 tool_b)* 工具/技能 (进行/来/做)? XXX"
    pattern = (
        r"(?:使用|调用|通过)\s*"
        r"`?(?:" + names_pattern + r")`?"
        r"(?:\s*(?:和|、|及|与|,)\s*`?(?:" + names_pattern + r")`?)*"
        r"\s*(?:工具|技能|skill)"
        r"(?:\s*(?:进行|来|做))?"
    )
    result = re.sub(pattern, "", text)

    # 移除反引号包裹的工具名单独出现的情况（如 "`data_summary`"）
    result = re.sub(r"`(?:" + names_pattern + r")`", "", result)

    # 清理多余空格和标点
    result = re.sub(r"[ \t]{2,}", " ", result)
    result = re.sub(r"^\s*[，,、]\s*", "", result, flags=re.MULTILINE)
    result = re.sub(r"\s+([，,。；;])", r"\1", result)

    return result.strip()


_PREVIEW_FORMAT_PRIORITY = {
    "png": 0,
    "jpg": 1,
    "jpeg": 1,
    "webp": 2,
    "svg": 3,
    "html": 4,
    "htm": 4,
    "json": 5,
    "pdf": 6,
}

_KEY_FINDING_TOOLS = {
    "correlation_analysis",
    "complete_anova",
    "complete_comparison",
    "t_test",
    "anova",
    "regression",
    "mann_whitney",
    "kruskal_wallis",
}


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


def _chart_group_key(name: str) -> str:
    """生成图表分组键，用于多格式去重。"""
    lower = name.lower()
    if lower.endswith(".plotly.json"):
        return lower[: -len(".plotly.json")]
    path = Path(lower)
    return str(path.with_suffix(""))


def _chart_format_priority(chart: dict[str, str]) -> int:
    name = chart.get("name", "")
    fmt = chart.get("format", "").lower()
    if name.lower().endswith(".plotly.json"):
        return _PREVIEW_FORMAT_PRIORITY.get("json", 99)
    return _PREVIEW_FORMAT_PRIORITY.get(fmt, 99)


def _select_preview_charts(charts: list[dict[str, str]]) -> list[dict[str, str]]:
    """按图表基名去重，选择单一主预览格式。"""
    groups: dict[str, list[dict[str, str]]] = {}
    order: list[str] = []
    for chart in charts:
        key = _chart_group_key(chart["name"])
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(chart)

    selected: list[dict[str, str]] = []
    for key in order:
        items = groups.get(key, [])
        if not items:
            continue
        primary = sorted(
            items,
            key=lambda item: (
                _chart_format_priority(item),
                item.get("name", ""),
            ),
        )[0]
        selected.append(primary)
    return selected


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
    charts = _select_preview_charts(_collect_chart_artifacts(session_id))
    if not charts:
        return ""

    lines: list[str] = []
    for idx, chart in enumerate(charts, 1):
        name = chart["name"]
        fmt = chart["format"].lower()
        url = chart["download_url"]
        suffix = Path(name).suffix.lower()

        # 友好标题：去掉文件扩展名和技术后缀
        friendly_name = name
        if friendly_name.lower().endswith(".plotly.json"):
            friendly_name = friendly_name[: -len(".plotly.json")]
        else:
            friendly_name = Path(friendly_name).stem
        lines.append(f"### 图 {idx}：{friendly_name}")

        # 统一使用 Markdown 图片语法：图片文件直接显示；
        # .plotly.json 由前端自定义渲染器转为交互图。
        if suffix in {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}:
            lines.append(f"![{friendly_name}]({url})")
        elif name.lower().endswith(".plotly.json") or fmt == "json":
            lines.append(f"![{friendly_name}]({url})")
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


def _safe_parse_json(content: Any) -> dict | None:
    """安全解析 JSON，失败返回 None。"""
    if isinstance(content, dict):
        return content
    if isinstance(content, str):
        try:
            parsed = json.loads(content.strip())
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _recent_findings(messages: list[dict[str, Any]], max_items: int = 12) -> str:
    """从结构化工具结果提取关键发现，避免噪声与中间步骤污染。"""
    findings: list[str] = []
    seen: set[tuple[str, str]] = set()

    for msg in reversed(messages):
        if msg.get("role") != "tool":
            continue

        if msg.get("status") and msg.get("status") != "success":
            continue

        parsed = _safe_parse_json(msg.get("content"))
        if not isinstance(parsed, dict):
            continue
        if parsed.get("success") is False:
            continue

        tool_name = str(msg.get("tool_name") or "").strip().lower()
        if not tool_name:
            # 历史消息兼容：仅做最小推断
            message_preview = str(parsed.get("message", "")).lower()
            if "相关性分析" in message_preview or "pearson" in message_preview:
                tool_name = "correlation_analysis"

        if tool_name not in _KEY_FINDING_TOOLS:
            continue

        message = str(parsed.get("message", "")).strip()
        if not message or _is_noise(message):
            continue

        item = (tool_name, message[:150])
        if item in seen:
            continue
        seen.add(item)
        findings.append(f"- {message[:150]}")

        if len(findings) >= max_items:
            break

    if not findings:
        return ""
    return "\n".join(["### 统计与模型发现"] + findings)


def _session_statistics(session: Session) -> str:
    """生成会话性能统计信息。"""
    messages = session.messages

    # 统计各类消息数量
    user_messages = sum(1 for m in messages if m.get("role") == "user")
    assistant_messages = sum(1 for m in messages if m.get("role") == "assistant")
    tool_messages = sum(1 for m in messages if m.get("role") == "tool")

    # 统计工具调用次数
    tool_calls_count = 0
    tool_names: dict[str, int] = {}
    for m in messages:
        if m.get("role") == "assistant" and m.get("tool_calls"):
            for tc in m.get("tool_calls", []):
                tool_calls_count += 1
                name = tc.get("function", {}).get("name", "unknown")
                tool_names[name] = tool_names.get(name, 0) + 1

    # 统计数据集
    dataset_count = len(session.datasets)
    total_rows = sum(len(df) for df in session.datasets.values())

    # 统计产物（以工作区索引为准，排除内部产物）
    workspace_artifacts = WorkspaceManager(session.id).list_artifacts()
    artifact_count = sum(
        1
        for item in workspace_artifacts
        if str(item.get("visibility", "deliverable")).lower() != "internal"
    )

    # 构建统计信息
    lines = [
        f"- **总消息数**: {len(messages)} 条（用户 {user_messages}，助手 {assistant_messages}，工具 {tool_messages}）",
        f"- **工具调用**: {tool_calls_count} 次",
    ]

    # 工具调用详情（前 5 个）
    if tool_names:
        top_tools = sorted(tool_names.items(), key=lambda x: x[1], reverse=True)[:5]
        tool_details = ", ".join([f"{name}×{count}" for name, count in top_tools])
        lines.append(f"  - 常用工具: {tool_details}")

    lines.extend(
        [
            f"- **数据集**: {dataset_count} 个，总计 {total_rows:,} 行数据",
            f"- **生成产物**: {artifact_count} 个",
        ]
    )

    return "\n".join(lines)


def _strip_leading_h2(text: str) -> str:
    """移除文本开头的 H2 标题（避免与模板重复）。"""
    import re

    # 匹配开头的 "## 标题\n"
    return re.sub(r"^##\s+[^\n]+\n+", "", text.strip(), count=1)


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
    include_session_stats: bool,
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
        cleaned_methods = _strip_leading_h2(methods.strip())
        sections.extend(["", "## 分析方法", cleaned_methods])

    # 分析摘要
    if summary_text and summary_text.strip():
        cleaned_summary = _strip_leading_h2(summary_text.strip())
        sections.extend(["", "## 分析摘要", cleaned_summary])

    # 图表预览（可选，不再附加冗余的图表清单表格）
    if include_charts:
        chart_preview_md = _chart_preview_markdown(session.id)
        if chart_preview_md:
            sections.extend(["", "## 图表", chart_preview_md])

    # 关键发现（从工具结果提取，过滤噪声）
    if include_recent_messages:
        findings = _recent_findings(session.messages)
        if findings:
            sections.extend(["", "## 关键发现", findings])

    # 结论与建议（可选）
    if conclusions and conclusions.strip():
        cleaned_conclusions = _strip_leading_h2(conclusions.strip())
        sections.extend(["", "## 结论与建议", cleaned_conclusions])

    # 分析统计（可选附录）
    if include_session_stats:
        stats = _session_statistics(session)
        if stats:
            sections.extend(["", "## 分析统计（系统观测）", stats])

    return "\n".join(sections).strip() + "\n"


def _resolve_output_name(
    session: Session,
    storage: ArtifactStorage,
    *,
    filename: Any,
    title: str,
) -> str:
    """解析并去重报告文件名，避免覆盖历史报告。支持从标题生成语义化文件名。"""
    manager = WorkspaceManager(session.id)

    if isinstance(filename, str) and filename.strip():
        # 用户指定了文件名，使用用户指定的
        raw_name = filename.strip()
    else:
        # 自动生成：从标题提取 + 时间戳
        sanitized_title = _sanitize_chinese_filename(title, max_bytes=60)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        raw_name = f"{sanitized_title}_{ts}.md"

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


def _make_downloadable_markdown(preview_md: str, session_id: str) -> str:
    """将前端预览 Markdown 转换为可下载版本。

    主要变换：
    1. 将 plotly.json 图片引用替换为同名 PNG（如果存在），使外部编辑器可渲染
    2. 将内部 API 路径 (/api/artifacts/...) 替换为相对路径 (./filename)
    3. 不存在 PNG 时添加注释提示
    """
    import re

    if not preview_md:
        return preview_md

    storage = ArtifactStorage(session_id)

    def _replace_image_ref(match: re.Match) -> str:  # type: ignore[type-arg]
        alt_text = match.group(1)
        url = match.group(2)

        # 提取文件名
        filename = url.rsplit("/", 1)[-1] if "/" in url else url

        # plotly.json → 尝试替换为 PNG
        if filename.lower().endswith(".plotly.json"):
            base_name = filename[: -len(".plotly.json")]
            png_name = f"{base_name}.png"
            if storage.get_path(png_name).exists():
                return f"![{alt_text}](./{png_name})"
            # 尝试用 kaleido 导出
            png_path = _try_export_plotly_to_png(storage, filename, png_name)
            if png_path:
                return f"![{alt_text}](./{png_name})"
            return f"<!-- 图表 {base_name} 需在应用内查看（Plotly 交互图） -->"

        # 非 plotly：内部 API 路径 → 相对路径
        if url.startswith("/api/artifacts/"):
            return f"![{alt_text}](./{filename})"

        return str(match.group(0))

    result = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", _replace_image_ref, preview_md)
    return result


def _try_export_plotly_to_png(
    storage: ArtifactStorage,
    plotly_filename: str,
    png_filename: str,
) -> Path | None:
    """尝试将 plotly.json 文件导出为 PNG。失败时返回 None。"""
    import logging

    logger = logging.getLogger(__name__)

    plotly_path = storage.get_path(plotly_filename)
    if not plotly_path.exists():
        return None

    try:
        import plotly.io as pio

        fig_json = plotly_path.read_text(encoding="utf-8")
        fig = pio.from_json(fig_json)
        png_path = storage.get_path(png_filename)
        fig.write_image(str(png_path), format="png", width=1200, height=800, scale=2)
        return png_path
    except Exception:
        logger.debug("Plotly PNG 导出失败: %s", plotly_filename, exc_info=True)
        return None


class GenerateReportSkill(Skill):
    """生成 Markdown 分析报告并保存为产物。"""

    @property
    def name(self) -> str:
        return "generate_report"

    @property
    def category(self) -> str:
        return "report"

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
                "include_session_stats": {
                    "type": "boolean",
                    "default": False,
                    "description": "是否附加系统观测统计（消息数、工具调用等）",
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
        summary_text = _strip_tool_mentions(str(kwargs.get("summary_text", "") or ""))
        methods = _strip_tool_mentions(str(kwargs.get("methods", "") or ""))
        conclusions = _strip_tool_mentions(str(kwargs.get("conclusions", "") or ""))
        dataset_names = kwargs.get("dataset_names") or None
        include_recent_messages = bool(kwargs.get("include_recent_messages", True))
        include_charts = bool(kwargs.get("include_charts", True))
        include_session_stats = bool(kwargs.get("include_session_stats", False))
        save_to_knowledge = bool(kwargs.get("save_to_knowledge", True))
        filename = kwargs.get("filename")

        # 前端预览版（保留 plotly.json 引用，前端可交互渲染）
        preview_md = _build_markdown(
            session,
            title=title,
            dataset_names=dataset_names,
            summary_text=summary_text,
            methods=methods,
            conclusions=conclusions,
            include_recent_messages=include_recent_messages,
            include_charts=include_charts,
            include_session_stats=include_session_stats,
        )

        # 可下载版（plotly.json → PNG，内部路径 → 相对路径）
        download_md = _make_downloadable_markdown(preview_md, session.id)

        storage = ArtifactStorage(session.id)
        output_name = _resolve_output_name(
            session,
            storage,
            filename=filename,
            title=title,
        )
        # 保存可下载版到文件系统
        path = storage.save_text(download_md, output_name)

        if save_to_knowledge:
            session.knowledge_memory.append(title, download_md)

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
                "report_markdown": preview_md,
            },
            artifacts=[artifact],
        )
