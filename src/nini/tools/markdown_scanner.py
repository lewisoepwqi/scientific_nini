"""Markdown 技能扫描与快照生成。"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Iterable
import logging
from pathlib import Path
import re
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from nini.tools.manifest import SkillManifest

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^\s*---\s*\n(.*?)\n---\s*\n?", re.DOTALL)

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

_CATEGORY_ALIASES: dict[str, str] = {
    "analysis": "statistics",
    "stat": "statistics",
    "stats": "statistics",
    "viz": "visualization",
    "chart": "visualization",
    "charts": "visualization",
    "plot": "visualization",
    "plots": "visualization",
    "data-analysis": "data",
    "data_analysis": "data",
    "automation": "workflow",
    "helper": "utility",
    "tools": "utility",
}


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
        from nini.tools.manifest import SkillManifest

        return SkillManifest(
            name=self.name,
            description=self.description,
            parameters={},
            category=self.category,
        )


def _parse_frontmatter(text: str) -> dict[str, Any]:
    """解析 YAML frontmatter，解析失败时返回空字典。"""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    block = m.group(1)
    try:
        parsed = yaml.safe_load(block) or {}
    except Exception as exc:  # pragma: no cover - 仅保护解析异常
        logger.warning("frontmatter YAML 解析失败: %s", exc)
        return {}
    if not isinstance(parsed, dict):
        return {}
    return dict(parsed)


def _extract_description(text: str, fallback_name: str) -> str:
    """从正文提取描述首行。"""
    body = text
    frontmatter = _FRONTMATTER_RE.match(text)
    if frontmatter:
        body = text[frontmatter.end() :]

    for line in body.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return f"{fallback_name} 的技能定义"


def _normalize_category(raw_category: Any) -> tuple[str, str | None]:
    """标准化分类，返回 (标准分类, 原始分类)。"""
    raw = str(raw_category or "").strip().lower()
    if not raw:
        return "other", None
    if raw in VALID_CATEGORIES:
        return raw, None
    alias = _CATEGORY_ALIASES.get(raw)
    if alias:
        return alias, raw
    return "other", raw


def _to_str_list(value: Any) -> list[str]:
    if isinstance(value, str):
        parts = [v.strip() for v in value.split(",")]
        return [v for v in parts if v]
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                out.append(text)
        return out
    return []


def _infer_standards(path: Path) -> list[str]:
    normalized = str(path).replace("\\", "/").lower()
    standards: list[str] = []
    if "/.claude/skills/" in normalized:
        standards.append("claude-code")
    if "/.codex/skills/" in normalized:
        standards.append("codex")
    if "/.agents/skills/" in normalized:
        standards.append("agent-skills")
    if not standards:
        standards.append("nini")
    return standards


def _parse_openai_agent_config(skill_dir: Path) -> dict[str, Any] | None:
    """读取 Agent Skills 规范中的 agents/openai.yaml。"""
    cfg_path = skill_dir / "agents" / "openai.yaml"
    if not cfg_path.exists():
        return None
    try:
        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # pragma: no cover - 仅保护解析异常
        logger.warning("解析 openai.yaml 失败: %s (%s)", cfg_path, exc)
        return {"path": str(cfg_path), "parse_error": str(exc)}
    if isinstance(data, dict):
        return {"path": str(cfg_path), "config": data}
    return {"path": str(cfg_path), "config": {}}


def _iter_skill_files(roots: list[Path]) -> Iterable[tuple[Path, Path, int]]:
    """遍历技能文件，返回 (root, skill_file, discovery_priority)。"""
    for priority, root in enumerate(roots):
        if not root.exists():
            continue
        visited: set[Path] = set()
        for pattern in ("SKILL.md", "skill.md"):
            for path in sorted(root.rglob(pattern)):
                resolved = path.resolve()
                if resolved in visited:
                    continue
                visited.add(resolved)
                yield root, resolved, priority


def scan_markdown_skills(skills_dir: Path | Iterable[Path]) -> list[MarkdownSkill]:
    """扫描 Markdown 技能并解析元数据。

    兼容目录：
    - Nini 默认：`skills/*/SKILL.md`
    - Claude Code：`.claude/skills/*/SKILL.md`
    - Codex：`.codex/skills/*/SKILL.md`
    - Agent Skills：`.agents/skills/*/SKILL.md`（可选 `agents/openai.yaml`）
    """
    roots = [skills_dir] if isinstance(skills_dir, Path) else [Path(p) for p in skills_dir]
    roots = [p.expanduser().resolve() for p in roots]
    if not roots:
        return []

    items: list[MarkdownSkill] = []
    for root, path, priority in _iter_skill_files(roots):
        try:
            text = path.read_text(encoding="utf-8")
            meta = _parse_frontmatter(text)

            # 名称：优先使用 frontmatter，回退到文件夹名
            name = str(meta.get("name", "")).strip() or path.parent.name
            if "name" not in meta or not str(meta.get("name", "")).strip():
                logger.warning(
                    "Markdown 技能 %s 缺少 frontmatter 中的 name 字段，已回退到文件夹名 '%s'",
                    path,
                    name,
                )

            # 描述：优先使用 frontmatter，回退到正文首行
            description = str(meta.get("description", "")).strip()
            if not description:
                description = _extract_description(text, name)
                logger.warning("Markdown 技能 %s 缺少 frontmatter 中的 description 字段", path)

            # 分类：标准化，兼容别名
            category, raw_category = _normalize_category(meta.get("category"))
            if raw_category:
                logger.warning(
                    "Markdown 技能 %s 的 category '%s' 非标准分类，已归一化为 '%s'",
                    path,
                    raw_category,
                    category,
                )

            standards = _infer_standards(path)
            openai_cfg = _parse_openai_agent_config(path.parent)
            metadata: dict[str, Any] = {
                "path": str(path),
                "source_root": str(root),
                "source_standard": standards,
                "discovery_priority": priority,
                "frontmatter": meta,
            }
            agents = _to_str_list(meta.get("agents"))
            if agents:
                metadata["agents"] = agents
            tags = _to_str_list(meta.get("tags"))
            if tags:
                metadata["tags"] = tags
            aliases = _to_str_list(meta.get("aliases") or meta.get("alias"))
            if aliases:
                metadata["aliases"] = aliases
            allowed_tools = _to_str_list(meta.get("allowed-tools") or meta.get("allowed_tools"))
            if allowed_tools:
                metadata["allowed_tools"] = allowed_tools
            argument_hint = str(
                meta.get("argument-hint") or meta.get("argument_hint") or ""
            ).strip()
            if argument_hint:
                metadata["argument_hint"] = argument_hint
            if isinstance(meta.get("user-invocable"), bool):
                metadata["user_invocable"] = meta.get("user-invocable")
            elif isinstance(meta.get("user_invocable"), bool):
                metadata["user_invocable"] = meta.get("user_invocable")
            if isinstance(meta.get("disable-model-invocation"), bool):
                metadata["disable_model_invocation"] = meta.get("disable-model-invocation")
            elif isinstance(meta.get("disable_model_invocation"), bool):
                metadata["disable_model_invocation"] = meta.get("disable_model_invocation")
            if raw_category:
                metadata["raw_category"] = raw_category
            if openai_cfg:
                metadata["openai_agent_config"] = openai_cfg

            items.append(
                MarkdownSkill(
                    name=name,
                    description=description,
                    location=str(path),
                    category=category,
                    metadata=metadata,
                )
            )
        except Exception as exc:  # pragma: no cover - 防御性保护
            logger.warning("解析 Markdown 技能失败: %s (%s)", path, exc)
    return items


def render_skills_snapshot(skills: list[dict[str, Any]]) -> str:
    """生成可读的技能快照文本。"""
    lines = ["# SKILLS_SNAPSHOT", "", "## available_skills", ""]
    for skill in skills:
        name = str(skill.get("name", "")).strip()
        if not name:
            continue
        metadata = skill.get("metadata")
        lines.append(f"- name: {name}")
        lines.append(f"  type: {skill.get('type', 'unknown')}")
        lines.append(f"  category: {skill.get('category', 'other')}")
        lines.append(f"  enabled: {bool(skill.get('enabled', True))}")
        lines.append(f"  description: {skill.get('description', '')}")
        lines.append(f"  location: {skill.get('location', '')}")
        if isinstance(metadata, dict):
            standards = metadata.get("source_standard")
            if isinstance(standards, list) and standards:
                lines.append(f"  source_standard: {', '.join(str(s) for s in standards)}")
            agents = metadata.get("agents")
            if isinstance(agents, list) and agents:
                lines.append(f"  agents: {', '.join(str(s) for s in agents)}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"
