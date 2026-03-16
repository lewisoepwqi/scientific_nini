"""HarnessRunner：在 AgentRunner 外围增加运行护栏。"""

from __future__ import annotations

import asyncio
import json
import re
import uuid

# 承诺产物检测正则：要求"完成语义词 + 产物词"在 15 字符内共现，避免能力描述类文本误触发
_PROMISED_ARTIFACT_RE = re.compile(
    r"(已生成|已导出|已完成|以下是|请查看|如下)[\s\S]{0,15}(图表|报告|产物|附件)"
    r"|(图表|报告|产物|附件)[\s\S]{0,8}(已生成|已导出|已完成|已保存)",
)
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Protocol

from nini.agent import event_builders as eb
from nini.agent.events import AgentEvent, EventType
from nini.agent.runner import AgentRunner
from nini.agent.session import Session
from nini.harness.models import (
    BlockedState,
    CompletionCheckItem,
    CompletionCheckResult,
    HarnessArtifactSummary,
    HarnessDatasetSummary,
    HarnessRunContext,
    HarnessRunSummary,
    HarnessTraceEvent,
    HarnessTraceRecord,
)
from nini.harness.store import HarnessTraceStore

_TRANSITIONAL_TEXT_RE = re.compile(r"^(接下来|下一步|我将|我会继续|我会先|下面将|随后将)")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentRunnerLike(Protocol):
    def run(
        self,
        session: Session,
        user_message: str,
        *,
        append_user_message: bool = True,
        stop_event: asyncio.Event | None = None,
        turn_id: str | None = None,
        stage_override: str | None = None,
    ) -> AsyncGenerator[AgentEvent, None]: ...


class HarnessTraceStoreLike(Protocol):
    async def save_run(self, record: HarnessTraceRecord) -> HarnessRunSummary | None: ...


class HarnessRunner:
    """对 AgentRunner 增加完成校验、坏循环恢复与 trace。"""

    def __init__(
        self,
        agent_runner: AgentRunnerLike | None = None,
        trace_store: HarnessTraceStoreLike | None = None,
    ) -> None:
        self._agent_runner: AgentRunnerLike = agent_runner or AgentRunner()
        self._trace_store: HarnessTraceStoreLike = trace_store or HarnessTraceStore()

    async def run(
        self,
        session: Session,
        user_message: str,
        *,
        append_user_message: bool = True,
        stop_event: asyncio.Event | None = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        """执行带 harness 约束的一轮运行。"""
        turn_id = uuid.uuid4().hex[:12]
        run_id = uuid.uuid4().hex
        run_context = self._build_run_context(session, turn_id=turn_id)
        session.harness_runtime_context = run_context.to_runtime_block()

        trace = HarnessTraceRecord(
            run_id=run_id,
            session_id=session.id,
            turn_id=turn_id,
            user_message=user_message,
            run_context=run_context,
        )

        combined_stop_event = asyncio.Event()
        bridge_task: asyncio.Task[None] | None = None
        if stop_event is not None:
            bridge_task = asyncio.create_task(
                self._bridge_stop_event(stop_event, combined_stop_event)
            )

        completion_attempt = 0
        pending_prompt = user_message
        append_flag = append_user_message
        tool_error_counts: dict[str, int] = {}
        tool_failure_messages: dict[str, str] = {}
        recovered_tool_signatures: set[str] = set()
        blocked_state: BlockedState | None = None
        completed = False

        try:
            run_context_event = eb.build_run_context_event(
                turn_id=turn_id,
                datasets=[item.model_dump() for item in run_context.datasets],
                artifacts=[item.model_dump() for item in run_context.artifacts],
                tool_hints=run_context.tool_hints,
                constraints=run_context.constraints,
            )
            while not completed and blocked_state is None:
                iteration_started = False
                run_context_emitted = False
                trace.stage_history.append(
                    {
                        "attempt": completion_attempt + 1,
                        "stage": "verification" if completion_attempt > 0 else "planning",
                        "purpose": "verification" if completion_attempt > 0 else "planning",
                        "reasoning_budget": "high" if completion_attempt >= 0 else "medium",
                    }
                )

                async for event in self._agent_runner.run(
                    session,
                    pending_prompt,
                    append_user_message=append_flag,
                    stop_event=combined_stop_event,
                    turn_id=turn_id,
                    stage_override="verification" if completion_attempt > 0 else None,
                ):
                    self._record_event(trace, event)

                    if event.type == EventType.ERROR:
                        trace.status = "error"
                        trace.finished_at = _utc_now_iso()
                        yield event
                        completed = True
                        break

                    if event.type == EventType.ITERATION_START:
                        iteration_started = True

                    if (
                        not run_context_emitted
                        and iteration_started
                        and event.type
                        not in {
                            EventType.ITERATION_START,
                            EventType.ERROR,
                            EventType.DONE,
                            EventType.STOPPED,
                            EventType.TRIAL_ACTIVATED,
                            EventType.TRIAL_EXPIRED,
                        }
                    ):
                        self._record_event(trace, run_context_event)
                        yield run_context_event
                        run_context_emitted = True

                    if event.type == EventType.TOOL_RESULT:
                        recovery_event, blocked_state = self._handle_tool_result(
                            session=session,
                            event=event,
                            turn_id=turn_id,
                            tool_error_counts=tool_error_counts,
                            tool_failure_messages=tool_failure_messages,
                            recovered_tool_signatures=recovered_tool_signatures,
                        )
                        if recovery_event is not None:
                            combined_stop_event.set()
                            yield recovery_event
                            append_flag = False
                            pending_prompt = (
                                "检测到同类工具路径连续失败。请退一步重新规划，"
                                "避免重复同一参数路径，优先解释失败原因并尝试替代方法。"
                            )
                        if blocked_state is not None:
                            combined_stop_event.set()

                    if event.type == EventType.DONE:
                        break

                    if blocked_state is None:
                        yield event

                if completed:
                    break

                if not run_context_emitted and blocked_state is None and iteration_started:
                    self._record_event(trace, run_context_event)
                    yield run_context_event

                if blocked_state is not None:
                    break

                if combined_stop_event.is_set() and stop_event is not None and stop_event.is_set():
                    trace.status = "stopped"
                    trace.finished_at = _utc_now_iso()
                    yield eb.build_stopped_event(turn_id=turn_id)
                    completed = True
                    break

                completion_attempt += 1
                completion = self._run_completion_check(
                    session,
                    turn_id=turn_id,
                    attempt=completion_attempt,
                )
                trace.completion_checks.append(completion)
                yield eb.build_completion_check_event(
                    turn_id=turn_id,
                    passed=completion.passed,
                    attempt=completion.attempt,
                    items=[item.model_dump() for item in completion.items],
                    missing_actions=completion.missing_actions,
                )

                if completion.passed:
                    trace.status = "completed"
                    trace.finished_at = _utc_now_iso()
                    trace.failure_tags = self._classify_failures(
                        completion=completion,
                        tool_failure_messages=tool_failure_messages,
                        blocked_state=None,
                    )
                    yield eb.build_done_event(turn_id=turn_id)
                    completed = True
                    break

                if completion_attempt >= 2:
                    blocked_state = BlockedState(
                        turn_id=turn_id,
                        reason_code="completion_verification_failed",
                        message="当前结果未通过完成校验，且补救后仍未满足结束条件。",
                        recoverable=True,
                        suggested_action="补充缺失分析、处理失败工具或调整问题范围后重试。",
                    )
                    break

                recovery_note = (
                    "系统已拦截过早结束：当前结果仍缺少必要验证或产物，"
                    "接下来将继续执行并优先补齐缺口。"
                )
                reasoning_event = eb.build_reasoning_event(
                    content=recovery_note,
                    turn_id=turn_id,
                    reasoning_live=False,
                    source="completion_verification",
                )
                self._record_event(trace, reasoning_event)
                yield reasoning_event
                pending_prompt = self._build_completion_recovery_prompt(completion)
                append_flag = False
                combined_stop_event = asyncio.Event()
                if stop_event is not None:
                    bridge_task = asyncio.create_task(
                        self._bridge_stop_event(stop_event, combined_stop_event)
                    )

            if blocked_state is not None:
                trace.blocked = blocked_state
                trace.status = "blocked"
                trace.finished_at = _utc_now_iso()
                trace.failure_tags = self._classify_failures(
                    completion=trace.completion_checks[-1] if trace.completion_checks else None,
                    tool_failure_messages=tool_failure_messages,
                    blocked_state=blocked_state,
                )
                yield eb.build_blocked_event(
                    turn_id=turn_id,
                    reason_code=blocked_state.reason_code,
                    message=blocked_state.message,
                    recoverable=blocked_state.recoverable,
                    suggested_action=blocked_state.suggested_action,
                )
                yield eb.build_stopped_event(message=blocked_state.message, turn_id=turn_id)
        finally:
            session.harness_runtime_context = ""
            if bridge_task is not None:
                bridge_task.cancel()
            trace.summary = self._build_trace_summary(trace)
            if trace.finished_at is None:
                trace.finished_at = _utc_now_iso()
                if stop_event is not None and stop_event.is_set():
                    trace.status = "stopped"
                elif trace.status == "completed":
                    trace.status = "error"
            await self._trace_store.save_run(trace)

    @staticmethod
    async def _bridge_stop_event(source: asyncio.Event, target: asyncio.Event) -> None:
        await source.wait()
        target.set()

    @staticmethod
    def _record_event(trace: HarnessTraceRecord, event: AgentEvent) -> None:
        if isinstance(event.data, dict):
            data: dict[str, Any] | str | None = dict(event.data)
        else:
            data = event.data
        trace.events.append(
            HarnessTraceEvent(
                type=event.type.value,
                turn_id=event.turn_id,
                tool_call_id=event.tool_call_id,
                tool_name=event.tool_name,
                data=data,
                metadata=dict(event.metadata),
                timestamp=event.timestamp.isoformat(),
            )
        )

    def _build_run_context(self, session: Session, *, turn_id: str) -> HarnessRunContext:
        datasets = []
        for name, df in session.datasets.items():
            shape = getattr(df, "shape", (None, None))
            rows = int(shape[0]) if shape[0] is not None else None
            columns = int(shape[1]) if shape[1] is not None else None
            datasets.append(HarnessDatasetSummary(name=name, rows=rows, columns=columns))

        artifacts = [
            HarnessArtifactSummary(
                name=str(item.get("name", key)),
                artifact_type=str(item.get("type", "")) or None,
            )
            for key, item in session.artifacts.items()
            if isinstance(item, dict)
        ]

        tool_hints: list[str] = []
        if session.task_manager.has_tasks():
            plan = session.task_manager.to_analysis_plan_dict()
            for step in plan.get("steps", []):
                hint = str(step.get("tool_hint", "") or "").strip()
                if hint and hint not in tool_hints:
                    tool_hints.append(hint)

        constraints = [
            "结束前必须回应用户原始问题并检查未处理失败。",
            "若承诺生成图表或报告，必须先确认产物事件已经出现。",
        ]
        chart_pref = str(getattr(session, "chart_output_preference", "") or "").strip()
        if chart_pref:
            constraints.append(f"图表偏好：{chart_pref}")

        return HarnessRunContext(
            turn_id=turn_id,
            datasets=datasets,
            artifacts=artifacts,
            tool_hints=tool_hints[:6],
            constraints=constraints,
        )

    def _run_completion_check(
        self,
        session: Session,
        *,
        turn_id: str,
        attempt: int,
    ) -> CompletionCheckResult:
        messages = [msg for msg in session.messages if msg.get("turn_id") == turn_id]
        assistant_messages = [
            msg
            for msg in messages
            if msg.get("role") == "assistant"
            and msg.get("event_type") in {None, "text"}
            and str(msg.get("content") or "").strip()
        ]
        final_text = (
            str(assistant_messages[-1].get("content", "")).strip() if assistant_messages else ""
        )

        tool_failures = [
            msg
            for msg in messages
            if msg.get("event_type") == "tool_result" and msg.get("status") == "error"
        ]
        strict_analysis_mode = session.task_manager.has_tasks() or bool(session.datasets)
        artifact_count = sum(
            1
            for msg in messages
            if str(msg.get("event_type", "")) in {"artifact", "image", "chart", "data"}
        )
        promised_artifact = bool(_PROMISED_ARTIFACT_RE.search(final_text))

        items = [
            CompletionCheckItem(
                key="answered_user",
                label="回应原始问题",
                passed=bool(final_text),
                detail="最终回答需直接对应用户最初目标。",
            ),
            CompletionCheckItem(
                key="ignored_tool_failures",
                label="未忽略失败工具",
                passed=(
                    not strict_analysis_mode
                    or not tool_failures
                    or any(
                        token in final_text.lower() for token in ("失败", "报错", "error", "未完成")
                    )
                ),
                detail="若存在失败工具，需先处理或解释失败影响。",
            ),
            CompletionCheckItem(
                key="artifact_generated",
                label="承诺产物已生成",
                passed=(not promised_artifact) or artifact_count > 0,
                detail="若回答声称已生成图表/报告，应先看到对应产物事件。",
            ),
            CompletionCheckItem(
                key="not_transitional",
                label="不是过渡性结尾",
                passed=not bool(_TRANSITIONAL_TEXT_RE.search(final_text)),
                detail="不能只说下一步计划而未真正完成。",
            ),
        ]
        missing_actions = [item.label for item in items if not item.passed]
        return CompletionCheckResult(
            turn_id=turn_id,
            attempt=attempt,
            passed=all(item.passed for item in items),
            items=items,
            missing_actions=missing_actions,
        )

    @staticmethod
    def _build_completion_recovery_prompt(completion: CompletionCheckResult) -> str:
        missing = "；".join(completion.missing_actions) or "补齐完成条件"
        return (
            "请不要结束当前任务。你刚才的结果未通过完成校验，"
            f"需要优先补齐以下缺口：{missing}。"
            "如果已有工具失败，请明确处理或解释；如果缺少产物，请先生成；"
            "如果只是描述下一步，请立即执行对应动作。"
        )

    @staticmethod
    def _handle_tool_result(
        *,
        session: Session,
        event: AgentEvent,
        turn_id: str,
        tool_error_counts: dict[str, int],
        tool_failure_messages: dict[str, str],
        recovered_tool_signatures: set[str],
    ) -> tuple[AgentEvent | None, BlockedState | None]:
        data = event.data if isinstance(event.data, dict) else {}
        status = str(data.get("status", "") or "")
        tool_name = str(event.tool_name or data.get("name", "") or "").strip()
        if not tool_name:
            return None, None
        signature = HarnessRunner._resolve_tool_failure_signature(
            session=session,
            event=event,
            tool_name=tool_name,
            data=data,
        )

        if status == "error":
            tool_error_counts[signature] = tool_error_counts.get(signature, 0) + 1
            tool_failure_messages[signature] = str(data.get("message", "") or "工具执行失败")
        else:
            tool_error_counts[signature] = 0
            tool_failure_messages.pop(signature, None)
            recovered_tool_signatures.discard(signature)
            return None, None

        count = tool_error_counts[signature]
        if count >= 2 and signature in recovered_tool_signatures:
            return None, BlockedState(
                turn_id=turn_id,
                reason_code="tool_loop",
                message=f"工具 `{tool_name}` 连续失败，恢复后仍未推进，当前轮已阻塞。",
                recoverable=True,
                suggested_action="检查参数、切换分析方法，或补充更明确的输入。",
            )
        if count >= 2:
            recovered_tool_signatures.add(signature)
            return (
                eb.build_reasoning_event(
                    content=(
                        f"检测到工具 `{tool_name}` 连续失败，系统将触发一次重规划，"
                        "避免继续重复同一路径。"
                    ),
                    turn_id=turn_id,
                    reasoning_live=False,
                    source="loop_recovery",
                ),
                None,
            )
        return None, None

    @staticmethod
    def _resolve_tool_failure_signature(
        *,
        session: Session,
        event: AgentEvent,
        tool_name: str,
        data: dict[str, Any],
    ) -> str:
        tool_call_id = str(event.tool_call_id or data.get("id", "") or "").strip()
        if tool_call_id:
            for message in reversed(session.messages):
                if message.get("event_type") != "tool_call":
                    continue
                tool_calls = message.get("tool_calls")
                if not isinstance(tool_calls, list):
                    continue
                for tool_call in tool_calls:
                    if (
                        not isinstance(tool_call, dict)
                        or str(tool_call.get("id", "")).strip() != tool_call_id
                    ):
                        continue
                    function_info = tool_call.get("function")
                    if not isinstance(function_info, dict):
                        continue
                    raw_arguments = function_info.get("arguments")
                    if isinstance(raw_arguments, str) and raw_arguments.strip():
                        normalized = raw_arguments.strip()
                        try:
                            parsed = json.loads(raw_arguments)
                            normalized = json.dumps(
                                parsed,
                                ensure_ascii=False,
                                sort_keys=True,
                                default=str,
                            )
                        except Exception:
                            normalized = raw_arguments.strip()
                        return f"{tool_name}::{normalized}"
                    break

        message_hint = str(data.get("message", "") or "").strip()
        return f"{tool_name}::{message_hint or 'unknown'}"

    @staticmethod
    def _classify_failures(
        *,
        completion: CompletionCheckResult | None,
        tool_failure_messages: dict[str, str],
        blocked_state: BlockedState | None,
    ) -> list[str]:
        tags: list[str] = []
        if completion is not None and not completion.passed:
            if any(
                item.key == "ignored_tool_failures" and not item.passed for item in completion.items
            ):
                tags.append("verification_missing")
            if any(
                item.key == "artifact_generated" and not item.passed for item in completion.items
            ):
                tags.append("artifact_missing")
            if any(item.key == "not_transitional" and not item.passed for item in completion.items):
                tags.append("premature_completion")
        if tool_failure_messages:
            tags.append("tool_loop")
        if (
            blocked_state is not None
            and blocked_state.reason_code == "completion_verification_failed"
        ):
            tags.append("verification_missing")
        return sorted(set(tags))

    @staticmethod
    def _build_trace_summary(trace: HarnessTraceRecord) -> dict[str, Any]:
        input_tokens = 0
        output_tokens = 0
        estimated_cost_usd = 0.0
        for event in trace.events:
            if event.type != EventType.TOKEN_USAGE.value:
                continue
            if isinstance(event.data, dict):
                input_tokens += int(event.data.get("input_tokens", 0) or 0)
                output_tokens += int(event.data.get("output_tokens", 0) or 0)
                estimated_cost_usd += float(event.data.get("cost_usd", 0.0) or 0.0)
        return {
            "event_count": len(trace.events),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost_usd": estimated_cost_usd,
        }
