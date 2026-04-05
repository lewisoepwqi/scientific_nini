"""测试 SubAgentSpawner 的核心功能。"""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from nini.agent.spawner import SubAgentResult, SubAgentSpawner
from nini.agent.registry import AgentDefinition, AgentRegistry


def make_agent_def(agent_id: str = "test_agent") -> AgentDefinition:
    return AgentDefinition(
        agent_id=agent_id,
        name=f"测试 {agent_id}",
        description="测试用",
        system_prompt="你是测试助手",
        purpose="default",
        allowed_tools=["stat_test"],
        timeout_seconds=5,
    )


def make_mock_session() -> MagicMock:
    session = MagicMock()
    session.id = "parent_session_id"
    session.datasets = {}
    session.artifacts = {}
    session.documents = {}
    session.event_callback = None
    return session


def make_registry(agent_id: str = "test_agent") -> MagicMock:
    registry = MagicMock()
    registry.get.return_value = make_agent_def(agent_id)
    return registry


def make_tool_registry() -> MagicMock:
    tool_registry = MagicMock()
    tool_registry.create_subset.return_value = MagicMock()
    return tool_registry


@pytest.mark.asyncio
async def test_spawn_unknown_agent_returns_failure():
    registry = MagicMock()
    registry.get.return_value = None
    spawner = SubAgentSpawner(registry, make_tool_registry())
    result = await spawner.spawn("unknown_agent", "任务", make_mock_session())
    assert result.success is False
    assert result.agent_id == "unknown_agent"


@pytest.mark.asyncio
async def test_spawn_timeout_returns_failure():
    registry = make_registry()
    spawner = SubAgentSpawner(registry, make_tool_registry())

    async def slow_execute(*args, **kwargs):
        await asyncio.sleep(100)
        return SubAgentResult(agent_id="test_agent", success=True)

    with patch.object(spawner, "_execute_agent", side_effect=slow_execute):
        result = await spawner.spawn(
            "test_agent", "任务", make_mock_session(), timeout_seconds=0.01
        )
    assert result.success is False
    assert "超时" in result.summary


@pytest.mark.asyncio
async def test_spawn_success():
    registry = make_registry()
    spawner = SubAgentSpawner(registry, make_tool_registry())

    async def mock_execute(*args, **kwargs):
        return SubAgentResult(agent_id="test_agent", success=True, summary="完成")

    with patch.object(spawner, "_execute_agent", side_effect=mock_execute):
        result = await spawner.spawn("test_agent", "任务", make_mock_session())
    assert result.success is True
    assert result.summary == "完成"


@pytest.mark.asyncio
async def test_spawn_with_retry_success_first_try():
    registry = make_registry()
    spawner = SubAgentSpawner(registry, make_tool_registry())
    call_count = 0

    async def mock_spawn(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return SubAgentResult(agent_id="test_agent", success=True, summary="成功")

    with patch.object(spawner, "spawn", side_effect=mock_spawn):
        result = await spawner.spawn_with_retry("test_agent", "任务", make_mock_session())
    assert result.success is True
    assert call_count == 1


@pytest.mark.asyncio
async def test_spawn_with_retry_retries_on_failure():
    registry = make_registry()
    spawner = SubAgentSpawner(registry, make_tool_registry())
    call_count = 0

    async def mock_spawn(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return SubAgentResult(agent_id="test_agent", success=False, summary="失败")

    with patch.object(spawner, "spawn", side_effect=mock_spawn):
        with patch("asyncio.sleep", return_value=None):
            result = await spawner.spawn_with_retry(
                "test_agent", "任务", make_mock_session(), max_retries=3
            )
    assert result.success is False
    assert call_count == 3


@pytest.mark.asyncio
async def test_spawn_batch_order_preserved():
    registry = MagicMock()
    call_order: list[str] = []

    def get_agent(agent_id: str):
        return make_agent_def(agent_id)

    registry.get.side_effect = get_agent
    spawner = SubAgentSpawner(registry, make_tool_registry())

    async def mock_execute(agent_def, task, session):
        return SubAgentResult(agent_id=agent_def.agent_id, success=True, summary=agent_def.agent_id)

    with patch.object(spawner, "_execute_agent", side_effect=mock_execute):
        results = await spawner.spawn_batch(
            [("agent_a", "任务A"), ("agent_b", "任务B"), ("agent_c", "任务C")],
            make_mock_session(),
        )
    assert [r.agent_id for r in results] == ["agent_a", "agent_b", "agent_c"]


@pytest.mark.asyncio
async def test_spawn_batch_single_failure_does_not_stop_others():
    registry = MagicMock()

    def get_agent(agent_id: str):
        return make_agent_def(agent_id)

    registry.get.side_effect = get_agent
    spawner = SubAgentSpawner(registry, make_tool_registry())

    async def mock_execute(agent_def, task, session):
        if agent_def.agent_id == "fail_agent":
            raise RuntimeError("模拟失败")
        return SubAgentResult(agent_id=agent_def.agent_id, success=True, summary="完成")

    with patch.object(spawner, "_execute_agent", side_effect=mock_execute):
        results = await spawner.spawn_batch(
            [("ok_agent", "任务A"), ("fail_agent", "任务B"), ("ok_agent2", "任务C")],
            make_mock_session(),
        )
    # ok_agent 和 ok_agent2 应成功，fail_agent 应失败
    agent_results = {r.agent_id: r for r in results}
    assert agent_results["ok_agent"].success is True
    assert agent_results["fail_agent"].success is False
    assert agent_results["ok_agent2"].success is True


@pytest.mark.asyncio
async def test_spawn_batch_artifacts_written_to_parent():
    registry = MagicMock()

    def get_agent(agent_id: str):
        return make_agent_def(agent_id)

    registry.get.side_effect = get_agent
    spawner = SubAgentSpawner(registry, make_tool_registry())
    parent_session = make_mock_session()

    async def mock_execute(agent_def, task, session):
        return SubAgentResult(
            agent_id=agent_def.agent_id,
            success=True,
            artifacts={"result.csv": "data"},
        )

    with patch.object(spawner, "_execute_agent", side_effect=mock_execute):
        await spawner.spawn_batch([("test_agent", "任务")], parent_session)
    assert "result.csv" in parent_session.artifacts


@pytest.mark.asyncio
async def test_spawn_batch_empty_returns_empty():
    spawner = SubAgentSpawner(MagicMock(), make_tool_registry())
    results = await spawner.spawn_batch([], make_mock_session())
    assert results == []


@pytest.mark.asyncio
async def test_spawn_stops_child_when_parent_stop_event_is_set():
    registry = make_registry()
    spawner = SubAgentSpawner(registry, make_tool_registry())
    parent_session = make_mock_session()
    parent_session.runtime_stop_event = asyncio.Event()

    async def mock_execute(agent_def, task, session, **kwargs):
        stop_event = kwargs["stop_event"]
        while not stop_event.is_set():
            await asyncio.sleep(0.01)
        return SubAgentResult(
            agent_id=agent_def.agent_id,
            success=False,
            summary="用户已终止该子 Agent",
            stopped=True,
            stop_reason="用户已终止该子 Agent",
        )

    with patch.object(spawner, "_execute_agent", side_effect=mock_execute):
        spawn_task = asyncio.create_task(spawner.spawn("test_agent", "任务", parent_session))
        await asyncio.sleep(0.05)
        parent_session.runtime_stop_event.set()
        result = await spawn_task

    assert result.stopped is True
    assert result.stop_reason == "用户已终止该子 Agent"
    assert parent_session.subagent_stop_events == {}


@pytest.mark.asyncio
async def test_spawn_batch_stops_all_children_when_parent_stop_event_is_set():
    registry = MagicMock()

    def get_agent(agent_id: str):
        return make_agent_def(agent_id)

    registry.get.side_effect = get_agent
    spawner = SubAgentSpawner(registry, make_tool_registry())
    parent_session = make_mock_session()
    parent_session.runtime_stop_event = asyncio.Event()

    async def mock_execute(agent_def, task, session, **kwargs):
        stop_event = kwargs["stop_event"]
        while not stop_event.is_set():
            await asyncio.sleep(0.01)
        return SubAgentResult(
            agent_id=agent_def.agent_id,
            success=False,
            summary=f"{agent_def.agent_id} stopped",
            stopped=True,
            stop_reason="用户已终止该子 Agent",
        )

    with patch.object(spawner, "_execute_agent", side_effect=mock_execute):
        batch_task = asyncio.create_task(
            spawner.spawn_batch(
                [("agent_a", "任务A"), ("agent_b", "任务B")],
                parent_session,
            )
        )
        await asyncio.sleep(0.05)
        parent_session.runtime_stop_event.set()
        results = await batch_task

    assert [result.stopped for result in results] == [True, True]
    assert parent_session.subagent_stop_events == {}
