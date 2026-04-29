"""Phase 4：会话持久化与恢复测试。"""

from __future__ import annotations

from datetime import datetime, timezone
import io
import json
import time
import zipfile
from pathlib import Path
from urllib.parse import quote

import pytest

from nini.agent.runner import AgentRunner, EventType
from nini.agent.session import Session, session_manager
from nini.app import create_app
from nini.config import settings
from nini.memory.conversation import ConversationMemory
from nini.sandbox.approval_manager import approval_manager
from nini.workspace import WorkspaceManager
from tests.client_utils import LocalASGIClient


@pytest.fixture(autouse=True)
def isolate_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()
    session_manager._sessions.clear()

    async def _mock_get_active_provider_id():
        return "dummy"

    async def _mock_list_user_configured_provider_ids():
        return ["dummy"]

    monkeypatch.setattr("nini.config_manager.get_active_provider_id", _mock_get_active_provider_id)
    monkeypatch.setattr(
        "nini.config_manager.list_user_configured_provider_ids",
        _mock_list_user_configured_provider_ids,
    )
    yield
    session_manager._sessions.clear()


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """创建带临时数据目录的 HTTP 测试客户端。"""
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()
    session_manager._sessions.clear()
    app = create_app()
    client = LocalASGIClient(app)
    yield client
    client.close()
    session_manager._sessions.clear()


class _ApprovalResolver:
    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages, tools=None, temperature=None, max_tokens=None, **kwargs):
        self.calls += 1

        class _Chunk:
            def __init__(self, *, text: str, tool_calls):
                self.text = text
                self.reasoning = ""
                self.raw_text = text
                self.tool_calls = tool_calls
                self.usage = None

        if self.calls == 1:
            yield _Chunk(
                text="尝试写文件",
                tool_calls=[
                    {
                        "id": "call_workspace_1",
                        "type": "function",
                        "function": {
                            "name": "workspace_session",
                            "arguments": json.dumps(
                                {
                                    "operation": "write",
                                    "file_path": "notes/test.md",
                                    "content": "hello",
                                },
                                ensure_ascii=False,
                            ),
                        },
                    }
                ],
            )
            return

        yield _Chunk(text="完成", tool_calls=[])


class _ApprovalRegistry:
    def get_tool_definitions(self) -> list[dict[str, object]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "workspace_session",
                    "description": "工作区会话工具",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

    def list_markdown_tools(self) -> list[dict[str, object]]:
        return [
            {
                "type": "markdown",
                "name": "guarded-skill",
                "description": "受限技能",
                "category": "workflow",
                "location": "/tmp/guarded/SKILL.md",
                "enabled": True,
                "metadata": {
                    "user_invocable": True,
                    "allowed_tools": ["run_code"],
                },
            }
        ]

    async def execute(self, tool_name: str, session: Session, **kwargs):
        if tool_name != "workspace_session":
            return {"error": f"unknown skill: {tool_name}"}
        return {"success": True, "message": "workspace write ok"}

    async def execute_with_fallback(self, tool_name: str, session: Session, **kwargs):
        return await self.execute(tool_name, session=session, **kwargs)


def test_session_messages_persist_and_restore() -> None:
    session = session_manager.create_session()
    session.add_message("user", "你好")
    session.add_message("assistant", "已收到")
    session.add_tool_result("tool-1", '{"ok": true}')
    session_id = session.id

    # 模拟进程重启后的内存清空
    session_manager._sessions.clear()
    restored = session_manager.get_or_create(session_id)

    assert restored.id == session_id
    assert len(restored.messages) == 3
    assert restored.messages[0]["content"] == "你好"
    assert restored.messages[1]["content"] == "已收到"
    assert restored.messages[2]["role"] == "tool"


def test_session_tool_approvals_persist_and_restore() -> None:
    session = session_manager.create_session()
    session.add_message("user", "请继续")
    session.grant_tool_approval("workspace_session:write")
    session_id = session.id

    session_manager._sessions.clear()
    restored = session_manager.get_or_create(session_id)

    assert restored.id == session_id
    assert restored.has_tool_approval("workspace_session:write")
    assert restored.tool_approval_grants == {"workspace_session:write": "session"}


def test_session_sandbox_import_approvals_persist_and_restore() -> None:
    session = session_manager.create_session()
    session.grant_sandbox_import_approval(["sympy"], scope="session")
    session_id = session.id

    session_manager._sessions.clear()
    restored = session_manager.get_or_create(session_id)

    assert restored.has_sandbox_import_approval("sympy")
    assert "sympy" in restored.sandbox_approved_imports


def test_persistent_sandbox_import_approvals_load_into_new_session() -> None:
    approval_manager.grant_approved_imports(["sympy"])

    session = session_manager.create_session()

    assert session.has_sandbox_import_approval("sympy")


@pytest.mark.asyncio
async def test_runner_tool_approval_persists_across_restart() -> None:
    session = session_manager.create_session()

    async def _ask_handler(_session: Session, _tool_call_id: str, _payload: dict[str, object]):
        return {"approval": "本会话同类工具都放行"}

    runner = AgentRunner(
        resolver=_ApprovalResolver(),
        tool_registry=_ApprovalRegistry(),
        ask_user_question_handler=_ask_handler,
    )

    async for event in runner.run(session, "/guarded-skill 执行流程"):
        if event.type == EventType.DONE:
            break

    session_id = session.id
    assert session.has_tool_approval("workspace_session:write")

    session_manager._sessions.clear()
    restored = session_manager.get_or_create(session_id)

    assert restored.has_tool_approval("workspace_session:write")


def test_session_messages_persist_canonical_metadata() -> None:
    """持久化后的消息应保留 canonical 字段。"""
    session = session_manager.create_session()
    turn_id = "turn-meta"
    session.add_message("user", "请分析", turn_id=turn_id)
    session.add_reasoning(
        "先确认分析范围",
        reasoning_type="planning",
        reasoning_id="reason-1",
        turn_id=turn_id,
    )
    session.add_message(
        "assistant",
        "这是最终回答",
        turn_id=turn_id,
        message_id="turn-meta-0",
        operation="replace",
    )
    session.add_tool_result(
        "call-meta",
        '{"ok": true}',
        tool_name="run_code",
        status="success",
        turn_id=turn_id,
        message_id="tool-result-call-meta",
    )
    session_id = session.id

    session_manager._sessions.clear()
    restored = session_manager.get_or_create(session_id)

    assert len(restored.messages) == 4
    assert restored.messages[0]["turn_id"] == turn_id
    assert restored.messages[0]["event_type"] == "message"
    assert restored.messages[0]["_ts"]
    assert restored.messages[1]["event_type"] == "reasoning"
    assert restored.messages[1]["reasoning_id"] == "reason-1"
    assert restored.messages[1]["operation"] == "complete"
    assert restored.messages[2]["message_id"] == "turn-meta-0"
    assert restored.messages[2]["operation"] == "replace"
    assert restored.messages[3]["event_type"] == "tool_result"
    assert restored.messages[3]["message_id"] == "tool-result-call-meta"
    assert restored.messages[3]["tool_name"] == "run_code"


def test_list_sessions_includes_disk_sessions() -> None:
    session = session_manager.create_session()
    session.add_message("user", "persist me")
    sid = session.id

    session_manager._sessions.clear()
    sessions = session_manager.list_sessions()

    found = next((item for item in sessions if item["id"] == sid), None)
    assert found is not None
    assert found["source"] == "disk"
    assert found["message_count"] >= 1


def test_list_sessions_message_count_includes_archived_history() -> None:
    """会话列表中的消息数应包含已压缩归档的历史。"""
    from nini.memory.compression import compress_session_history

    session = session_manager.create_session()
    session.add_message("user", "开始分析")
    session.add_message("assistant", "步骤一")
    session.add_message("assistant", "步骤二")
    session.add_message("assistant", "步骤三")
    session.add_message("user", "继续")
    session.add_message("assistant", "步骤四")
    total_before = len(session.messages)
    sid = session.id

    result = compress_session_history(session, ratio=0.5, min_messages=4)
    assert result["success"] is True
    assert len(session.messages) < total_before

    session_manager._sessions.clear()
    sessions = session_manager.list_sessions()

    found = next(item for item in sessions if item["id"] == sid)
    assert found["message_count"] == total_before


def test_list_sessions_sorts_by_updated_at_desc() -> None:
    older = session_manager.create_session()
    older.add_message("user", "old")
    newer = session_manager.create_session()
    newer.add_message("user", "new")

    session_manager._sessions.clear()
    older_mtime = (settings.sessions_dir / older.id / "memory.jsonl").stat().st_mtime
    newer_mtime = (settings.sessions_dir / newer.id / "memory.jsonl").stat().st_mtime
    session_manager._save_session_meta_fields(
        older.id,
        {
            "updated_at": "2026-01-01T00:00:00+00:00",
            "_memory_mtime": older_mtime,
            "message_count": 1,
        },
    )
    session_manager._save_session_meta_fields(
        newer.id,
        {
            "updated_at": "2026-01-02T00:00:00+00:00",
            "_memory_mtime": newer_mtime,
            "message_count": 1,
        },
    )

    sessions = session_manager.list_sessions()
    ids = [item["id"] for item in sessions]
    assert ids.index(newer.id) < ids.index(older.id)


def test_list_sessions_refreshes_updated_at_when_memory_file_changes() -> None:
    session = session_manager.create_session()
    session.add_message("user", "first")
    session_id = session.id

    session_manager._sessions.clear()
    session_manager._save_session_meta_fields(
        session_id,
        {"updated_at": "2026-01-01T00:00:00+00:00"},
    )

    memory_path = settings.sessions_dir / session_id / "memory.jsonl"
    assert memory_path.exists()
    time.sleep(0.01)
    with memory_path.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "role": "assistant",
                    "content": "second",
                    "_ts": "2026-03-07T00:00:00+00:00",
                    "event_type": "text",
                },
                ensure_ascii=False,
            )
            + "\n"
        )

    sessions = session_manager.list_sessions()
    found = next(item for item in sessions if item["id"] == session_id)
    expected_updated_at = datetime.fromtimestamp(
        memory_path.stat().st_mtime, timezone.utc
    ).isoformat()

    assert found["updated_at"] == expected_updated_at


def test_list_sessions_does_not_backfill_created_at_with_scan_time() -> None:
    """列表扫描刷新消息计数时，不应把旧会话 created_at 写成当前扫描时间。"""
    session = session_manager.create_session()
    session.add_message("user", "old message")
    session_id = session.id
    session_manager._sessions.clear()

    memory_path = settings.sessions_dir / session_id / "memory.jsonl"
    assert memory_path.exists()
    old_message_ts = "2026-01-01T00:00:00+00:00"
    memory_path.write_text(
        json.dumps(
            {
                "role": "user",
                "content": "old message",
                "event_type": "message",
                "turn_id": "turn-old",
                "_ts": old_message_ts,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    meta_path = settings.sessions_dir / session_id / "meta.json"
    if meta_path.exists():
        meta_path.unlink()
    db_path = settings.sessions_dir / session_id / settings.session_db_filename
    if db_path.exists():
        db_path.unlink()

    sessions = session_manager.list_sessions()
    found = next(item for item in sessions if item["id"] == session_id)

    assert found["created_at"] == old_message_ts
    assert found["updated_at"] != found["created_at"] or found["updated_at"] >= found["created_at"]


def test_list_sessions_normalizes_created_at_newer_than_updated_at() -> None:
    """已污染的 created_at 不应继续作为 API 输出的创建时间。"""
    session = session_manager.create_session()
    session.add_message("user", "historical")
    session_id = session.id
    session_manager._sessions.clear()

    memory_path = settings.sessions_dir / session_id / "memory.jsonl"
    first_ts = "2026-01-02T00:00:00+00:00"
    memory_path.write_text(
        json.dumps(
            {
                "role": "user",
                "content": "historical",
                "event_type": "message",
                "turn_id": "turn-historical",
                "_ts": first_ts,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    memory_mtime = memory_path.stat().st_mtime
    session_manager._save_session_meta_fields(
        session_id,
        {
            "created_at": "2026-04-29T02:57:18+00:00",
            "updated_at": "2026-01-02T00:00:01+00:00",
            "_memory_mtime": memory_mtime,
            "message_count": 1,
        },
    )

    sessions = session_manager.list_sessions()
    found = next(item for item in sessions if item["id"] == session_id)

    assert found["created_at"] == first_ts
    assert found["created_at"] <= found["updated_at"]


def test_list_sessions_sorts_by_parsed_updated_at_not_iso_string() -> None:
    """不同 ISO 表示法应按真实时间排序，而不是按字符串字典序排序。"""
    older = session_manager.create_session()
    older.add_message("user", "older")
    newer = session_manager.create_session()
    newer.add_message("user", "newer")
    session_manager._sessions.clear()

    older_mtime = (settings.sessions_dir / older.id / "memory.jsonl").stat().st_mtime
    newer_mtime = (settings.sessions_dir / newer.id / "memory.jsonl").stat().st_mtime
    session_manager._save_session_meta_fields(
        older.id,
        {
            "created_at": "2026-01-02T00:00:00+00:00",
            "updated_at": "2026-01-02T00:30:00+00:00",
            "_memory_mtime": older_mtime,
            "message_count": 1,
        },
    )
    session_manager._save_session_meta_fields(
        newer.id,
        {
            "created_at": "2026-01-01T23:00:00-01:00",
            "updated_at": "2026-01-01T23:45:00-01:00",
            "_memory_mtime": newer_mtime,
            "message_count": 1,
        },
    )

    sessions = session_manager.list_sessions()
    ids = [item["id"] for item in sessions]

    assert ids.index(newer.id) < ids.index(older.id)


def test_list_sessions_supports_query_and_pagination(client: LocalASGIClient) -> None:
    alpha = session_manager.create_session()
    alpha.title = "Alpha session"
    session_manager.save_session_title(alpha.id, alpha.title)

    beta = session_manager.create_session()
    beta.title = "Beta analysis"
    session_manager.save_session_title(beta.id, beta.title)

    gamma = session_manager.create_session()
    gamma.title = "Gamma notes"
    session_manager.save_session_title(gamma.id, gamma.title)

    resp = client.get("/api/sessions?q=beta&limit=1&offset=0")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["success"] is True
    data = payload["data"]
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["id"] == beta.id
    assert "updated_at" in data[0]


def test_get_session_detail_message_count_includes_archived_history(
    client: LocalASGIClient,
) -> None:
    """会话详情中的消息数应包含已压缩归档的历史。"""
    from nini.memory.compression import compress_session_history

    resp = client.post("/api/sessions")
    session_id = resp.json()["data"]["session_id"]

    session = session_manager.get_session(session_id)
    assert session is not None
    session.add_message("user", "开始分析")
    session.add_message("assistant", "步骤一")
    session.add_message("assistant", "步骤二")
    session.add_message("assistant", "步骤三")
    session.add_message("user", "继续")
    session.add_message("assistant", "步骤四")
    total_before = len(session.messages)

    result = compress_session_history(session, ratio=0.5, min_messages=4)
    assert result["success"] is True
    assert len(session.messages) < total_before

    detail_resp = client.get(f"/api/sessions/{session_id}")
    assert detail_resp.status_code == 200
    payload = detail_resp.json()
    assert payload["data"]["message_count"] == total_before


def test_get_session_agent_runs_returns_run_summaries(client: LocalASGIClient) -> None:
    """agent-runs 端点默认返回线程摘要，不再返回全量事件。"""
    resp = client.post("/api/sessions")
    assert resp.status_code == 201
    session_id = resp.json()["data"]["session_id"]

    session_manager.append_agent_run_event(
        session_id,
        {
            "type": "agent_progress",
            "turn_id": "turn-agent-1",
            "data": {"event_type": "agent_progress", "message": "处理中"},
            "metadata": {
                "run_scope": "subagent",
                "run_id": "agent:turn-agent-1:statistician:1",
                "parent_run_id": "dispatch:call-1",
                "agent_id": "statistician",
                "agent_name": "统计分析",
                "attempt": 1,
                "phase": "thinking",
                "turn_id": "turn-agent-1",
            },
        },
    )
    session_manager.append_agent_run_event(
        session_id,
        {
            "type": "dispatch_agents_preflight",
            "turn_id": "turn-agent-1",
            "data": {
                "task_count": 1,
                "routed_task_count": 1,
                "runnable_count": 1,
                "preflight_failure_count": 0,
                "routing_failure_count": 0,
                "preflight_failures": [],
                "routed_agents": ["statistician"],
            },
            "metadata": {
                "run_scope": "dispatch",
                "run_id": "dispatch:call-1",
                "parent_run_id": "root:turn-agent-1",
                "agent_id": "dispatch_agents",
                "agent_name": "dispatch_agents",
                "attempt": 1,
                "phase": "preflight",
                "turn_id": "turn-agent-1",
            },
        },
    )
    session_manager.append_agent_run_event(
        session_id,
        {
            "type": "dispatch_agents_result",
            "turn_id": "turn-agent-2",
            "data": {
                "task_count": 2,
                "success_count": 0,
                "failure_count": 3,
                "stopped_count": 0,
                "preflight_failure_count": 1,
                "routing_failure_count": 1,
                "execution_failure_count": 1,
                "preflight_failures": [
                    {
                        "agent_id": "statistician",
                        "task": "执行正态性检验",
                        "error": "模型额度不足",
                    }
                ],
                "routing_failures": [
                    {
                        "agent_id": "router_guard",
                        "task": "识别干预标记",
                        "error": "未找到可用 agent",
                    }
                ],
                "execution_failures": [
                    {
                        "agent_id": "viz_designer",
                        "task": "绘制散点图",
                        "error": "Plotly 导出失败",
                    }
                ],
            },
            "metadata": {
                "run_scope": "dispatch",
                "run_id": "dispatch:call-2",
                "parent_run_id": "root:turn-agent-2",
                "agent_id": "dispatch_agents",
                "agent_name": "dispatch_agents",
                "attempt": 1,
                "phase": "fused",
                "turn_id": "turn-agent-2",
            },
        },
    )
    session_manager.append_agent_run_event(
        session_id,
        {
            "type": "dispatch_agents_result",
            "turn_id": "turn-agent-1",
            "data": {
                "task_count": 1,
                "routed_agents": ["statistician"],
                "subtasks": [],
                "preflight_failure_count": 0,
                "routing_failure_count": 0,
                "execution_failure_count": 0,
                "preflight_failures": [],
                "routing_failures": [],
                "execution_failures": [],
            },
            "metadata": {
                "run_scope": "dispatch",
                "run_id": "dispatch:call-1",
                "parent_run_id": "root:turn-agent-1",
                "agent_id": "dispatch_agents",
                "agent_name": "dispatch_agents",
                "attempt": 1,
                "phase": "fused",
                "turn_id": "turn-agent-1",
            },
        },
    )

    agent_runs_resp = client.get(f"/api/sessions/{session_id}/agent-runs?turn_id=turn-agent-1")
    assert agent_runs_resp.status_code == 200
    payload = agent_runs_resp.json()
    assert payload["success"] is True
    data = payload["data"]
    assert data["session_id"] == session_id
    assert data["turn_id"] == "turn-agent-1"
    assert data["event_count"] == 3
    assert "events" not in data
    assert len(data["runs"]) == 2

    dispatch_run = next(item for item in data["runs"] if item["run_id"] == "dispatch:call-1")
    child_run = next(
        item for item in data["runs"] if item["run_id"] == "agent:turn-agent-1:statistician:1"
    )
    assert dispatch_run["run_scope"] == "dispatch"
    assert dispatch_run["latest_phase"] == "fused"
    assert dispatch_run["status"] == "completed"
    assert dispatch_run["failure_count"] == 0
    assert dispatch_run["failures"] == []
    assert dispatch_run["dispatch_ledger"] == []
    assert child_run["agent_name"] == "统计分析"
    assert child_run["parent_run_id"] == "dispatch:call-1"
    assert child_run["progress_message"] == "处理中"


def test_get_session_agent_runs_includes_preflight_failure_details(
    client: LocalASGIClient,
) -> None:
    """dispatch 摘要应包含预检失败明细，便于前端账本直接消费。"""
    resp = client.post("/api/sessions")
    assert resp.status_code == 201
    session_id = resp.json()["data"]["session_id"]

    session_manager.append_agent_run_event(
        session_id,
        {
            "type": "dispatch_agents_preflight",
            "turn_id": "turn-agent-2",
            "data": {
                "task_count": 2,
                "routed_task_count": 1,
                "runnable_count": 1,
                "preflight_failure_count": 1,
                "routing_failure_count": 0,
                "preflight_failures": [
                    {
                        "agent_id": "statistician",
                        "task": "执行正态性检验",
                        "error": "模型额度不足",
                    }
                ],
            },
            "metadata": {
                "run_scope": "dispatch",
                "run_id": "dispatch:call-2",
                "parent_run_id": "root:turn-agent-2",
                "agent_id": "dispatch_agents",
                "agent_name": "dispatch_agents",
                "attempt": 1,
                "phase": "preflight",
                "turn_id": "turn-agent-2",
            },
        },
    )
    session_manager.append_agent_run_event(
        session_id,
        {
            "type": "dispatch_agents_result",
            "turn_id": "turn-agent-2",
            "data": {
                "task_count": 2,
                "success_count": 0,
                "failure_count": 3,
                "stopped_count": 0,
                "preflight_failure_count": 1,
                "routing_failure_count": 1,
                "execution_failure_count": 1,
                "preflight_failures": [
                    {
                        "agent_id": "statistician",
                        "task": "执行正态性检验",
                        "error": "模型额度不足",
                    }
                ],
                "routing_failures": [
                    {
                        "agent_id": "router_guard",
                        "task": "识别干预标记",
                        "error": "未找到可用 agent",
                    }
                ],
                "execution_failures": [
                    {
                        "agent_id": "viz_designer",
                        "task": "绘制散点图",
                        "error": "Plotly 导出失败",
                    }
                ],
                "subtasks": [
                    {
                        "agent_id": "statistician",
                        "agent_name": "统计分析",
                        "task": "执行正态性检验",
                        "status": "error",
                        "stop_reason": "preflight_failed",
                        "summary": "模型额度不足",
                        "error": "模型额度不足",
                        "execution_time_ms": 0,
                        "artifact_count": 0,
                        "document_count": 0,
                    },
                    {
                        "agent_id": "router_guard",
                        "agent_name": "路由守卫",
                        "task": "识别干预标记",
                        "status": "error",
                        "stop_reason": "routing_failed",
                        "summary": "未找到可用 agent",
                        "error": "未找到可用 agent",
                        "execution_time_ms": 0,
                        "artifact_count": 0,
                        "document_count": 0,
                    },
                    {
                        "agent_id": "viz_designer",
                        "agent_name": "可视化设计",
                        "task": "绘制散点图",
                        "status": "error",
                        "stop_reason": "child_execution_failed",
                        "summary": "Plotly 导出失败",
                        "error": "Plotly 导出失败",
                        "execution_time_ms": 3200,
                        "artifact_count": 1,
                        "document_count": 0,
                    },
                    {
                        "agent_id": "data_cleaner",
                        "agent_name": "数据清洗",
                        "task": "标准化列名",
                        "status": "success",
                        "stop_reason": "",
                        "summary": "已完成清洗",
                        "error": "",
                        "execution_time_ms": 1200,
                        "artifact_count": 1,
                        "document_count": 0,
                    },
                    {
                        "agent_id": "scheduler",
                        "agent_name": "调度器",
                        "task": "等待人工确认",
                        "status": "stopped",
                        "stop_reason": "user_stopped",
                        "summary": "用户手动终止",
                        "error": "",
                        "execution_time_ms": 50,
                        "artifact_count": 0,
                        "document_count": 0,
                    },
                ],
            },
            "metadata": {
                "run_scope": "dispatch",
                "run_id": "dispatch:call-2",
                "parent_run_id": "root:turn-agent-2",
                "agent_id": "dispatch_agents",
                "agent_name": "dispatch_agents",
                "attempt": 1,
                "phase": "fused",
                "turn_id": "turn-agent-2",
            },
        },
    )

    agent_runs_resp = client.get(f"/api/sessions/{session_id}/agent-runs?turn_id=turn-agent-2")
    assert agent_runs_resp.status_code == 200
    payload = agent_runs_resp.json()
    dispatch_run = payload["data"]["runs"][0]
    assert dispatch_run["run_id"] == "dispatch:call-2"
    assert dispatch_run["failure_count"] == 3
    assert dispatch_run["failures"] == [
        {
            "agent_id": "statistician",
            "task": "执行正态性检验",
            "error": "模型额度不足",
        },
        {
            "agent_id": "router_guard",
            "task": "识别干预标记",
            "error": "未找到可用 agent",
        },
        {
            "agent_id": "viz_designer",
            "task": "绘制散点图",
            "error": "Plotly 导出失败",
        },
    ]
    assert dispatch_run["dispatch_ledger"] == [
        {
            "agent_id": "statistician",
            "agent_name": "统计分析",
            "task": "执行正态性检验",
            "status": "error",
            "stop_reason": "preflight_failed",
            "summary": "模型额度不足",
            "error": "模型额度不足",
            "execution_time_ms": 0,
            "artifact_count": 0,
            "document_count": 0,
        },
        {
            "agent_id": "router_guard",
            "agent_name": "路由守卫",
            "task": "识别干预标记",
            "status": "error",
            "stop_reason": "routing_failed",
            "summary": "未找到可用 agent",
            "error": "未找到可用 agent",
            "execution_time_ms": 0,
            "artifact_count": 0,
            "document_count": 0,
        },
        {
            "agent_id": "viz_designer",
            "agent_name": "可视化设计",
            "task": "绘制散点图",
            "status": "error",
            "stop_reason": "child_execution_failed",
            "summary": "Plotly 导出失败",
            "error": "Plotly 导出失败",
            "execution_time_ms": 3200,
            "artifact_count": 1,
            "document_count": 0,
        },
        {
            "agent_id": "data_cleaner",
            "agent_name": "数据清洗",
            "task": "标准化列名",
            "status": "success",
            "stop_reason": "",
            "summary": "已完成清洗",
            "error": "",
            "execution_time_ms": 1200,
            "artifact_count": 1,
            "document_count": 0,
        },
        {
            "agent_id": "scheduler",
            "agent_name": "调度器",
            "task": "等待人工确认",
            "status": "stopped",
            "stop_reason": "user_stopped",
            "summary": "用户手动终止",
            "error": "",
            "execution_time_ms": 50,
            "artifact_count": 0,
            "document_count": 0,
        },
    ]


def test_get_session_agent_run_events_supports_run_filter(client: LocalASGIClient) -> None:
    """agent-runs/events 支持按 run_id 按需读取事件。"""
    resp = client.post("/api/sessions")
    assert resp.status_code == 201
    session_id = resp.json()["data"]["session_id"]

    session_manager.append_agent_run_event(
        session_id,
        {
            "type": "agent_progress",
            "turn_id": "turn-agent-2",
            "data": {"event_type": "agent_progress", "message": "agent-a"},
            "metadata": {
                "run_scope": "subagent",
                "run_id": "agent:turn-agent-2:agent-a:task1:1",
                "turn_id": "turn-agent-2",
            },
        },
    )
    session_manager.append_agent_run_event(
        session_id,
        {
            "type": "agent_progress",
            "turn_id": "turn-agent-2",
            "data": {"event_type": "agent_progress", "message": "agent-b"},
            "metadata": {
                "run_scope": "subagent",
                "run_id": "agent:turn-agent-2:agent-b:task2:1",
                "turn_id": "turn-agent-2",
            },
        },
    )

    events_resp = client.get(
        f"/api/sessions/{session_id}/agent-runs/events?turn_id=turn-agent-2"
        "&run_id=agent%3Aturn-agent-2%3Aagent-a%3Atask1%3A1&limit=10"
    )
    assert events_resp.status_code == 200
    payload = events_resp.json()
    assert payload["success"] is True
    data = payload["data"]
    assert data["total"] == 1
    assert data["returned"] == 1
    assert data["events"][0]["data"]["message"] == "agent-a"


def test_get_session_dispatch_ledger_returns_independent_overview(
    client: LocalASGIClient,
) -> None:
    """dispatch-ledger 端点应独立返回当前会话的派发账本。"""
    resp = client.post("/api/sessions")
    assert resp.status_code == 201
    session_id = resp.json()["data"]["session_id"]

    session_manager.append_agent_run_event(
        session_id,
        {
            "type": "dispatch_agents_result",
            "turn_id": "turn-ledger-1",
            "data": {
                "task_count": 2,
                "success_count": 1,
                "failure_count": 1,
                "stopped_count": 0,
                "preflight_failure_count": 0,
                "routing_failure_count": 0,
                "execution_failure_count": 1,
                "subtasks": [
                    {
                        "agent_id": "data_cleaner",
                        "agent_name": "数据清洗",
                        "task": "标准化列名",
                        "status": "success",
                        "stop_reason": "",
                        "summary": "已完成清洗",
                        "error": "",
                        "execution_time_ms": 1200,
                        "artifact_count": 1,
                        "document_count": 0,
                    },
                    {
                        "agent_id": "viz_designer",
                        "agent_name": "可视化设计",
                        "task": "绘制散点图",
                        "status": "error",
                        "stop_reason": "child_execution_failed",
                        "summary": "Plotly 导出失败",
                        "error": "Plotly 导出失败",
                        "execution_time_ms": 3200,
                        "artifact_count": 0,
                        "document_count": 0,
                    },
                ],
            },
            "metadata": {
                "run_scope": "dispatch",
                "run_id": "dispatch:call-ledger-1",
                "parent_run_id": "root:turn-ledger-1",
                "agent_id": "dispatch_agents",
                "agent_name": "dispatch_agents",
                "attempt": 1,
                "phase": "fused",
                "turn_id": "turn-ledger-1",
            },
        },
    )

    ledger_resp = client.get(f"/api/sessions/{session_id}/dispatch-ledger?turn_id=turn-ledger-1")
    assert ledger_resp.status_code == 200
    payload = ledger_resp.json()
    assert payload["success"] is True
    data = payload["data"]
    assert data["ledger_count"] == 1
    ledger = data["ledgers"][0]
    assert ledger["run_id"] == "dispatch:call-ledger-1"
    assert ledger["failure_count"] == 1
    assert ledger["dispatch_ledger"] == [
        {
            "agent_id": "data_cleaner",
            "agent_name": "数据清洗",
            "task": "标准化列名",
            "status": "success",
            "stop_reason": "",
            "summary": "已完成清洗",
            "error": "",
            "execution_time_ms": 1200,
            "artifact_count": 1,
            "document_count": 0,
        },
        {
            "agent_id": "viz_designer",
            "agent_name": "可视化设计",
            "task": "绘制散点图",
            "status": "error",
            "stop_reason": "child_execution_failed",
            "summary": "Plotly 导出失败",
            "error": "Plotly 导出失败",
            "execution_time_ms": 3200,
            "artifact_count": 0,
            "document_count": 0,
        },
    ]


# ---- GET /api/sessions/{session_id}/messages 端点测试 ----


def test_get_session_messages_from_memory(client: LocalASGIClient) -> None:
    """从内存中的活跃会话获取消息历史。"""
    # 创建会话
    resp = client.post("/api/sessions")
    assert resp.status_code == 201
    session_id = resp.json()["data"]["session_id"]

    # 向会话添加消息
    session = session_manager.get_session(session_id)
    assert session is not None
    session.add_message("user", "你好世界")
    session.add_message("assistant", "你好！有什么可以帮助你的？")

    # 通过 API 获取消息
    resp = client.get(f"/api/sessions/{session_id}/messages")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["session_id"] == session_id

    messages = data["data"]["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "你好世界"
    assert isinstance(messages[0]["_ts"], str)
    assert isinstance(messages[0]["turn_id"], str)
    assert messages[0]["turn_id"]
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "你好！有什么可以帮助你的？"
    assert messages[1]["event_type"] == "text"
    assert messages[1]["operation"] == "complete"
    assert isinstance(messages[1]["message_id"], str)
    assert messages[1]["turn_id"] == messages[0]["turn_id"]


def test_get_session_messages_from_disk(client: LocalASGIClient) -> None:
    """从磁盘持久化的会话获取消息历史。"""
    # 创建会话并添加消息
    resp = client.post("/api/sessions")
    session_id = resp.json()["data"]["session_id"]

    session = session_manager.get_session(session_id)
    assert session is not None
    session.add_message("user", "持久化测试")
    session.add_message("assistant", "消息已保存")

    # 清空内存，模拟重启
    session_manager._sessions.clear()

    # 从磁盘加载消息
    resp = client.get(f"/api/sessions/{session_id}/messages")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True

    messages = data["data"]["messages"]
    assert len(messages) == 2
    assert messages[0]["content"] == "持久化测试"
    assert messages[1]["content"] == "消息已保存"


def test_get_session_messages_include_archived_history(client: LocalASGIClient) -> None:
    """历史接口应同时返回已压缩归档和当前活跃的消息。"""
    from nini.memory.compression import compress_session_history

    resp = client.post("/api/sessions")
    session_id = resp.json()["data"]["session_id"]

    session = session_manager.get_session(session_id)
    assert session is not None
    session.add_message("user", "开始分析", turn_id="turn-1")
    session.add_tool_call(
        "call_task_init",
        "task_state",
        json.dumps(
            {
                "operation": "init",
                "tasks": [
                    {"id": 1, "title": "检查数据质量", "status": "done"},
                    {"id": 2, "title": "生成报告", "status": "in_progress"},
                ],
            },
            ensure_ascii=False,
        ),
        turn_id="turn-1",
    )
    session.add_tool_result(
        "call_task_init",
        '{"success": true, "message": "任务已初始化"}',
        tool_name="task_state",
        status="success",
        turn_id="turn-1",
    )
    session.add_message("assistant", "继续执行剩余任务。", turn_id="turn-1")
    session.add_message("user", "继续", turn_id="turn-2")
    session.add_message("assistant", "正在生成报告。", turn_id="turn-2")

    result = compress_session_history(session, ratio=0.5, min_messages=4)
    assert result["success"] is True
    assert result["archived_count"] >= 1

    resp = client.get(f"/api/sessions/{session_id}/messages")
    assert resp.status_code == 200
    messages = resp.json()["data"]["messages"]

    assert [msg["content"] for msg in messages if msg["role"] == "user"] == ["开始分析", "继续"]
    task_state_message = next(
        msg for msg in messages if msg["role"] == "assistant" and (msg.get("tool_calls") or [])
    )
    assert task_state_message["tool_calls"][0]["function"]["name"] == "task_state"
    assert messages[-1]["content"] == "正在生成报告。"


def test_get_session_messages_404_for_nonexistent(client: LocalASGIClient) -> None:
    """请求不存在的会话返回 404。"""
    resp = client.get("/api/sessions/nonexistent-session-id/messages")
    assert resp.status_code == 404


def test_get_session_messages_filters_internal_fields(client: LocalASGIClient) -> None:
    """返回的消息应过滤掉内部字段，只包含前端需要的字段。"""
    resp = client.post("/api/sessions")
    session_id = resp.json()["data"]["session_id"]

    session = session_manager.get_session(session_id)
    assert session is not None
    session.add_message("user", "测试字段过滤")

    resp = client.get(f"/api/sessions/{session_id}/messages")
    data = resp.json()
    messages = data["data"]["messages"]

    assert len(messages) == 1
    msg = messages[0]
    # 应包含的字段
    assert "role" in msg
    assert "content" in msg
    # 允许的可选字段
    allowed_keys = {
        "role",
        "content",
        "_ts",
        "message_id",
        "turn_id",
        "tool_calls",
        "tool_call_id",
        "event_type",
        "operation",
        "tool_name",
        "status",
        "intent",
        "execution_id",
        "reasoning_id",
        "reasoning_live",
        "reasoning_type",
        "key_decisions",
        "confidence_score",
        "chart_data",
        "data_preview",
        "artifacts",
        "images",
    }
    assert set(msg.keys()) <= allowed_keys


def test_get_session_messages_with_tool_calls(client: LocalASGIClient) -> None:
    """包含工具调用的消息应正确返回 tool_calls 字段。"""
    resp = client.post("/api/sessions")
    session_id = resp.json()["data"]["session_id"]

    session = session_manager.get_session(session_id)
    assert session is not None

    # 添加带 tool_calls 的 assistant 消息
    tool_call_msg = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_123",
                "type": "function",
                "function": {"name": "run_code", "arguments": '{"code": "1+1"}'},
            }
        ],
    }
    session.messages.append(tool_call_msg)
    session.conversation_memory.append(tool_call_msg)

    # 添加 tool 结果消息
    session.add_tool_result("call_123", '{"result": 2}')

    resp = client.get(f"/api/sessions/{session_id}/messages")
    data = resp.json()
    messages = data["data"]["messages"]

    assert len(messages) == 2
    # assistant 消息应包含 tool_calls
    assert messages[0]["tool_calls"] is not None
    assert len(messages[0]["tool_calls"]) == 1
    assert messages[0]["tool_calls"][0]["function"]["name"] == "run_code"
    # tool 结果消息应包含 tool_call_id
    assert messages[1]["role"] == "tool"
    assert messages[1]["tool_call_id"] == "call_123"
    assert messages[1]["message_id"] == "tool-result-call_123"


def test_get_session_messages_only_returns_persisted_history(client: LocalASGIClient) -> None:
    """运行时状态不应改变 `/messages` 的历史返回契约。"""
    resp = client.post("/api/sessions")
    session_id = resp.json()["data"]["session_id"]

    session = session_manager.get_session(session_id)
    assert session is not None

    turn_id = "turn_history_boundary"
    session.add_message("user", "请分析这批样本", turn_id=turn_id)
    session.add_tool_call(
        "call_history_boundary",
        "run_code",
        json.dumps({"code": "print('analysis')"}, ensure_ascii=False),
        turn_id=turn_id,
        message_id="tool-call-call_history_boundary",
    )
    session.add_tool_result(
        "call_history_boundary",
        '{"success": true, "summary": "分析完成"}',
        tool_name="run_code",
        status="success",
        turn_id=turn_id,
        message_id="tool-result-call_history_boundary",
    )
    session.add_message(
        "assistant",
        "最终结论：存在显著差异。",
        turn_id=turn_id,
        message_id="assistant-final-turn_history_boundary",
    )

    # 这些字段仅属于运行时状态，不应被 `/messages` 合成进历史记录。
    session.harness_runtime_context = "运行时上下文：已载入 2 个数据集"
    session.task_manager = session.task_manager.init_tasks(
        [
            {"id": 1, "title": "检查数据质量", "status": "completed"},
            {"id": 2, "title": "计算显著性", "status": "in_progress"},
        ]
    )

    live_resp = client.get(f"/api/sessions/{session_id}/messages")
    assert live_resp.status_code == 200
    live_messages = live_resp.json()["data"]["messages"]

    session_manager._sessions.clear()

    reloaded_resp = client.get(f"/api/sessions/{session_id}/messages")
    assert reloaded_resp.status_code == 200
    reloaded_messages = reloaded_resp.json()["data"]["messages"]

    assert live_messages == reloaded_messages
    assert [msg["event_type"] for msg in live_messages] == [
        "message",
        "tool_call",
        "tool_result",
        "text",
    ]
    assert [msg["content"] for msg in live_messages] == [
        "请分析这批样本",
        None,
        '{"success": true, "summary": "分析完成"}',
        "最终结论：存在显著差异。",
    ]
    assert all(
        msg["event_type"]
        not in {"analysis_plan", "plan_step_update", "plan_progress", "task_attempt"}
        for msg in live_messages
    )
    assert all("harness_runtime_context" not in msg for msg in live_messages)


def test_get_session_messages_empty_session(client: LocalASGIClient) -> None:
    """新创建的空会话（内存中有但无消息）应返回空消息列表。"""
    resp = client.post("/api/sessions")
    session_id = resp.json()["data"]["session_id"]

    resp = client.get(f"/api/sessions/{session_id}/messages")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["messages"] == []


def test_get_session_messages_canonicalizes_legacy_records(client: LocalASGIClient) -> None:
    """旧记录通过历史接口读取时应补齐 canonical 字段。"""
    resp = client.post("/api/sessions")
    session_id = resp.json()["data"]["session_id"]

    memory = ConversationMemory(session_id)
    memory.append({"role": "user", "content": "旧问题"})
    memory.append({"role": "assistant", "content": "旧回答"})
    memory.append({"role": "assistant", "content": "旧推理", "reasoning_type": "analysis"})
    memory.append({"role": "tool", "tool_call_id": "call-legacy", "content": "旧工具结果"})
    session_manager._sessions.clear()

    resp = client.get(f"/api/sessions/{session_id}/messages")
    assert resp.status_code == 200
    messages = resp.json()["data"]["messages"]

    assert len(messages) == 4
    assert messages[0]["event_type"] == "message"
    assert messages[0]["turn_id"].startswith("legacy-turn-")
    assert messages[1]["event_type"] == "text"
    assert messages[1]["message_id"].startswith("legacy-message-")
    assert messages[1]["turn_id"] == messages[0]["turn_id"]
    assert messages[2]["event_type"] == "reasoning"
    assert messages[2]["reasoning_id"].startswith("legacy-reasoning-")
    assert messages[3]["event_type"] == "tool_result"
    assert messages[3]["message_id"] == "tool-result-call-legacy"


def test_get_session_messages_includes_persisted_event_fields(client: LocalASGIClient) -> None:
    """图表/数据/产物事件应可从历史接口恢复。"""
    resp = client.post("/api/sessions")
    session_id = resp.json()["data"]["session_id"]

    session = session_manager.get_session(session_id)
    assert session is not None
    session.add_assistant_event(
        "chart",
        "图表已生成",
        chart_data={"type": "bar", "data": [1, 2]},
    )
    session.add_assistant_event(
        "data",
        "数据预览如下",
        data_preview={"columns": [{"name": "x"}], "data": [{"x": 1}]},
    )
    session.add_assistant_event(
        "artifact",
        "产物已生成",
        artifacts=[
            {
                "name": "report.md",
                "type": "report",
                "download_url": "/api/artifacts/demo/report.md",
            }
        ],
    )

    resp = client.get(f"/api/sessions/{session_id}/messages")
    assert resp.status_code == 200
    messages = resp.json()["data"]["messages"]
    assert len(messages) == 3

    assert messages[0]["event_type"] == "chart"
    assert messages[0]["chart_data"]["type"] == "bar"
    assert messages[1]["event_type"] == "data"
    assert messages[1]["data_preview"]["columns"][0]["name"] == "x"
    assert messages[2]["event_type"] == "artifact"
    assert messages[2]["artifacts"][0]["name"] == "report.md"


def test_get_session_messages_resolve_referenced_chart_payload(client: LocalASGIClient) -> None:
    """磁盘恢复消息时应自动解引用大型 chart_data。"""
    resp = client.post("/api/sessions")
    session_id = resp.json()["data"]["session_id"]
    session = session_manager.get_session(session_id)
    assert session is not None

    large_chart = {
        "data": [{"x": list(range(1500)), "y": list(range(1500))}],
        "layout": {"title": "large chart"},
    }
    session.add_assistant_event("chart", "图表已生成", chart_data=large_chart)

    # 模拟重启，强制走磁盘读取路径
    session_manager._sessions.clear()

    resp = client.get(f"/api/sessions/{session_id}/messages")
    assert resp.status_code == 200
    messages = resp.json()["data"]["messages"]
    assert len(messages) == 1
    chart_data = messages[0]["chart_data"]
    assert isinstance(chart_data, dict)
    assert "_ref" not in str(chart_data)
    assert isinstance(chart_data.get("data"), list)


def test_download_markdown_bundle_with_images(client: LocalASGIClient) -> None:
    """含图片引用的 Markdown 下载应返回 zip 打包。"""
    resp = client.post("/api/sessions")
    session_id = resp.json()["data"]["session_id"]
    session = session_manager.get_session(session_id)
    assert session is not None

    wm = WorkspaceManager(session_id)
    artifact_dir = settings.sessions_dir / session_id / "workspace" / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    image_name = "chart.png"
    image_path = artifact_dir / image_name
    image_path.write_bytes(b"fakepng")
    wm.add_artifact_record(
        name=image_name,
        artifact_type="chart",
        file_path=image_path,
        format_hint="png",
    )

    md_name = "report.md"
    md_path = artifact_dir / md_name
    md_path.write_text(
        f"![图表](/api/artifacts/{session_id}/{image_name})\n",
        encoding="utf-8",
    )
    wm.add_artifact_record(
        name=md_name,
        artifact_type="report",
        file_path=md_path,
        format_hint="md",
    )

    resp = client.get(f"/api/workspace/{session_id}/files/artifacts/{quote(md_name)}?bundle=1")
    assert resp.status_code == 200
    assert resp.headers.get("content-type", "").startswith("application/zip")

    content = resp.content
    with zipfile.ZipFile(io.BytesIO(content), "r") as zf:
        names = set(zf.namelist())
        assert md_name in names
        assert f"images/{image_name}" in names
        bundled_md = zf.read(md_name).decode("utf-8")
        assert f"![图表](images/{image_name})" in bundled_md


def test_get_session_messages_normalizes_legacy_figure_payload(client: LocalASGIClient) -> None:
    """历史 `figure` 包装图表应被转换为顶层 data/layout。"""
    resp = client.post("/api/sessions")
    session_id = resp.json()["data"]["session_id"]
    session = session_manager.get_session(session_id)
    assert session is not None

    session.add_assistant_event(
        "chart",
        "图表已生成",
        chart_data={
            "figure": {
                "data": [{"x": [1, 2], "y": [3, 4], "type": "scatter"}],
                "layout": {"title": "legacy"},
            },
            "chart_type": "line",
        },
    )
    session_manager._sessions.clear()

    resp = client.get(f"/api/sessions/{session_id}/messages")
    assert resp.status_code == 200
    messages = resp.json()["data"]["messages"]
    assert len(messages) == 1
    chart_data = messages[0]["chart_data"]
    assert isinstance(chart_data, dict)
    assert "data" in chart_data
    assert "layout" in chart_data
    assert "figure" not in chart_data


def test_missing_session_read_routes_do_not_create_session(client: LocalASGIClient) -> None:
    missing_session_id = "ghost-session"

    session_resp = client.get(f"/api/sessions/{missing_session_id}")
    assert session_resp.status_code == 404

    context_resp = client.get(f"/api/sessions/{missing_session_id}/context-size")
    assert context_resp.status_code == 404

    export_resp = client.get(f"/api/sessions/{missing_session_id}/export-all")
    assert export_resp.status_code == 404

    dataset_resp = client.get(f"/api/datasets/{missing_session_id}/missing_dataset")
    assert dataset_resp.status_code == 404

    assert session_manager.session_exists(missing_session_id) is False
    assert all(item["id"] != missing_session_id for item in session_manager.list_sessions())


def test_task_recovery_preserves_depends_on_after_update() -> None:
    """会话恢复时 depends_on 字段在 update 操作后应保持完整。

    修复：session.py 任务恢复逻辑读取 update 操作的参数键为 'tasks'（而非错误的 'updates'）。
    """
    session = session_manager.create_session()
    session_id = session.id

    # 初始化含 depends_on 的任务
    session.add_message("user", "请分析数据", turn_id="turn-1")
    session.add_tool_call(
        "call_init",
        "task_state",
        json.dumps(
            {
                "operation": "init",
                "tasks": [
                    {"id": 1, "title": "清洗数据", "status": "pending", "depends_on": []},
                    {"id": 2, "title": "统计分析", "status": "pending", "depends_on": [1]},
                ],
            },
            ensure_ascii=False,
        ),
        turn_id="turn-1",
    )
    session.add_tool_result("call_init", '{"success": true}', turn_id="turn-1")

    # 更新任务 1 为 completed（使用 'tasks' 键，与 task_state 工具一致）
    session.add_tool_call(
        "call_update",
        "task_state",
        json.dumps(
            {
                "operation": "update",
                "tasks": [{"id": 1, "status": "completed"}],
            },
            ensure_ascii=False,
        ),
        turn_id="turn-1",
    )
    session.add_tool_result("call_update", '{"success": true}', turn_id="turn-1")

    # 模拟进程重启
    session_manager._sessions.clear()
    restored = session_manager.get_or_create(session_id)

    assert restored.task_manager.initialized
    tasks = {t.id: t for t in restored.task_manager.tasks}
    # 任务 2 的 depends_on 应在恢复后保持完整
    assert tasks[2].depends_on == [1]
    # 任务 1 的状态更新应被正确恢复
    assert tasks[1].status == "completed"
