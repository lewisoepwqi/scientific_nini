"""测试 DispatchAgentsTool —— 新 schema: agents=[{agent_id, task}]。

覆盖场景：
- 正常并行执行，结果正确拼接
- agents 为空时快速返回
- 非法 agent_id 返回结构化错误
- 部分子 Agent 失败时结果仍完整返回
"""

from __future__ import annotations

import pytest

from nini.agent.spawner import SubAgentResult
from nini.tools.dispatch_agents import DispatchAgentsTool
from nini.tools.base import ToolResult


# ─── 辅助 ────────────────────────────────────────────────────────────────────


class _MockRegistry:
    """最小 AgentRegistry stub，注册两个合法 agent_id。"""

    def list_agents(self):
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
        agents=[{"agent_id": "literature_search", "task": "检索高血压文献"}],
    )
    assert isinstance(result, ToolResult)
    assert result.success is True
    assert "[literature_search]" in result.message
    assert "检索完成" in result.message
    assert result.metadata["agent_count"] == 1
    assert result.metadata["success_count"] == 1
    assert result.metadata["failure_count"] == 0


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
        agents=[
            {"agent_id": "literature_search", "task": "检索文献"},
            {"agent_id": "data_cleaner", "task": "清洗数据"},
        ],
    )
    assert len(spawner.spawn_batch_calls) == 1
    pairs = spawner.spawn_batch_calls[0]
    assert pairs[0] == ("literature_search", "检索文献")
    assert pairs[1] == ("data_cleaner", "清洗数据")


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
        agents=[{"agent_id": "data_engineer", "task": "做些事"}],
    )
    assert result.success is False
    assert result.metadata["error_code"] == "INVALID_AGENT_IDS"
    assert "data_engineer" in result.metadata["invalid_ids"]
    assert "literature_search" in result.metadata["available_ids"]
    assert "data_cleaner" in result.metadata["available_ids"]
    assert result.recovery_hint
    assert "data_cleaner" in result.metadata["suggested_agent_ids"]["data_engineer"]


@pytest.mark.asyncio
async def test_execute_mixed_valid_invalid_agent_ids_returns_error():
    """混合合法/非法 agent_id 时全部拒绝，不部分执行。"""
    tool = DispatchAgentsTool(
        agent_registry=_MockRegistry(),
        spawner=_MockSpawner(),
    )
    result = await tool.execute(
        None,
        agents=[
            {"agent_id": "literature_search", "task": "合法任务"},
            {"agent_id": "bad_agent", "task": "非法任务"},
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
                SubAgentResult(
                    agent_id="literature_search", success=True, summary="检索到 10 篇"
                ),
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
        agents=[
            {"agent_id": "literature_search", "task": "检索文献"},
            {"agent_id": "data_cleaner", "task": "清洗数据"},
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
        agents=[{"agent_id": "literature_search", "task": "检索文献"}],
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
        agents=[{"agent_id": "literature_search", "task": "任务"}],
    )
    assert result.success is False
    assert result.metadata["error_code"] == "DISPATCH_AGENTS_NOT_INITIALIZED"


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
    """parameters 中 agents 字段 schema 符合新格式。"""
    tool = DispatchAgentsTool()
    params = tool.parameters
    assert "agents" in params["properties"]
    agent_item = params["properties"]["agents"]["items"]
    assert "agent_id" in agent_item["properties"]
    assert "task" in agent_item["properties"]
    assert "agents" in params["required"]
