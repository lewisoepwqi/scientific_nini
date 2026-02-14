"""Markdown 技能扫描与快照生成。"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from pathlib import Path
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from nini.skills.manifest import SkillManifest

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^\s*---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_KV_RE = re.compile(r"^\s*([A-Za-z0-9_-]+)\s*:\s*(.*?)\s*$")

# 标准分类体系，与 Function Skills 保持一致
VALID_CATEGORIES = frozenset(
    {
        "data",
        "statistics",
        "visualization",
        "export",
        "report",
        "workflow",
        "utility",
        "other",
    }
)


@dataclass
class MarkdownSkill:
    name: str
    description: str
    location: str
    category: str = "other"
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "markdown",
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "location": self.location,
            "enabled": self.enabled,
            "metadata": self.metadata,
        }

    def to_manifest(self) -> "SkillManifest":
        """导出为统一技能清单，与 Function Skill 保持一致的接口。"""
        from nini.skills.manifest import SkillManifest

        return SkillManifest(
            name=self.name,
            description=self.description,
            parameters={},
            category=self.category,
        )


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
    """扫描 skills/*/SKILL.md，解析元数据。

    每个 SKILL.md 应包含 YAML Frontmatter，至少包含 name 和 description 字段。
    可选字段：category（须为 VALID_CATEGORIES 中的值）。
    缺少 name 时回退到父文件夹名并输出警告。
    """
    if not skills_dir.exists():
        return []

    items: list[MarkdownSkill] = []
    for path in sorted(skills_dir.rglob("SKILL.md")):
        try:
            text = path.read_text(encoding="utf-8")
            meta = _parse_frontmatter(text)

            # 名称：优先使用 frontmatter，回退到文件夹名
            name = str(meta.get("name", "")).strip()
            if not name:
                name = path.parent.name
                logger.warning(
                    "Markdown 技能 %s 缺少 frontmatter 中的 name 字段，" "已回退到文件夹名 '%s'",
                    path,
                    name,
                )

            # 描述：优先使用 frontmatter，回退到正文首行
            description = str(meta.get("description", "")).strip()
            if not description:
                first_line = ""
                for line in text.splitlines():
                    stripped = line.strip()
                    if stripped and not stripped.startswith("---") and not stripped.startswith("#"):
                        first_line = stripped
                        break
                description = first_line or f"{name} 的技能定义"
                logger.warning(
                    "Markdown 技能 %s 缺少 frontmatter 中的 description 字段",
                    path,
                )

            # 分类：验证合法性
            category = str(meta.get("category", "")).strip().lower() or "other"
            if category not in VALID_CATEGORIES:
                logger.warning(
                    "Markdown 技能 %s 的 category '%s' 不在标准分类中 %s，已回退到 'other'",
                    path,
                    category,
                    sorted(VALID_CATEGORIES),
                )
                category = "other"

            items.append(
                MarkdownSkill(
                    name=name,
                    description=description,
                    location=str(path),
                    category=category,
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
        lines.append(f"  category: {skill.get('category', 'other')}")
        lines.append(f"  enabled: {bool(skill.get('enabled', True))}")
        lines.append(f"  description: {skill.get('description', '')}")
        lines.append(f"  location: {skill.get('location', '')}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"
