"""假设驱动范式集成测试 —— 验证 9.4 场景。

测试覆盖：
- hypothesis 事件通过 event_callback 链路完整推送
- paradigm_switched 先于 hypothesis_generated 触发
- 事件 data 结构符合 WebSocket 协议（可序列化为 JSON）
- 混合范式 dispatch 时 hypothesis 事件正确归属到对应 Agent
"""

from __future__ import annotations

import asyncio
import json
import pytest
from unittest.mock import patch

from nini.agent.hypothesis_context import Hypothesis, HypothesisContext
from nini.agent.spawner import SubAgentResult, SubAgentSpawner
from nini.agent.registry import AgentDefinition

# ── 辅助函数 ───────────────────────────────────────────────────────────────────


def make_hypothesis_def(agent_id: str = "literature_reading") -> AgentDefinition:
    return AgentDefinition(
        agent_id=agent_id,
        name="文献精读",
        description="Hypothesis-Driven 精读",
        system_prompt="你是假设驱动文献精读助手",
        purpose="default",
        allowed_tools=[],
        timeout_seconds=30,
        paradigm="hypothesis_driven",
    )


def make_session_with_capture() -> tuple:
    """创建带事件捕获的模拟会话，返回 (session, captured_events)。"""
    from unittest.mock import MagicMock

    captured: list = []

    async def capture_callback(event):
        captured.append(event)

    session = MagicMock()
    session.id = "integration_session"
    session.datasets = {}
    session.artifacts = {}
    session.documents = {}
    session.event_callback = capture_callback
    return session, captured


def make_tool_registry():
    from unittest.mock import MagicMock

    registry = MagicMock()
    registry.create_subset.return_value = MagicMock()
    return registry


def make_registry(agent_def: AgentDefinition):
    from unittest.mock import MagicMock

    registry = MagicMock()
    registry.get.return_value = agent_def
    return registry


# ── 测试 1：事件顺序 —— paradigm_switched 先于 hypothesis_generated ─────────


@pytest.mark.asyncio
async def test_paradigm_switched_precedes_hypothesis_generated():
    """_spawn_hypothesis_driven 推送事件顺序正确：paradigm_switched 在前。"""
    agent_def = make_hypothesis_def()
    spawner = SubAgentSpawner(make_registry(agent_def), make_tool_registry())
    session, captured = make_session_with_capture()

    async def mock_runner_run(sess, task):
        from nini.agent.events import AgentEvent, EventType

        yield AgentEvent(type=EventType.TEXT, data="假设：近5年XXX领域存在显著趋势")

    with patch("nini.agent.runner.AgentRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run = mock_runner_run
        await spawner._spawn_hypothesis_driven(agent_def, "综述近5年研究进展", session)

    event_types = [e.type.value for e in captured]
    assert "paradigm_switched" in event_types
    assert "hypothesis_generated" in event_types
    # 验证顺序
    paradigm_idx = next(i for i, e in enumerate(captured) if e.type.value == "paradigm_switched")
    hyp_idx = next(i for i, e in enumerate(captured) if e.type.value == "hypothesis_generated")
    assert (
        paradigm_idx < hyp_idx
    ), f"paradigm_switched({paradigm_idx}) 应在 hypothesis_generated({hyp_idx}) 之前"


# ── 测试 2：paradigm_switched 事件 data 结构可 JSON 序列化 ────────────────────


@pytest.mark.asyncio
async def test_hypothesis_events_json_serializable():
    """所有假设事件 data 字段可被 json.dumps 序列化（WebSocket 可传输）。"""
    agent_def = make_hypothesis_def()
    spawner = SubAgentSpawner(make_registry(agent_def), make_tool_registry())
    session, captured = make_session_with_capture()

    async def mock_runner_run(sess, task):
        from nini.agent.events import AgentEvent, EventType

        yield AgentEvent(type=EventType.TEXT, data="假设推理内容")

    with patch("nini.agent.runner.AgentRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run = mock_runner_run
        await spawner._spawn_hypothesis_driven(agent_def, "测试任务", session)

    for event in captured:
        # 每个事件的 data 必须可序列化为 JSON（WebSocket 传输要求）
        try:
            serialized = json.dumps(event.data, ensure_ascii=False)
            assert serialized is not None
        except (TypeError, ValueError) as e:
            pytest.fail(f"事件 {event.type.value} data 无法 JSON 序列化: {e}")


# ── 测试 3：hypothesis_generated data 包含必要字段 ─────────────────────────────


@pytest.mark.asyncio
async def test_hypothesis_generated_event_data_structure():
    """hypothesis_generated 事件 data 包含 agent_id 和 hypotheses 字段。"""
    agent_def = make_hypothesis_def("literature_reading")
    spawner = SubAgentSpawner(make_registry(agent_def), make_tool_registry())
    session, captured = make_session_with_capture()

    async def mock_runner_run(sess, task):
        from nini.agent.events import AgentEvent, EventType

        yield AgentEvent(type=EventType.TEXT, data="近5年研究表明XXX")

    with patch("nini.agent.runner.AgentRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run = mock_runner_run
        await spawner._spawn_hypothesis_driven(agent_def, "综述近5年研究", session)

    hyp_events = [e for e in captured if e.type.value == "hypothesis_generated"]
    assert len(hyp_events) >= 1

    evt_data = hyp_events[0].data
    assert isinstance(evt_data, dict), f"data 应为 dict，实际为 {type(evt_data)}"
    assert "agent_id" in evt_data, f"缺少 agent_id 字段，data={evt_data}"
    assert "hypotheses" in evt_data, f"缺少 hypotheses 字段，data={evt_data}"
    assert isinstance(evt_data["hypotheses"], list)


# ── 测试 4：paradigm_switched data 包含 agent_id ──────────────────────────────


@pytest.mark.asyncio
async def test_paradigm_switched_event_data_structure():
    """paradigm_switched 事件 data 包含 agent_id 字段。"""
    agent_def = make_hypothesis_def("research_planner")
    spawner = SubAgentSpawner(make_registry(agent_def), make_tool_registry())
    session, captured = make_session_with_capture()

    async def mock_runner_run(sess, task):
        from nini.agent.events import AgentEvent, EventType

        yield AgentEvent(type=EventType.TEXT, data="")

    with patch("nini.agent.runner.AgentRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run = mock_runner_run
        await spawner._spawn_hypothesis_driven(agent_def, "规划研究方向", session)

    ps_events = [e for e in captured if e.type.value == "paradigm_switched"]
    assert len(ps_events) == 1

    evt_data = ps_events[0].data
    assert isinstance(evt_data, dict)
    assert evt_data.get("agent_id") == "research_planner"


# ── 测试 5：evidence_collected 事件在第二轮迭代触发 ────────────────────────────


@pytest.mark.asyncio
async def test_evidence_collected_in_second_iteration():
    """第二轮迭代（已有假设后）推送 evidence_collected 事件。"""
    agent_def = make_hypothesis_def()
    spawner = SubAgentSpawner(make_registry(agent_def), make_tool_registry())
    session, captured = make_session_with_capture()

    call_count = [0]

    async def mock_runner_run(sess, task):
        from nini.agent.events import AgentEvent, EventType

        call_count[0] += 1
        yield AgentEvent(type=EventType.TEXT, data=f"第{call_count[0]}轮输出")

    with patch("nini.agent.runner.AgentRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run = mock_runner_run
        # max_iterations=3，让它跑多轮直到硬上限
        await spawner._spawn_hypothesis_driven(agent_def, "综述任务", session)

    event_types = [e.type.value for e in captured]
    # 至少有一次 evidence_collected（第2轮+）
    assert (
        "evidence_collected" in event_types
    ), f"未收到 evidence_collected，实际事件类型：{event_types}"


# ── 测试 6：hypothesis_validated 在置信度达到阈值时推送 ──────────────────────


@pytest.mark.asyncio
async def test_hypothesis_validated_when_confidence_high():
    """置信度达到 >= 0.65 时推送 hypothesis_validated 事件。"""
    agent_def = make_hypothesis_def()
    spawner = SubAgentSpawner(make_registry(agent_def), make_tool_registry())
    session, captured = make_session_with_capture()

    # 跑 3 轮，每轮 +0.15 支持证据，起始 0.5 → 0.65 → validated
    async def mock_runner_run(sess, task):
        from nini.agent.events import AgentEvent, EventType

        yield AgentEvent(type=EventType.TEXT, data="强有力的证据支持该假设")

    with patch("nini.agent.runner.AgentRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run = mock_runner_run
        result = await spawner._spawn_hypothesis_driven(agent_def, "验证假设", session)

    assert result.success is True
    event_types = [e.type.value for e in captured]
    # 经过 3 轮（max_iterations=3），置信度应达到 validated 区间
    assert "hypothesis_validated" in event_types, (
        f"未收到 hypothesis_validated，实际事件类型：{event_types}\n"
        f"可能置信度未达阈值或事件推送缺失"
    )


# ── 测试 7：spawn() 通过 dispatch_agents 上层路径触发 hypothesis 事件 ─────────


@pytest.mark.asyncio
async def test_spawn_entry_point_emits_hypothesis_events():
    """通过 spawn() 顶层入口（非直接调用 _spawn_hypothesis_driven）触发假设事件。"""
    agent_def = make_hypothesis_def()
    spawner = SubAgentSpawner(make_registry(agent_def), make_tool_registry())
    session, captured = make_session_with_capture()

    async def mock_runner_run(sess, task):
        from nini.agent.events import AgentEvent, EventType

        yield AgentEvent(type=EventType.TEXT, data="假设推理")

    with patch("nini.agent.runner.AgentRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run = mock_runner_run
        result = await spawner.spawn("literature_reading", "综述近5年研究进展", session)

    assert result.success is True
    event_types = [e.type.value for e in captured]
    # spawn() 入口同样触发 paradigm_switched 和 hypothesis_generated
    assert "paradigm_switched" in event_types, f"缺少 paradigm_switched，events={event_types}"
    assert "hypothesis_generated" in event_types, f"缺少 hypothesis_generated，events={event_types}"
