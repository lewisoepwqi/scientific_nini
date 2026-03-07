"""Prompt 改进回归测试。"""

from __future__ import annotations

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
        # 错误示例已从 system prompt 中移出，在 PDCA_DETAIL_BLOCK 中
        assert "错误示例 6" in PDCA_DETAIL_BLOCK
        assert "错误示例 7" in PDCA_DETAIL_BLOCK
        assert "缺失值" in PDCA_DETAIL_BLOCK
        assert "异常值" in PDCA_DETAIL_BLOCK
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
        assert "不要再次调用 workspace_session 去读取 SKILL.md" in prompt
