"""Prompt 改进回归测试。"""

from __future__ import annotations

import pytest

from nini.agent.prompts.scientific import get_system_prompt
from nini.config import settings


class TestFewShotExamples:
    def test_error_examples_exist_in_prompt(
        self,
        tmp_path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """验证错误示例已注入 prompt。"""
        monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
        prompt = get_system_prompt()
        assert "错误示例 6" in prompt
        assert "错误示例 7" in prompt
        assert "缺失值" in prompt
        assert "异常值" in prompt

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
