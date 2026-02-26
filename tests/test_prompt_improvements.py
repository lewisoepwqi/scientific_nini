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

    def test_anova_trigger_condition_in_prompt(
        self,
        tmp_path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """验证 ANOVA 触发条件为 p ≤ 0.05。"""
        monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
        prompt = get_system_prompt()
        assert "p<=0.05" in prompt or "p <= 0.05" in prompt
        assert "分组数>=3" in prompt or "3 组或更多" in prompt
