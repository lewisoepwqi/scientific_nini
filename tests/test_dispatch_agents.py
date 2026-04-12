"""测试 DispatchAgentsTool —— 新 schema: agents=[{agent_id, task}]。

覆盖场景：
- 正常并行执行，结果正确拼接
- agents 为空时快速返回
- 非法 agent_id 返回结构化错误
- 部分子 Agent 失败时结果仍完整返回
"""

from __future__ import annotations

import pytest

from nini.agent.task_manager import TaskManager
from nini.agent.spawner import SubAgentResult
from nini.tools.dispatch_agents import DispatchAgentsTool
from nini.tools.base import ToolResult

# ─── 辅助 ────────────────────────────────────────────────────────────────────


class _MockRegistry:
    """最小 AgentRegistry stub，注册两个合法 agent_id。"""

    def list_dispatchable_agents(self):
        return [
            type("Def", (), {"agent_id": "literature_search"})(),
            type("Def", (), {"agent_id": "data_cleaner"})(),
        ]


class _MockSpawner:
    """最小 SubAgentSpawner stub，spawn_batch 返回固定结果列表。"""

    def __init__(self, results: list[SubAgentResult] | None = None) -> None:
        self._results = results or [
            SubAgentResult(agent_id="literature_search", success=True, summary="检索完成")
        ]
        self.spawn_batch_calls: list[list[tuple[str, str]]] = []

    async def spawn_batch(self, tasks, session, **kwargs):
        self.spawn_batch_calls.append(list(tasks))
        return self._results


class _SessionWithTasks:
    """携带 TaskManager 的最小 session stub。"""

    def __init__(self, tasks: list[dict]) -> None:
        self.id = "session-test"
        self.event_callback = None
        self.task_manager = TaskManager().init_tasks(tasks)


# ─── 正常执行 ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_returns_tool_result():
    """正常执行返回 ToolResult，success=True，message 含子 Agent 标签。"""
    tool = DispatchAgentsTool(
        agent_registry=_MockRegistry(),
        spawner=_MockSpawner(),
    )
    result = await tool.execute(
        None,
        tasks=[{"task_id": 1, "agent_id": "literature_search", "task": "检索高血压文献"}],
    )
    assert isinstance(result, ToolResult)
    assert result.success is True
    assert "[literature_search]" in result.message
    assert "检索完成" in result.message
    assert result.metadata["agent_count"] == 1
    assert result.metadata["success_count"] == 1
    assert result.metadata["failure_count"] == 0
    assert result.metadata["subtasks"][0]["task_id"] == 1


@pytest.mark.asyncio
async def test_execute_calls_spawn_batch_with_correct_pairs():
    """execute() 应将 agents 列表转换为 (agent_id, task) 对后调用 spawn_batch。"""
    spawner = _MockSpawner(
        results=[
            SubAgentResult(agent_id="literature_search", success=True, summary="A"),
            SubAgentResult(agent_id="data_cleaner", success=True, summary="B"),
        ]
    )
    tool = DispatchAgentsTool(agent_registry=_MockRegistry(), spawner=spawner)
    await tool.execute(
        None,
        tasks=[
            {"task_id": 1, "agent_id": "literature_search", "task": "检索文献"},
            {"task_id": 2, "agent_id": "data_cleaner", "task": "清洗数据"},
        ],
    )
    assert len(spawner.spawn_batch_calls) == 1
    pairs = spawner.spawn_batch_calls[0]
    assert pairs[0][0] == "literature_search"
    assert "task_id: 1" in pairs[0][1]
    assert "goal: 检索文献" in pairs[0][1]
    assert pairs[1][0] == "data_cleaner"
    assert "task_id: 2" in pairs[1][1]


# ─── 空列表 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_empty_agents_returns_empty():
    """agents=[] 时快速返回 ToolResult(message='')，不调用 spawn_batch。"""
    spawner = _MockSpawner()
    tool = DispatchAgentsTool(agent_registry=_MockRegistry(), spawner=spawner)
    result = await tool.execute(None, agents=[])
    assert result.success is True
    assert result.message == ""
    assert result.metadata["agent_count"] == 0
    assert spawner.spawn_batch_calls == []


@pytest.mark.asyncio
async def test_execute_none_agents_treated_as_empty():
    """agents=None 等同于空列表，不抛出异常。"""
    spawner = _MockSpawner()
    tool = DispatchAgentsTool(agent_registry=_MockRegistry(), spawner=spawner)
    result = await tool.execute(None, agents=None)
    assert result.success is True
    assert result.message == ""
    assert spawner.spawn_batch_calls == []


# ─── 非法 agent_id ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_invalid_agent_id_returns_error():
    """agents 中含非法 agent_id 时返回 success=False，列出可用列表。"""
    tool = DispatchAgentsTool(
        agent_registry=_MockRegistry(),
        spawner=_MockSpawner(),
    )
    result = await tool.execute(
        None,
        tasks=[{"task_id": 1, "agent_id": "nonexistent_agent", "task": "做些事"}],
    )
    assert result.success is False
    assert result.metadata["error_code"] == "INVALID_AGENT_IDS"
    assert "nonexistent_agent" in result.metadata["invalid_ids"]
    assert "literature_search" in result.metadata["available_ids"]
    assert "data_cleaner" in result.metadata["available_ids"]


@pytest.mark.asyncio
async def test_execute_mixed_valid_invalid_agent_ids_returns_error():
    """混合合法/非法 agent_id 时全部拒绝，不部分执行。"""
    tool = DispatchAgentsTool(
        agent_registry=_MockRegistry(),
        spawner=_MockSpawner(),
    )
    result = await tool.execute(
        None,
        tasks=[
            {"task_id": 1, "agent_id": "literature_search", "task": "合法任务"},
            {"task_id": 2, "agent_id": "bad_agent", "task": "非法任务"},
        ],
    )
    assert result.success is False
    assert "bad_agent" in result.metadata["invalid_ids"]
    assert "literature_search" not in result.metadata["invalid_ids"]


# ─── 部分失败 ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_partial_failure_included_in_message():
    """部分子 Agent 失败时，失败信息也包含在拼接结果中，success=True（至少一个成功）。"""
    tool = DispatchAgentsTool(
        agent_registry=_MockRegistry(),
        spawner=_MockSpawner(
            results=[
                SubAgentResult(agent_id="literature_search", success=True, summary="检索到 10 篇"),
                SubAgentResult(
                    agent_id="data_cleaner",
                    success=False,
                    summary="数据格式错误",
                    error="数据格式错误",
                ),
            ]
        ),
    )
    result = await tool.execute(
        None,
        tasks=[
            {"task_id": 1, "agent_id": "literature_search", "task": "检索文献"},
            {"task_id": 2, "agent_id": "data_cleaner", "task": "清洗数据"},
        ],
    )
    assert result.success is True
    assert "检索到 10 篇" in result.message
    assert "执行失败" in result.message
    assert result.metadata["success_count"] == 1
    assert result.metadata["failure_count"] == 1


@pytest.mark.asyncio
async def test_execute_all_failed_returns_failure():
    """所有子 Agent 都失败时，dispatch success=False。"""
    tool = DispatchAgentsTool(
        agent_registry=_MockRegistry(),
        spawner=_MockSpawner(
            results=[
                SubAgentResult(
                    agent_id="literature_search",
                    success=False,
                    summary="超时",
                    error="超时",
                ),
            ]
        ),
    )
    result = await tool.execute(
        None,
        tasks=[{"task_id": 1, "agent_id": "literature_search", "task": "检索文献"}],
    )
    assert result.success is False
    assert result.metadata["failure_count"] == 1
    assert result.metadata["success_count"] == 0


# ─── 依赖未注入 ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_no_spawner_returns_error():
    """spawner=None 时返回 success=False，不抛出异常。"""
    tool = DispatchAgentsTool(agent_registry=_MockRegistry(), spawner=None)
    result = await tool.execute(
        None,
        tasks=[{"task_id": 1, "agent_id": "literature_search", "task": "任务"}],
    )
    assert result.success is False
    assert result.metadata["error_code"] == "DISPATCH_AGENTS_NOT_INITIALIZED"


@pytest.mark.asyncio
async def test_execute_allows_current_wave_task_with_satisfied_dependencies():
    """已满足依赖且已进入当前 wave 的任务，应允许进入 dispatch。"""
    tool = DispatchAgentsTool(agent_registry=_MockRegistry(), spawner=_MockSpawner())
    session = _SessionWithTasks(
        [
            {"id": 1, "title": "准备数据", "status": "completed"},
            {"id": 2, "title": "清洗数据", "depends_on": [1], "status": "pending"},
        ]
    )
    result = await tool.execute(
        session,
        tasks=[
            {
                "task_id": 2,
                "agent_id": "data_cleaner",
                "task": "清洗数据",
                "depends_on": [1],
            }
        ],
    )
    assert result.success is True
    assert result.metadata["success_count"] == 1


@pytest.mark.asyncio
async def test_execute_rejects_task_outside_current_wave():
    """后续 wave 的任务不允许抢跑进入 dispatch。"""
    tool = DispatchAgentsTool(agent_registry=_MockRegistry(), spawner=_MockSpawner())
    session = _SessionWithTasks(
        [
            {"id": 1, "title": "准备数据", "status": "pending"},
            {"id": 2, "title": "清洗数据", "depends_on": [1], "status": "pending"},
        ]
    )
    result = await tool.execute(
        session,
        tasks=[
            {
                "task_id": 2,
                "agent_id": "data_cleaner",
                "task": "清洗数据",
                "depends_on": [1],
            }
        ],
    )
    assert result.success is False
    assert result.metadata["error_code"] == "TASK_NOT_IN_CURRENT_WAVE"
    assert result.metadata["current_wave_task_ids"] == [1]


@pytest.mark.asyncio
async def test_execute_rejects_conflicting_parallel_tasks():
    """存在读写冲突的任务必须串行，不允许同批派发。"""
    tool = DispatchAgentsTool(agent_registry=_MockRegistry(), spawner=_MockSpawner())
    result = await tool.execute(
        None,
        tasks=[
            {
                "task_id": 1,
                "agent_id": "data_cleaner",
                "task": "清洗原始数据",
                "output_refs": ["dataset:cleaned.v1"],
            },
            {
                "task_id": 2,
                "agent_id": "literature_search",
                "task": "消费清洗后数据做统计准备",
                "input_refs": ["dataset:cleaned.v1"],
            },
        ],
    )
    assert result.success is False
    assert result.metadata["error_code"] == "PARALLEL_TASK_CONFLICT"
    assert result.metadata["conflict_task_ids"] == [1, 2]


# ─── 工具元数据 ──────────────────────────────────────────────────────────────


def test_tool_name():
    """工具名称为 dispatch_agents。"""
    tool = DispatchAgentsTool()
    assert tool.name == "dispatch_agents"


def test_tool_expose_to_llm_false():
    """expose_to_llm 为 False（仅主 Agent 通过 Orchestrator 可用）。"""
    tool = DispatchAgentsTool()
    assert tool.expose_to_llm is False


def test_tool_parameters_schema():
    """parameters 同时支持结构化 tasks 和兼容 agents。"""
    tool = DispatchAgentsTool()
    params = tool.parameters
    assert "agents" in params["properties"]
    assert "tasks" in params["properties"]
    task_item = params["properties"]["tasks"]["items"]
    assert "task_id" in task_item["properties"]
    assert "agent_id" in task_item["properties"]
    assert "task" in task_item["properties"]
    assert "anyOf" in params
