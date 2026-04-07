"""测试 SubAgentSpawner 的假设驱动范式路由与执行。"""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from nini.agent.spawner import SubAgentResult, SubAgentSpawner
from nini.agent.registry import AgentDefinition

# ── 测试辅助函数 ───────────────────────────────────────────────────────────────


def make_react_agent_def(agent_id: str = "react_agent") -> AgentDefinition:
    """创建 react 范式 AgentDefinition。"""
    return AgentDefinition(
        agent_id=agent_id,
        name=f"ReAct {agent_id}",
        description="ReAct 测试 Agent",
        system_prompt="你是测试助手",
        purpose="default",
        allowed_tools=["stat_test"],
        timeout_seconds=10,
        paradigm="react",
    )


def make_hypothesis_agent_def(agent_id: str = "hyp_agent") -> AgentDefinition:
    """创建 hypothesis_driven 范式 AgentDefinition。"""
    return AgentDefinition(
        agent_id=agent_id,
        name=f"假设驱动 {agent_id}",
        description="假设驱动测试 Agent",
        system_prompt="你是假设驱动推理助手",
        purpose="default",
        allowed_tools=["stat_test"],
        timeout_seconds=10,
        paradigm="hypothesis_driven",
    )


def make_mock_session(captured_events: list | None = None) -> MagicMock:
    """创建模拟父会话，可选地捕获推送事件。"""
    session = MagicMock()
    session.id = "parent_session_id"
    session.datasets = {}
    session.artifacts = {}
    session.documents = {}

    if captured_events is not None:

        async def capture_callback(event):
            captured_events.append(event)

        session.event_callback = capture_callback
    else:
        session.event_callback = None
    return session


def make_registry(agent_def: AgentDefinition) -> MagicMock:
    registry = MagicMock()
    registry.get.return_value = agent_def
    return registry


def make_tool_registry() -> MagicMock:
    tool_registry = MagicMock()
    tool_registry.create_subset.return_value = MagicMock()
    return tool_registry


# ── 范式路由测试 ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_spawn_routes_react_to_execute_agent():
    """react 范式应调用 _execute_agent，不调用 _spawn_hypothesis_driven。"""
    agent_def = make_react_agent_def()
    spawner = SubAgentSpawner(make_registry(agent_def), make_tool_registry())

    mock_result = SubAgentResult(agent_id="react_agent", success=True, summary="React 完成")
    execute_called = []

    async def mock_execute(ad, task, session):
        execute_called.append("execute_agent")
        return mock_result

    with (
        patch.object(spawner, "_preflight_agent_execution", new=AsyncMock(return_value=None)),
        patch.object(spawner, "_execute_agent", side_effect=mock_execute),
        patch.object(spawner, "_spawn_hypothesis_driven", side_effect=AssertionError("不应调用")),
    ):
        result = await spawner.spawn("react_agent", "任务", make_mock_session())

    assert result.success is True
    assert "execute_agent" in execute_called


@pytest.mark.asyncio
async def test_spawn_routes_hypothesis_driven():
    """hypothesis_driven 范式应调用 _spawn_hypothesis_driven，不调用 _execute_agent。"""
    agent_def = make_hypothesis_agent_def()
    spawner = SubAgentSpawner(make_registry(agent_def), make_tool_registry())

    mock_result = SubAgentResult(agent_id="hyp_agent", success=True, summary="假设完成")
    hyp_called = []

    async def mock_hyp(ad, task, session):
        hyp_called.append("hypothesis_driven")
        return mock_result

    with (
        patch.object(spawner, "_preflight_agent_execution", new=AsyncMock(return_value=None)),
        patch.object(spawner, "_execute_agent", side_effect=AssertionError("不应调用")),
        patch.object(spawner, "_spawn_hypothesis_driven", side_effect=mock_hyp),
    ):
        result = await spawner.spawn("hyp_agent", "任务", make_mock_session())

    assert result.success is True
    assert "hypothesis_driven" in hyp_called


# ── _spawn_hypothesis_driven 成功路径 ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_spawn_hypothesis_driven_returns_success():
    """_spawn_hypothesis_driven 正常迭代后返回 success=True。"""
    agent_def = make_hypothesis_agent_def()
    spawner = SubAgentSpawner(make_registry(agent_def), make_tool_registry())

    # AgentRunner.run 模拟：返回一个 TEXT 事件
    async def mock_runner_run(session, task):
        from nini.agent.events import AgentEvent, EventType

        yield AgentEvent(type=EventType.TEXT, data="初始假设：XXX 存在显著相关性")

    with patch("nini.agent.runner.AgentRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run = mock_runner_run
        result = await spawner._spawn_hypothesis_driven(
            agent_def, "分析研究进展", make_mock_session()
        )

    assert result.success is True
    assert result.agent_id == "hyp_agent"
    # 不应包含内部 _hypothesis_context artifact
    assert "_hypothesis_context" not in result.artifacts


# ── 超时路径 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_spawn_hypothesis_driven_timeout():
    """spawn() 超时时返回 success=False。"""
    agent_def = make_hypothesis_agent_def()
    spawner = SubAgentSpawner(make_registry(agent_def), make_tool_registry())

    async def slow_hyp(ad, task, session):
        await asyncio.sleep(100)
        return SubAgentResult(agent_id="hyp_agent", success=True)

    with (
        patch.object(spawner, "_preflight_agent_execution", new=AsyncMock(return_value=None)),
        patch.object(spawner, "_spawn_hypothesis_driven", side_effect=slow_hyp),
    ):
        result = await spawner.spawn("hyp_agent", "任务", make_mock_session(), timeout_seconds=1)

    assert result.success is False
    assert "超时" in result.summary


# ── paradigm_switched 事件推送 ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_paradigm_switched_event_pushed():
    """_spawn_hypothesis_driven 开始时推送 paradigm_switched 事件。"""
    agent_def = make_hypothesis_agent_def()
    spawner = SubAgentSpawner(make_registry(agent_def), make_tool_registry())
    captured: list = []
    session = make_mock_session(captured_events=captured)

    async def mock_runner_run(sess, task):
        from nini.agent.events import AgentEvent, EventType

        yield AgentEvent(type=EventType.TEXT, data="假设推理结果")

    with patch("nini.agent.runner.AgentRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run = mock_runner_run
        await spawner._spawn_hypothesis_driven(agent_def, "测试任务", session)

    event_types = [e.type.value if hasattr(e.type, "value") else str(e.type) for e in captured]
    assert "paradigm_switched" in event_types


# ── spawn_batch 混合范式并发 ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_spawn_batch_mixed_paradigms():
    """spawn_batch 中混合 react 和 hypothesis_driven Agent 并发执行互不影响。"""
    react_def = make_react_agent_def("react_1")
    hyp_def = make_hypothesis_agent_def("hyp_1")

    registry = MagicMock()

    def get_agent(agent_id: str):
        if agent_id == "react_1":
            return react_def
        if agent_id == "hyp_1":
            return hyp_def
        return None

    registry.get.side_effect = get_agent
    spawner = SubAgentSpawner(registry, make_tool_registry())

    async def mock_execute(ad, task, session):
        return SubAgentResult(agent_id=ad.agent_id, success=True, summary="react done")

    async def mock_hyp(ad, task, session):
        return SubAgentResult(agent_id=ad.agent_id, success=True, summary="hyp done")

    with (
        patch.object(spawner, "_preflight_agent_execution", new=AsyncMock(return_value=None)),
        patch.object(spawner, "_execute_agent", side_effect=mock_execute),
        patch.object(spawner, "_spawn_hypothesis_driven", side_effect=mock_hyp),
    ):
        results = await spawner.spawn_batch(
            [("react_1", "react任务"), ("hyp_1", "假设任务")],
            make_mock_session(),
        )

    assert len(results) == 2
    # 两个都成功
    assert all(r.success for r in results)
    # 结果顺序与输入一致
    agent_ids = [r.agent_id for r in results]
    assert "react_1" in agent_ids
    assert "hyp_1" in agent_ids
