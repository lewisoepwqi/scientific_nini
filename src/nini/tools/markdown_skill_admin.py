"""Markdown Skill 管理工具。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any

import yaml

from nini.tools.markdown_scanner import VALID_CATEGORIES

_FRONTMATTER_RE = re.compile(r"^\s*---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_SKILL_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


@dataclass
class MarkdownSkillDocument:
    name: str
    description: str
    category: str
    body: str
    frontmatter: dict[str, Any] = field(default_factory=dict)


def validate_skill_name(name: str) -> str:
    """校验 skill 名称（兼容 snake_case / kebab-case）。"""
    candidate = name.strip()
    if not _SKILL_NAME_RE.match(candidate):
        raise ValueError(f"名称 '{candidate}' 不合法，必须以字母开头，仅包含字母/数字/_/-")
    return candidate


def guess_skill_name_from_filename(filename: str) -> str:
    """根据文件名推导合法的 skill 名称。"""
    stem = Path(filename).stem.strip().lower()
    stem = re.sub(r"[^a-z0-9_-]+", "-", stem)
    stem = re.sub(r"-+", "-", stem).strip("-_")
    if not stem:
        raise ValueError("无法从文件名推导技能名称")
    if not stem[0].isalpha():
        stem = f"skill-{stem}"
    return validate_skill_name(stem)


def normalize_category(category: str | None, *, strict: bool = False) -> str:
    """标准化技能分类。"""
    normalized = (category or "other").strip().lower() or "other"
    if normalized in VALID_CATEGORIES:
        return normalized
    if strict:
        raise ValueError(f"分类 '{category}' 不在标准分类中：{sorted(VALID_CATEGORIES)}")
    return "other"


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """拆分 Frontmatter 与正文。"""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text.strip()

    try:
        raw_meta = yaml.safe_load(m.group(1)) or {}
    except Exception:
        raw_meta = {}
    meta = raw_meta if isinstance(raw_meta, dict) else {}

    body = text[m.end() :].strip()
    return dict(meta), body


def _infer_description_from_body(body: str, name: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        return stripped
    return f"{name} 技能"


def _default_skill_body(name: str, description: str) -> str:
    return (
        f"# {name}\n\n"
        f"{description}\n\n"
        "## 适用场景\n\n"
        "- 说明该技能适用于哪些问题类型、输入条件与预期输出。\n"
        "- 如果有前置依赖（数据、工具、权限），在此明确标注。\n\n"
        "## 步骤\n\n"
        "1. 描述执行前的准备动作（如读取上下文、校验输入）。\n"
        "2. 描述核心执行流程（调用哪些工具、按何顺序执行）。\n"
        "3. 描述输出要求（结果格式、产物命名、失败时回退策略）。\n\n"
        "## 注意事项\n\n"
        "- 明确边界条件和风险点（如大数据集、长耗时、外部依赖失败）。\n"
        "- 明确不可执行动作或必须人工确认的步骤。\n"
    )


def parse_skill_document(
    text: str,
    *,
    fallback_name: str | None = None,
) -> MarkdownSkillDocument:
    """解析 Markdown Skill 文档。"""
    meta, body = split_frontmatter(text)

    raw_name = str(meta.get("name", "")).strip()
    if not raw_name:
        raw_name = (fallback_name or "").strip()
    if not raw_name:
        raise ValueError("技能名称不能为空")
    name = validate_skill_name(raw_name)

    description = str(meta.get("description", "")).strip()
    if not description:
        description = _infer_description_from_body(body, name)

    category = normalize_category(str(meta.get("category", "") or ""), strict=False)
    return MarkdownSkillDocument(
        name=name,
        description=description,
        category=category,
        body=body,
        frontmatter=meta,
    )


def render_skill_document(document: MarkdownSkillDocument) -> str:
    """将结构化 Skill 文档渲染为 Markdown。"""
    name = validate_skill_name(document.name)
    description = " ".join(document.description.strip().split()) or f"{name} 技能"
    category = normalize_category(document.category, strict=True)
    body = document.body.strip() or _default_skill_body(name, description)

    frontmatter = dict(document.frontmatter)
    frontmatter["name"] = name
    frontmatter["description"] = description
    frontmatter["category"] = category

    fm_text = yaml.safe_dump(
        frontmatter,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    ).strip()

    return f"---\n{fm_text}\n---\n\n{body.rstrip()}\n"
