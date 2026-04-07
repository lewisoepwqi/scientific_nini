"""multi-agent-foundation 剩余任务的集成验证。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nini.agent import event_builders as eb
from nini.agent.fusion import FusionResult
from nini.agent.runner import AgentRunner
from nini.agent.session import session_manager
from nini.agent.spawner import SubAgentResult
from nini.api import websocket as websocket_module
from nini.api.websocket import get_tool_registry
from nini.app import create_app
from nini.config import settings
from tests.client_utils import LocalASGIClient, live_websocket_connect


@pytest.fixture
def app_with_temp_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """使用临时目录隔离多 Agent 集成测试数据。"""
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()
    session_manager._sessions.clear()
    yield create_app()
    session_manager._sessions.clear()


def _create_session_and_upload(app) -> str:
    """创建会话并上传测试数据集，返回 session_id。"""
    with LocalASGIClient(app) as client:
        session_resp = client.post("/api/sessions")
        session_id = session_resp.json()["data"]["session_id"]
        upload_resp = client.post(
            "/api/upload",
            data={"session_id": session_id},
            files={
                "file": (
                    "experiment.csv",
                    "group,value\ncontrol,1.0\ntreatment,2.5\n",
                    "text/csv",
                )
            },
        )
        assert upload_resp.status_code == 200
        assert upload_resp.json()["success"] is True
        return session_id


def _install_dispatch_stubs(
    monkeypatch: pytest.MonkeyPatch,
    *,
    failing_agent: str | None = None,
) -> None:
    """将 dispatch_agents 的子 Agent 执行与结果融合替换为确定性 stub。"""
    registry = get_tool_registry()
    assert registry is not None
    tool = registry.get("dispatch_agents")
    assert tool is not None

    async def fake_execute_agent(agent_def, task, session, **kwargs):
        if failing_agent and agent_def.agent_id == failing_agent:
            raise RuntimeError(f"模拟 {agent_def.agent_id} 失败")
        return SubAgentResult(
            agent_id=agent_def.agent_id,
            success=True,
            summary=f"{agent_def.agent_id} 完成",
            # 使用简单键名：命名空间回写后最终键为 "{agent_id}.output"
            artifacts={
                "output": {
                    "agent_id": agent_def.agent_id,
                    "task": task,
                }
            },
        )

    async def fake_fuse(results, strategy="auto"):
        content = " | ".join(
            result.summary
            for result in results
            if isinstance(result, SubAgentResult) and result.summary
        )
        return FusionResult(
            content=content,
            strategy="concatenate",
            sources=[result.agent_id for result in results],
        )

    monkeypatch.setattr(tool._spawner, "_execute_agent", fake_execute_agent)
    monkeypatch.setattr(tool._fusion_engine, "fuse", fake_fuse)


def _collect_until_terminal(ws, limit: int = 40) -> list[dict]:
    """收集事件直到 done/error。"""
    events: list[dict] = []
    for _ in range(limit):
        event = ws.receive_json()
        events.append(event)
        if event["type"] in {"done", "error"}:
            break
    return events


def _install_harness_dispatch_flow(
    monkeypatch: pytest.MonkeyPatch,
    *,
    failing_agent: str | None = None,
    final_text: str = "多 Agent 分析已完成。",
) -> None:
    """用确定性的 Harness 流程驱动真实 dispatch_agents 执行。"""

    async def fake_run(
        self,
        session,
        user_message,
        *,
        append_user_message: bool = True,
        stop_event=None,
    ):
        del self, stop_event
        _install_dispatch_stubs(monkeypatch, failing_agent=failing_agent)
        turn_id = "turn-multi-agent"
        tool_call_id = "dispatch-call"
        dispatch_args = json.dumps(
            {
                "tasks": ["清洗这份数据", "做统计分析"],
                "context": "用户已上传 experiment.csv",
            },
            ensure_ascii=False,
        )

        if append_user_message:
            session.add_message("user", user_message, turn_id=turn_id)
        session.title = "多 Agent 测试"

        yield eb.build_iteration_start_event(iteration=0, turn_id=turn_id)
        session.add_tool_call(tool_call_id, "dispatch_agents", dispatch_args, turn_id=turn_id)
        yield eb.build_tool_call_event(
            tool_call_id=tool_call_id,
            name="dispatch_agents",
            arguments=dispatch_args,
            turn_id=turn_id,
        )

        agent_runner = AgentRunner(tool_registry=get_tool_registry())
        dispatch_tc = {
            "id": tool_call_id,
            "function": {
                "name": "dispatch_agents",
                "arguments": dispatch_args,
            },
        }
        async for event in agent_runner._handle_dispatch_agents(dispatch_tc, session, turn_id):
            yield event

        session.add_message("assistant", final_text, turn_id=turn_id)
        yield eb.build_text_event(final_text, turn_id=turn_id)
        yield eb.build_done_event(turn_id=turn_id)

    monkeypatch.setattr(websocket_module.HarnessRunner, "run", fake_run)


def test_websocket_dispatch_agents_emits_expected_agent_start_events(
    app_with_temp_data,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """上传数据后发起多 Agent 请求，应收到 data_cleaner/statistician 的启动事件。"""
    session_id = _create_session_and_upload(app_with_temp_data)
    _install_harness_dispatch_flow(monkeypatch)

    with live_websocket_connect(app_with_temp_data, "/ws") as ws:
        ws.send_text(
            json.dumps(
                {
                    "type": "chat",
                    "content": "帮我清洗这份数据并做统计分析",
                    "session_id": session_id,
                },
                ensure_ascii=False,
            )
        )
        events = _collect_until_terminal(ws)

    agent_start_ids = [
        event["data"]["agent_id"] for event in events if event["type"] == "agent_start"
    ]
    assert "data_cleaner" in agent_start_ids
    assert "statistician" in agent_start_ids
    assert "error" not in [event["type"] for event in events]


def test_websocket_dispatch_agents_writes_child_artifacts_to_parent_session(
    app_with_temp_data,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """两个子 Agent 完成后，父会话应汇总子 Agent 产物。"""
    session_id = _create_session_and_upload(app_with_temp_data)
    _install_harness_dispatch_flow(monkeypatch, final_text="结果已合并。")

    with live_websocket_connect(app_with_temp_data, "/ws") as ws:
        ws.send_text(
            json.dumps(
                {
                    "type": "chat",
                    "content": "帮我清洗这份数据并做统计分析",
                    "session_id": session_id,
                },
                ensure_ascii=False,
            )
        )
        events = _collect_until_terminal(ws)

    session = session_manager.get_session(session_id)
    assert session is not None
    # 命名空间键格式：{agent_id}.{artifact_key}
    assert "data_cleaner.output" in session.artifacts
    assert "statistician.output" in session.artifacts
    assert "done" in [event["type"] for event in events]


def test_websocket_dispatch_agents_partial_failure_does_not_interrupt_main_agent(
    app_with_temp_data,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """单个子 Agent 失败时，其余子 Agent 与主 Agent 仍应继续完成。"""
    session_id = _create_session_and_upload(app_with_temp_data)
    _install_harness_dispatch_flow(
        monkeypatch,
        failing_agent="data_cleaner",
        final_text="主 Agent 已处理部分失败并继续返回结果。",
    )

    with live_websocket_connect(app_with_temp_data, "/ws") as ws:
        ws.send_text(
            json.dumps(
                {
                    "type": "chat",
                    "content": "帮我清洗这份数据并做统计分析",
                    "session_id": session_id,
                },
                ensure_ascii=False,
            )
        )
        events = _collect_until_terminal(ws)

    event_types = [event["type"] for event in events]
    agent_errors = [event["data"]["agent_id"] for event in events if event["type"] == "agent_error"]
    agent_completes = [
        event["data"]["agent_id"] for event in events if event["type"] == "agent_complete"
    ]
    tool_result = next(event for event in events if event["type"] == "tool_result")

    assert "data_cleaner" in agent_errors
    assert "statistician" in agent_completes
    assert tool_result["data"]["status"] == "success"
    assert tool_result["data"]["result"]["metadata"]["partial_failure"] is True
    assert tool_result["data"]["result"]["metadata"]["failure_count"] == 1
    assert "done" in event_types
    assert "error" not in event_types
