"""Recipe Center 与 deep task MVP 测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nini.agent import event_builders as eb
from nini.agent.session import session_manager
from nini.app import create_app
from nini.config import settings
from nini.recipe import get_recipe_registry
from tests.client_utils import LocalASGIClient, live_websocket_connect


@pytest.fixture
def app_with_temp_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()
    session_manager._sessions.clear()
    return create_app()


def test_recipe_registry_exposes_three_public_recipes() -> None:
    """Recipe 注册表应至少提供 3 个公开模板。"""
    registry = get_recipe_registry()

    recipes = registry.list_public()

    assert len(recipes) >= 3
    assert {item["recipe_id"] for item in recipes} >= {
        "literature_review",
        "experiment_plan",
        "results_interpretation",
    }


def test_recipe_route_returns_public_metadata(app_with_temp_data) -> None:
    """Recipe 路由应返回前端可直接消费的元数据。"""
    with LocalASGIClient(app_with_temp_data) as client:
        response = client.get("/api/recipes")

    payload = response.json()
    assert response.status_code == 200
    assert payload["success"] is True
    assert len(payload["data"]["recipes"]) >= 3
    assert "input_fields" in payload["data"]["recipes"][0]


def test_websocket_recipe_chat_emits_deep_task_events(
    app_with_temp_data,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """显式使用 Recipe 启动时，应推送 deep task 生命周期与工作区初始化事件。"""

    async def fake_run(self, session, content, append_user_message, stop_event):
        _ = self
        _ = stop_event
        session.add_message("user", "请按模板推进")
        session.add_message("assistant", "已完成模板任务。")
        yield eb.build_text_event("已完成模板任务。", turn_id="turn-recipe")
        yield eb.build_done_event(turn_id="turn-recipe")

    from nini.api import websocket as websocket_module

    monkeypatch.setattr(websocket_module.HarnessRunner, "run", fake_run)

    with live_websocket_connect(app_with_temp_data, "/ws") as ws:
        ws.send_text(
            json.dumps(
                {
                    "type": "chat",
                    "content": "帮我做文献综述提纲",
                    "metadata": {
                        "recipe_id": "literature_review",
                        "recipe_inputs": {"topic": "肠道菌群与抑郁症"},
                    },
                },
                ensure_ascii=False,
            )
        )

        events = []
        for _ in range(20):
            event = ws.receive_json()
            events.append(event)
            if event["type"] in {"done", "error"}:
                break

    event_types = [event["type"] for event in events]
    session_event = next(event for event in events if event["type"] == "session")
    workspace_event = next(event for event in events if event["type"] == "workspace_update")
    progress_event = next(event for event in events if event["type"] == "plan_progress")

    assert "analysis_plan" in event_types
    assert session_event["data"]["task_kind"] == "deep_task"
    assert session_event["data"]["recipe_id"] == "literature_review"
    assert session_event["data"]["deep_task_state"]["task_id"]
    assert workspace_event["data"]["initialized"] is True
    assert workspace_event["data"]["task_id"] == session_event["data"]["deep_task_state"]["task_id"]
    assert progress_event["data"]["recipe_id"] == "literature_review"
    assert progress_event["data"]["task_kind"] == "deep_task"
