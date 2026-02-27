"""Phase 4：WebSocket 下 ask_user_question 事件流测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nini.agent.model_resolver import LLMChunk, model_resolver
from nini.agent.session import session_manager
from nini.app import create_app
from nini.config import settings
from tests.client_utils import live_websocket_connect


@pytest.fixture
def app_with_temp_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    session_manager._sessions.clear()
    return create_app()


def test_websocket_ask_user_question_flow(
    app_with_temp_data,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """模型调用 ask_user_question 后，前端回答后可继续生成结果。"""
    call_state = {"count": 0}

    async def fake_chat(messages, tools=None, temperature=None, max_tokens=None, **kwargs):
        call_state["count"] += 1
        if call_state["count"] == 1:
            yield LLMChunk(
                tool_calls=[
                    {
                        "id": "tool-ask-1",
                        "type": "function",
                        "function": {
                            "name": "ask_user_question",
                            "arguments": json.dumps(
                                {
                                    "questions": [
                                        {
                                            "question": "你更关注哪类结果？",
                                            "header": "分析偏好",
                                            "options": [
                                                {
                                                    "label": "显著性",
                                                    "description": "优先输出显著性结论",
                                                },
                                                {
                                                    "label": "效应量",
                                                    "description": "优先输出效应量解释",
                                                },
                                            ],
                                            "multiSelect": False,
                                        }
                                    ]
                                },
                                ensure_ascii=False,
                            ),
                        },
                    }
                ],
                finish_reason="tool_calls",
            )
            return

        yield LLMChunk(text="已根据你的回答继续分析。")

    monkeypatch.setattr(model_resolver, "chat", fake_chat)

    with live_websocket_connect(app_with_temp_data, "/ws") as ws:
        ws.send_text(json.dumps({"type": "chat", "content": "请帮我开始分析"}))

        events = []
        ask_event = None
        for _ in range(24):
            evt = ws.receive_json()
            events.append(evt)
            if evt["type"] == "ask_user_question":
                ask_event = evt
                ws.send_text(
                    json.dumps(
                        {
                            "type": "ask_user_question_answer",
                            "tool_call_id": evt.get("tool_call_id"),
                            "answers": {
                                "你更关注哪类结果？": "效应量",
                            },
                        },
                        ensure_ascii=False,
                    )
                )
            if evt["type"] in {"done", "error"}:
                break

    assert ask_event is not None, events
    event_types = [event["type"] for event in events]
    assert "tool_call" in event_types
    assert "ask_user_question" in event_types
    assert "tool_result" in event_types
    assert "text" in event_types
    assert "done" in event_types
    assert "error" not in event_types

    ask_result = next(
        event
        for event in events
        if event["type"] == "tool_result" and event.get("tool_name") == "ask_user_question"
    )
    assert ask_result["data"]["status"] == "success"
    answers = ask_result["data"]["result"]["data"]["answers"]
    assert answers["你更关注哪类结果？"] == "效应量"
