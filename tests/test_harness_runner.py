"""HarnessRunner 与 trace 存储测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nini.agent import event_builders as eb
from nini.agent.events import AgentEvent, EventType
from nini.agent.session import Session
from nini.config import settings
from nini.harness.models import CompletionCheckResult, HarnessRunContext, HarnessTraceRecord
from nini.harness.runner import HarnessRunner
from nini.harness.store import HarnessTraceStore
from nini.models.database import init_db
from nini.tools.dispatch_agents import DispatchAgentsTool


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


class _StagePollutionRunner:
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
            tool_call_id = f"widget-{self.calls}-{idx}"
            result_payload = {
                "success": False,
                "message": "generate_widget 只能展示已完成结果。",
                "error_code": "WIDGET_RESULT_REQUIRED",
                "data": {
                    "recovery_hint": "请先执行 code_session 或 stat_test，再展示结果。",
                },
            }
            session.add_tool_result(
                tool_call_id,
                json.dumps(result_payload, ensure_ascii=False),
                tool_name="generate_widget",
                status="error",
                turn_id=turn_id,
            )
            yield eb.build_tool_result_event(
                tool_call_id=tool_call_id,
                name="generate_widget",
                status="error",
                message="generate_widget 只能展示已完成结果。",
                data={"result": result_payload},
                turn_id=turn_id,
            )
        yield eb.build_done_event(turn_id=turn_id)


class _IncompleteTaskRunner:
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
        _ = user_message, stop_event, stage_override
        self.calls += 1
        assert turn_id is not None
        if append_user_message:
            session.add_message("user", "开始分析", turn_id=turn_id)
        if not session.task_manager.initialized:
            session.task_manager = session.task_manager.init_tasks(
                [
                    {"id": 1, "title": "数据清洗", "status": "completed"},
                    {"id": 2, "title": "描述性统计", "status": "completed"},
                    {"id": 3, "title": "生成图表", "status": "pending"},
                    {"id": 4, "title": "生成汇总报告", "status": "pending"},
                ]
            )
        yield eb.build_iteration_start_event(iteration=self.calls - 1, turn_id=turn_id)
        session.add_message("assistant", "描述性统计完成，接下来准备生成图表。", turn_id=turn_id)
        yield eb.build_text_event("描述性统计完成，接下来准备生成图表。", turn_id=turn_id)
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


class _SoftViolationRunner:
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
        yield AgentEvent(
            type=EventType.ERROR,
            data={
                "level": "allowed_tools_soft_violation",
                "tool": "code_session",
                "risk_level": "low",
                "message": "低风险越界，继续执行。",
            },
            turn_id=turn_id,
        )
        session.add_message("assistant", "最终分析完成。", turn_id=turn_id)
        yield eb.build_text_event("最终分析完成。", turn_id=turn_id)
        yield eb.build_done_event(turn_id=turn_id)


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


class _StructuredDatasetTransformRecoveryRunner:
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
            raw_args = json.dumps(
                {
                    "operation": "run",
                    "dataset_name": "raw",
                    "steps": [
                        {
                            "id": "rename",
                            "op": "rename_columns",
                            "params": {"收缩压/Hgmm": "收缩压"},
                        }
                    ],
                },
                ensure_ascii=False,
            )
            error_payload = {
                "error_code": "DATASET_TRANSFORM_RENAME_MAPPING_REQUIRED",
                "expected_params": ["mapping"],
                "recovery_hint": "请将映射放入 params.mapping 后重试。",
                "minimal_example": '{"mapping":{"收缩压/Hgmm":"收缩压"}}',
            }
            for idx in range(2):
                tool_call_id = f"dataset-transform-invalid-{idx}"
                session.add_tool_call(tool_call_id, "dataset_transform", raw_args, turn_id=turn_id)
                session.add_tool_result(
                    tool_call_id,
                    "数据变换失败: rename_columns 缺少 mapping",
                    tool_name="dataset_transform",
                    status="error",
                    turn_id=turn_id,
                    data=error_payload,
                )
                yield eb.build_tool_result_event(
                    tool_call_id=tool_call_id,
                    name="dataset_transform",
                    status="error",
                    message="数据变换失败: rename_columns 缺少 mapping",
                    data=error_payload,
                    turn_id=turn_id,
                )
                if stop_event is not None and stop_event.is_set():
                    return
        else:
            raw_args = json.dumps(
                {
                    "operation": "run",
                    "dataset_name": "raw",
                    "steps": [
                        {
                            "id": "rename",
                            "op": "rename_columns",
                            "params": {"mapping": {"收缩压/Hgmm": "收缩压"}},
                        }
                    ],
                },
                ensure_ascii=False,
            )
            tool_call_id = "dataset-transform-valid"
            session.add_tool_call(tool_call_id, "dataset_transform", raw_args, turn_id=turn_id)
            session.add_tool_result(
                tool_call_id,
                "数据变换完成",
                tool_name="dataset_transform",
                status="success",
                turn_id=turn_id,
                data={"resource_id": "ds_clean", "resource_type": "dataset"},
            )
            yield eb.build_tool_result_event(
                tool_call_id=tool_call_id,
                name="dataset_transform",
                status="success",
                message="数据变换完成",
                data={"resource_id": "ds_clean", "resource_type": "dataset"},
                turn_id=turn_id,
            )
            session.add_message(
                "assistant",
                "已根据 error_code 改用 params.mapping 重试并完成分析。",
                turn_id=turn_id,
            )
            yield eb.build_text_event(
                "已根据 error_code 改用 params.mapping 重试并完成分析。",
                turn_id=turn_id,
            )
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


class _BudgetRunner:
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
            session.add_message("user", "执行深任务", turn_id=turn_id)
        yield eb.build_iteration_start_event(iteration=0, turn_id=turn_id)
        yield eb.build_tool_call_event(
            tool_call_id="call_budget",
            name="run_code",
            arguments={"code": "print(1)"},
            turn_id=turn_id,
        )
        yield eb.build_token_usage_event(
            input_tokens=60,
            output_tokens=40,
            model="demo-model",
            cost_usd=0.25,
            turn_id=turn_id,
        )
        session.add_message("assistant", "最终分析完成。", turn_id=turn_id)
        yield eb.build_text_event("最终分析完成。", turn_id=turn_id)
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
async def test_harness_runner_marks_stage_pollution_loop() -> None:
    runner = HarnessRunner(agent_runner=_StagePollutionRunner())
    session = Session()

    events = [event async for event in runner.run(session, "请分析数据差异")]
    blocked_events = [event for event in events if event.type.value == "blocked"]

    assert blocked_events
    assert blocked_events[-1].data["reason_code"] == "stage_pollution_loop"


@pytest.mark.asyncio
async def test_harness_runner_persists_blocked_summary_for_incomplete_tasks() -> None:
    runner = HarnessRunner(agent_runner=_IncompleteTaskRunner())
    session = Session()

    events = [event async for event in runner.run(session, "开始分析")]
    text_events = [event for event in events if event.type.value == "text"]

    assert any(event.type.value == "blocked" for event in events)
    assert any(
        isinstance(event.data, dict)
        and "当前轮分析已暂停" in str(event.data.get("content", ""))
        and "生成图表" in str(event.data.get("content", ""))
        and "生成汇总报告" in str(event.data.get("content", ""))
        for event in text_events
    )
    assistant_messages = [
        msg
        for msg in session.messages
        if msg.get("role") == "assistant" and msg.get("event_type") == "text"
    ]
    assert "当前轮分析已暂停" in str(assistant_messages[-1].get("content", ""))
    assert "所有任务已完成" in str(assistant_messages[-1].get("content", ""))


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
async def test_harness_runner_ignores_allowed_tools_soft_violation_error() -> None:
    trace_store = _CaptureTraceStore()
    runner = HarnessRunner(agent_runner=_SoftViolationRunner(), trace_store=trace_store)
    session = Session()

    events = [event async for event in runner.run(session, "请分析数据差异")]
    event_types = [event.type.value for event in events]

    assert event_types[0] == "iteration_start"
    assert "error" in event_types
    assert "text" in event_types
    assert event_types[-1] == "done"
    assert trace_store.records[0].status == "completed"


@pytest.mark.asyncio
async def test_harness_runner_records_task_metrics_and_budget_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "deep_task_budget_token_limit", 50)
    monkeypatch.setattr(settings, "deep_task_budget_cost_limit_usd", 0.2)
    monkeypatch.setattr(settings, "deep_task_budget_tool_call_limit", 1)

    trace_store = _CaptureTraceStore()
    runner = HarnessRunner(agent_runner=_BudgetRunner(), trace_store=trace_store)
    session = Session()
    session.bind_recipe_context(task_kind="deep_task", recipe_id="literature_review")
    session.set_deep_task_state(
        task_id="task_demo",
        retry_count=0,
        current_attempt_id="task_demo:workflow:1",
    )

    events = [event async for event in runner.run(session, "执行深任务")]

    budget_events = [event for event in events if event.type.value == "budget_warning"]
    assert len(budget_events) >= 2
    assert all(event.data["task_id"] == "task_demo" for event in budget_events)
    assert any(event.data["metric"] == "tokens" for event in budget_events)
    assert any(event.data["metric"] == "cost_usd" for event in budget_events)

    record = trace_store.records[0]
    assert record.task_id == "task_demo"
    assert record.recipe_id == "literature_review"
    assert record.task_metrics is not None
    assert record.task_metrics.final_status == "completed"
    assert record.task_metrics.total_duration_ms >= 0
    assert record.task_metrics.tool_call_count == 1
    assert record.task_metrics.recovery_count == 0
    assert record.task_metrics.step_durations_ms
    assert len(record.budget_warnings) >= 2


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


@pytest.mark.asyncio
async def test_harness_runner_completes_after_structured_tool_failure_recovery() -> None:
    inner_runner = _StructuredDatasetTransformRecoveryRunner()
    trace_store = _CaptureTraceStore()
    runner = HarnessRunner(agent_runner=inner_runner, trace_store=trace_store)
    session = Session()

    events = [event async for event in runner.run(session, "请先清洗再分析数据")]
    event_types = [event.type.value for event in events]

    assert "blocked" not in event_types
    assert event_types[-1] == "done"
    assert len(inner_runner.calls) == 2
    assert inner_runner.calls[1]["append_user_message"] is False
    assert any(
        event.type == EventType.REASONING
        and isinstance(event.data, dict)
        and event.data.get("source") == "loop_recovery"
        for event in events
    )
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
    assert session.list_pending_actions(action_type="tool_failure_unresolved") == []
    assert trace_store.records[0].status == "completed"
    assert trace_store.records[0].task_metrics is not None
    assert trace_store.records[0].task_metrics.recovery_count >= 1


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


@pytest.mark.asyncio
async def test_harness_trace_store_evaluates_core_recipe_gate(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()
    await init_db()

    store = HarnessTraceStore()
    for recipe_id in ("literature_review", "experiment_plan"):
        await store.save_run(
            HarnessTraceRecord(
                run_id=f"run_{recipe_id}",
                session_id="session_gate",
                turn_id=f"turn_{recipe_id}",
                user_message="请执行回放",
                run_context=HarnessRunContext(turn_id=f"turn_{recipe_id}", recipe_id=recipe_id),
                task_id=f"task_{recipe_id}",
                recipe_id=recipe_id,
                status="completed",
                finished_at="2026-03-14T00:00:01+00:00",
            )
        )

    result = await store.evaluate_core_recipe_benchmarks_async(session_id="session_gate")

    assert result["core_recipe_benchmarks"]["gate_passed"] is False
    assert result["core_recipe_benchmarks"]["sample_results"]
    assert result["core_recipe_benchmarks"]["top_failure_tags"]


@pytest.mark.asyncio
async def test_harness_trace_store_reinitializes_schema_for_new_db_path(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_data_dir = tmp_path / "data_first"
    second_data_dir = tmp_path / "data_second"

    monkeypatch.setattr(settings, "data_dir", first_data_dir)
    settings.ensure_dirs()
    await init_db()

    store = HarnessTraceStore()
    await store.save_run(
        HarnessTraceRecord(
            run_id="run_first",
            session_id="session_first",
            turn_id="turn_first",
            user_message="请分析第一组数据",
            run_context=HarnessRunContext(turn_id="turn_first"),
            status="completed",
            finished_at="2026-03-14T00:00:01+00:00",
        )
    )

    monkeypatch.setattr(settings, "data_dir", second_data_dir)
    settings.ensure_dirs()

    await store.save_run(
        HarnessTraceRecord(
            run_id="run_second",
            session_id="session_second",
            turn_id="turn_second",
            user_message="请分析第二组数据",
            run_context=HarnessRunContext(turn_id="turn_second"),
            status="completed",
            finished_at="2026-03-14T00:00:02+00:00",
        )
    )

    summaries = await store.list_runs(session_id="session_second", limit=5)

    assert summaries
    assert summaries[0].run_id == "run_second"


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


def test_completion_check_passes_when_only_in_progress_remains() -> None:
    """无 pending 任务且 LLM 已输出文本时，all_tasks_completed 应通过。"""
    runner = HarnessRunner(agent_runner=None)  # type: ignore[arg-type]
    session = Session()
    turn_id = "turn-last-ip"

    # 模拟：任务1 completed，任务2 in_progress（无 pending）
    session.task_manager = session.task_manager.init_tasks(
        [
            {"id": 1, "title": "数据清洗", "status": "pending"},
            {"id": 2, "title": "结果汇总", "status": "pending"},
        ]
    )
    result = session.task_manager.update_tasks(
        [{"id": 1, "status": "completed"}, {"id": 2, "status": "in_progress"}]
    )
    session.task_manager = result.manager

    # LLM 输出了实质性的最终文本（需满足 substantive 检查）
    session.add_message(
        "assistant",
        "## 分析总结\n\n数据质量良好，共2627条记录。"
        "收缩压均值118.09mmHg，处于正常范围。"
        "建议继续监测，重点关注舒张压趋势。",
        turn_id=turn_id,
    )

    check = runner._run_completion_check(session, turn_id=turn_id, attempt=0)  # noqa: SLF001
    task_item = next(item for item in check.items if item.key == "all_tasks_completed")
    assert task_item.passed is True, "无 pending 且有文本输出时应视为通过"


def test_completion_check_fails_when_pending_tasks_exist() -> None:
    """仍有 pending 任务时，即使有文本输出也不应通过。"""
    runner = HarnessRunner(agent_runner=None)  # type: ignore[arg-type]
    session = Session()
    turn_id = "turn-has-pending"

    # 模拟：任务1 completed，任务2 in_progress，任务3 pending
    session.task_manager = session.task_manager.init_tasks(
        [
            {"id": 1, "title": "数据清洗", "status": "pending"},
            {"id": 2, "title": "统计分析", "status": "pending"},
            {"id": 3, "title": "生成报告", "status": "pending"},
        ]
    )
    result = session.task_manager.update_tasks(
        [{"id": 1, "status": "completed"}, {"id": 2, "status": "in_progress"}]
    )
    session.task_manager = result.manager

    session.add_message("assistant", "分析完成。", turn_id=turn_id)

    check = runner._run_completion_check(session, turn_id=turn_id, attempt=0)  # noqa: SLF001
    task_item = next(item for item in check.items if item.key == "all_tasks_completed")
    assert task_item.passed is False, "仍有 pending 任务时不应通过"


def test_completion_check_registers_artifact_and_transitional_pending_actions() -> None:
    runner = HarnessRunner(agent_runner=None)  # type: ignore[arg-type]
    session = Session()
    turn_id = "turn-pending-actions"
    session.add_message("assistant", "以下是分析报告，接下来我会继续补图。", turn_id=turn_id)

    check = runner._run_completion_check(session, turn_id=turn_id, attempt=0)  # noqa: SLF001

    pending_types = {item["type"] for item in session.list_pending_actions(status="pending")}
    assert check.passed is False
    assert "artifact_promised_not_materialized" in pending_types
    assert "task_noop_blocked" in pending_types


def test_completion_check_allows_transitional_phrasing_when_tasks_done() -> None:
    runner = HarnessRunner(agent_runner=None)  # type: ignore[arg-type]
    session = Session()
    turn_id = "turn-transitional-done"

    session.task_manager = session.task_manager.init_tasks(
        [
            {"id": 1, "title": "抽取主要发现", "status": "pending"},
            {"id": 2, "title": "建立解释框架", "status": "pending"},
            {"id": 3, "title": "输出结论与下一步", "status": "pending"},
        ]
    )
    result = session.task_manager.update_tasks(
        [
            {"id": 1, "status": "completed"},
            {"id": 2, "status": "completed"},
            {"id": 3, "status": "completed"},
        ]
    )
    session.task_manager = result.manager
    session.add_message(
        "assistant",
        "我将先总结主要结果，再给出下一步建议。结论：当前结果支持干预有效，但仍需补充效应量。",
        turn_id=turn_id,
    )

    check = runner._run_completion_check(session, turn_id=turn_id, attempt=0)  # noqa: SLF001

    not_transitional = next(item for item in check.items if item.key == "not_transitional")
    assert not_transitional.passed is True
    pending_types = {item["type"] for item in session.list_pending_actions(status="pending")}
    assert "task_noop_blocked" not in pending_types


def test_completion_recovery_prompt_in_recipe_mode_forces_defaults() -> None:
    completion = CompletionCheckResult(
        turn_id="turn-recipe",
        attempt=1,
        passed=False,
        items=[],
        missing_actions=["所有任务已完成"],
        evidence={"pending_actions": []},
    )
    prompt = HarnessRunner._build_completion_recovery_prompt(  # noqa: SLF001
        completion=completion,
        remaining_tasks=2,
        recipe_mode=True,
    )

    assert "Recipe 模式" in prompt
    assert "保守常见默认值继续完成" in prompt


def test_handle_tool_result_registers_and_clears_pending_failure() -> None:
    session = Session()
    turn_id = "turn-tool-failure"
    tool_call_id = "call-demo"
    session.add_tool_call(
        tool_call_id,
        "export_report",
        '{"operation":"export","format":"pdf"}',
        turn_id=turn_id,
    )
    error_event = AgentEvent(
        type=EventType.TOOL_RESULT,
        tool_call_id=tool_call_id,
        tool_name="export_report",
        turn_id=turn_id,
        data={"status": "error", "message": "导出超时：超过 10 秒"},
    )
    success_event = AgentEvent(
        type=EventType.TOOL_RESULT,
        tool_call_id=tool_call_id,
        tool_name="export_report",
        turn_id=turn_id,
        data={"status": "success", "message": "导出成功"},
    )

    _, blocked_state = HarnessRunner._handle_tool_result(  # noqa: SLF001
        session=session,
        event=error_event,
        turn_id=turn_id,
        task_id=None,
        attempt_id=None,
        tool_error_counts={},
        tool_failure_messages={},
        recovered_tool_signatures=set(),
    )
    assert blocked_state is None
    pending = session.list_pending_actions(action_type="tool_failure_unresolved")
    assert len(pending) == 1
    assert pending[0]["metadata"]["failure_kind"] == "timeout"
    assert pending[0]["metadata"]["purpose"] == "export"

    HarnessRunner._handle_tool_result(  # noqa: SLF001
        session=session,
        event=success_event,
        turn_id=turn_id,
        task_id=None,
        attempt_id=None,
        tool_error_counts={f'export_report::{{"format":"pdf","operation":"export"}}': 1},
        tool_failure_messages={},
        recovered_tool_signatures=set(),
    )
    assert session.list_pending_actions(action_type="tool_failure_unresolved") == []


def test_completion_check_ignores_non_blocking_pending_actions() -> None:
    runner = HarnessRunner(agent_runner=None)  # type: ignore[arg-type]
    session = Session()
    turn_id = "turn-non-blocking"
    session.upsert_pending_action(
        action_type="tool_failure_unresolved",
        key='task_state::{"operation":"init"}',
        summary="task_state 失败：任务列表已初始化且无法重新初始化。",
        source_tool="task_state",
        blocking=False,
        failure_category="idempotent_conflict",
        metadata={"turn_id": "old-turn"},
    )
    session.add_message("assistant", "结论：相关分析已完成。", turn_id=turn_id)

    check = runner._run_completion_check(session, turn_id=turn_id, attempt=0)  # noqa: SLF001

    pending_item = next(item for item in check.items if item.key == "pending_actions_resolved")
    assert pending_item.passed is True


def test_handle_tool_result_success_clears_non_blocking_failure_from_same_turn() -> None:
    session = Session()
    turn_id = "turn-task-state"
    tool_call_id = "call-task-state"
    session.add_tool_call(
        tool_call_id,
        "task_state",
        '{"operation":"init","tasks":[{"id":1,"title":"分析","status":"pending"}]}',
        turn_id=turn_id,
    )
    session.upsert_pending_action(
        action_type="tool_failure_unresolved",
        key='task_state::{"operation":"init","tasks":[{"id":1,"title":"分析","status":"pending"}]}',
        summary="task_state 失败：任务列表已初始化且无法重新初始化。",
        source_tool="task_state",
        blocking=False,
        failure_category="idempotent_conflict",
        metadata={"turn_id": turn_id},
    )

    success_event = AgentEvent(
        type=EventType.TOOL_RESULT,
        tool_call_id=tool_call_id,
        tool_name="task_state",
        turn_id=turn_id,
        data={"status": "success", "message": "任务状态已更新"},
    )

    HarnessRunner._handle_tool_result(  # noqa: SLF001
        session=session,
        event=success_event,
        turn_id=turn_id,
        task_id=None,
        attempt_id=None,
        tool_error_counts={},
        tool_failure_messages={},
        recovered_tool_signatures=set(),
    )

    assert session.list_pending_actions(action_type="tool_failure_unresolved") == []


def test_handle_tool_result_marks_workspace_binary_read_as_non_blocking() -> None:
    session = Session()
    turn_id = "turn-workspace-binary"
    tool_call_id = "call-workspace-binary"
    session.add_tool_call(
        tool_call_id,
        "workspace_session",
        '{"operation":"read","file_path":"demo.xlsx"}',
        turn_id=turn_id,
    )

    error_event = AgentEvent(
        type=EventType.TOOL_RESULT,
        tool_call_id=tool_call_id,
        tool_name="workspace_session",
        turn_id=turn_id,
        data={
            "status": "error",
            "message": "不能直接按文本读取 `demo.xlsx`。该文件是二进制或 Office 文档，请改用合适的专用工具。",
            "data": {"error_code": "WORKSPACE_READ_BINARY_UNSUPPORTED"},
        },
    )

    _, blocked_state = HarnessRunner._handle_tool_result(  # noqa: SLF001
        session=session,
        event=error_event,
        turn_id=turn_id,
        task_id=None,
        attempt_id=None,
        tool_error_counts={},
        tool_failure_messages={},
        recovered_tool_signatures=set(),
    )

    assert blocked_state is None
    pending = session.list_pending_actions(action_type="tool_failure_unresolved")
    assert len(pending) == 1
    assert pending[0]["blocking"] is False
    assert pending[0]["failure_category"] == "recoverable_input_misuse"


def test_handle_tool_result_marks_task_state_init_status_error_as_non_blocking() -> None:
    session = Session()
    turn_id = "turn-task-state-init-status"
    tool_call_id = "call-task-state-init-status"
    session.add_tool_call(
        tool_call_id,
        "task_state",
        '{"operation":"init","tasks":[{"id":1,"title":"澄清问题","status":"in_progress"}]}',
        turn_id=turn_id,
    )

    error_event = AgentEvent(
        type=EventType.TOOL_RESULT,
        tool_call_id=tool_call_id,
        tool_name="task_state",
        turn_id=turn_id,
        data={
            "status": "error",
            "message": "init 操作中的所有任务初始状态必须为 pending",
            "result": {
                "success": False,
                "message": "init 操作中的所有任务初始状态必须为 pending",
                "data": {"error_code": "TASK_STATE_INIT_STATUS_INVALID"},
            },
        },
    )

    _, blocked_state = HarnessRunner._handle_tool_result(  # noqa: SLF001
        session=session,
        event=error_event,
        turn_id=turn_id,
        task_id=None,
        attempt_id=None,
        tool_error_counts={},
        tool_failure_messages={},
        recovered_tool_signatures=set(),
    )

    assert blocked_state is None
    pending = session.list_pending_actions(action_type="tool_failure_unresolved")
    assert len(pending) == 1
    assert pending[0]["blocking"] is False
    assert pending[0]["failure_category"] == "recoverable_input_misuse"


def test_handle_tool_result_marks_task_state_missing_operation_as_non_blocking() -> None:
    session = Session()
    turn_id = "turn-task-state-missing-operation"
    tool_call_id = "call-task-state-missing-operation"
    session.add_tool_call(tool_call_id, "task_state", "{}", turn_id=turn_id)

    error_event = AgentEvent(
        type=EventType.TOOL_RESULT,
        tool_call_id=tool_call_id,
        tool_name="task_state",
        turn_id=turn_id,
        data={
            "status": "error",
            "message": "缺少 operation，请指定 init、update、get 或 current",
            "result": {
                "success": False,
                "message": "缺少 operation，请指定 init、update、get 或 current",
                "data": {"error_code": "TASK_STATE_OPERATION_REQUIRED"},
            },
        },
    )

    _, blocked_state = HarnessRunner._handle_tool_result(  # noqa: SLF001
        session=session,
        event=error_event,
        turn_id=turn_id,
        task_id=None,
        attempt_id=None,
        tool_error_counts={},
        tool_failure_messages={},
        recovered_tool_signatures=set(),
    )

    assert blocked_state is None
    pending = session.list_pending_actions(action_type="tool_failure_unresolved")
    assert len(pending) == 1
    assert pending[0]["blocking"] is False
    assert pending[0]["failure_category"] == "recoverable_input_misuse"


def test_handle_tool_result_marks_task_write_missing_mode_as_non_blocking() -> None:
    session = Session()
    turn_id = "turn-task-write-missing-mode"
    tool_call_id = "call-task-write-missing-mode"
    session.add_tool_call(tool_call_id, "task_write", "{}", turn_id=turn_id)

    error_event = AgentEvent(
        type=EventType.TOOL_RESULT,
        tool_call_id=tool_call_id,
        tool_name="task_write",
        turn_id=turn_id,
        data={
            "status": "error",
            "message": "缺少 mode，请指定 init 或 update",
            "result": {
                "success": False,
                "message": "缺少 mode，请指定 init 或 update",
                "data": {"error_code": "TASK_WRITE_MODE_REQUIRED"},
            },
        },
    )

    _, blocked_state = HarnessRunner._handle_tool_result(  # noqa: SLF001
        session=session,
        event=error_event,
        turn_id=turn_id,
        task_id=None,
        attempt_id=None,
        tool_error_counts={},
        tool_failure_messages={},
        recovered_tool_signatures=set(),
    )

    assert blocked_state is None
    pending = session.list_pending_actions(action_type="tool_failure_unresolved")
    assert len(pending) == 1
    assert pending[0]["blocking"] is False
    assert pending[0]["failure_category"] == "recoverable_input_misuse"


def test_handle_tool_result_marks_dispatch_context_error_as_non_blocking() -> None:
    session = Session()
    turn_id = "turn-dispatch-context"
    tool_call_id = "call-dispatch-context"
    session.add_tool_call(
        tool_call_id,
        "dispatch_agents",
        '{"tasks":[{"task_id":1,"agent_id":"statistician","task":"查看前20行"}]}',
        turn_id=turn_id,
    )

    error_event = AgentEvent(
        type=EventType.TOOL_RESULT,
        tool_call_id=tool_call_id,
        tool_name="dispatch_agents",
        turn_id=turn_id,
        data={
            "status": "error",
            "message": "任务1 当前处于 in_progress。",
            "result": {
                "success": False,
                "message": "任务1 当前处于 in_progress。",
                "data": {
                    "error_code": "DISPATCH_CONTEXT_MISMATCH",
                    "task_id": 1,
                    "current_in_progress_task_id": 1,
                    "current_pending_wave_task_ids": [2, 3],
                    "recovery_action": "run_direct_tool_or_use_parent_task_id",
                    "recommended_tools": ["dataset_catalog", "run_code"],
                    "recovery_hint": "请直接执行当前任务，或改用 parent_task_id。",
                },
            },
        },
    )

    _, blocked_state = HarnessRunner._handle_tool_result(  # noqa: SLF001
        session=session,
        event=error_event,
        turn_id=turn_id,
        task_id=None,
        attempt_id=None,
        tool_error_counts={},
        tool_failure_messages={},
        recovered_tool_signatures=set(),
    )

    assert blocked_state is None
    pending = session.list_pending_actions(action_type="tool_failure_unresolved")
    assert len(pending) == 1
    assert pending[0]["blocking"] is False
    assert pending[0]["failure_category"] == "dispatch_context_misuse"
    assert pending[0]["metadata"]["recovery_action"] == "run_direct_tool_or_use_parent_task_id"
    assert pending[0]["metadata"]["current_pending_wave_task_ids"] == [2, 3]


def test_handle_tool_result_resolves_dispatch_pending_action_after_direct_tool_success() -> None:
    session = Session()
    turn_id = "turn-dispatch-resolve"
    session.upsert_pending_action(
        action_type="tool_failure_unresolved",
        key="dispatch_agents::DISPATCH_CONTEXT_MISMATCH::1",
        status="pending",
        summary="dispatch_agents 失败：任务1 当前处于 in_progress。",
        source_tool="dispatch_agents",
        blocking=False,
        failure_category="dispatch_context_misuse",
        metadata={"turn_id": turn_id},
    )

    success_event = AgentEvent(
        type=EventType.TOOL_RESULT,
        tool_call_id="call-run-code",
        tool_name="run_code",
        turn_id=turn_id,
        data={"status": "success", "message": "执行成功"},
    )

    _, blocked_state = HarnessRunner._handle_tool_result(  # noqa: SLF001
        session=session,
        event=success_event,
        turn_id=turn_id,
        task_id=None,
        attempt_id=None,
        tool_error_counts={},
        tool_failure_messages={},
        recovered_tool_signatures=set(),
    )

    assert blocked_state is None
    assert session.list_pending_actions(action_type="tool_failure_unresolved") == []


@pytest.mark.asyncio
async def test_session_3be947_dispatch_dead_loop_replay_fixture_resolves_with_direct_tool() -> None:
    """基于真实会话 trace 构造等价 fixture，验证新逻辑不再卡在 dispatch dead loop。"""

    # 可选：本地 trace 文件验证（CI 中不存在则跳过）
    trace_path = Path("data/sessions/3be947d505b7/harness/traces/756b65a5401f48a5b028e40294b1798e.json")
    if trace_path.exists():
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
        dispatch_messages = [
            str(event.get("data", {}).get("message", "")).strip()
            for event in trace.get("events", [])
            if event.get("type") == "tool_result" and event.get("tool_name") == "dispatch_agents"
        ]
        assert any("data-explorer" in message for message in dispatch_messages)
        assert sum("任务1 不在当前可执行 wave 中" in message for message in dispatch_messages) >= 1

    session = Session()
    session.task_manager = session.task_manager.init_tasks(
        [
            {"id": 1, "title": "读取all sheet并检查数据结构", "status": "pending", "tool_hint": "dataset_catalog"},
            {"id": 2, "title": "数据预处理", "status": "pending", "tool_hint": "dataset_transform"},
            {"id": 3, "title": "数据聚合", "status": "pending", "tool_hint": "stat_test"},
            {"id": 4, "title": "绘制柱状图", "status": "pending", "tool_hint": "chart_session"},
        ]
    )
    session.task_manager = session.task_manager.update_tasks([{"id": 1, "status": "in_progress"}]).manager

    class _ReplayRegistry:
        def list_dispatchable_agents(self):
            return [type("Def", (), {"agent_id": "statistician"})()]

    class _ReplaySpawner:
        async def spawn_batch(self, tasks, session, **kwargs):  # noqa: ANN001
            return []

    tool = DispatchAgentsTool(agent_registry=_ReplayRegistry(), spawner=_ReplaySpawner())
    result = await tool.execute(
        session,
        tasks=[{"task_id": 1, "agent_id": "statistician", "task": "查看前20行数据"}],
    )

    assert result.success is False
    assert result.data["error_code"] == "DISPATCH_CONTEXT_MISMATCH"
    assert result.data["current_in_progress_task_id"] == 1
    assert result.data["current_pending_wave_task_ids"] == [2, 3, 4]
    assert result.data["recovery_action"] == "run_direct_tool_or_use_parent_task_id"

    error_event = AgentEvent(
        type=EventType.TOOL_RESULT,
        tool_call_id="call-dispatch-replay",
        tool_name="dispatch_agents",
        turn_id="turn-replay",
        data={
            "status": "error",
            "message": result.message,
            "result": result.to_dict(),
        },
    )
    HarnessRunner._handle_tool_result(  # noqa: SLF001
        session=session,
        event=error_event,
        turn_id="turn-replay",
        task_id=None,
        attempt_id=None,
        tool_error_counts={},
        tool_failure_messages={},
        recovered_tool_signatures=set(),
    )
    assert session.list_pending_actions(action_type="tool_failure_unresolved")

    success_event = AgentEvent(
        type=EventType.TOOL_RESULT,
        tool_call_id="call-run-code-replay",
        tool_name="run_code",
        turn_id="turn-replay",
        data={"status": "success", "message": "已读取前20行数据"},
    )
    HarnessRunner._handle_tool_result(  # noqa: SLF001
        session=session,
        event=success_event,
        turn_id="turn-replay",
        task_id=None,
        attempt_id=None,
        tool_error_counts={},
        tool_failure_messages={},
        recovered_tool_signatures=set(),
    )
    assert session.list_pending_actions(action_type="tool_failure_unresolved") == []


@pytest.mark.asyncio
async def test_harness_trace_store_marks_crash_as_error() -> None:
    trace_store = _CaptureTraceStore()
    runner = HarnessRunner(agent_runner=_CrashRunner(), trace_store=trace_store)
    session = Session()

    with pytest.raises(RuntimeError, match="boom"):
        _ = [event async for event in runner.run(session, "请分析数据差异")]

    assert trace_store.records[0].status == "error"


# ─── promised_artifact 正则修复测试 ─────────────────────────────────────────


class _CapabilityIntroRunner:
    """模拟 AI 输出指定文本的 Runner。"""

    def __init__(self, text: str) -> None:
        self._text = text

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
        assert turn_id is not None
        if append_user_message:
            session.add_message("user", user_message, turn_id=turn_id)
        yield eb.build_iteration_start_event(iteration=0, turn_id=turn_id)
        session.add_message("assistant", self._text, turn_id=turn_id)
        yield eb.build_text_event(self._text, turn_id=turn_id)
        yield eb.build_done_event(turn_id=turn_id)


@pytest.mark.asyncio
async def test_harness_no_false_positive_on_capability_intro() -> None:
    """能力介绍文本含"图表"/"报告"但无完成语义词时，artifact_generated 应 passed=True。"""
    text = "我可以帮你制作图表、生成报告、清洗数据和进行统计分析。"
    runner = HarnessRunner(agent_runner=_CapabilityIntroRunner(text))
    session = Session()

    events = [event async for event in runner.run(session, "你能做什么")]
    check_events = [
        e for e in events if e.type.value == "completion_check" and isinstance(e.data, dict)
    ]
    assert check_events, "应触发至少一次完成校验"
    for ce in check_events:
        items = ce.data.get("items", [])
        for item in items:
            if item.get("key") == "artifact_generated":
                assert (
                    item["passed"] is True
                ), f"能力介绍文本不应触发 artifact_generated 校验失败: {text!r}"


@pytest.mark.asyncio
async def test_harness_detects_real_artifact_promise() -> None:
    """含"以下是分析报告"的回答应触发 artifact_generated 校验失败（无产物事件）。"""
    text = "以下是分析报告，数据差异显著。"
    runner = HarnessRunner(agent_runner=_CapabilityIntroRunner(text))
    session = Session()

    events = [event async for event in runner.run(session, "分析数据")]
    check_events = [
        e for e in events if e.type.value == "completion_check" and isinstance(e.data, dict)
    ]
    assert check_events, "应触发至少一次完成校验"
    first_check = check_events[0]
    items = first_check.data.get("items", [])
    artifact_item = [item for item in items if item.get("key") == "artifact_generated"]
    assert artifact_item, "应有 artifact_generated 校验项"
    assert artifact_item[0]["passed"] is False, "承诺产物但无产物事件时应校验失败"
