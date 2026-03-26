"""Skill 可观测性与 review gate WebSocket 交互测试。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from nini.agent.session import session_manager
from nini.app import create_app
from nini.config import settings
from nini.models.skill_contract import SkillContract, SkillStep
from nini.skills.contract_runner import ContractRunner
from tests.client_utils import live_websocket_connect


def _build_contract(*steps: SkillStep) -> SkillContract:
    return SkillContract(steps=list(steps))


class _FakeReviewRunner:
    def __init__(self) -> None:
        self.approved_steps: list[str] = []
        self.rejected_steps: list[str] = []

    def approve_review(self, step_id: str) -> None:
        self.approved_steps.append(step_id)

    def reject_review(self, step_id: str) -> None:
        self.rejected_steps.append(step_id)


@pytest.fixture
def app_with_temp_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "api_key", "")
    settings.ensure_dirs()
    session_manager._sessions.clear()
    return create_app()


@pytest.mark.asyncio
async def test_contract_runner_emits_skill_summary_event() -> None:
    contract = _build_contract(
        SkillStep(id="load", name="加载数据", description="加载数据"),
        SkillStep(id="plan", name="生成方案", description="生成方案", depends_on=["load"]),
    )
    events: list[tuple[str, Any]] = []

    async def callback(event_type: str, data: Any) -> None:
        events.append((event_type, data))

    runner = ContractRunner(contract=contract, skill_name="experiment-design", callback=callback)
    result = await runner.run(session=None)

    assert result.status == "completed"
    summary_events = [data for event_type, data in events if event_type == "skill_summary"]
    assert len(summary_events) == 1
    summary = summary_events[0]
    assert summary.skill_name == "experiment-design"
    assert summary.total_steps == 2
    assert summary.completed_steps == 2
    assert summary.skipped_steps == 0
    assert summary.failed_steps == 0
    assert summary.overall_status == "completed"
    assert summary.total_duration_ms is not None


def test_websocket_review_confirm_and_cancel_are_routed_to_active_runner(
    app_with_temp_data,
) -> None:
    session = session_manager.get_or_create("skill-review-session")
    fake_runner = _FakeReviewRunner()
    setattr(session, "_active_contract_runner", fake_runner)

    with live_websocket_connect(app_with_temp_data, "/ws") as ws:
        ws.send_text(
            json.dumps(
                {
                    "type": "review_confirm",
                    "session_id": session.id,
                    "step_id": "generate_plan",
                }
            )
        )
        ws.send_text(
            json.dumps(
                {
                    "type": "review_cancel",
                    "session_id": session.id,
                    "step_id": "generate_plan",
                }
            )
        )

    assert fake_runner.approved_steps == ["generate_plan"]
    assert fake_runner.rejected_steps == ["generate_plan"]
