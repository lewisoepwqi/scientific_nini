"""Prompt 改进回归测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from nini.agent.prompts.scientific import get_system_prompt
from nini.config import settings


class TestFewShotExamples:
    def test_error_examples_exist_in_pdca_detail_block(
        self,
        tmp_path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """验证错误示例已迁移到 PDCA_DETAIL_BLOCK（按意图条件注入）。"""
        from nini.agent.prompt_policy import PDCA_DETAIL_BLOCK

        monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
        settings.ensure_dirs()
        # 错误示例已从 system prompt 中移出，在 PDCA_DETAIL_BLOCK 中
        assert "错误示例 6" in PDCA_DETAIL_BLOCK
        assert "错误示例 7" in PDCA_DETAIL_BLOCK
        assert "缺失值" in PDCA_DETAIL_BLOCK
        assert "异常值" in PDCA_DETAIL_BLOCK
        assert "任务1 自动开始" not in PDCA_DETAIL_BLOCK
        assert "前一个 in_progress 的任务会自动标记为 completed" not in PDCA_DETAIL_BLOCK
        # system prompt 中不再包含错误示例（减少非分析任务的 context 开销）
        prompt = get_system_prompt()
        assert "错误示例 6" not in prompt
        assert "错误示例 7" not in prompt

    def test_base_tools_mentioned_in_prompt(
        self,
        tmp_path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """验证新基础工具层在系统提示词中被提及。"""
        monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
        settings.ensure_dirs()
        prompt = get_system_prompt()
        # 验证基础工具名在提示词中
        assert "dataset_catalog" in prompt
        assert "dataset_transform" in prompt
        assert "stat_test" in prompt
        assert "chart_session" in prompt
        assert "code_session" in prompt
        # 验证资源引用规则
        assert "resource_id" in prompt
        assert ".nini/skills" in prompt
        assert "不要再次调用 workspace_session 读取 SKILL.md" in prompt
        assert "当系统已注入某个技能的 skill_definition 运行时上下文时" in prompt
        assert "`code_session`、`chart_session`、`run_code` 是工具，不是 agent_id" in prompt
        assert "必须先读取该技能定义文件" not in prompt


def test_prompt_component_files_do_not_describe_implicit_task_progression() -> None:
    """任务提示词组件不应再描述 init 自动开始或 update 自动完成。"""
    repo_root = Path(__file__).resolve().parents[1]
    strategy_core = (repo_root / "data" / "prompt_components" / "strategy_core.md").read_text(
        encoding="utf-8"
    )
    strategy_task = (repo_root / "data" / "prompt_components" / "strategy_task.md").read_text(
        encoding="utf-8"
    )

    combined = strategy_core + "\n" + strategy_task
    assert "任务1 自动开始" not in combined
    assert "自动将任务1 设为 in_progress" not in combined
    assert "当前任务自动完成" not in combined
    assert "自动将当前 in_progress 的任务标记为 completed" not in combined
    assert "init 只负责声明任务" in combined
