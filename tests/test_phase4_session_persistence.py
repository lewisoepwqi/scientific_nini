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

    def list_markdown_skills(self) -> list[dict[str, object]]:
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

    async def execute(self, skill_name: str, session: Session, **kwargs):
        if skill_name != "workspace_session":
            return {"error": f"unknown skill: {skill_name}"}
        return {"success": True, "message": "workspace write ok"}

    async def execute_with_fallback(self, skill_name: str, session: Session, **kwargs):
        return await self.execute(skill_name, session=session, **kwargs)


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
        skill_registry=_ApprovalRegistry(),
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


# ---- GET /api/sessions/{session_id}/messages 端点测试 ----


def test_get_session_messages_from_memory(client: LocalASGIClient) -> None:
    """从内存中的活跃会话获取消息历史。"""
    # 创建会话
    resp = client.post("/api/sessions")
    assert resp.status_code == 200
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

    resp = client.get(f"/api/workspace/{session_id}/artifacts/{quote(md_name)}/bundle")
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
