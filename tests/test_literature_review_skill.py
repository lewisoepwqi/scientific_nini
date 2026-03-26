"""literature-review Markdown Skill 测试。"""

from __future__ import annotations

from pathlib import Path

from nini.models.risk import TrustLevel
from nini.tools.markdown_scanner import get_markdown_tool_instruction, scan_markdown_tools


def _get_literature_review_skill():
    skills_dir = Path(__file__).parent.parent / ".nini" / "skills"
    skills = scan_markdown_tools(skills_dir)
    skill = next((item for item in skills if item.name == "literature-review"), None)
    assert skill is not None, "literature-review skill 未找到"
    return skill


def test_literature_review_skill_is_discoverable() -> None:
    skill = _get_literature_review_skill()

    assert skill.category == "workflow"
    assert skill.research_domain == "general"
    assert "search_literature" in (skill.metadata.get("allowed_tools") or [])


def test_literature_review_skill_contract_is_parsed() -> None:
    skill = _get_literature_review_skill()
    contract = skill.metadata.get("contract")

    assert contract is not None, "contract 字段未解析"
    assert contract.trust_ceiling == TrustLevel.T1
    assert contract.evidence_required is True
    assert [step.id for step in contract.steps] == [
        "search_papers",
        "filter_papers",
        "synthesize",
        "generate_output",
    ]


def test_literature_review_skill_instruction_contains_offline_path() -> None:
    skill_path = (
        Path(__file__).parent.parent / ".nini" / "skills" / "literature-review" / "SKILL.md"
    )
    payload = get_markdown_tool_instruction(skill_path)
    instruction = payload["instruction"]

    assert "当前为离线模式，无法在线检索文献" in instruction
    assert "上传 PDF" in instruction
    assert "O2 草稿级" in instruction
    assert "缺少文献支撑，需进一步检索验证" in instruction
