"""HarnessRunner 与 trace 存储测试。"""

from __future__ import annotations

import json

import pytest

from nini.agent import event_builders as eb
from nini.agent.session import Session
from nini.harness.models import HarnessRunContext, HarnessTraceRecord
from nini.harness.runner import HarnessRunner
from nini.harness.store import HarnessTraceStore
from nini.models.database import init_db


class _CompletionRecoveryRunner:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def run(
        self,
        session: Session,
        user_message: str,
        *,
        append_user_message: bool = True,
        stop_event=None,
        turn_id: str | None = None,
        stage_override: str | None = None,
    ):
        self.calls.append({"user_message": user_message, "stage_override": stage_override})
        assert turn_id is not None
        if append_user_message:
            session.add_message("user", user_message, turn_id=turn_id)

        yield eb.build_iteration_start_event(iteration=len(self.calls) - 1, turn_id=turn_id)
        if len(self.calls) == 1:
            session.add_message("assistant", "下一步我将继续分析", turn_id=turn_id)
            yield eb.build_text_event("下一步我将继续分析", turn_id=turn_id)
        else:
            session.add_message("assistant", "最终结论：差异显著，分析已完成。", turn_id=turn_id)
            yield eb.build_text_event("最终结论：差异显著，分析已完成。", turn_id=turn_id)
        yield eb.build_done_event(turn_id=turn_id)


class _LoopRunner:
    def __init__(self) -> None:
        self.calls = 0

    async def run(
        self,
        session: Session,
        user_message: str,
        *,
        append_user_message: bool = True,
        stop_event=None,
        turn_id: str | None = None,
        stage_override: str | None = None,
    ):
        _ = user_message, stage_override, stop_event
        self.calls += 1
        assert turn_id is not None
        if append_user_message:
            session.add_message("user", "分析数据", turn_id=turn_id)
        for idx in range(2):
            tool_call_id = f"call-{self.calls}-{idx}"
            session.add_tool_result(
                tool_call_id,
                "工具执行失败",
                tool_name="run_code",
                status="error",
                turn_id=turn_id,
            )
            yield eb.build_tool_result_event(
                tool_call_id=tool_call_id,
                name="run_code",
                status="error",
                message="工具执行失败",
                turn_id=turn_id,
            )
        yield eb.build_done_event(turn_id=turn_id)


@pytest.mark.asyncio
async def test_harness_runner_recovers_from_failed_completion_check() -> None:
    runner = HarnessRunner(agent_runner=_CompletionRecoveryRunner())
    session = Session()

    events = [event async for event in runner.run(session, "请分析数据差异")]
    event_types = [event.type.value for event in events]

    assert "run_context" in event_types
    assert event_types.count("completion_check") == 2
    assert event_types[-1] == "done"
    assert any(
        event.type.value == "completion_check" and isinstance(event.data, dict) and event.data.get("passed") is False
        for event in events
    )
    assert any(
        event.type.value == "completion_check" and isinstance(event.data, dict) and event.data.get("passed") is True
        for event in events
    )


@pytest.mark.asyncio
async def test_harness_runner_blocks_after_repeated_loop_recovery() -> None:
    runner = HarnessRunner(agent_runner=_LoopRunner())
    session = Session()

    events = [event async for event in runner.run(session, "请分析数据差异")]
    event_types = [event.type.value for event in events]

    assert "blocked" in event_types
    assert event_types[-1] == "stopped"


def test_agent_runner_stage_routing_is_stage_aware() -> None:
    from nini.agent.runner import AgentRunner

    assert AgentRunner._resolve_model_purpose(iteration=0, pending_followup_prompt=None, stage_override=None) == "planning"  # noqa: SLF001
    assert AgentRunner._resolve_model_purpose(iteration=1, pending_followup_prompt="继续", stage_override=None) == "verification"  # noqa: SLF001
    assert AgentRunner._resolve_model_purpose(iteration=1, pending_followup_prompt=None, stage_override=None) == "chat"  # noqa: SLF001


@pytest.mark.asyncio
async def test_harness_trace_store_persists_and_replays(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from nini.config import settings

    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    await init_db()

    store = HarnessTraceStore()
    record = HarnessTraceRecord(
        run_id="run_demo",
        session_id="session_demo",
        turn_id="turn_demo",
        user_message="请分析",
        run_context=HarnessRunContext(turn_id="turn_demo"),
        status="blocked",
        failure_tags=["tool_loop"],
        finished_at="2026-03-14T00:00:01+00:00",
        summary={"input_tokens": 10, "output_tokens": 5, "estimated_cost_usd": 0.01},
    )
    await store.save_run(record)

    summaries = await store.list_runs(session_id="session_demo", limit=5)
    replay = store.replay_run("run_demo", session_id="session_demo")
    aggregate = await store.aggregate_failures(session_id="session_demo")

    assert summaries[0].run_id == "run_demo"
    assert replay["status"] == "blocked"
    assert aggregate["failure_distribution"]["tool_loop"] == 1
    trace_path = tmp_path / "data" / "sessions" / "session_demo" / "harness" / "traces" / "run_demo.json"
    assert json.loads(trace_path.read_text(encoding="utf-8"))["run_id"] == "run_demo"
