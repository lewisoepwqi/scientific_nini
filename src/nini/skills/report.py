"""分析报告生成技能。"""

from __future__ import annotations

from datetime import datetime, timezone
import json
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


def _recent_findings(messages: list[dict[str, Any]], max_items: int = 12) -> str:
    findings: list[str] = []
    for msg in reversed(messages):
        role = msg.get("role")
        if role == "tool":
            content = msg.get("content")
            parsed = None
            if isinstance(content, str):
                try:
                    parsed = json.loads(content)
                except Exception:
                    parsed = None
            if isinstance(parsed, dict):
                message = parsed.get("message")
                if message:
                    findings.append(f"- {message}")
            elif isinstance(content, str) and content.strip():
                findings.append(f"- {content.strip()[:180]}")
        if len(findings) >= max_items:
            break

    if not findings:
        return "- 暂无工具分析结论，建议先执行统计分析或作图。"
    findings.reverse()
    return "\n".join(findings)


def _build_markdown(
    session: Session,
    *,
    title: str,
    dataset_names: list[str] | None,
    summary_text: str,
    include_recent_messages: bool,
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sections = [
        f"# {title}",
        "",
        f"- 会话 ID: `{session.id}`",
        f"- 生成时间: {now}",
        "",
        "## 数据集概览",
        _dataset_overview(session, dataset_names),
        "",
        "## 分析摘要",
        summary_text.strip() if summary_text.strip() else "（未提供摘要文本）",
    ]
    if include_recent_messages:
        sections.extend(
            [
                "",
                "## 近期分析发现",
                _recent_findings(session.messages),
            ]
        )
    return "\n".join(sections).strip() + "\n"


class GenerateReportSkill(Skill):
    """生成 Markdown 分析报告并保存为产物。"""

    @property
    def name(self) -> str:
        return "generate_report"

    @property
    def description(self) -> str:
        return "生成结构化 Markdown 报告，可保存为会话产物并同步写入知识记忆。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string", "default": "科研数据分析报告"},
                "summary_text": {
                    "type": "string",
                    "description": "可选。用户提供的摘要或结论",
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
        dataset_names = kwargs.get("dataset_names") or None
        include_recent_messages = bool(kwargs.get("include_recent_messages", True))
        save_to_knowledge = bool(kwargs.get("save_to_knowledge", True))
        filename = kwargs.get("filename")

        markdown = _build_markdown(
            session,
            title=title,
            dataset_names=dataset_names,
            summary_text=summary_text,
            include_recent_messages=include_recent_messages,
        )

        storage = ArtifactStorage(session.id)
        output_name = (
            str(filename).strip()
            if isinstance(filename, str) and filename.strip()
            else "analysis_report.md"
        )
        if not output_name.endswith(".md"):
            output_name += ".md"
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
