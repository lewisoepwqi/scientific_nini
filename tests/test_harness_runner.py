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
            if stop_event is not None and stop_event.is_set():
                return
        yield eb.build_done_event(turn_id=turn_id)


class _ErrorRunner:
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
        _ = user_message, stop_event, stage_override
        assert turn_id is not None
        if append_user_message:
            session.add_message("user", "分析失败", turn_id=turn_id)
        yield eb.build_iteration_start_event(iteration=0, turn_id=turn_id)
        yield eb.build_error_event("LLM 调用失败", turn_id=turn_id)


class _ToolRecoveryRunner:
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
        _ = stop_event, stage_override
        self.calls.append(
            {
                "user_message": user_message,
                "append_user_message": append_user_message,
            }
        )
        assert turn_id is not None
        if append_user_message:
            session.add_message("user", user_message, turn_id=turn_id)
        yield eb.build_iteration_start_event(iteration=len(self.calls) - 1, turn_id=turn_id)
        if len(self.calls) == 1:
            raw_args = json.dumps({"code": "print("}, ensure_ascii=False)
            for idx in range(2):
                tool_call_id = f"tool-recovery-{idx}"
                session.add_tool_call(tool_call_id, "run_code", raw_args, turn_id=turn_id)
                session.add_tool_result(
                    tool_call_id,
                    "语法错误",
                    tool_name="run_code",
                    status="error",
                    turn_id=turn_id,
                )
                yield eb.build_tool_result_event(
                    tool_call_id=tool_call_id,
                    name="run_code",
                    status="error",
                    message="语法错误",
                    turn_id=turn_id,
                )
                if stop_event is not None and stop_event.is_set():
                    return
        else:
            session.add_message("assistant", "已改用替代方案并完成分析。", turn_id=turn_id)
            yield eb.build_text_event("已改用替代方案并完成分析。", turn_id=turn_id)
        yield eb.build_done_event(turn_id=turn_id)


class _CrashRunner:
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
        _ = session, user_message, append_user_message, stop_event, turn_id, stage_override
        raise RuntimeError("boom")
        yield  # pragma: no cover


class _CaptureTraceStore:
    def __init__(self) -> None:
        self.records: list[HarnessTraceRecord] = []

    async def save_run(self, record: HarnessTraceRecord):
        self.records.append(record.model_copy(deep=True))
        return None


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
        event.type.value == "completion_check"
        and isinstance(event.data, dict)
        and event.data.get("passed") is False
        for event in events
    )
    assert any(
        event.type.value == "completion_check"
        and isinstance(event.data, dict)
        and event.data.get("passed") is True
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


@pytest.mark.asyncio
async def test_harness_runner_stops_after_error_without_completion_check() -> None:
    trace_store = _CaptureTraceStore()
    runner = HarnessRunner(agent_runner=_ErrorRunner(), trace_store=trace_store)
    session = Session()

    events = [event async for event in runner.run(session, "请分析数据差异")]
    event_types = [event.type.value for event in events]

    assert event_types == ["iteration_start", "error"]
    assert trace_store.records[0].status == "error"


@pytest.mark.asyncio
async def test_harness_runner_tool_recovery_prompt_is_not_appended_as_user_message() -> None:
    inner_runner = _ToolRecoveryRunner()
    runner = HarnessRunner(agent_runner=inner_runner)
    session = Session()

    events = [event async for event in runner.run(session, "请分析数据差异")]
    event_types = [event.type.value for event in events]

    assert "done" in event_types
    assert len(inner_runner.calls) == 2
    assert inner_runner.calls[1]["append_user_message"] is False
    user_messages = [msg for msg in session.messages if msg.get("role") == "user"]
    assert len(user_messages) == 1
    assert "检测到同类工具路径连续失败" not in str(user_messages[0].get("content", ""))


def test_harness_runner_tool_failure_signature_uses_tool_arguments() -> None:
    session = Session()
    session.add_tool_call(
        "call-a", "run_code", json.dumps({"code": "print(1)"}, ensure_ascii=False)
    )
    session.add_tool_call(
        "call-b", "run_code", json.dumps({"code": "print(2)"}, ensure_ascii=False)
    )

    signature_a = HarnessRunner._resolve_tool_failure_signature(  # noqa: SLF001
        session=session,
        event=eb.build_tool_result_event(
            tool_call_id="call-a",
            name="run_code",
            status="error",
            message="语法错误",
        ),
        tool_name="run_code",
        data={"id": "call-a", "message": "语法错误"},
    )
    signature_b = HarnessRunner._resolve_tool_failure_signature(  # noqa: SLF001
        session=session,
        event=eb.build_tool_result_event(
            tool_call_id="call-b",
            name="run_code",
            status="error",
            message="语法错误",
        ),
        tool_name="run_code",
        data={"id": "call-b", "message": "语法错误"},
    )

    assert signature_a != signature_b


def test_agent_runner_stage_routing_is_stage_aware() -> None:
    from nini.agent.runner import AgentRunner

    assert (
        AgentRunner._resolve_model_purpose(
            iteration=0, pending_followup_prompt=None, stage_override=None
        )
        == "planning"
    )  # noqa: SLF001
    assert (
        AgentRunner._resolve_model_purpose(
            iteration=1, pending_followup_prompt="继续", stage_override=None
        )
        == "verification"
    )  # noqa: SLF001
    assert (
        AgentRunner._resolve_model_purpose(
            iteration=1, pending_followup_prompt=None, stage_override=None
        )
        == "chat"
    )  # noqa: SLF001


@pytest.mark.asyncio
async def test_harness_trace_store_persists_and_replays(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nini.config import settings

    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()
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
    trace_path = (
        tmp_path / "data" / "sessions" / "session_demo" / "harness" / "traces" / "run_demo.json"
    )
    assert json.loads(trace_path.read_text(encoding="utf-8"))["run_id"] == "run_demo"


def test_artifact_check_passes_for_capability_description() -> None:
    """能力介绍类文本（含产物词但无完成语义词）不应触发承诺产物校验。"""
    runner = HarnessRunner(agent_runner=None)  # type: ignore[arg-type]
    session = Session()
    turn_id = "turn-cap"
    # 仅提及能力，不含"以下是"/"已生成"等完成语义词
    session.add_message(
        "assistant", "我可以制作图表和分析报告，帮您完成数据可视化。", turn_id=turn_id
    )

    result = runner._run_completion_check(session, turn_id=turn_id, attempt=0)  # noqa: SLF001
    artifact_item = next(item for item in result.items if item.key == "artifact_generated")

    assert artifact_item.passed is True, "能力描述类文本不应触发承诺产物校验"


def test_artifact_check_fails_when_promised_but_not_delivered() -> None:
    """含完成语义词的回答（'以下是分析报告'）应触发承诺产物校验。"""
    runner = HarnessRunner(agent_runner=None)  # type: ignore[arg-type]
    session = Session()
    turn_id = "turn-promise"
    # 含"以下是...报告"——命中完成语义词 + 产物词
    session.add_message("assistant", "以下是分析报告，请查阅。", turn_id=turn_id)

    result = runner._run_completion_check(session, turn_id=turn_id, attempt=0)  # noqa: SLF001
    artifact_item = next(item for item in result.items if item.key == "artifact_generated")

    # 无产物事件时应 passed=False
    assert artifact_item.passed is False, "承诺了产物但未生成产物事件时应校验失败"


@pytest.mark.asyncio
async def test_harness_trace_store_marks_crash_as_error() -> None:
    trace_store = _CaptureTraceStore()
    runner = HarnessRunner(agent_runner=_CrashRunner(), trace_store=trace_store)
    session = Session()

    with pytest.raises(RuntimeError, match="boom"):
        _ = [event async for event in runner.run(session, "请分析数据差异")]

    assert trace_store.records[0].status == "error"
