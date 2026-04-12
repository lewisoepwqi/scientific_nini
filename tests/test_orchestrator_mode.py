"""测试 Orchestrator 模式 —— dispatch_agents 拦截、工具暴露控制。"""

from __future__ import annotations

import pytest

from nini.agent.runner import AgentRunner, ORCHESTRATOR_TOOL_NAMES
from nini.agent.sub_session import SubSession

# ─── 辅助 ───────────────────────────────────────────────────────────────────


def _make_runner_with_dispatch_registered():
    """构建已注册 dispatch_agents 工具的 AgentRunner。"""
    from nini.agent.spawner import SubAgentResult
    from nini.tools.dispatch_agents import DispatchAgentsTool
    from nini.tools.registry import ToolRegistry

    class _MockRegistry:
        def list_agents(self):
            return [type("Def", (), {"agent_id": "literature_search"})()]

    class _MockSpawner:
        async def spawn_batch(self, tasks, session, **kwargs):
            return [SubAgentResult(agent_id=aid, success=True, summary="完成") for aid, _ in tasks]

    tool = DispatchAgentsTool(
        agent_registry=_MockRegistry(),
        spawner=_MockSpawner(),
    )
    registry = ToolRegistry()
    registry._tools.clear()
    registry._llm_exposed_function_tools = set()
    registry._tools["dispatch_agents"] = tool
    # 不加入 _llm_exposed_function_tools，由 Orchestrator 路径控制

    return AgentRunner(tool_registry=registry)


def _make_sub_session():
    """构建最小 SubSession 实例。"""
    return SubSession(
        parent_session_id="parent-123",
        datasets={},
        artifacts={},
        documents={},
        event_callback=None,
    )


def _make_plain_session(tmp_path):
    """构建最小主 Session 实例（使用临时路径避免磁盘写入）。"""
    from nini.agent.session import Session
    from unittest.mock import patch

    with patch("nini.config.settings.data_dir", tmp_path):
        return Session(id="main-session-001")


# ─── ORCHESTRATOR_TOOL_NAMES 常量 ────────────────────────────────────────────


def test_orchestrator_tool_names_contains_dispatch_agents():
    """ORCHESTRATOR_TOOL_NAMES 包含 dispatch_agents。"""
    assert "dispatch_agents" in ORCHESTRATOR_TOOL_NAMES


# ─── 子 Agent 不暴露 dispatch_agents ────────────────────────────────────────


def test_sub_session_does_not_expose_dispatch_agents():
    """SubSession 时 _get_tool_definitions 不包含 dispatch_agents。"""
    runner = _make_runner_with_dispatch_registered()
    sub_session = _make_sub_session()

    tool_defs = runner._get_tool_definitions(session=sub_session)
    names = {
        t.get("function", {}).get("name") for t in tool_defs if isinstance(t.get("function"), dict)
    }
    assert "dispatch_agents" not in names, "子 Agent 不应暴露 dispatch_agents，防止递归派发"


# ─── 主 Agent 暴露 dispatch_agents ──────────────────────────────────────────


def test_main_session_exposes_dispatch_agents(tmp_path):
    """非 SubSession 时 _get_tool_definitions 包含 dispatch_agents。"""
    runner = _make_runner_with_dispatch_registered()
    plain_session = _make_plain_session(tmp_path)

    tool_defs = runner._get_tool_definitions(session=plain_session)
    names = {
        t.get("function", {}).get("name") for t in tool_defs if isinstance(t.get("function"), dict)
    }
    assert "dispatch_agents" in names, "主 Agent 应暴露 dispatch_agents 工具"


def test_none_session_exposes_dispatch_agents():
    """session=None（向后兼容）时应暴露 dispatch_agents（视为主 Agent）。"""
    runner = _make_runner_with_dispatch_registered()
    tool_defs = runner._get_tool_definitions(session=None)
    names = {
        t.get("function", {}).get("name") for t in tool_defs if isinstance(t.get("function"), dict)
    }
    assert "dispatch_agents" in names


def test_sub_session_keeps_subset_tools_without_stage_filter():
    """子会话应直接使用 subset registry，不再被主 Agent 阶段策略二次裁剪。"""
    from nini.tools.registry import ToolRegistry

    class _SubsetOnlyTool:
        name = "code_session"
        description = "代码会话"
        category = "utility"
        expose_to_llm = True
        parameters = {"type": "object", "properties": {}, "additionalProperties": False}

        def get_tool_definition(self):
            return {
                "type": "function",
                "function": {
                    "name": "code_session",
                    "description": "代码会话",
                    "parameters": self.parameters,
                },
            }

    registry = ToolRegistry()
    registry._tools.clear()
    registry._llm_exposed_function_tools = {"code_session"}
    registry._tools["code_session"] = _SubsetOnlyTool()

    runner = AgentRunner(tool_registry=registry)
    sub_session = _make_sub_session()
    tool_defs = runner._get_tool_definitions(session=sub_session)
    names = {
        t.get("function", {}).get("name") for t in tool_defs if isinstance(t.get("function"), dict)
    }
    assert "code_session" in names


# ─── Orchestrator 钩子拦截 ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_dispatch_agents_produces_tool_result_event():
    """_handle_dispatch_agents 应产生至少一个 tool_result 事件。"""
    from nini.agent.events import EventType

    runner = _make_runner_with_dispatch_registered()
    sub_session = _make_sub_session()

    dispatch_tc = {
        "id": "call-123",
        "function": {
            "name": "dispatch_agents",
            "arguments": '{"agents": [{"agent_id": "literature_search", "task": "检索文献"}]}',
        },
    }

    events = []
    async for evt in runner._handle_dispatch_agents(dispatch_tc, sub_session, "turn-001"):
        events.append(evt)

    # 应产生 tool_result 事件
    event_types = [e.type for e in events]
    assert EventType.TOOL_RESULT in event_types or len(events) > 0
    tool_result_event = next(
        event for event in events if getattr(event, "type", None) == EventType.TOOL_RESULT
    )
    result_payload = tool_result_event.data["data"]["result"]["metadata"]
    assert result_payload["dispatch_run_id"] == "dispatch:call-123"
    assert result_payload["agent_count"] == 1
    assert result_payload["success_count"] == 1


@pytest.mark.asyncio
async def test_handle_dispatch_agents_injects_tool_result_to_session():
    """_handle_dispatch_agents 完成后 session 应包含 tool_result 消息。"""
    runner = _make_runner_with_dispatch_registered()
    sub_session = _make_sub_session()

    dispatch_tc = {
        "id": "call-456",
        "function": {
            "name": "dispatch_agents",
            "arguments": '{"agents": [{"agent_id": "literature_search", "task": "统计分析"}]}',
        },
    }

    async for _ in runner._handle_dispatch_agents(dispatch_tc, sub_session, "turn-002"):
        pass

    # 会话消息中应有 tool_result
    tool_result_msgs = [
        m
        for m in sub_session.messages
        if m.get("role") == "tool" and m.get("tool_call_id") == "call-456"
    ]
    assert len(tool_result_msgs) >= 1


@pytest.mark.asyncio
async def test_handle_dispatch_agents_no_registry_yields_error_event():
    """ToolRegistry 未初始化时 _handle_dispatch_agents 仍 yield 错误事件，不抛出异常。"""
    runner = AgentRunner(tool_registry=None)
    sub_session = _make_sub_session()

    dispatch_tc = {
        "id": "call-789",
        "function": {
            "name": "dispatch_agents",
            "arguments": '{"agents": [{"agent_id": "literature_search", "task": "任务"}]}',
        },
    }

    events = []
    async for evt in runner._handle_dispatch_agents(dispatch_tc, sub_session, "turn-003"):
        events.append(evt)

    # 应产生至少一个事件（错误事件）
    assert len(events) >= 1
