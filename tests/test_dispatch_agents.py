"""测试 DispatchAgentsTool —— 正常执行、空任务、依赖未注入。"""

from __future__ import annotations

from pathlib import Path

import pytest

from nini.agent.fusion import FusionResult, ResultFusionEngine
from nini.agent.session import Session, session_manager
from nini.agent.spawner import BatchPreflightPlan, SubAgentResult
from nini.config import settings
from nini.tools.dispatch_agents import DispatchAgentsTool
from nini.tools.base import ToolResult

# ─── 辅助 ───────────────────────────────────────────────────────────────────


class _MockRegistry:
    """最小 AgentRegistry stub。"""

    def list_agents(self):
        return [type("Def", (), {"agent_id": "data_cleaner"})()]


class _MultiAgentRegistry:
    """多个 agent 的注册表，模拟真实内置顺序场景。"""

    def list_agents(self):
        return [
            type("Def", (), {"agent_id": "citation_manager"})(),
            type("Def", (), {"agent_id": "data_cleaner"})(),
            type("Def", (), {"agent_id": "statistician"})(),
        ]


class _MockSpawner:
    """最小 SubAgentSpawner stub，返回固定结果。支持并行（spawn_batch）和串行（spawn）两条路径。"""

    def __init__(self, results=None):
        self._results = results or [
            SubAgentResult(agent_id="data_cleaner", success=True, summary="清洗完成")
        ]
        self.spawn_batch_count = 0
        self.spawn_count = 0
        self._spawn_index = 0
        self.preflight_batch_count = 0

    async def spawn_batch(self, tasks, session, **kwargs):
        self.spawn_batch_count += 1
        return self._results

    async def preflight_batch(self, tasks, session, **kwargs):
        self.preflight_batch_count += 1
        ordered_results: list[SubAgentResult | None] = [None] * len(tasks)
        executable_tasks: list[tuple[int, str, str]] = []
        for index, (agent_id, task) in enumerate(tasks, start=1):
            next_result = self._results[index - 1] if index - 1 < len(self._results) else None
            if next_result is not None and next_result.stop_reason == "preflight_failed":
                ordered_results[index - 1] = next_result
            else:
                executable_tasks.append((index, agent_id, task))
        return BatchPreflightPlan(
            ordered_results=ordered_results,
            executable_tasks=executable_tasks,
        )

    async def spawn(self, agent_id, task, session, **kwargs):
        self.spawn_count += 1
        while self._spawn_index < len(self._results):
            result = self._results[self._spawn_index]
            self._spawn_index += 1
            if result.stop_reason == "preflight_failed":
                continue
            return result
        return SubAgentResult(agent_id=agent_id, success=True)

    async def _emit_preflight_failure_event(self, **kwargs):
        return None

    def _attach_snapshot(self, session, result, *, attempt):
        return None


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
    assert spawner.preflight_batch_count == 1
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
    assert spawner.preflight_batch_count == 1
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


@pytest.mark.asyncio
async def test_execute_does_not_fallback_to_first_agent_when_multiple_agents_unmatched():
    """多 agent 场景下，未匹配任务不应退到注册表第一个 agent。"""
    tool = DispatchAgentsTool(
        agent_registry=_MultiAgentRegistry(),
        spawner=_MockSpawner(),
        fusion_engine=_MockFusion(),
        task_router=None,
    )

    result = await tool.execute(None, tasks=["完全未知任务"])

    assert result.success is False
    assert result.data["error_code"] == "DISPATCH_AGENTS_NO_MATCHED_AGENTS"


@pytest.mark.asyncio
async def test_execute_partial_unmatched_tasks_become_routing_failures():
    """部分任务未匹配时，应保留成功结果并补充 routing_failed 子结果。"""

    class _SelectiveRouter(_MockRouter):
        async def route(self, intent: str, context=None):
            from nini.agent.router import RoutingDecision

            if "清洗" in intent:
                return await super().route(intent, context=context)
            return RoutingDecision(
                agent_ids=[],
                tasks=[],
                confidence=0.0,
                strategy="rule",
                parallel=False,
            )

    tool = DispatchAgentsTool(
        agent_registry=_MultiAgentRegistry(),
        spawner=_MockSpawner(
            results=[SubAgentResult(agent_id="data_cleaner", success=True, summary="清洗完成")]
        ),
        fusion_engine=_MockFusion(),
        task_router=_SelectiveRouter(parallel=False, agent_id="data_cleaner"),
    )

    result = await tool.execute(None, tasks=["清洗数据", "完全未知任务"])

    assert result.success is True
    assert result.metadata["partial_failure"] is True
    assert result.metadata["failure_count"] == 1
    failed_item = next(item for item in result.metadata["subtasks"] if item["status"] == "error")
    assert failed_item["agent_id"] == "routing_guard"
    assert failed_item["stop_reason"] == "routing_failed"
    assert result.metadata["routing_failures"] == [
        {
            "agent_id": "routing_guard",
            "task": "完全未知任务",
            "error": "未找到与该任务兼容的 specialist agent",
        }
    ]


@pytest.mark.asyncio
async def test_execute_surfaces_preflight_failures_in_metadata_and_message():
    """批量调度中的 preflight_failed 应被显式分类，而不是混入普通执行失败。"""
    tool = DispatchAgentsTool(
        agent_registry=_MockRegistry(),
        spawner=_MockSpawner(
            results=[
                SubAgentResult(
                    agent_id="data_cleaner",
                    agent_name="数据清洗",
                    success=False,
                    task="任务1",
                    summary="系统内置「快速」试用额度已用完",
                    error="系统内置「快速」试用额度已用完",
                    stop_reason="preflight_failed",
                ),
                SubAgentResult(
                    agent_id="data_cleaner",
                    agent_name="数据清洗",
                    success=True,
                    task="任务2",
                    summary="任务2完成",
                ),
            ]
        ),
        fusion_engine=_MockFusion(),
        task_router=_MockRouter(parallel=True),
    )

    result = await tool.execute(None, tasks=["任务1", "任务2"])

    assert result.success is True
    assert result.metadata["preflight_failure_count"] == 1
    assert result.metadata["execution_failure_count"] == 0
    assert result.metadata["routing_failure_count"] == 0
    assert result.metadata["preflight_failures"] == [
        {
            "agent_id": "data_cleaner",
            "task": "任务1",
            "error": "系统内置「快速」试用额度已用完",
        }
    ]
    assert result.metadata["routing_failures"] == []
    assert result.metadata["execution_failures"] == []


@pytest.mark.asyncio
async def test_execute_all_preflight_failures_return_categorized_message():
    """当所有子任务都因额度/配置预检失败时，返回消息应直接说明该类别。"""
    tool = DispatchAgentsTool(
        agent_registry=_MockRegistry(),
        spawner=_MockSpawner(
            results=[
                SubAgentResult(
                    agent_id="data_cleaner",
                    agent_name="数据清洗",
                    success=False,
                    task="清洗数据",
                    summary="系统内置「快速」试用额度已用完",
                    error="系统内置「快速」试用额度已用完",
                    stop_reason="preflight_failed",
                )
            ]
        ),
        fusion_engine=_MockFusion(),
        task_router=_MockRouter(parallel=False),
    )

    result = await tool.execute(None, tasks=["清洗数据"])

    assert result.success is False
    assert result.metadata["preflight_failure_count"] == 1
    assert "模型额度或配置不可执行" in result.message
    assert "系统内置「快速」试用额度已用完" in result.message


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
    assert "dispatch_agents_preflight" in event_types
    assert "subagent_result" in event_types
    assert "dispatch_agents_result" in event_types

    preflight_event = next(
        event for event in events if event["type"] == "dispatch_agents_preflight"
    )
    assert preflight_event["metadata"]["phase"] == "preflight"

    dispatch_event = next(event for event in events if event["type"] == "dispatch_agents_result")
    assert dispatch_event["metadata"]["run_id"] == "dispatch:call-001"
    assert dispatch_event["data"]["failure_count"] == 1
    assert dispatch_event["data"]["subtasks"][0]["artifact_names"] == ["clean.csv"]


@pytest.mark.asyncio
async def test_execute_records_preflight_breakdown_in_dispatch_event(
    isolated_data_dir: Path,
):
    """dispatch 运行事件应记录 preflight 失败拆分，便于上层直接消费。"""
    tool = DispatchAgentsTool(
        agent_registry=_MockRegistry(),
        spawner=_MockSpawner(
            results=[
                SubAgentResult(
                    agent_id="data_cleaner",
                    agent_name="数据清洗",
                    success=False,
                    task="清洗数据",
                    summary="系统内置「快速」试用额度已用完",
                    error="系统内置「快速」试用额度已用完",
                    stop_reason="preflight_failed",
                    run_id="agent:turn-002:data_cleaner:1",
                    parent_session_id="session-dispatch",
                    resource_session_id="session-dispatch",
                ),
                SubAgentResult(
                    agent_id="statistician",
                    agent_name="统计分析",
                    success=False,
                    task="统计分析",
                    summary="统计失败",
                    error="样本量不足",
                    stop_reason="child_execution_failed",
                    run_id="agent:turn-002:statistician:1",
                    parent_session_id="session-dispatch",
                    resource_session_id="session-dispatch",
                ),
            ]
        ),
        fusion_engine=_MockFusion(),
        task_router=_MockRouter(parallel=True),
    )
    session = session_manager.create_session("session-dispatch")

    result = await tool.execute(
        session,
        tasks=["清洗数据", "统计分析"],
        turn_id="turn-002",
        tool_call_id="call-002",
    )

    assert result.metadata["preflight_failure_count"] == 1
    assert result.metadata["execution_failure_count"] == 1

    events = session_manager.load_agent_run_events("session-dispatch", turn_id="turn-002")
    dispatch_event = next(event for event in events if event["type"] == "dispatch_agents_result")
    assert dispatch_event["data"]["preflight_failure_count"] == 1
    assert dispatch_event["data"]["execution_failure_count"] == 1
    assert dispatch_event["data"]["preflight_failures"] == [
        {
            "agent_id": "data_cleaner",
            "task": "清洗数据",
            "error": "系统内置「快速」试用额度已用完",
        }
    ]
    assert dispatch_event["data"]["execution_failures"] == [
        {
            "agent_id": "statistician",
            "task": "统计分析",
            "error": "样本量不足",
        }
    ]
    assert dispatch_event["data"]["routing_failures"] == []


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
async def test_execute_dag_records_wave_preflight_events(isolated_data_dir: Path):
    """DAG 路径应按 wave 写入 dispatch_agents_preflight 事件。"""
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
    session = session_manager.create_session("session-dag-preflight")

    result = await tool.execute(
        session,
        tasks=[
            {"task": "清洗数据", "id": "t1"},
            {"task": "统计分析", "id": "t2", "depends_on": ["t1"]},
        ],
        turn_id="turn-dag-1",
        tool_call_id="call-dag-1",
    )

    assert result.success is True
    events = session_manager.load_agent_run_events("session-dag-preflight", turn_id="turn-dag-1")
    preflight_events = [event for event in events if event["type"] == "dispatch_agents_preflight"]
    assert len(preflight_events) == 2
    assert preflight_events[0]["data"]["wave_index"] == 1
    assert preflight_events[1]["data"]["wave_index"] == 2


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
