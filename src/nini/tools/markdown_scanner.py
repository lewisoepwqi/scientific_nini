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
    brief_description: str = ""
    research_domain: str = "general"
    difficulty_level: str = "intermediate"
    typical_use_cases: list[str] = field(default_factory=list)
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "markdown",
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "brief_description": self.brief_description,
            "research_domain": self.research_domain,
            "difficulty_level": self.difficulty_level,
            "typical_use_cases": self.typical_use_cases,
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
            brief_description=self.brief_description,
            research_domain=self.research_domain,
            difficulty_level=self.difficulty_level,
            typical_use_cases=self.typical_use_cases,
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


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """拆分 Frontmatter 与正文。"""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text.strip()
    meta = _parse_frontmatter(text)
    body = text[m.end() :].strip()
    return meta, body


def _extract_description(text: str, fallback_name: str) -> str:
    """从正文提取描述首行。"""
    _, body = split_frontmatter(text)

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


def _normalize_brief_description(raw_brief: Any, description: str) -> str:
    brief = str(raw_brief or "").strip()
    if brief:
        return brief
    single_line = " ".join(description.split())
    if len(single_line) <= 80:
        return single_line
    return single_line[:77] + "..."


def _normalize_difficulty(raw_value: Any) -> str:
    difficulty = str(raw_value or "").strip().lower()
    return difficulty or "intermediate"


def _infer_standards(path: Path) -> list[str]:
    normalized = str(path).replace("\\", "/").lower()
    standards: list[str] = []
    if "/.claude/skills/" in normalized:
        standards.append("claude-code")
    if "/.codex/skills/" in normalized:
        standards.append("codex")
    if "/.opencode/skills/" in normalized:
        standards.append("opencode")
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


def get_markdown_skill_instruction(
    skill_path: Path,
) -> dict[str, Any]:
    """读取 Markdown Skill 的正文说明层。"""
    text = skill_path.read_text(encoding="utf-8")
    frontmatter, body = split_frontmatter(text)
    return {
        "path": str(skill_path),
        "frontmatter": frontmatter,
        "instruction": body,
    }


def list_markdown_skill_runtime_resources(skill_path: Path) -> list[dict[str, Any]]:
    """列出 Skill 目录中除说明文件外的运行时资源。"""
    skill_dir = skill_path.parent
    resources: list[dict[str, Any]] = []
    for path in sorted(skill_dir.rglob("*")):
        if path == skill_path or path.name.startswith("."):
            continue
        rel_path = str(path.relative_to(skill_dir))
        if path.is_dir():
            child_count = sum(1 for child in path.iterdir())
            resources.append(
                {
                    "path": rel_path,
                    "type": "dir",
                    "child_count": child_count,
                }
            )
            continue
        top_level = rel_path.split("/", 1)[0]
        resources.append(
            {
                "path": rel_path,
                "type": "file",
                "size": path.stat().st_size,
                "top_level": top_level,
            }
        )
    return resources


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
    - OpenCode：`.opencode/skills/*/SKILL.md`
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
            brief_description = _normalize_brief_description(
                meta.get("brief-description") or meta.get("brief_description"),
                description,
            )
            research_domain = str(
                meta.get("research-domain") or meta.get("research_domain") or "general"
            ).strip() or "general"
            difficulty_level = _normalize_difficulty(
                meta.get("difficulty-level") or meta.get("difficulty_level")
            )
            typical_use_cases = _to_str_list(
                meta.get("typical-use-cases") or meta.get("typical_use_cases")
            )
            metadata: dict[str, Any] = {
                "path": str(path),
                "source_root": str(root),
                "source_standard": standards,
                "discovery_priority": priority,
                "frontmatter": meta,
                "brief_description": brief_description,
                "research_domain": research_domain,
                "difficulty_level": difficulty_level,
                "typical_use_cases": typical_use_cases,
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
                    brief_description=brief_description,
                    research_domain=research_domain,
                    difficulty_level=difficulty_level,
                    typical_use_cases=typical_use_cases,
                    metadata=metadata,
                )
            )
        except Exception as exc:  # pragma: no cover - 防御性保护
            logger.warning("解析 Markdown 技能失败: %s (%s)", path, exc)
    return items


def _render_snapshot_section(title: str, items: list[dict[str, Any]]) -> list[str]:
    lines = [f"## {title}", ""]
    if not items:
        lines.append("- (none)")
        lines.append("")
        return lines

    for skill in items:
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
    return lines


def render_skills_snapshot(
    skills_or_tools: list[dict[str, Any]],
    markdown_skills: list[dict[str, Any]] | None = None,
) -> str:
    """生成可读的技能快照文本。

    新格式会拆分为两个清单，避免将可执行工具与 Markdown Skill 混在同一节。
    为了兼容旧调用，允许仅传入一个聚合列表，此时会按 type 自动分组。
    """
    if markdown_skills is None:
        tools = [item for item in skills_or_tools if item.get("type") == "function"]
        markdown = [item for item in skills_or_tools if item.get("type") == "markdown"]
    else:
        tools = list(skills_or_tools)
        markdown = list(markdown_skills)

    lines = ["# SKILLS_SNAPSHOT", ""]
    lines.extend(_render_snapshot_section("available_tools", tools))
    lines.extend(_render_snapshot_section("available_markdown_skills", markdown))
    return "\n".join(lines).strip() + "\n"
