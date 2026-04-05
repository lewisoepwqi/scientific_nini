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
