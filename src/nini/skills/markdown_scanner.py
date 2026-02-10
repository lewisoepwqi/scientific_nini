"""Markdown 技能扫描与快照生成。"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import re
from typing import Any

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^\s*---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_KV_RE = re.compile(r"^\s*([A-Za-z0-9_-]+)\s*:\s*(.*?)\s*$")


@dataclass
class MarkdownSkill:
    name: str
    description: str
    location: str
    enabled: bool = True
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "markdown",
            "name": self.name,
            "description": self.description,
            "location": self.location,
            "enabled": self.enabled,
            "metadata": self.metadata or {},
        }


def _parse_frontmatter(text: str) -> dict[str, str]:
    m = _FRONTMATTER_RE.search(text)
    if not m:
        return {}
    block = m.group(1)
    result: dict[str, str] = {}
    for raw in block.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        kv = _KV_RE.match(line)
        if kv:
            key, value = kv.group(1), kv.group(2).strip().strip('"').strip("'")
            result[key] = value
    return result


def scan_markdown_skills(skills_dir: Path) -> list[MarkdownSkill]:
    """扫描 skills/*/SKILL.md，解析元数据。"""
    if not skills_dir.exists():
        return []

    items: list[MarkdownSkill] = []
    for path in sorted(skills_dir.rglob("SKILL.md")):
        try:
            text = path.read_text(encoding="utf-8")
            meta = _parse_frontmatter(text)
            name = str(meta.get("name", "")).strip() or path.parent.name
            description = str(meta.get("description", "")).strip()
            if not description:
                first_line = ""
                for line in text.splitlines():
                    line = line.strip()
                    if line and not line.startswith("---") and not line.startswith("#"):
                        first_line = line
                        break
                description = first_line or f"{name} 的技能定义"
            items.append(
                MarkdownSkill(
                    name=name,
                    description=description,
                    location=str(path),
                    metadata={"path": str(path)},
                )
            )
        except Exception as exc:
            logger.warning("解析 Markdown 技能失败: %s (%s)", path, exc)
    return items


def render_skills_snapshot(skills: list[dict[str, Any]]) -> str:
    """生成可读的技能快照文本。"""
    lines = ["# SKILLS_SNAPSHOT", "", "## available_skills", ""]
    for skill in skills:
        name = str(skill.get("name", "")).strip()
        if not name:
            continue
        lines.append(f"- name: {name}")
        lines.append(f"  type: {skill.get('type', 'unknown')}")
        lines.append(f"  enabled: {bool(skill.get('enabled', True))}")
        lines.append(f"  description: {skill.get('description', '')}")
        lines.append(f"  location: {skill.get('location', '')}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"

