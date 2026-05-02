"""测试 AgentRegistry 的初始化与功能。"""

import logging
import textwrap
from pathlib import Path

import pytest

from nini.agent.registry import AgentDefinition, AgentRegistry


def test_builtin_agents_loaded():
    """初始化后应加载 9 个内置 Agent。"""
    registry = AgentRegistry()
    agents = registry.list_agents()
    assert len(agents) >= 9


def test_research_planner_not_dispatchable():
    """research_planner 仍保留注册，但不应出现在可派发 specialist 列表中。"""
    registry = AgentRegistry()
    planner = registry.get("research_planner")
    assert planner is not None
    assert planner.dispatchable is False
    dispatchable_ids = {agent.agent_id for agent in registry.list_dispatchable_agents()}
    assert "research_planner" not in dispatchable_ids


def test_get_known_agent():
    registry = AgentRegistry()
    agent = registry.get("data_cleaner")
    assert agent is not None
    assert agent.agent_id == "data_cleaner"
    assert agent.name != ""


def test_get_nonexistent_returns_none():
    registry = AgentRegistry()
    assert registry.get("nonexistent_agent") is None


def test_agent_definition_defaults():
    defn = AgentDefinition(
        agent_id="test",
        name="测试",
        description="测试用",
        system_prompt="你是测试助手",
        purpose="default",
    )
    assert defn.paradigm == "react"
    assert defn.max_tokens == 8000
    assert defn.allowed_tools == []


def test_custom_yaml_override(tmp_path, monkeypatch):
    """自定义 YAML 应覆盖同名内置 Agent。"""
    import nini.agent.registry as reg_module

    custom_dir = tmp_path / "agents"
    custom_dir.mkdir()
    yaml_content = textwrap.dedent(
        """
        agent_id: data_cleaner
        name: 自定义数据清洗
        description: 覆盖版本
        system_prompt: 覆盖
        purpose: analysis
        allowed_tools: []
    """
    )
    (custom_dir / "data_cleaner.yaml").write_text(yaml_content, encoding="utf-8")
    monkeypatch.setattr(reg_module, "_CUSTOM_AGENTS_DIR", custom_dir)

    registry = AgentRegistry()
    agent = registry.get("data_cleaner")
    assert agent is not None
    assert agent.name == "自定义数据清洗"


def test_invalid_tool_warning(caplog):
    """无效工具名应记录 WARNING。"""
    with caplog.at_level(logging.WARNING, logger="nini.agent.registry"):
        registry = AgentRegistry()
        from nini.tools.registry import create_default_tool_registry

        registry._tool_registry = create_default_tool_registry()
        defn = AgentDefinition(
            agent_id="test_warn",
            name="测试警告",
            description="",
            system_prompt="",
            purpose="default",
            allowed_tools=["nonexistent_tool_xyz"],
        )
        registry.register(defn)
    assert any("nonexistent_tool_xyz" in r.message for r in caplog.records)
    # Agent 仍应注册
    assert registry.get("test_warn") is not None
