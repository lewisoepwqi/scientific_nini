"""Phase 4：WebSocket 下 ask_user_question 事件流测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nini.agent.model_resolver import LLMChunk, model_resolver
from nini.agent.session import session_manager
from nini import app as app_module
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


def test_websocket_ask_user_question_text_is_not_duplicated(
    app_with_temp_data,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """首轮同时输出文本与 ask_user_question 时，不应重复推送同一段说明文本。"""
    call_state = {"count": 0}
    intro_text = "好的，我们将进行相关性分析。让我先确认一下分析范围。"

    async def fake_chat(messages, tools=None, temperature=None, max_tokens=None, **kwargs):
        call_state["count"] += 1
        if call_state["count"] == 1:
            yield LLMChunk(
                text=intro_text,
                tool_calls=[
                    {
                        "id": "tool-ask-dup-1",
                        "type": "function",
                        "function": {
                            "name": "ask_user_question",
                            "arguments": json.dumps(
                                {
                                    "questions": [
                                        {
                                            "question": "请选择分析变量",
                                            "header": "分析范围",
                                            "options": [
                                                {
                                                    "label": "收缩压",
                                                    "description": "仅分析收缩压",
                                                },
                                                {
                                                    "label": "全部变量",
                                                    "description": "分析全部数值变量",
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

        yield LLMChunk(text="收到，继续分析。")

    monkeypatch.setattr(model_resolver, "chat", fake_chat)

    with live_websocket_connect(app_with_temp_data, "/ws") as ws:
        ws.send_text(json.dumps({"type": "chat", "content": "请开始分析"}))

        events = []
        for _ in range(24):
            evt = ws.receive_json()
            events.append(evt)
            if evt["type"] == "ask_user_question":
                ws.send_text(
                    json.dumps(
                        {
                            "type": "ask_user_question_answer",
                            "tool_call_id": evt.get("tool_call_id"),
                            "answers": {
                                "请选择分析变量": "全部变量",
                            },
                        },
                        ensure_ascii=False,
                    )
                )
            if evt["type"] in {"done", "error"}:
                break

    text_events = [
        evt["data"] for evt in events if evt["type"] == "text" and isinstance(evt.get("data"), str)
    ]
    assert text_events.count(intro_text) == 1
    assert "收到，继续分析。" in text_events


def test_websocket_file_name_confirmation_is_converted_to_ask_user_question(
    app_with_temp_data,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """文件名确认场景即使模型未主动调用工具，也应兜底为 ask_user_question。"""
    call_state = {"count": 0}
    suggestion = "blood_pressure_heart_rate_correlation_20260304.md"

    async def fake_chat(messages, tools=None, temperature=None, max_tokens=None, **kwargs):
        call_state["count"] += 1
        if call_state["count"] == 1:
            yield LLMChunk(
                text=(
                    f"建议文件名为 `{suggestion}`。"
                    "您确认使用此文件名，或希望修改后再生成文章？"
                )
            )
            return

        yield LLMChunk(text="已确认文件名，继续生成内容。")

    monkeypatch.setattr(model_resolver, "chat", fake_chat)

    with live_websocket_connect(app_with_temp_data, "/ws") as ws:
        ws.send_text(json.dumps({"type": "chat", "content": "请写一篇分析文章"}))

        events = []
        for _ in range(24):
            evt = ws.receive_json()
            events.append(evt)
            if evt["type"] == "ask_user_question":
                ws.send_text(
                    json.dumps(
                        {
                            "type": "ask_user_question_answer",
                            "tool_call_id": evt.get("tool_call_id"),
                            "answers": {
                                f"建议文件名为 {suggestion}。是否使用这个文件名？": "使用建议文件名",
                            },
                        },
                        ensure_ascii=False,
                    )
                )
            if evt["type"] in {"done", "error"}:
                break

    event_types = [event["type"] for event in events]
    assert "ask_user_question" in event_types
    assert "tool_call" in event_types
    assert "tool_result" in event_types
    assert "done" in event_types
    assert "error" not in event_types

    ask_event = next(event for event in events if event["type"] == "ask_user_question")
    question = ask_event["data"]["questions"][0]
    assert question["header"] == "文件名"
    assert question["allowTextInput"] is True
    assert suggestion in question["question"]
    text_events = [
        evt["data"] for evt in events if evt["type"] == "text" and isinstance(evt.get("data"), str)
    ]
    assert "已确认文件名，继续生成内容。" in text_events


def test_websocket_sandbox_import_approval_flow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_code 触发沙盒审批后，前端回答应恢复原始工具执行。"""
    model_calls = {"count": 0}
    run_code_calls = {"count": 0}

    async def fake_chat(messages, tools=None, temperature=None, max_tokens=None, **kwargs):
        model_calls["count"] += 1
        if model_calls["count"] == 1:
            yield LLMChunk(
                tool_calls=[
                    {
                        "id": "tool-run-code-1",
                        "type": "function",
                        "function": {
                            "name": "run_code",
                            "arguments": json.dumps(
                                {
                                    "code": "import sympy\nresult = 1",
                                    "intent": "验证审批流程",
                                },
                                ensure_ascii=False,
                            ),
                        },
                    }
                ],
                finish_reason="tool_calls",
            )
            return

        yield LLMChunk(text="审批后已继续执行。")

    async def fake_execute_with_fallback(skill_name: str, session, enable_fallback=True, **kwargs):
        assert enable_fallback is True
        assert skill_name == "run_code"
        run_code_calls["count"] += 1
        extra_allowed_imports = kwargs.get("extra_allowed_imports") or []
        if "sympy" not in extra_allowed_imports and not session.has_sandbox_import_approval("sympy"):
            return {
                "success": False,
                "message": "继续执行前需要用户审批导入扩展包：sympy",
                "data": {
                    "_sandbox_review_required": True,
                    "requested_packages": ["sympy"],
                    "sandbox_violations": [
                        {
                            "message": "导入扩展包 'sympy' 需要用户审批",
                            "module": "sympy",
                            "root": "sympy",
                            "risk_level": "reviewable",
                        }
                    ],
                },
            }
        return {"success": True, "message": "run_code 审批后执行成功", "data": {"result": 1}}

    class _FakeRegistry:
        def list_skills(self):
            return ["run_code"]

        def get_tool_definitions(self):
            return [
                {
                    "type": "function",
                    "function": {
                        "name": "run_code",
                        "description": "运行代码",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ]

        def list_markdown_skills(self):
            return []

        async def execute_with_fallback(self, skill_name, session, enable_fallback=True, **kwargs):
            return await fake_execute_with_fallback(
                skill_name,
                session,
                enable_fallback=enable_fallback,
                **kwargs,
            )

    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    session_manager._sessions.clear()
    monkeypatch.setattr(model_resolver, "chat", fake_chat)
    monkeypatch.setattr(app_module, "create_default_tool_registry", lambda: _FakeRegistry())
    app = create_app()

    with live_websocket_connect(app, "/ws", receive_timeout=2.0) as ws:
        ws.send_text(json.dumps({"type": "chat", "content": "请运行需要 sympy 的代码"}))

        events = []
        for _ in range(36):
            evt = ws.receive_json()
            events.append(evt)
            if evt["type"] == "ask_user_question":
                question = evt["data"]["questions"][0]["question"]
                ws.send_text(
                    json.dumps(
                        {
                            "type": "ask_user_question_answer",
                            "tool_call_id": evt.get("tool_call_id"),
                            "answers": {question: "本会话允许"},
                        },
                        ensure_ascii=False,
                    )
                )
            if evt["type"] in {"done", "error"}:
                break

    event_types = [event["type"] for event in events]
    assert "ask_user_question" in event_types
    assert "tool_result" in event_types
    assert "done" in event_types
    assert "error" not in event_types
    assert run_code_calls["count"] == 2

    ask_result = next(
        event
        for event in events
        if event["type"] == "tool_result" and event.get("tool_name") == "ask_user_question"
    )
    assert ask_result["data"]["status"] == "success"
    final_run_code_result = next(
        event
        for event in reversed(events)
        if event["type"] == "tool_result" and event.get("tool_name") == "run_code"
    )
    assert final_run_code_result["data"]["status"] == "success"
