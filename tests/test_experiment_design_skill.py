"""experiment-design-helper Markdown Skill 集成测试。

验证：
1. scan_markdown_tools 能正确发现并解析 SKILL.md
2. contract 字段可解析为 SkillContract 实例
3. 四步骤 DAG 顺序正确（define_problem → choose_design → calculate_params → generate_plan）
4. generate_plan 步骤有 review_gate=true
5. trust_ceiling 为 t1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nini.tools.markdown_scanner import scan_markdown_tools

# ---------------------------------------------------------------------------
# 工具函数：拓扑排序（Kahn 算法），返回步骤 id 有序列表
# ---------------------------------------------------------------------------


def _topological_sort(steps: list) -> list[str]:
    """对 SkillStep 列表做拓扑排序，返回有序 step id 列表。"""
    from collections import deque

    in_degree: dict[str, int] = {s.id: 0 for s in steps}
    adj: dict[str, list[str]] = {s.id: [] for s in steps}

    for step in steps:
        for dep in step.depends_on:
            adj[dep].append(step.id)
            in_degree[step.id] += 1

    queue: deque[str] = deque(s.id for s in steps if in_degree[s.id] == 0)
    result: list[str] = []
    while queue:
        node = queue.popleft()
        result.append(node)
        for neighbor in adj[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
    return result


# ---------------------------------------------------------------------------
# Markdown Skill 扫描与解析测试
# ---------------------------------------------------------------------------


class TestExperimentDesignSkillDiscovery:
    """测试 Skill 可被扫描器发现。"""

    def test_skill_is_discoverable(self) -> None:
        """experiment-design-helper/SKILL.md 能被扫描器正确发现。"""
        skills_dir = Path(__file__).parent.parent / ".nini" / "skills"
        skills = scan_markdown_tools(skills_dir)
        names = [s.name for s in skills]
        assert (
            "experiment_design_helper" in names or "experiment-design-helper" in names
        ), f"期望找到 experiment_design_helper，实际找到: {names}"

    def test_skill_frontmatter_fields(self) -> None:
        """experiment-design-helper Skill 的 frontmatter 包含必要字段。"""
        skills_dir = Path(__file__).parent.parent / ".nini" / "skills"
        skills = scan_markdown_tools(skills_dir)
        skill = next(
            (
                s
                for s in skills
                if s.name in ("experiment_design_helper", "experiment-design-helper")
            ),
            None,
        )
        assert skill is not None, "experiment-design-helper skill 未找到"
        assert skill.description, "description 不能为空"
        assert (
            skill.category == "experiment_design"
        ), f"期望 category=experiment_design，实际: {skill.category}"

    def test_skill_has_instruction_body(self) -> None:
        """SKILL.md 正文（工作流说明）不能为空。"""
        from nini.tools.markdown_scanner import get_markdown_tool_instruction

        skill_path = (
            Path(__file__).parent.parent
            / ".nini"
            / "skills"
            / "experiment-design-helper"
            / "SKILL.md"
        )
        assert skill_path.exists(), f"SKILL.md 不存在: {skill_path}"

        payload = get_markdown_tool_instruction(skill_path)
        instruction = payload.get("instruction", "")
        assert len(instruction) > 200, "工作流说明内容过短，可能未正确读取"
        # 验证四步骤章节存在
        assert "define_problem" in instruction or "问题定义" in instruction
        assert "generate_plan" in instruction or "方案生成" in instruction


# ---------------------------------------------------------------------------
# Contract 解析测试
# ---------------------------------------------------------------------------


class TestSkillContract:
    """测试 Skill contract 可被正确解析。"""

    @pytest.fixture
    def skill(self):
        """返回 experiment-design-helper MarkdownTool 实例。"""
        skills_dir = Path(__file__).parent.parent / ".nini" / "skills"
        skills = scan_markdown_tools(skills_dir)
        skill = next(
            (
                s
                for s in skills
                if s.name in ("experiment_design_helper", "experiment-design-helper")
            ),
            None,
        )
        assert skill is not None, "experiment-design-helper skill 未找到"
        return skill

    def test_contract_is_parsed(self, skill) -> None:
        """metadata['contract'] 应为有效的 SkillContract 实例。"""
        from nini.models.skill_contract import SkillContract

        contract = skill.metadata.get("contract")
        assert contract is not None, "contract 字段未解析，检查 SKILL.md 的 frontmatter"
        assert isinstance(
            contract, SkillContract
        ), f"contract 类型错误，期望 SkillContract，实际: {type(contract)}"

    def test_contract_has_four_steps(self, skill) -> None:
        """contract 应包含 4 个步骤。"""
        from nini.models.skill_contract import SkillContract

        contract: SkillContract = skill.metadata["contract"]
        assert (
            len(contract.steps) == 4
        ), f"期望 4 个步骤，实际: {len(contract.steps)}。步骤 id: {[s.id for s in contract.steps]}"

    def test_contract_trust_ceiling_is_t1(self, skill) -> None:
        """contract 的 trust_ceiling 应为 t1。"""
        from nini.models.risk import TrustLevel
        from nini.models.skill_contract import SkillContract

        contract: SkillContract = skill.metadata["contract"]
        assert (
            contract.trust_ceiling == TrustLevel.T1
        ), f"期望 trust_ceiling=t1，实际: {contract.trust_ceiling}"

    def test_step_ids_are_correct(self, skill) -> None:
        """contract 的四个步骤 id 应为预期值。"""
        from nini.models.skill_contract import SkillContract

        contract: SkillContract = skill.metadata["contract"]
        step_ids = {s.id for s in contract.steps}
        expected_ids = {"define_problem", "choose_design", "calculate_params", "generate_plan"}
        assert step_ids == expected_ids, f"步骤 id 不匹配。期望: {expected_ids}，实际: {step_ids}"

    def test_topological_order_is_correct(self, skill) -> None:
        """拓扑排序结果应为 define_problem → choose_design → calculate_params → generate_plan。"""
        from nini.models.skill_contract import SkillContract

        contract: SkillContract = skill.metadata["contract"]
        order = _topological_sort(contract.steps)

        expected_order = ["define_problem", "choose_design", "calculate_params", "generate_plan"]
        assert order == expected_order, f"步骤顺序不正确。期望: {expected_order}，实际: {order}"

    def test_generate_plan_has_review_gate(self, skill) -> None:
        """generate_plan 步骤的 review_gate 应为 True。"""
        from nini.models.skill_contract import SkillContract

        contract: SkillContract = skill.metadata["contract"]
        generate_plan_step = next((s for s in contract.steps if s.id == "generate_plan"), None)
        assert generate_plan_step is not None, "未找到 generate_plan 步骤"
        assert generate_plan_step.review_gate is True, "generate_plan 步骤的 review_gate 应为 True"

    def test_non_generate_plan_steps_have_no_review_gate(self, skill) -> None:
        """其他步骤的 review_gate 应为 False。"""
        from nini.models.skill_contract import SkillContract

        contract: SkillContract = skill.metadata["contract"]
        for step in contract.steps:
            if step.id != "generate_plan":
                assert (
                    step.review_gate is False
                ), f"步骤 '{step.id}' 的 review_gate 应为 False，实际为 True"

    def test_linear_dag_dependencies(self, skill) -> None:
        """验证线性 DAG 依赖关系正确。"""
        from nini.models.skill_contract import SkillContract

        contract: SkillContract = skill.metadata["contract"]
        deps: dict[str, list[str]] = {s.id: s.depends_on for s in contract.steps}

        assert deps["define_problem"] == [], "define_problem 不应有前置依赖"
        assert "define_problem" in deps["choose_design"], "choose_design 应依赖 define_problem"
        assert "choose_design" in deps["calculate_params"], "calculate_params 应依赖 choose_design"
        assert "calculate_params" in deps["generate_plan"], "generate_plan 应依赖 calculate_params"

    def test_all_steps_trust_level_within_ceiling(self, skill) -> None:
        """所有步骤的 trust_level 不应超过 trust_ceiling=t1。"""
        from nini.models.risk import TrustLevel
        from nini.models.skill_contract import SkillContract

        contract: SkillContract = skill.metadata["contract"]
        # 验证所有步骤的 trust_level 为 t1（SkillContract model_validator 已检验，此处双重确认）
        for step in contract.steps:
            assert (
                step.trust_level == TrustLevel.T1
            ), f"步骤 '{step.id}' 的 trust_level '{step.trust_level}' 超过了 ceiling t1"
