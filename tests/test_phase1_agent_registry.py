"""Phase 1：AgentDefinition.model_preference 字段解析测试。"""

from __future__ import annotations

import logging
import textwrap
from pathlib import Path

import pytest

from nini.agent.registry import AgentDefinition, AgentRegistry


# ─── AgentDefinition 默认值 ───────────────────────────────────────────────────


def test_agent_definition_model_preference_defaults_to_none():
    """AgentDefinition 未传 model_preference 时默认为 None。"""
    defn = AgentDefinition(
        agent_id="test",
        name="测试",
        description="测试用",
        system_prompt="你是测试助手",
        purpose="default",
    )
    assert defn.model_preference is None


# ─── YAML 解析：合法值 ────────────────────────────────────────────────────────


@pytest.mark.parametrize("value", ["haiku", "sonnet", "opus"])
def test_yaml_valid_model_preference_parsed(tmp_path, monkeypatch, value):
    """YAML 中合法 model_preference 值应被正确解析为字符串。"""
    import nini.agent.registry as reg_module

    builtin_dir = tmp_path / "builtin"
    builtin_dir.mkdir()
    yaml_content = textwrap.dedent(f"""
        agent_id: test_agent
        name: 测试 Agent
        description: 测试用
        system_prompt: 你是测试助手
        purpose: default
        model_preference: {value}
    """)
    (builtin_dir / "test_agent.yaml").write_text(yaml_content, encoding="utf-8")

    monkeypatch.setattr(reg_module, "_BUILTIN_AGENTS_DIR", builtin_dir)
    monkeypatch.setattr(reg_module, "_CUSTOM_AGENTS_DIR", tmp_path / "nonexistent")

    registry = AgentRegistry()
    agent = registry.get("test_agent")
    assert agent is not None
    assert agent.model_preference == value


# ─── YAML 解析：缺失字段 ──────────────────────────────────────────────────────


def test_yaml_missing_model_preference_defaults_to_none(tmp_path, monkeypatch):
    """YAML 中缺少 model_preference 时，AgentDefinition.model_preference 应为 None，不抛异常，不记录 WARNING。"""
    import nini.agent.registry as reg_module

    builtin_dir = tmp_path / "builtin"
    builtin_dir.mkdir()
    yaml_content = textwrap.dedent("""
        agent_id: test_agent
        name: 测试 Agent
        description: 测试用
        system_prompt: 你是测试助手
        purpose: default
    """)
    (builtin_dir / "test_agent.yaml").write_text(yaml_content, encoding="utf-8")

    monkeypatch.setattr(reg_module, "_BUILTIN_AGENTS_DIR", builtin_dir)
    monkeypatch.setattr(reg_module, "_CUSTOM_AGENTS_DIR", tmp_path / "nonexistent")

    registry = AgentRegistry()
    agent = registry.get("test_agent")
    assert agent is not None
    assert agent.model_preference is None


# ─── YAML 解析：非法值降级 ────────────────────────────────────────────────────


def test_yaml_invalid_model_preference_falls_back_to_none_with_warning(
    tmp_path, monkeypatch, caplog
):
    """YAML 中非法 model_preference（如 gpt4）应降级为 None，并记录 WARNING，不抛异常。"""
    import nini.agent.registry as reg_module

    builtin_dir = tmp_path / "builtin"
    builtin_dir.mkdir()
    yaml_content = textwrap.dedent("""
        agent_id: test_agent
        name: 测试 Agent
        description: 测试用
        system_prompt: 你是测试助手
        purpose: default
        model_preference: gpt4
    """)
    (builtin_dir / "test_agent.yaml").write_text(yaml_content, encoding="utf-8")

    monkeypatch.setattr(reg_module, "_BUILTIN_AGENTS_DIR", builtin_dir)
    monkeypatch.setattr(reg_module, "_CUSTOM_AGENTS_DIR", tmp_path / "nonexistent")

    with caplog.at_level(logging.WARNING, logger="nini.agent.registry"):
        registry = AgentRegistry()

    agent = registry.get("test_agent")
    assert agent is not None
    assert agent.model_preference is None
    assert any("model_preference" in record.message for record in caplog.records)
    assert any("gpt4" in record.message for record in caplog.records)


# ─── 内置 Agent 中的 model_preference ────────────────────────────────────────


def test_builtin_data_cleaner_has_haiku_preference():
    """内置 data_cleaner 应配置 model_preference=haiku。"""
    registry = AgentRegistry()
    agent = registry.get("data_cleaner")
    assert agent is not None
    assert agent.model_preference == "haiku"


def test_builtin_statistician_has_sonnet_preference():
    """内置 statistician 应配置 model_preference=sonnet。"""
    registry = AgentRegistry()
    agent = registry.get("statistician")
    assert agent is not None
    assert agent.model_preference == "sonnet"


def test_builtin_research_planner_has_no_preference():
    """内置 research_planner 不应设置 model_preference（继承父模型）。"""
    registry = AgentRegistry()
    agent = registry.get("research_planner")
    assert agent is not None
    assert agent.model_preference is None
