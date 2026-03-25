"""工具调用 Guardrail 框架测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from nini.tools.guardrails import (
    DangerousPatternGuardrail,
    GuardrailAction,
    GuardrailDecision,
    ToolGuardrail,
)
from nini.tools.registry import ToolRegistry

# ---------------------------------------------------------------------------
# DangerousPatternGuardrail 单元测试
# ---------------------------------------------------------------------------


class TestDangerousPatternGuardrail:
    """测试危险模式拦截规则。"""

    def setup_method(self):
        self.guardrail = DangerousPatternGuardrail()

    # 规则 1：clean_data + inplace=True + raw dataset

    def test_clean_data_inplace_raw_dataset_blocked(self):
        """clean_data + inplace=True + dataset 名含 _raw → BLOCK。"""
        decision = self.guardrail.evaluate(
            "clean_data",
            {"dataset_name": "experiment_raw", "inplace": True},
        )
        assert decision.decision == GuardrailAction.BLOCK
        assert "experiment_raw" in decision.reason

    def test_clean_data_inplace_original_dataset_blocked(self):
        """clean_data + inplace=True + dataset 名含 _original → BLOCK。"""
        decision = self.guardrail.evaluate(
            "clean_data",
            {"dataset_name": "survey_original", "inplace": True},
        )
        assert decision.decision == GuardrailAction.BLOCK

    def test_clean_data_inplace_original_keyword_blocked(self):
        """clean_data + inplace=True + dataset 名含 original → BLOCK。"""
        decision = self.guardrail.evaluate(
            "clean_data",
            {"dataset_name": "original_data", "inplace": True},
        )
        assert decision.decision == GuardrailAction.BLOCK

    def test_clean_data_inplace_false_allowed(self):
        """clean_data + inplace=False → ALLOW，不影响正常操作。"""
        decision = self.guardrail.evaluate(
            "clean_data",
            {"dataset_name": "experiment_raw", "inplace": False},
        )
        assert decision.decision == GuardrailAction.ALLOW

    def test_clean_data_non_raw_dataset_inplace_allowed(self):
        """clean_data + inplace=True 但 dataset 名不含 raw/original → ALLOW。"""
        decision = self.guardrail.evaluate(
            "clean_data",
            {"dataset_name": "cleaned_data", "inplace": True},
        )
        assert decision.decision == GuardrailAction.ALLOW

    # 规则 2：organize_workspace 批量删除

    def test_organize_workspace_delete_all_blocked(self):
        """organize_workspace + delete_all=True → BLOCK。"""
        decision = self.guardrail.evaluate(
            "organize_workspace",
            {"delete_all": True},
        )
        assert decision.decision == GuardrailAction.BLOCK

    def test_organize_workspace_wildcard_pattern_blocked(self):
        """organize_workspace + pattern='*' → BLOCK。"""
        decision = self.guardrail.evaluate(
            "organize_workspace",
            {"pattern": "*"},
        )
        assert decision.decision == GuardrailAction.BLOCK

    def test_organize_workspace_normal_allowed(self):
        """organize_workspace 正常参数 → ALLOW。"""
        decision = self.guardrail.evaluate(
            "organize_workspace",
            {"pattern": "*.csv"},
        )
        assert decision.decision == GuardrailAction.ALLOW

    # 规则 3：系统路径

    def test_system_path_etc_blocked(self):
        """参数含 /etc/ 路径 → BLOCK。"""
        decision = self.guardrail.evaluate(
            "fetch_url",
            {"url": "/etc/passwd"},
        )
        assert decision.decision == GuardrailAction.BLOCK

    def test_system_path_sys_blocked(self):
        """参数含 /sys/ 路径 → BLOCK。"""
        decision = self.guardrail.evaluate(
            "run_code",
            {"code": "open('/sys/kernel/notes')"},
        )
        assert decision.decision == GuardrailAction.BLOCK

    def test_system_path_ssh_blocked(self):
        """参数含 ~/.ssh/ 路径 → BLOCK。"""
        decision = self.guardrail.evaluate(
            "load_dataset",
            {"path": "~/.ssh/id_rsa"},
        )
        assert decision.decision == GuardrailAction.BLOCK

    def test_system_path_proc_blocked(self):
        """参数含 /proc/ 路径 → BLOCK。"""
        decision = self.guardrail.evaluate(
            "run_code",
            {"file_path": "/proc/self/environ"},
        )
        assert decision.decision == GuardrailAction.BLOCK

    def test_normal_tool_call_allowed(self):
        """普通工具调用 → ALLOW。"""
        decision = self.guardrail.evaluate(
            "load_dataset",
            {"path": "/home/user/data/result.csv"},
        )
        assert decision.decision == GuardrailAction.ALLOW


# ---------------------------------------------------------------------------
# ToolRegistry 集成测试
# ---------------------------------------------------------------------------


class TestToolRegistryGuardrailIntegration:
    """测试 ToolRegistry.execute() 的 guardrail 集成。"""

    def _make_registry_with_mock_tool(self) -> tuple[ToolRegistry, MagicMock]:
        """创建包含 mock 工具的 ToolRegistry 实例。"""
        registry = ToolRegistry()
        # 清空默认工具，只注册一个 mock 工具
        registry._tools.clear()

        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.execute = AsyncMock(
            return_value=MagicMock(to_dict=lambda: {"success": True, "message": "ok"})
        )
        registry._tools["test_tool"] = mock_tool
        return registry, mock_tool

    @pytest.mark.asyncio
    async def test_block_returns_failure_dict_without_calling_execute(self):
        """guardrail BLOCK 时，execute() 返回 success=False，不调用 Tool.execute()。"""
        registry, mock_tool = self._make_registry_with_mock_tool()

        # 注入一个始终 BLOCK 的 guardrail
        class AlwaysBlockGuardrail(ToolGuardrail):
            def evaluate(self, tool_name, kwargs):
                return GuardrailDecision(decision=GuardrailAction.BLOCK, reason="测试拦截")

        # 替换默认 guardrail 链
        registry._guardrails = [AlwaysBlockGuardrail()]

        result = await registry.execute("test_tool", session=None)  # type: ignore[arg-type]

        assert result["success"] is False
        assert "测试拦截" in result["message"]
        mock_tool.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_allow_calls_tool_execute(self):
        """guardrail ALLOW 时，execute() 正常调用 Tool.execute()。"""
        registry, mock_tool = self._make_registry_with_mock_tool()

        # 注入一个始终 ALLOW 的 guardrail
        class AlwaysAllowGuardrail(ToolGuardrail):
            def evaluate(self, tool_name, kwargs):
                return GuardrailDecision(decision=GuardrailAction.ALLOW)

        registry._guardrails = [AlwaysAllowGuardrail()]

        mock_session = MagicMock()
        result = await registry.execute("test_tool", session=mock_session)

        # Tool.execute 被调用（通过 _execute_tool_in_thread → lane_queue）
        # 此处验证调用未被拦截，返回 success=True
        assert result.get("success") is True

    @pytest.mark.asyncio
    async def test_default_guardrail_chain_contains_dangerous_pattern_guardrail(self):
        """默认 guardrail 链包含 DangerousPatternGuardrail 实例。"""
        registry = ToolRegistry()
        assert any(isinstance(g, DangerousPatternGuardrail) for g in registry._guardrails)

    @pytest.mark.asyncio
    async def test_add_guardrail_appends_to_chain(self):
        """add_guardrail() 将新规则追加到链末尾。"""
        registry = ToolRegistry()
        initial_count = len(registry._guardrails)

        class ExtraGuardrail(ToolGuardrail):
            def evaluate(self, tool_name, kwargs):
                return GuardrailDecision(decision=GuardrailAction.ALLOW)

        extra = ExtraGuardrail()
        registry.add_guardrail(extra)

        assert len(registry._guardrails) == initial_count + 1
        assert registry._guardrails[-1] is extra
