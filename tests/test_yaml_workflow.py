"""YAML 声明式工作流安全校验测试。"""

from __future__ import annotations

import pytest

from nini.workflow.validator import detect_cycle, safe_resolve_reference, validate_yaml_workflow


class TestYAMLWorkflow:
    def test_yaml_injection_blocked(self) -> None:
        """验证 YAML 注入攻击被拦截。"""
        yaml_text = """
version: "1.0"
kind: "WorkflowTemplate"
steps:
  - id: s1
    skill: run_code
    parameters:
      code: "${__import__('os').system('rm -rf /')}"
"""
        result = validate_yaml_workflow(yaml_text)
        assert len(result.errors) > 0
        assert any("危险参数模式" in err or "非法命名空间" in err for err in result.errors)

    def test_cycle_detection(self) -> None:
        """验证循环依赖检测。"""
        steps = [
            {"id": "a", "depends_on": ["b"]},
            {"id": "b", "depends_on": ["c"]},
            {"id": "c", "depends_on": ["a"]},
        ]
        assert detect_cycle(steps) is True

    def test_allowed_namespaces(self) -> None:
        """验证仅允许三个命名空间。"""
        with pytest.raises(ValueError):
            safe_resolve_reference("evil.xxx", {})

        result = safe_resolve_reference("params.dataset", {"params": {"dataset": "test"}})
        assert result == "test"
