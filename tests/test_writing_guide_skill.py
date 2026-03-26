"""writing-guide Markdown Skill 测试。"""

from __future__ import annotations

from pathlib import Path

from nini.models.risk import TrustLevel
from nini.tools.markdown_scanner import get_markdown_tool_instruction, scan_markdown_tools


def _get_writing_guide_skill():
    skills_dir = Path(__file__).parent.parent / ".nini" / "skills"
    skills = scan_markdown_tools(skills_dir)
    skill = next((item for item in skills if item.name == "writing-guide"), None)
    assert skill is not None, "writing-guide skill 未找到"
    return skill


def test_writing_guide_skill_is_discoverable() -> None:
    skill = _get_writing_guide_skill()

    assert skill.category == "workflow"
    assert skill.research_domain == "general"
    assert "collect_artifacts" in (skill.metadata.get("allowed_tools") or [])


def test_writing_guide_skill_contract_is_parsed() -> None:
    skill = _get_writing_guide_skill()
    contract = skill.metadata.get("contract")

    assert contract is not None, "contract 字段未解析"
    assert contract.trust_ceiling == TrustLevel.T1
    assert [step.id for step in contract.steps] == [
        "collect_materials",
        "plan_structure",
        "write_sections",
        "review_revise",
    ]


def test_writing_guide_skill_instruction_contains_templates() -> None:
    skill_path = Path(__file__).parent.parent / ".nini" / "skills" / "writing-guide" / "SKILL.md"
    payload = get_markdown_tool_instruction(skill_path)
    instruction = payload["instruction"]

    assert "O2 草稿级" in instruction
    assert "如图 1 所示" in instruction
    assert "当前会话暂无可引用的统计结果或图表" in instruction
