"""技能清单（Skill Manifest）—— Nini Skills 与 Claude Code Skills 的统一描述协议。

提供 SkillManifest 数据类，用于：
1. 导出 Nini Skill 为 Claude Code 兼容的 Markdown 描述
2. 从 Markdown 描述导入技能元数据
3. 统一技能的跨平台发现与文档生成
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillManifest:
    """统一技能元数据。"""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    category: str = ""
    examples: list[str] = field(default_factory=list)
    brief_description: str = ""
    research_domain: str = "general"
    difficulty_level: str = "intermediate"
    typical_use_cases: list[str] = field(default_factory=list)
    # Nini 专有
    is_idempotent: bool = False
    output_types: list[str] = field(default_factory=list)  # chart, dataframe, report, artifact


def export_to_claude_code(manifest: SkillManifest) -> str:
    """将 SkillManifest 导出为 Claude Code 兼容的 Markdown 技能描述。

    Claude Code Skills 本质是 Markdown 文件，包含工作流描述和上下文信息。
    此函数将 Nini Skill 的结构化元数据转换为可读的 Markdown 格式。
    """
    lines: list[str] = []
    lines.append(f"# {manifest.name}")
    lines.append("")
    lines.append(manifest.description)
    lines.append("")

    if manifest.category:
        lines.append(f"**分类**: {manifest.category}")
        lines.append("")

    if manifest.brief_description:
        lines.append(f"**简述**: {manifest.brief_description}")
        lines.append("")

    if manifest.research_domain:
        lines.append(f"**研究领域**: {manifest.research_domain}")
        lines.append("")

    if manifest.difficulty_level:
        lines.append(f"**难度**: {manifest.difficulty_level}")
        lines.append("")

    # 参数说明
    props = manifest.parameters.get("properties", {})
    required = set(manifest.parameters.get("required", []))
    if props:
        lines.append("## 参数")
        lines.append("")
        for param_name, param_schema in props.items():
            req_mark = "（必填）" if param_name in required else "（可选）"
            desc = param_schema.get("description", "")
            ptype = param_schema.get("type", "any")
            lines.append(f"- **{param_name}** (`{ptype}`) {req_mark}: {desc}")
        lines.append("")

    # 使用示例
    if manifest.examples:
        lines.append("## 使用示例")
        lines.append("")
        for ex in manifest.examples:
            lines.append(f"- {ex}")
        lines.append("")

    if manifest.typical_use_cases:
        lines.append("## 典型场景")
        lines.append("")
        for use_case in manifest.typical_use_cases:
            lines.append(f"- {use_case}")
        lines.append("")

    # 输出类型
    if manifest.output_types:
        lines.append(f"**输出类型**: {', '.join(manifest.output_types)}")
        lines.append("")

    if manifest.is_idempotent:
        lines.append("*此技能是幂等的，多次调用结果相同。*")
        lines.append("")

    return "\n".join(lines)


def import_from_markdown(md_content: str) -> SkillManifest:
    """从 Markdown 描述导入技能元数据。

    解析 Claude Code 风格的 Markdown 技能描述，提取：
    - 标题作为技能名称
    - 正文作为描述
    - "## 参数" 段落中的参数定义
    - "## 使用示例" 段落中的示例
    """
    lines = md_content.strip().split("\n")
    name = ""
    description_lines: list[str] = []
    parameters: dict[str, Any] = {"type": "object", "properties": {}}
    examples: list[str] = []
    category = ""
    brief_description = ""
    research_domain = "general"
    difficulty_level = "intermediate"
    typical_use_cases: list[str] = []
    current_section = "description"

    for line in lines:
        stripped = line.strip()

        # 标题 -> 名称
        if stripped.startswith("# ") and not name:
            name = stripped[2:].strip()
            continue

        # 二级标题切换段落
        if stripped.startswith("## "):
            section_name = stripped[3:].strip()
            if "参数" in section_name:
                current_section = "parameters"
            elif "示例" in section_name:
                current_section = "examples"
            elif "典型场景" in section_name or "使用场景" in section_name:
                current_section = "typical_use_cases"
            else:
                current_section = "other"
            continue

        # 分类行
        cat_match = re.match(r"\*\*分类\*\*:\s*(.+)", stripped)
        if cat_match:
            category = cat_match.group(1).strip()
            continue
        brief_match = re.match(r"\*\*简述\*\*:\s*(.+)", stripped)
        if brief_match:
            brief_description = brief_match.group(1).strip()
            continue
        domain_match = re.match(r"\*\*研究领域\*\*:\s*(.+)", stripped)
        if domain_match:
            research_domain = domain_match.group(1).strip()
            continue
        difficulty_match = re.match(r"\*\*难度\*\*:\s*(.+)", stripped)
        if difficulty_match:
            difficulty_level = difficulty_match.group(1).strip()
            continue

        # 参数段落
        if current_section == "parameters" and stripped.startswith("- **"):
            param_match = re.match(
                r"- \*\*(\w+)\*\*\s*\(`(\w+)`\)\s*（([^）]+)）:\s*(.*)",
                stripped,
            )
            if param_match:
                pname = param_match.group(1)
                ptype = param_match.group(2)
                pdesc = param_match.group(4)
                parameters["properties"][pname] = {
                    "type": ptype,
                    "description": pdesc,
                }
                if "必填" in param_match.group(3):
                    parameters.setdefault("required", []).append(pname)
            continue

        # 示例段落
        if current_section == "examples" and stripped.startswith("- "):
            examples.append(stripped[2:])
            continue

        if current_section == "typical_use_cases" and stripped.startswith("- "):
            typical_use_cases.append(stripped[2:])
            continue

        # 描述段落
        if current_section == "description" and stripped:
            description_lines.append(stripped)

    return SkillManifest(
        name=name,
        description="\n".join(description_lines),
        parameters=parameters if parameters["properties"] else {},
        category=category,
        examples=examples,
        brief_description=brief_description,
        research_domain=research_domain,
        difficulty_level=difficulty_level,
        typical_use_cases=typical_use_cases,
    )


def export_all_skills_markdown(skills: list[SkillManifest]) -> str:
    """将多个技能清单导出为单个 Markdown 文档（技能目录）。"""
    lines = ["# Nini 技能目录", ""]

    # 按分类分组
    by_category: dict[str, list[SkillManifest]] = {}
    for s in skills:
        cat = s.category or "未分类"
        by_category.setdefault(cat, []).append(s)

    for cat, cat_skills in sorted(by_category.items()):
        lines.append(f"## {cat}")
        lines.append("")
        for s in cat_skills:
            lines.append(f"### {s.name}")
            lines.append("")
            lines.append(s.description.split("\n")[0])  # 首行描述
            lines.append("")

    return "\n".join(lines)
