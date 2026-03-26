"""L1 基线验收测试。"""

from __future__ import annotations

from collections import deque
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from nini.agent.components.context_builder import ContextBuilder
from nini.agent.session import Session
from nini.models.risk import ResearchPhase
from nini.tools.detect_phase import detect_phase_from_text
from nini.tools.markdown_scanner import scan_markdown_tools
from nini.tools.registry import create_default_tool_registry

SKILLS_DIR = Path(__file__).parent.parent / ".nini" / "skills"


PHASE_CASES: list[tuple[str, ResearchPhase]] = [
    ("请帮我做文献综述，梳理这个方向的相关研究", ResearchPhase.LITERATURE_REVIEW),
    ("我想先做文献调研，看看近五年的研究现状", ResearchPhase.LITERATURE_REVIEW),
    ("related work 这一节应该怎么组织", ResearchPhase.LITERATURE_REVIEW),
    ("需要一个 literature review 的检索提纲", ResearchPhase.LITERATURE_REVIEW),
    ("请比较现有综述对这个机制的看法", ResearchPhase.LITERATURE_REVIEW),
    ("帮我设计实验方案，并估算样本量", ResearchPhase.EXPERIMENT_DESIGN),
    ("RCT 方案里效应量和功效分析怎么设", ResearchPhase.EXPERIMENT_DESIGN),
    ("研究设计阶段需要考虑哪些变量控制", ResearchPhase.EXPERIMENT_DESIGN),
    ("sample size calculation 应该怎么做", ResearchPhase.EXPERIMENT_DESIGN),
    ("这个课题的研究方案和随机对照怎么安排", ResearchPhase.EXPERIMENT_DESIGN),
    ("请帮我写论文的方法章节", ResearchPhase.PAPER_WRITING),
    ("我现在要写论文，先给我一个摘要结构", ResearchPhase.PAPER_WRITING),
    ("结果章节怎么描述这张图", ResearchPhase.PAPER_WRITING),
    ("paper writing 阶段先写引言还是讨论", ResearchPhase.PAPER_WRITING),
    ("帮我整理论文初稿的讨论章节", ResearchPhase.PAPER_WRITING),
    ("请分析这个数据集的差异", ResearchPhase.DATA_ANALYSIS),
    ("做一下回归分析并解释结果", ResearchPhase.DATA_ANALYSIS),
    ("看看数据分布和异常值", ResearchPhase.DATA_ANALYSIS),
    ("我需要画图展示实验结果", ResearchPhase.DATA_ANALYSIS),
    ("根据当前数据做统计检验", ResearchPhase.DATA_ANALYSIS),
]


@pytest.fixture(scope="module")
def scanned_skills():
    return scan_markdown_tools(SKILLS_DIR)


def _topological_sort(steps: list) -> list[str]:
    """对 SkillStep 列表做拓扑排序。"""
    in_degree: dict[str, int] = {step.id: 0 for step in steps}
    adjacency: dict[str, list[str]] = {step.id: [] for step in steps}

    for step in steps:
        for dep in step.depends_on:
            adjacency[dep].append(step.id)
            in_degree[step.id] += 1

    queue: deque[str] = deque(step.id for step in steps if in_degree[step.id] == 0)
    ordered: list[str] = []
    while queue:
        node = queue.popleft()
        ordered.append(node)
        for neighbor in adjacency[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
    return ordered


@pytest.mark.parametrize(
    ("skill_name", "expected_steps"),
    [
        ("experiment-design-helper", 4),
        ("literature-review", 4),
        ("writing-guide", 4),
    ],
)
def test_l1_new_skills_are_discoverable_and_contract_valid(
    scanned_skills,
    skill_name: str,
    expected_steps: int,
) -> None:
    skill = next((item for item in scanned_skills if item.name == skill_name), None)
    assert skill is not None, f"{skill_name} skill 未找到"

    contract = skill.metadata.get("contract")
    assert contract is not None, f"{skill_name} contract 未解析"
    assert len(contract.steps) == expected_steps
    assert _topological_sort(contract.steps)


@pytest.mark.parametrize(("user_message", "expected_phase"), PHASE_CASES)
def test_l1_detect_phase_typical_messages(
    user_message: str,
    expected_phase: ResearchPhase,
) -> None:
    actual_phase, _confidence, _matched_keywords = detect_phase_from_text(user_message)
    assert actual_phase == expected_phase


def test_l1_detect_phase_accuracy_threshold() -> None:
    correct = 0
    for user_message, expected_phase in PHASE_CASES:
        actual_phase, _confidence, _matched_keywords = detect_phase_from_text(user_message)
        if actual_phase == expected_phase:
            correct += 1
    assert correct >= 16, f"detect_phase 准确数不足：{correct}/20"


@pytest.mark.asyncio
async def test_l1_detect_phase_tool_registered_and_queryable() -> None:
    registry = create_default_tool_registry()

    assert registry.get("detect_phase") is not None

    result = await registry.execute(
        "detect_phase",
        session=Session(),
        user_message="请帮我设计实验并估算样本量",
    )
    assert result["success"] is True
    assert result["data"]["current_phase"] == ResearchPhase.EXPERIMENT_DESIGN.value


@pytest.mark.asyncio
async def test_l1_context_builder_injects_phase_navigation_for_experiment_design(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Session()
    session.add_message("user", "请帮我做实验设计并估算样本量")
    builder = ContextBuilder(tool_registry=create_default_tool_registry())

    monkeypatch.setattr(
        builder, "build_intent_runtime_context", lambda _msg, intent_analysis=None: ""
    )
    monkeypatch.setattr(builder, "build_explicit_tool_context", lambda _msg: "")
    monkeypatch.setattr(
        builder,
        "_inject_knowledge",
        AsyncMock(return_value=None),
        raising=False,
    )
    monkeypatch.setattr(
        "nini.agent.components.context_builder.list_session_analysis_memories",
        lambda session_id: [],
    )
    monkeypatch.setattr(
        "nini.agent.components.context_builder.build_research_profile_context",
        lambda session, default_profile_id, get_profile_manager: "",
    )

    messages, _ = await builder.build_messages_and_retrieval(session)
    runtime_context = messages[1]["content"]

    assert "current_phase: experiment_design" in runtime_context
    assert "recommended_capabilities: research_planning" in runtime_context
    assert "recommended_skills: experiment-design-helper" in runtime_context


@pytest.mark.asyncio
async def test_l1_context_builder_keeps_data_analysis_recommendation_stable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Session()
    session.add_message("user", "请分析这个数据集并做回归")
    builder = ContextBuilder(tool_registry=create_default_tool_registry())

    monkeypatch.setattr(
        builder, "build_intent_runtime_context", lambda _msg, intent_analysis=None: ""
    )
    monkeypatch.setattr(builder, "build_explicit_tool_context", lambda _msg: "")
    monkeypatch.setattr(
        builder,
        "_inject_knowledge",
        AsyncMock(return_value=None),
        raising=False,
    )
    monkeypatch.setattr(
        "nini.agent.components.context_builder.list_session_analysis_memories",
        lambda session_id: [],
    )
    monkeypatch.setattr(
        "nini.agent.components.context_builder.build_research_profile_context",
        lambda session, default_profile_id, get_profile_manager: "",
    )

    messages, _ = await builder.build_messages_and_retrieval(session)
    runtime_context = messages[1]["content"]

    assert "current_phase: data_analysis" in runtime_context
    assert "difference_analysis" in runtime_context
    assert "regression_analysis" in runtime_context
    assert "recommended_skills" not in runtime_context
    assert "experiment-design-helper" not in runtime_context
    assert "literature-review" not in runtime_context
    assert "writing-guide" not in runtime_context
