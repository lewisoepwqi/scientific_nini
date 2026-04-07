"""测试 DispatchAgentsTool —— 正常执行、空任务、依赖未注入。"""

from __future__ import annotations

from pathlib import Path

import pytest

from nini.agent.fusion import FusionResult, ResultFusionEngine
from nini.agent.session import Session, session_manager
from nini.agent.spawner import SubAgentResult
from nini.config import settings
from nini.tools.dispatch_agents import DispatchAgentsTool
from nini.tools.base import ToolResult

# ─── 辅助 ───────────────────────────────────────────────────────────────────


class _MockRegistry:
    """最小 AgentRegistry stub。"""

    def list_agents(self):
        return [type("Def", (), {"agent_id": "data_cleaner"})()]


class _MockSpawner:
    """最小 SubAgentSpawner stub，返回固定结果。支持并行（spawn_batch）和串行（spawn）两条路径。"""

    def __init__(self, results=None):
        self._results = results or [
            SubAgentResult(agent_id="data_cleaner", success=True, summary="清洗完成")
        ]
        self.spawn_batch_count = 0
        self.spawn_count = 0
        self._spawn_index = 0

    async def spawn_batch(self, tasks, session, **kwargs):
        self.spawn_batch_count += 1
        return self._results

    async def spawn(self, agent_id, task, session, **kwargs):
        self.spawn_count += 1
        if self._spawn_index < len(self._results):
            result = self._results[self._spawn_index]
            self._spawn_index += 1
            return result
        return SubAgentResult(agent_id=agent_id, success=True)


class _MockRouter:
    """最小 TaskRouter stub，可配置返回 parallel 标志。"""

    def __init__(self, *, parallel: bool, agent_id: str = "data_cleaner"):
        from nini.agent.router import RoutingDecision

        self._decision_parallel = parallel
        self._agent_id = agent_id
        self._RoutingDecision = RoutingDecision

    async def route(self, intent: str, context=None):
        return self._RoutingDecision(
            agent_ids=[self._agent_id],
            tasks=[intent],
            confidence=0.9,
            strategy="llm",
            parallel=self._decision_parallel,
        )


class _MockFusion:
    """最小 ResultFusionEngine stub，返回固定融合结果。"""

    async def fuse(self, results, strategy="auto"):
        content = " | ".join(r.summary for r in results if r.summary)
        return FusionResult(content=content, strategy="concatenate")


@pytest.fixture
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """隔离 dispatch_agents 运行事件输出目录。"""
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()
    session_manager._sessions.clear()
    yield tmp_path
    session_manager._sessions.clear()


# ─── 正常执行 ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_returns_skill_result():
    """正常执行时返回 ToolResult，message 包含融合结果。"""
    tool = DispatchAgentsTool(
        agent_registry=_MockRegistry(),
        spawner=_MockSpawner(),
        fusion_engine=_MockFusion(),
    )
    result = await tool.execute(None, tasks=["清洗数据"])
    assert isinstance(result, ToolResult)
    assert result.success is True
    assert "清洗完成" in result.message
    assert result.metadata["task_count"] == 1
    assert result.metadata["routed_agents"] == ["data_cleaner"]
    assert result.metadata["success_count"] == 1
    assert result.metadata["failure_count"] == 0
    assert result.metadata["subtasks"][0]["agent_id"] == "data_cleaner"


@pytest.mark.asyncio
async def test_execute_calls_spawn_batch_when_parallel():
    """路由决策 parallel=True 时 execute() 调用 spawn_batch()。"""
    spawner = _MockSpawner()
    tool = DispatchAgentsTool(
        agent_registry=_MockRegistry(),
        spawner=spawner,
        fusion_engine=_MockFusion(),
        task_router=_MockRouter(parallel=True),
    )
    await tool.execute(None, tasks=["任务1", "任务2"])
    assert spawner.spawn_batch_count == 1
    assert spawner.spawn_count == 0


@pytest.mark.asyncio
async def test_execute_calls_spawn_serially_when_not_parallel():
    """路由决策 parallel=False 时 execute() 按顺序调用 spawn()，第 N+1 个任务在第 N 个完成后才开始。"""
    execution_order: list[str] = []

    class _OrderTrackingSpawner(_MockSpawner):
        async def spawn(self, agent_id, task, session, **kwargs):
            result = await super().spawn(agent_id, task, session, **kwargs)
            execution_order.append(task)
            return result

    spawner = _OrderTrackingSpawner(
        results=[
            SubAgentResult(agent_id="data_cleaner", success=True, summary="任务1完成"),
            SubAgentResult(agent_id="data_cleaner", success=True, summary="任务2完成"),
        ]
    )
    tool = DispatchAgentsTool(
        agent_registry=_MockRegistry(),
        spawner=spawner,
        fusion_engine=_MockFusion(),
        task_router=_MockRouter(parallel=False),
    )
    result = await tool.execute(None, tasks=["任务1", "任务2"])
    assert result.success is True
    assert spawner.spawn_batch_count == 0
    assert spawner.spawn_count == 2
    # 任务按顺序执行：任务1 先于 任务2
    assert len(execution_order) == 2
    assert "任务1" in execution_order[0]
    assert "任务2" in execution_order[1]


@pytest.mark.asyncio
async def test_execute_with_context():
    """context 参数正常传递，不影响执行结果格式。"""
    tool = DispatchAgentsTool(
        agent_registry=_MockRegistry(),
        spawner=_MockSpawner(),
        fusion_engine=_MockFusion(),
    )
    result = await tool.execute(None, tasks=["数据分析"], context="背景信息")
    assert result.success is True


# ─── 空任务 ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_empty_tasks_returns_empty():
    """tasks 为空时返回 ToolResult(message="")，不抛出异常。"""
    tool = DispatchAgentsTool(
        agent_registry=_MockRegistry(),
        spawner=_MockSpawner(),
        fusion_engine=_MockFusion(),
    )
    result = await tool.execute(None, tasks=[])
    assert result.success is True
    assert result.message == ""
    assert result.metadata["task_count"] == 0
    assert result.metadata["routed_agents"] == []


@pytest.mark.asyncio
async def test_execute_none_tasks_returns_empty():
    """tasks=None 等同于空任务，不抛出异常。"""
    tool = DispatchAgentsTool(
        agent_registry=_MockRegistry(),
        spawner=_MockSpawner(),
        fusion_engine=_MockFusion(),
    )
    result = await tool.execute(None, tasks=None)
    assert result.success is True
    assert result.message == ""
    assert result.metadata["task_count"] == 0


# ─── 依赖未注入 ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_no_spawner_returns_error():
    """spawner 为 None 时返回 success=False，不抛出异常。"""
    tool = DispatchAgentsTool(
        agent_registry=_MockRegistry(),
        spawner=None,
        fusion_engine=_MockFusion(),
    )
    result = await tool.execute(None, tasks=["任务"])
    assert result.success is False
    assert result.data["error_code"] == "DISPATCH_AGENTS_NOT_INITIALIZED"
    assert result.data["expected_fields"] == ["tasks"]


@pytest.mark.asyncio
async def test_execute_no_fusion_returns_error():
    """fusion_engine 为 None 时返回 success=False，不抛出异常。"""
    tool = DispatchAgentsTool(
        agent_registry=_MockRegistry(),
        spawner=_MockSpawner(),
        fusion_engine=None,
    )
    result = await tool.execute(None, tasks=["任务"])
    assert result.success is False
    assert result.data["error_code"] == "DISPATCH_AGENTS_NOT_INITIALIZED"


@pytest.mark.asyncio
async def test_execute_no_matched_agent_returns_structured_error():
    """没有可用 Agent 时应返回结构化错误。"""
    tool = DispatchAgentsTool(
        agent_registry=None,
        spawner=_MockSpawner(),
        fusion_engine=_MockFusion(),
    )
    result = await tool.execute(None, tasks=["任务"])

    assert result.success is False
    assert result.data["error_code"] == "DISPATCH_AGENTS_NO_MATCHED_AGENTS"
    assert "Agent" in result.data["recovery_hint"]


# ─── 工具元数据 ──────────────────────────────────────────────────────────────


def test_tool_name():
    """工具名称为 dispatch_agents。"""
    tool = DispatchAgentsTool()
    assert tool.name == "dispatch_agents"


def test_tool_expose_to_llm_false():
    """expose_to_llm 为 False（通过 Orchestrator 路径暴露）。"""
    tool = DispatchAgentsTool()
    assert tool.expose_to_llm is False


@pytest.mark.asyncio
async def test_execute_records_structured_agent_run_events(isolated_data_dir: Path):
    """执行完成后应写入父会话级结构化 dispatch/子任务事件。"""
    tool = DispatchAgentsTool(
        agent_registry=_MockRegistry(),
        spawner=_MockSpawner(
            results=[
                SubAgentResult(
                    agent_id="data_cleaner",
                    agent_name="数据清洗",
                    success=True,
                    task="清洗数据",
                    summary="清洗完成",
                    run_id="agent:turn-001:data_cleaner:1",
                    parent_session_id="session-dispatch",
                    resource_session_id="session-dispatch",
                    artifacts={"clean.csv": {}},
                ),
                SubAgentResult(
                    agent_id="statistician",
                    agent_name="统计分析",
                    success=False,
                    task="统计分析",
                    summary="统计失败",
                    error="样本量不足",
                    run_id="agent:turn-001:statistician:1",
                    parent_session_id="session-dispatch",
                    resource_session_id="session-dispatch",
                ),
            ]
        ),
        fusion_engine=_MockFusion(),
    )
    session = session_manager.create_session("session-dispatch")

    result = await tool.execute(
        session,
        tasks=["清洗数据", "统计分析"],
        turn_id="turn-001",
        tool_call_id="call-001",
    )

    assert result.metadata["dispatch_run_id"] == "dispatch:call-001"
    assert result.metadata["partial_failure"] is True
    assert result.metadata["failure_count"] == 1
    assert result.metadata["subtasks"][1]["error"] == "样本量不足"

    events = session_manager.load_agent_run_events("session-dispatch", turn_id="turn-001")
    event_types = [event["type"] for event in events]
    assert "subagent_result" in event_types
    assert "dispatch_agents_result" in event_types

    dispatch_event = next(event for event in events if event["type"] == "dispatch_agents_result")
    assert dispatch_event["metadata"]["run_id"] == "dispatch:call-001"
    assert dispatch_event["data"]["failure_count"] == 1
    assert dispatch_event["data"]["subtasks"][0]["artifact_names"] == ["clean.csv"]


# ─── DAG 路径测试 ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_string_tasks_use_c1_path():
    """旧格式字符串任务：走 C1 路径，不触发 DAG。"""
    spawner = _MockSpawner()
    tool = DispatchAgentsTool(
        agent_registry=_MockRegistry(),
        spawner=spawner,
        fusion_engine=_MockFusion(),
        task_router=_MockRouter(parallel=True),
    )
    result = await tool.execute(None, tasks=["清洗数据", "统计分析"])
    assert result.success is True
    # C1 路径：spawn_batch 被调用一次（并行）
    assert spawner.spawn_batch_count == 1
    assert "dag_error" not in result.metadata


@pytest.mark.asyncio
async def test_execute_dict_tasks_with_depends_on_trigger_dag():
    """对象格式含 depends_on 时：触发 DAG 路径，按 wave 执行。"""
    spawn_calls: list[list[tuple[str, str]]] = []

    class _TrackingSpawner(_MockSpawner):
        async def spawn_batch(self, tasks, session, **kwargs):
            spawn_calls.append(list(tasks))
            return [SubAgentResult(agent_id=a, success=True, summary="done") for a, _ in tasks]

    tool = DispatchAgentsTool(
        agent_registry=_MockRegistry(),
        spawner=_TrackingSpawner(),
        fusion_engine=_MockFusion(),
        task_router=_MockRouter(parallel=True),
    )
    result = await tool.execute(
        None,
        tasks=[
            {"task": "清洗数据", "id": "t1"},
            {"task": "统计分析", "id": "t2", "depends_on": ["t1"]},
        ],
    )
    assert result.success is True
    # DAG 路径：链式依赖 → 2 个 wave → spawn_batch 调用 2 次
    assert len(spawn_calls) == 2


@pytest.mark.asyncio
async def test_execute_mixed_format_tasks():
    """字符串和字典混合格式：无 depends_on 则走 C1 路径。"""
    spawner = _MockSpawner()
    tool = DispatchAgentsTool(
        agent_registry=_MockRegistry(),
        spawner=spawner,
        fusion_engine=_MockFusion(),
        task_router=_MockRouter(parallel=True),
    )
    result = await tool.execute(
        None,
        tasks=["清洗数据", {"task": "统计分析", "id": "t2"}],
    )
    assert result.success is True
    # 无 depends_on → C1 路径
    assert spawner.spawn_batch_count == 1


@pytest.mark.asyncio
async def test_execute_dag_invalid_depends_on_logs_warning(caplog):
    """无效 depends_on 引用（不存在的 id）时：记录 WARNING，任务仍被执行。"""
    import logging

    spawner = _MockSpawner(
        results=[SubAgentResult(agent_id="data_cleaner", success=True, summary="ok")]
    )
    tool = DispatchAgentsTool(
        agent_registry=_MockRegistry(),
        spawner=spawner,
        fusion_engine=_MockFusion(),
        task_router=_MockRouter(parallel=True),
    )
    with caplog.at_level(logging.WARNING, logger="nini.agent.dag_executor"):
        result = await tool.execute(
            None,
            tasks=[{"task": "统计分析", "id": "t1", "depends_on": ["NONEXISTENT"]}],
        )
    assert result.success is True
    assert "NONEXISTENT" in caplog.text
