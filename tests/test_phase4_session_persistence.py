"""Phase 4：会话持久化与恢复测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from nini.agent.session import session_manager
from nini.app import create_app
from nini.config import settings
from tests.client_utils import LocalASGIClient


@pytest.fixture(autouse=True)
def isolate_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    session_manager._sessions.clear()
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
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "你好！有什么可以帮助你的？"


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
        "tool_calls",
        "tool_call_id",
        "event_type",
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


def test_get_session_messages_empty_session(client: LocalASGIClient) -> None:
    """新创建的空会话（内存中有但无消息）应返回空消息列表。"""
    resp = client.post("/api/sessions")
    session_id = resp.json()["data"]["session_id"]

    resp = client.get(f"/api/sessions/{session_id}/messages")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["messages"] == []


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
