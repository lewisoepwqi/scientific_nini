"""测试 DispatchAgentsTool —— 正常执行、空任务、依赖未注入。"""

from __future__ import annotations

import pytest

from nini.agent.fusion import FusionResult, ResultFusionEngine
from nini.agent.spawner import SubAgentResult
from nini.tools.dispatch_agents import DispatchAgentsTool
from nini.tools.base import ToolResult

# ─── 辅助 ───────────────────────────────────────────────────────────────────


class _MockRegistry:
    """最小 AgentRegistry stub。"""

    def list_agents(self):
        return [type("Def", (), {"agent_id": "data_cleaner"})()]


class _MockSpawner:
    """最小 SubAgentSpawner stub，返回固定结果。"""

    def __init__(self, results=None):
        self._results = results or [
            SubAgentResult(agent_id="data_cleaner", success=True, summary="清洗完成")
        ]
        self.call_count = 0

    async def spawn_batch(self, tasks, session, **kwargs):
        self.call_count += 1
        return self._results


class _MockFusion:
    """最小 ResultFusionEngine stub，返回固定融合结果。"""

    async def fuse(self, results, strategy="auto"):
        content = " | ".join(r.summary for r in results if r.summary)
        return FusionResult(content=content, strategy="concatenate")


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


@pytest.mark.asyncio
async def test_execute_calls_spawn_batch():
    """execute() 调用 spawner.spawn_batch()。"""
    spawner = _MockSpawner()
    tool = DispatchAgentsTool(
        agent_registry=_MockRegistry(),
        spawner=spawner,
        fusion_engine=_MockFusion(),
    )
    await tool.execute(None, tasks=["任务1", "任务2"])
    assert spawner.call_count == 1


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
    assert "dispatch_agents" in result.message.lower() or result.message


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


# ─── 工具元数据 ──────────────────────────────────────────────────────────────


def test_tool_name():
    """工具名称为 dispatch_agents。"""
    tool = DispatchAgentsTool()
    assert tool.name == "dispatch_agents"


def test_tool_expose_to_llm_false():
    """expose_to_llm 为 False（通过 Orchestrator 路径暴露）。"""
    tool = DispatchAgentsTool()
    assert tool.expose_to_llm is False
