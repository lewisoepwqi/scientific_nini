"""测试 markdown_scanner 的契约解析：带 contract 的 Skill、无 contract 兼容、格式错误降级。"""

import textwrap
from pathlib import Path

import pytest

from nini.models.skill_contract import SkillContract
from nini.tools.markdown_scanner import scan_markdown_tools


def write_skill(tmp_path: Path, content: str) -> Path:
    """在临时目录创建 SKILL.md 并返回其所在 skills 根目录。"""
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    return tmp_path


class TestScannerContractParsing:
    def test_skill_with_contract_parsed(self, tmp_path: Path) -> None:
        content = textwrap.dedent(
            """\
            ---
            name: experiment-design-helper
            description: 实验设计辅助技能
            category: workflow
            contract:
              version: "1"
              trust_ceiling: t1
              steps:
                - id: define_problem
                  name: 问题定义
                  description: 明确研究假设和变量
                  trust_level: t1
                - id: choose_design
                  name: 设计选择
                  description: 选择实验设计类型
                  depends_on: [define_problem]
                  trust_level: t1
            ---
            实验设计辅助工作流正文。
            """
        )
        root = write_skill(tmp_path, content)
        tools = scan_markdown_tools(root)

        assert len(tools) == 1
        tool = tools[0]
        assert "contract" in tool.metadata
        contract = tool.metadata["contract"]
        assert isinstance(contract, SkillContract)
        assert len(contract.steps) == 2
        assert contract.steps[0].id == "define_problem"
        assert contract.steps[1].depends_on == ["define_problem"]

    def test_skill_without_contract_unaffected(self, tmp_path: Path) -> None:
        content = textwrap.dedent(
            """\
            ---
            name: legacy-skill
            description: 旧式 Skill，无 contract
            category: utility
            ---
            旧式 Skill 正文。
            """
        )
        root = write_skill(tmp_path, content)
        tools = scan_markdown_tools(root)

        assert len(tools) == 1
        tool = tools[0]
        assert "contract" not in tool.metadata
        assert tool.name == "legacy-skill"

    def test_malformed_contract_degrades_gracefully(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """contract 格式错误时记录警告，Skill 正常创建但不含 contract 键。"""
        content = textwrap.dedent(
            """\
            ---
            name: broken-skill
            description: contract 格式错误的 Skill
            category: workflow
            contract:
              version: "1"
              steps:
                - id: step_a
                  name: 步骤 A
                  description: 合法步骤
                  depends_on: [nonexistent_step]
            ---
            正文内容。
            """
        )
        root = write_skill(tmp_path, content)
        import logging

        with caplog.at_level(logging.WARNING, logger="nini.tools.markdown_scanner"):
            tools = scan_markdown_tools(root)

        assert len(tools) == 1
        tool = tools[0]
        # contract 解析失败，不应出现在 metadata 中
        assert "contract" not in tool.metadata
        # 应该有警告日志
        assert any("contract" in record.message for record in caplog.records)

    def test_contract_with_review_gate_parsed(self, tmp_path: Path) -> None:
        content = textwrap.dedent(
            """\
            ---
            name: guarded-skill
            description: 带 review_gate 的 Skill
            category: workflow
            contract:
              version: "1"
              trust_ceiling: t1
              steps:
                - id: prepare
                  name: 准备
                  description: 准备数据
                  trust_level: t1
                - id: analyze
                  name: 分析
                  description: 执行分析
                  depends_on: [prepare]
                  review_gate: true
                  trust_level: t1
            ---
            带 review_gate 的工作流。
            """
        )
        root = write_skill(tmp_path, content)
        tools = scan_markdown_tools(root)

        assert len(tools) == 1
        contract = tools[0].metadata["contract"]
        assert isinstance(contract, SkillContract)
        assert contract.steps[1].review_gate is True


class TestToolAdapterRouting:
    def test_has_contract_true_for_skill_with_contract(self, tmp_path: Path) -> None:
        content = textwrap.dedent(
            """\
            ---
            name: contract-skill
            description: 有契约
            category: workflow
            contract:
              version: "1"
              trust_ceiling: t1
              steps:
                - id: only_step
                  name: 唯一步骤
                  description: 只有一步
            ---
            正文。
            """
        )
        root = write_skill(tmp_path, content)
        from nini.tools.tool_adapter import has_contract

        tools = scan_markdown_tools(root)
        assert has_contract(tools[0]) is True

    def test_has_contract_false_for_legacy_skill(self, tmp_path: Path) -> None:
        content = textwrap.dedent(
            """\
            ---
            name: old-skill
            description: 旧式
            category: utility
            ---
            旧式 Skill。
            """
        )
        root = write_skill(tmp_path, content)
        from nini.tools.tool_adapter import has_contract

        tools = scan_markdown_tools(root)
        assert has_contract(tools[0]) is False
