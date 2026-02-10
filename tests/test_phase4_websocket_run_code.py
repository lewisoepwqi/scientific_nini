"""Phase 4：WebSocket 下 run_code 事件流测试。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from nini.agent.model_resolver import LLMChunk, model_resolver
from nini.agent.session import session_manager
from nini.app import create_app
from nini.config import settings


@pytest.fixture
def app_with_temp_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    session_manager._sessions.clear()
    return create_app()


def test_websocket_run_code_event_flow(
    app_with_temp_data,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证 run_code 的 tool_call -> code artifact -> tool_result -> text -> done 事件流。"""
    call_state = {"count": 0}

    async def fake_chat(messages, tools=None, temperature=None, max_tokens=None):
        call_state["count"] += 1
        if call_state["count"] == 1:
            yield LLMChunk(
                tool_calls=[
                    {
                        "id": "tool-call-1",
                        "type": "function",
                        "function": {
                            "name": "run_code",
                            "arguments": json.dumps({"code": "result = 6 * 7"}),
                        },
                    }
                ],
                finish_reason="tool_calls",
            )
            return
        yield LLMChunk(text="代码执行完成。")

    monkeypatch.setattr(model_resolver, "chat", fake_chat)

    with TestClient(app_with_temp_data) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_text(json.dumps({"type": "chat", "content": "请运行一段代码"}))

            events = []
            for _ in range(16):
                evt = ws.receive_json()
                events.append(evt)
                if evt["type"] in {"done", "error"}:
                    break

    event_types = [e["type"] for e in events]
    assert "session" in event_types
    assert "tool_call" in event_types
    assert "artifact" in event_types
    assert "tool_result" in event_types
    assert "text" in event_types
    assert "done" in event_types
    assert "error" not in event_types

    tool_result_event = next(e for e in events if e["type"] == "tool_result")
    assert tool_result_event["data"]["status"] == "success"
    assert tool_result_event["data"]["result"]["success"] is True
    assert tool_result_event["data"]["result"]["data"]["result"] == 42

    artifact_event = next(e for e in events if e["type"] == "artifact")
    assert artifact_event["data"]["type"] == "code"
    assert artifact_event["data"]["format"] == "py"
    assert artifact_event["data"]["name"].endswith(".py")


def test_websocket_stop_can_interrupt_and_continue(
    app_with_temp_data,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """生成中点击 stop 后可继续发起新请求。"""
    call_state = {"count": 0}

    async def fake_chat(messages, tools=None, temperature=None, max_tokens=None):
        call_state["count"] += 1
        if call_state["count"] == 1:
            for idx in range(40):
                await asyncio.sleep(0.01)
                yield LLMChunk(text=f"片段{idx}")
            return
        yield LLMChunk(text="已继续新的请求。")

    monkeypatch.setattr(model_resolver, "chat", fake_chat)

    with TestClient(app_with_temp_data) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_text(json.dumps({"type": "chat", "content": "请开始长输出"}))

            # 至少收到一次文本流后再停止
            for _ in range(20):
                evt = ws.receive_json()
                if evt["type"] == "text":
                    break

            ws.send_text(json.dumps({"type": "stop"}))

            stop_received = False
            for _ in range(20):
                evt = ws.receive_json()
                if evt["type"] == "stopped":
                    stop_received = True
                    break
            assert stop_received is True

            ws.send_text(json.dumps({"type": "chat", "content": "继续请求"}))
            events = []
            for _ in range(20):
                evt = ws.receive_json()
                events.append(evt)
                if evt["type"] in {"done", "error"}:
                    break

    event_types = [e["type"] for e in events]
    assert "done" in event_types
    assert "error" not in event_types
    assert any(e["type"] == "text" and "已继续新的请求" in e.get("data", "") for e in events)


def test_websocket_retry_clears_last_agent_turn_and_regenerates(
    app_with_temp_data,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """retry 应回滚上一轮 Agent 输出并重新生成。"""
    call_state = {"count": 0}

    async def fake_chat(messages, tools=None, temperature=None, max_tokens=None):
        call_state["count"] += 1
        if call_state["count"] == 1:
            yield LLMChunk(text="第一次回答")
            return
        yield LLMChunk(text="重试后回答")

    monkeypatch.setattr(model_resolver, "chat", fake_chat)

    with TestClient(app_with_temp_data) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_text(json.dumps({"type": "chat", "content": "解释一下结果"}))

            session_id = ""
            first_events = []
            for _ in range(20):
                evt = ws.receive_json()
                first_events.append(evt)
                if evt["type"] == "session":
                    session_id = evt["data"]["session_id"]
                if evt["type"] in {"done", "error"}:
                    break

            assert session_id
            assert any(
                e["type"] == "text" and "第一次回答" in e.get("data", "")
                for e in first_events
            )

            ws.send_text(json.dumps({"type": "retry", "session_id": session_id}))

            retry_events = []
            for _ in range(20):
                evt = ws.receive_json()
                retry_events.append(evt)
                if evt["type"] in {"done", "error"}:
                    break

    retry_types = [e["type"] for e in retry_events]
    assert "done" in retry_types
    assert "error" not in retry_types
    assert any(
        e["type"] == "text" and "重试后回答" in e.get("data", "")
        for e in retry_events
    )

    session = session_manager.get_session(session_id)
    assert session is not None
    assert len([m for m in session.messages if m.get("role") == "user"]) == 1
    assistant_contents = [
        str(m.get("content", ""))
        for m in session.messages
        if m.get("role") == "assistant"
    ]
    assert any("重试后回答" in content for content in assistant_contents)
    assert all("第一次回答" not in content for content in assistant_contents)


def test_websocket_emits_retrieval_event(
    app_with_temp_data,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """命中知识检索时，应推送 retrieval 事件并包含必要字段。"""

    # 写入知识文件（关键词命中）
    knowledge_file = settings.knowledge_dir / "ttest.md"
    knowledge_file.parent.mkdir(parents=True, exist_ok=True)
    knowledge_file.write_text(
        "<!-- keywords: t检验, 差异 -->\n<!-- priority: high -->\n"
        "t 检验用于比较两个样本均值差异。",
        encoding="utf-8",
    )

    async def fake_chat(messages, tools=None, temperature=None, max_tokens=None):
        yield LLMChunk(text="收到检索上下文。")

    monkeypatch.setattr(model_resolver, "chat", fake_chat)

    with TestClient(app_with_temp_data) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_text(json.dumps({"type": "chat", "content": "请做 t检验"}))

            events = []
            for _ in range(20):
                evt = ws.receive_json()
                events.append(evt)
                if evt["type"] in {"done", "error"}:
                    break

    retrieval_event = next((e for e in events if e["type"] == "retrieval"), None)
    assert retrieval_event is not None, events
    data = retrieval_event["data"]
    assert data["query"] == "请做 t检验"
    assert isinstance(data["results"], list) and data["results"]
    assert "source" in data["results"][0]
    assert "snippet" in data["results"][0]
