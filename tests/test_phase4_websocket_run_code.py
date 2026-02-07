"""Phase 4：WebSocket 下 run_code 事件流测试。"""

from __future__ import annotations

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
    """验证 run_code 的 tool_call -> tool_result -> text -> done 事件流。"""
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
    assert "tool_result" in event_types
    assert "text" in event_types
    assert "done" in event_types
    assert "error" not in event_types

    tool_result_event = next(e for e in events if e["type"] == "tool_result")
    assert tool_result_event["data"]["status"] == "success"
    assert tool_result_event["data"]["result"]["success"] is True
    assert tool_result_event["data"]["result"]["data"]["result"] == 42
