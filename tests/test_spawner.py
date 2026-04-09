"""测试 SubAgentSpawner 的核心功能。"""

from __future__ import annotations

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from nini.agent.model_resolver import ModelPreflightResult
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


@pytest.fixture(autouse=True)
def _mock_model_preflight():
    """默认将模型预检固定为可用，避免无关测试依赖本机试用额度状态。"""
    with patch(
        "nini.agent.model_resolver.model_resolver.preflight",
        AsyncMock(
            return_value=ModelPreflightResult(
                available=True,
                purpose="analysis",
                provider_id="mock",
                provider_name="mock",
                model="mock-model",
            )
        ),
    ):
        yield


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
async def test_spawn_batch_artifacts_written_to_parent_with_namespace():
    """spawn_batch 回写产物时使用命名空间键 {agent_id}.{key}。"""
    registry = MagicMock()

    def get_agent(agent_id: str):
        return make_agent_def(agent_id)

    registry.get.side_effect = get_agent
    spawner = SubAgentSpawner(registry, make_tool_registry())
    parent_session = make_mock_session()

    async def mock_execute(agent_def, task, session, **kwargs):
        return SubAgentResult(
            agent_id=agent_def.agent_id,
            success=True,
            artifacts={"result.csv": "data"},
        )

    with patch.object(spawner, "_execute_agent", side_effect=mock_execute):
        await spawner.spawn_batch([("test_agent", "任务")], parent_session)
    assert "test_agent.result.csv" in parent_session.artifacts
    assert "result.csv" not in parent_session.artifacts


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


def test_build_run_id_distinguishes_repeated_specialist_subtasks():
    spawner = SubAgentSpawner(MagicMock(), make_tool_registry())

    first = spawner._build_run_id("turn-1", "statistician", 1, 1)
    second = spawner._build_run_id("turn-1", "statistician", 1, 2)

    assert first != second
    assert first == "agent:turn-1:statistician:task1:1"
    assert second == "agent:turn-1:statistician:task2:1"


def test_derive_progress_payload_skips_token_level_reasoning_and_text():
    from nini.agent.events import AgentEvent, EventType

    spawner = SubAgentSpawner(MagicMock(), make_tool_registry())
    reasoning_event = AgentEvent(type=EventType.REASONING, data={"content": "思考中"})
    text_event = AgentEvent(type=EventType.TEXT, data="分片输出")

    assert spawner._derive_progress_payload(reasoning_event) is None
    assert spawner._derive_progress_payload(text_event) is None


# ─── datasets 隔离 ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_agent_datasets_shallow_copy():
    """_execute_agent 构造 SubSession 时使用父会话 datasets 的浅拷贝（而非共享引用）。"""
    registry = MagicMock()
    registry.get.return_value = make_agent_def()
    spawner = SubAgentSpawner(registry, make_tool_registry())
    parent_session = make_mock_session()
    parent_session.datasets = {"original_key": "value"}

    captured: dict = {}

    class _CapturingSubSession:
        """拦截 SubSession 构造，记录 datasets 参数后提前终止。"""

        def __init__(self, **kwargs):
            datasets_arg = kwargs.get("datasets", {})
            captured["is_copy"] = datasets_arg is not parent_session.datasets
            captured["has_original_key"] = "original_key" in datasets_arg
            raise RuntimeError("stop early for test")

    with patch("nini.agent.sub_session.SubSession", _CapturingSubSession):
        try:
            await spawner.spawn("test_agent", "任务", parent_session)
        except RuntimeError:
            pass

    assert (
        captured.get("is_copy") is True
    ), "SubSession 应接收 datasets 的浅拷贝，而非父会话原始引用"
    assert captured.get("has_original_key") is True, "浅拷贝应包含父会话原有键"


# ─── 命名空间回写 ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_spawn_batch_namespace_writeback_multi_agent_same_key():
    """多 Agent 同名键产物回写时，命名空间键 {agent_id}.{key} 相互独立，不丢失数据。"""
    registry = MagicMock()

    def get_agent(agent_id: str):
        return make_agent_def(agent_id)

    registry.get.side_effect = get_agent
    spawner = SubAgentSpawner(registry, make_tool_registry())
    parent_session = make_mock_session()

    call_count = 0

    async def mock_execute(agent_def, task, session, **kwargs):
        nonlocal call_count
        call_count += 1
        # 两个 agent 都产出同名键 "output.json"
        return SubAgentResult(
            agent_id=agent_def.agent_id,
            success=True,
            artifacts={"output.json": f"来自 {agent_def.agent_id}"},
        )

    with patch.object(spawner, "_execute_agent", side_effect=mock_execute):
        await spawner.spawn_batch([("agent_a", "任务1"), ("agent_b", "任务2")], parent_session)

    assert parent_session.artifacts.get("agent_a.output.json") == "来自 agent_a"
    assert parent_session.artifacts.get("agent_b.output.json") == "来自 agent_b"
    assert "output.json" not in parent_session.artifacts


# ─── 沙箱隔离与产物归档 ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_archive_sandbox_moves_files_on_success(tmp_path):
    """_archive_sandbox 成功时将沙箱产物移入 artifacts/{agent_id}/。"""
    from pathlib import Path
    from nini.agent.artifact_ref import ArtifactRef

    registry = make_registry("agent_a")
    spawner = SubAgentSpawner(registry, make_tool_registry())

    sandbox_dir = tmp_path / "sandbox_tmp" / "run_001"
    sandbox_dir.mkdir(parents=True)
    (sandbox_dir / "chart.json").write_text("plotly data")

    artifacts: dict = {
        "latest_chart": ArtifactRef(
            path="chart.json", type="chart", summary="测试图表", agent_id=""
        )
    }

    await spawner._archive_sandbox(
        sandbox_dir=sandbox_dir,
        parent_workspace=tmp_path,
        agent_id="agent_a",
        run_id="run_001",
        success=True,
        artifacts=artifacts,
    )

    dest = tmp_path / "artifacts" / "agent_a"
    assert dest.exists(), "归档目录应存在"
    assert (dest / "chart.json").exists(), "文件应已移动"
    assert not sandbox_dir.exists(), "沙箱目录应已移走"

    ref = artifacts["latest_chart"]
    assert isinstance(ref, ArtifactRef)
    assert "agent_a" in ref.path, f"路径应包含 agent_id，实际: {ref.path}"
    assert ref.agent_id == "agent_a"


@pytest.mark.asyncio
async def test_archive_sandbox_moves_to_failed_on_failure(tmp_path):
    """_archive_sandbox 失败时将沙箱产物移入 sandbox_tmp/.failed/{run_id}/。"""
    from nini.agent.artifact_ref import ArtifactRef

    registry = make_registry("agent_b")
    spawner = SubAgentSpawner(registry, make_tool_registry())

    sandbox_dir = tmp_path / "sandbox_tmp" / "run_002"
    sandbox_dir.mkdir(parents=True)
    (sandbox_dir / "partial.csv").write_text("incomplete data")

    artifacts: dict = {}

    await spawner._archive_sandbox(
        sandbox_dir=sandbox_dir,
        parent_workspace=tmp_path,
        agent_id="agent_b",
        run_id="run_002",
        success=False,
        artifacts=artifacts,
    )

    failed_dir = tmp_path / "sandbox_tmp" / ".failed" / "run_002"
    assert failed_dir.exists(), "失败归档目录应存在"
    assert (failed_dir / "partial.csv").exists(), "失败产物应保留"


@pytest.mark.asyncio
async def test_archive_sandbox_skips_empty_sandbox(tmp_path):
    """沙箱目录为空时，_archive_sandbox 应跳过移动。"""
    registry = make_registry("agent_c")
    spawner = SubAgentSpawner(registry, make_tool_registry())

    sandbox_dir = tmp_path / "sandbox_tmp" / "run_003"
    sandbox_dir.mkdir(parents=True)
    # 沙箱为空，不写入任何文件

    await spawner._archive_sandbox(
        sandbox_dir=sandbox_dir,
        parent_workspace=tmp_path,
        agent_id="agent_c",
        run_id="run_003",
        success=True,
        artifacts={},
    )

    dest = tmp_path / "artifacts" / "agent_c"
    assert not dest.exists(), "空沙箱不应创建归档目录"


# ─── model_preference 路由 ────────────────────────────────────────────────────


def make_agent_def_with_pref(
    agent_id: str = "test_agent", model_preference: str | None = None
) -> AgentDefinition:
    return AgentDefinition(
        agent_id=agent_id,
        name=f"测试 {agent_id}",
        description="测试用",
        system_prompt="你是测试助手",
        purpose="default",
        allowed_tools=[],
        timeout_seconds=5,
        model_preference=model_preference,
    )


def make_mock_session_with_depth() -> MagicMock:
    """创建带有 spawn_depth=0 的 mock 会话，避免 MagicMock < int 比较错误。"""
    session = make_mock_session()
    session.spawn_depth = 0
    return session


def make_tool_registry_with_list() -> MagicMock:
    """创建支持 list_tools() 的 mock 工具注册表。"""
    tool_registry = make_tool_registry()
    tool_registry.list_tools.return_value = []
    return tool_registry


@pytest.mark.asyncio
async def test_execute_agent_haiku_uses_fast_purpose(tmp_path, monkeypatch):
    """model_preference='haiku' 时，AgentRunner 应使用 purpose='fast' 的 resolver。"""
    from nini.agent.spawner import _FixedPurposeResolver
    from nini.config import settings

    registry = MagicMock()
    registry.get.return_value = make_agent_def_with_pref("haiku_agent", model_preference="haiku")
    spawner = SubAgentSpawner(registry, make_tool_registry_with_list())

    captured_resolver = {}

    def capture_runner(resolver=None, tool_registry=None, **kwargs):
        captured_resolver["resolver"] = resolver
        raise RuntimeError("stop early for test")

    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()

    with patch("nini.agent.runner.AgentRunner", side_effect=capture_runner):
        try:
            await spawner.spawn("haiku_agent", "任务", make_mock_session_with_depth())
        except RuntimeError:
            pass

    resolver = captured_resolver.get("resolver")
    assert isinstance(resolver, _FixedPurposeResolver), "应使用 _FixedPurposeResolver 包装"
    assert resolver._purpose == "fast", f"haiku 应映射到 purpose='fast'，实际: {resolver._purpose}"


@pytest.mark.asyncio
async def test_execute_agent_none_preference_uses_analysis_purpose(tmp_path, monkeypatch):
    """model_preference=None 时，AgentRunner 应使用 purpose='analysis' 的 resolver。"""
    from nini.agent.spawner import _FixedPurposeResolver
    from nini.config import settings

    registry = MagicMock()
    registry.get.return_value = make_agent_def_with_pref("default_agent", model_preference=None)
    spawner = SubAgentSpawner(registry, make_tool_registry_with_list())

    captured_resolver = {}

    def capture_runner(resolver=None, tool_registry=None, **kwargs):
        captured_resolver["resolver"] = resolver
        raise RuntimeError("stop early for test")

    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()

    with patch("nini.agent.runner.AgentRunner", side_effect=capture_runner):
        try:
            await spawner.spawn("default_agent", "任务", make_mock_session_with_depth())
        except RuntimeError:
            pass

    resolver = captured_resolver.get("resolver")
    assert isinstance(resolver, _FixedPurposeResolver), "应使用 _FixedPurposeResolver 包装"
    assert (
        resolver._purpose == "analysis"
    ), f"None preference 应映射到 purpose='analysis'，实际: {resolver._purpose}"


@pytest.mark.asyncio
async def test_spawn_marks_child_tool_error_as_failure_and_persists_child_session(
    tmp_path,
    monkeypatch,
):
    """子 Agent 出现 error 型 tool_result 时，应返回失败并保留可审计子会话目录。"""
    from nini.agent.events import AgentEvent, EventType
    from nini.config import settings

    registry = make_registry()
    tool_registry = make_tool_registry_with_list()
    tool_registry.list_tools.return_value = ["dataset_catalog", "task_state"]
    spawner = SubAgentSpawner(registry, tool_registry)
    parent_session = make_mock_session_with_depth()

    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()

    async def fake_iter(_runner, _session, _task, _stop_event):
        yield AgentEvent(
            type=EventType.TOOL_RESULT,
            data={
                "id": "call-1",
                "name": "dataset_catalog",
                "status": "error",
                "message": "系统内置「快速」试用额度已用完",
            },
        )

    with patch.object(spawner, "_iterate_runner_events", side_effect=fake_iter):
        result = await spawner.spawn("test_agent", "任务", parent_session)

    assert result.success is False
    assert result.stop_reason == "child_execution_failed"
    assert "试用额度已用完" in result.error
    assert result.child_session_id

    meta_path = tmp_path / "data" / "sessions" / result.child_session_id / "meta.json"
    assert meta_path.exists(), "子会话审计元信息应落盘"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["is_subsession"] is True
    assert meta["parent_session_id"] == parent_session.id


@pytest.mark.asyncio
async def test_execute_agent_strips_task_state_tools_from_regular_subagents(
    tmp_path,
    monkeypatch,
):
    """普通 specialist 子 Agent 不应再拿到 task_state/task_write。"""
    from nini.config import settings

    registry = MagicMock()
    registry.get.return_value = AgentDefinition(
        agent_id="plannerless_agent",
        name="测试 Agent",
        description="测试用",
        system_prompt="你是测试助手",
        purpose="analysis",
        allowed_tools=["dataset_catalog", "task_state", "task_write"],
        timeout_seconds=5,
    )
    tool_registry = make_tool_registry_with_list()
    tool_registry.list_tools.return_value = ["dataset_catalog", "task_state", "task_write"]
    captured_tools: dict[str, list[str]] = {}

    def capture_subset(tools):
        captured_tools["tools"] = list(tools)
        return MagicMock()

    tool_registry.create_subset.side_effect = capture_subset
    spawner = SubAgentSpawner(registry, tool_registry)
    parent_session = make_mock_session_with_depth()

    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()

    async def fake_iter(_runner, _session, _task, _stop_event):
        if False:
            yield None

    with patch.object(spawner, "_iterate_runner_events", side_effect=fake_iter):
        result = await spawner.spawn("plannerless_agent", "执行字段检查", parent_session)

    assert result.success is True
    assert captured_tools["tools"] == ["dataset_catalog"]


