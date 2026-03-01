"""article_draft Markdown Skill 集成测试。

验证：
1. scan_markdown_skills 能正确发现并解析 SKILL.md
2. frontmatter 字段完整（name、description、category）
3. article_draft Capability 在 create_default_capabilities() 中正确返回
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nini.tools.markdown_scanner import scan_markdown_skills
from nini.capabilities.defaults import create_default_capabilities


# ---------------------------------------------------------------------------
# Markdown Skill 扫描测试
# ---------------------------------------------------------------------------


def test_article_draft_skill_is_discoverable():
    """article-draft/SKILL.md 能被扫描器正确发现。"""
    skills_dir = Path(__file__).parent.parent / "src" / "nini" / "skills"
    skills = scan_markdown_skills(skills_dir)
    names = [s.name for s in skills]
    assert "article_draft" in names, f"期望找到 article_draft，实际找到: {names}"


def test_article_draft_skill_frontmatter_fields():
    """article_draft Skill 的 frontmatter 包含必要字段。"""
    skills_dir = Path(__file__).parent.parent / "src" / "nini" / "skills"
    skills = scan_markdown_skills(skills_dir)
    skill = next((s for s in skills if s.name == "article_draft"), None)

    assert skill is not None, "article_draft skill 未找到"
    assert skill.description, "description 不能为空"
    assert skill.category == "report", f"期望 category=report，实际: {skill.category}"
    assert skill.research_domain == "general"
    assert skill.difficulty_level == "advanced"
    assert len(skill.typical_use_cases) > 0, "typical_use_cases 不能为空"


def test_article_draft_skill_has_instruction_body():
    """SKILL.md 正文（工作流说明）不能为空。"""
    from nini.tools.markdown_scanner import get_markdown_skill_instruction

    skill_path = (
        Path(__file__).parent.parent / "src" / "nini" / "skills" / "article-draft" / "SKILL.md"
    )
    assert skill_path.exists(), f"SKILL.md 不存在: {skill_path}"

    payload = get_markdown_skill_instruction(skill_path)
    instruction = payload.get("instruction", "")
    assert len(instruction) > 100, "工作流说明内容过短，可能未正确读取"
    # 验证关键章节存在
    assert "edit_file" in instruction
    assert "data_summary" in instruction


# ---------------------------------------------------------------------------
# Capability 测试
# ---------------------------------------------------------------------------


def test_article_draft_capability_in_defaults():
    """article_draft Capability 在默认能力列表中存在。"""
    capabilities = create_default_capabilities()
    names = [c.name for c in capabilities]
    assert "article_draft" in names, f"期望找到 article_draft，实际: {names}"


def test_article_draft_capability_fields():
    """article_draft Capability 的字段配置正确。"""
    capabilities = {c.name: c for c in create_default_capabilities()}
    cap = capabilities["article_draft"]

    assert cap.display_name == "科研文章初稿"
    assert cap.icon == "📝"
    assert cap.is_executable is False, "article_draft 应为非可执行（由 Markdown Skill 驱动）"
    assert "edit_file" in cap.required_tools
    assert "data_summary" in cap.required_tools
    assert cap.execution_message, "execution_message 不能为空"


def test_article_draft_capability_suggested_workflow():
    """article_draft Capability 的 suggested_workflow 包含关键工具。"""
    capabilities = {c.name: c for c in create_default_capabilities()}
    cap = capabilities["article_draft"]

    assert "data_summary" in cap.suggested_workflow
    assert "edit_file" in cap.suggested_workflow
    assert "export_report" in cap.suggested_workflow
