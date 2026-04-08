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
# 压缩记忆中的产物生成记录（如"已生成 6 个产物"、"自动导出了 3 个图表"）
_COMPRESSED_ARTIFACT_RE = re.compile(
    r"已生成\s*\d+\s*个(图表|产物|附件)"
    r"|自动导出\w{0,2}\s*\d+\s*个(图表|产物)"
    r"|(图表|产物|附件).*?已(生成|导出|创建)",
)
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Protocol

from nini.agent import event_builders as eb
from nini.agent.components.context_builder import _extract_intent_hints
from nini.agent.events import AgentEvent, EventType
from nini.agent.prompts.builder import build_system_prompt_with_report
from nini.agent.runner import AgentRunner
from nini.agent.session import Session
from nini.config import settings
from nini.harness.models import (
    BlockedState,
    CompletionEvidence,
    CompletionCheckItem,
    CompletionCheckResult,
    HarnessArtifactSummary,
    HarnessBudgetWarning,
    HarnessDatasetSummary,
    HarnessRunContext,
    HarnessSessionSnapshot,
    HarnessRunSummary,
    HarnessTaskMetrics,
    HarnessTraceEvent,
    HarnessTraceRecord,
    ToolCallEntry,
)
from nini.harness.store import HarnessTraceStore

_TRANSITIONAL_TEXT_RE = re.compile(r"(接下来|下一步|我将|我会继续|我会先|下面将|随后将)")
_USER_CONFIRMATION_RE = re.compile(r"(是否使用|是否采用|需要确认|请确认|是否继续)")
_TIMEOUT_RE = re.compile(r"(超时|timeout)", re.IGNORECASE)


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

        # 新 turn 开始时清理上一轮残留的 turn-scoped pending_actions
        # 这些 pending_action 的 key 与 turn 绑定，新 turn 无法 resolve 旧 key
        session.clear_pending_actions(action_type="artifact_promised_not_materialized")
        session.clear_pending_actions(action_type="user_confirmation_pending")
        session.clear_pending_actions(action_type="task_noop_blocked")
        session.clear_pending_actions(action_type="script_not_run")

        run_id = uuid.uuid4().hex
        run_context = self._build_run_context(session, turn_id=turn_id)
        session.harness_runtime_context = run_context.to_runtime_block()
        task_id = run_context.task_id
        recipe_id = run_context.recipe_id

        trace = HarnessTraceRecord(
            run_id=run_id,
            session_id=session.id,
            turn_id=turn_id,
            user_message=user_message,
            run_context=run_context,
            task_id=task_id,
            recipe_id=recipe_id,
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
        recovery_count = 0
        tool_call_count = 0
        tool_call_sequence: list[ToolCallEntry] = []
        # tool_call_id → 序列索引，用于 TOOL_RESULT 回填状态
        _pending_tool_calls: dict[str, int] = {}
        emitted_budget_levels: set[tuple[str, str]] = set()

        try:
            run_context_event = eb.build_run_context_event(
                turn_id=turn_id,
                datasets=[item.model_dump() for item in run_context.datasets],
                artifacts=[item.model_dump() for item in run_context.artifacts],
                tool_hints=run_context.tool_hints,
                constraints=run_context.constraints,
                task_id=task_id,
                recipe_id=recipe_id,
            )
            while not completed and blocked_state is None:
                iteration_started = False
                run_context_emitted = False
                self._finish_current_stage(trace)
                trace.stage_history.append(
                    {
                        "attempt": completion_attempt + 1,
                        "stage": "verification" if completion_attempt > 0 else "planning",
                        "purpose": "verification" if completion_attempt > 0 else "planning",
                        "reasoning_budget": "high" if completion_attempt >= 0 else "medium",
                        "started_at": _utc_now_iso(),
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
                        error_level = ""
                        if isinstance(event.data, dict):
                            error_level = str(event.data.get("level", "") or "").strip()
                        if error_level == "allowed_tools_soft_violation":
                            yield event
                            continue
                        trace.status = "error"
                        trace.finished_at = _utc_now_iso()
                        yield event
                        completed = True
                        break

                    if event.type == EventType.TOOL_CALL:
                        tool_call_count += 1
                        # 记录工具调用序列条目
                        call_tool_name = str(event.tool_name or "").strip()
                        call_args_hash = ""
                        call_id = ""
                        if isinstance(event.data, dict):
                            call_id = str(event.data.get("id", "") or "").strip()
                            raw_args = event.data.get("arguments", "")
                            if isinstance(raw_args, str) and raw_args.strip():
                                import hashlib

                                call_args_hash = hashlib.md5(raw_args.strip().encode()).hexdigest()[
                                    :8
                                ]
                            elif isinstance(raw_args, dict):
                                import hashlib

                                call_args_hash = hashlib.md5(
                                    json.dumps(raw_args, sort_keys=True).encode()
                                ).hexdigest()[:8]
                        entry = ToolCallEntry(
                            tool_name=call_tool_name,
                            arguments_hash=call_args_hash,
                            result_status="pending",
                            stage=run_context.tool_hints[0] if run_context.tool_hints else "",
                        )
                        seq_idx = len(tool_call_sequence)
                        tool_call_sequence.append(entry)
                        if call_id:
                            _pending_tool_calls[call_id] = seq_idx
                        budget_event = self._build_budget_warning_if_needed(
                            trace=trace,
                            task_id=task_id,
                            recipe_id=recipe_id,
                            metric="tool_calls",
                            current_value=float(tool_call_count),
                            threshold=float(settings.deep_task_budget_tool_call_limit),
                            emitted_levels=emitted_budget_levels,
                            turn_id=turn_id,
                        )
                        if budget_event is not None:
                            yield budget_event

                    if event.type == EventType.TOKEN_USAGE:
                        summary_after_event = self._build_trace_summary(trace)
                        token_total = float(
                            int(summary_after_event.get("input_tokens", 0))
                            + int(summary_after_event.get("output_tokens", 0))
                        )
                        for metric, current_value, threshold in (
                            (
                                "tokens",
                                token_total,
                                float(settings.deep_task_budget_token_limit),
                            ),
                            (
                                "cost_usd",
                                float(summary_after_event.get("estimated_cost_usd", 0.0)),
                                float(settings.deep_task_budget_cost_limit_usd),
                            ),
                        ):
                            budget_event = self._build_budget_warning_if_needed(
                                trace=trace,
                                task_id=task_id,
                                recipe_id=recipe_id,
                                metric=metric,
                                current_value=current_value,
                                threshold=threshold,
                                emitted_levels=emitted_budget_levels,
                                turn_id=turn_id,
                            )
                            if budget_event is not None:
                                yield budget_event

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
                        # 回填工具调用结果状态
                        result_data = event.data if isinstance(event.data, dict) else {}
                        result_call_id = str(
                            event.tool_call_id or result_data.get("id", "") or ""
                        ).strip()
                        result_status = str(result_data.get("status", "success") or "success")
                        if result_call_id and result_call_id in _pending_tool_calls:
                            idx = _pending_tool_calls.pop(result_call_id)
                            if idx < len(tool_call_sequence):
                                tool_call_sequence[idx] = tool_call_sequence[idx].model_copy(
                                    update={"result_status": result_status}
                                )
                        recovery_event, blocked_state = self._handle_tool_result(
                            session=session,
                            event=event,
                            turn_id=turn_id,
                            task_id=task_id,
                            attempt_id=self._current_attempt_id(session, task_id),
                            tool_error_counts=tool_error_counts,
                            tool_failure_messages=tool_failure_messages,
                            recovered_tool_signatures=recovered_tool_signatures,
                        )
                        if recovery_event is not None:
                            recovery_count += 1
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
                    task_id=task_id,
                )

                if completion.passed:
                    # 完成校验通过时，自动完成所有剩余任务（pending 或 in_progress）
                    # 确保 snapshot 反映正确的任务终态
                    if (
                        session.task_manager.has_tasks()
                        and session.task_manager.remaining_count() > 0
                    ):
                        force_updates = [
                            {"id": t.id, "status": "completed"}
                            for t in session.task_manager.tasks
                            if t.status in ("pending", "in_progress")
                        ]
                        if force_updates:
                            force_result = session.task_manager.update_tasks(force_updates)
                            session.task_manager = force_result.manager
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
                        task_id=task_id,
                        attempt_id=self._current_attempt_id(session, task_id),
                        suggested_action="补充缺失分析、处理失败工具或调整问题范围后重试。",
                    )
                    break

                recovery_count += 1
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
                pending_prompt = self._build_completion_recovery_prompt(
                    completion,
                    remaining_tasks=session.task_manager.remaining_count(),
                    recipe_mode=bool(session.recipe_id),
                )
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
                blocked_message = self._build_blocked_final_message(
                    session=session,
                    blocked_state=blocked_state,
                    completion=trace.completion_checks[-1] if trace.completion_checks else None,
                )
                if blocked_message:
                    session.add_message("assistant", blocked_message, turn_id=turn_id)
                    blocked_text_event = eb.build_text_event(
                        blocked_message,
                        turn_id=turn_id,
                        source="harness_blocked",
                    )
                    self._record_event(trace, blocked_text_event)
                    yield blocked_text_event
                yield eb.build_blocked_event(
                    turn_id=turn_id,
                    reason_code=blocked_state.reason_code,
                    message=blocked_state.message,
                    recoverable=blocked_state.recoverable,
                    task_id=blocked_state.task_id,
                    attempt_id=blocked_state.attempt_id,
                    suggested_action=blocked_state.suggested_action,
                )
                yield eb.build_stopped_event(message=blocked_state.message, turn_id=turn_id)
        finally:
            session.harness_runtime_context = ""
            if bridge_task is not None:
                bridge_task.cancel()
            self._finish_current_stage(trace)
            trace.summary = self._build_trace_summary(trace)
            trace.summary["prompt_audit"] = self._build_prompt_audit(
                session=session,
                user_message=user_message,
            )
            if trace.finished_at is None:
                trace.finished_at = _utc_now_iso()
                if stop_event is not None and stop_event.is_set():
                    trace.status = "stopped"
                elif trace.status == "completed":
                    trace.status = "error"
            trace.task_metrics = self._build_task_metrics(
                trace,
                recovery_count=recovery_count,
                tool_call_count=tool_call_count,
                tool_call_sequence=tool_call_sequence,
            )
            runtime_snapshot = self._build_runtime_snapshot(
                session=session,
                trace=trace,
            )
            trace.summary["runtime_snapshot"] = runtime_snapshot.model_dump(mode="json")
            await self._trace_store.save_run(trace)

    @staticmethod
    async def _bridge_stop_event(source: asyncio.Event, target: asyncio.Event) -> None:
        await source.wait()
        target.set()

    @staticmethod
    def _record_event(trace: HarnessTraceRecord, event: AgentEvent) -> None:
        if isinstance(event.data, dict):
            data: dict[str, Any] | str | None = _sanitize_event_data(event.data)
        else:
            data = event.data
        trace.events.append(
            HarnessTraceEvent(
                type=event.type.value,
                turn_id=event.turn_id,
                tool_call_id=event.tool_call_id,
                tool_name=event.tool_name,
                data=data,
                metadata=(
                    _sanitize_event_data(event.metadata)
                    if isinstance(event.metadata, dict)
                    else event.metadata
                ),
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

        task_id = str(session.deep_task_state.get("task_id", "")).strip() or None
        recipe_id = str(session.recipe_id or "").strip() or None

        return HarnessRunContext(
            turn_id=turn_id,
            datasets=datasets,
            artifacts=artifacts,
            tool_hints=tool_hints[:6],
            constraints=constraints,
            task_id=task_id,
            recipe_id=recipe_id,
        )

    @staticmethod
    def _build_prompt_audit(session: Session, user_message: str) -> dict[str, Any]:
        """记录本轮系统提示词是否发生预算截断。"""
        context_window = getattr(session, "_model_context_window", None)
        intent_hints = _extract_intent_hints(user_message, None)
        _, report = build_system_prompt_with_report(
            context_window=context_window,
            intent_hints=intent_hints,
        )
        return {
            "profile": report.profile,
            "truncated": report.truncated,
            "total_tokens_before": report.total_tokens_before,
            "total_tokens_after": report.total_tokens_after,
            "token_budget": report.token_budget,
        }

    def _run_completion_check(
        self,
        session: Session,
        *,
        turn_id: str,
        attempt: int,
    ) -> CompletionCheckResult:
        evidence = self._build_completion_evidence(session, turn_id=turn_id)
        strict_analysis_mode = session.task_manager.has_tasks() or bool(session.datasets)
        unresolved_pending_actions = evidence.blocking_pending_actions
        all_tasks_completed = (
            not session.task_manager.has_tasks()
            or session.task_manager.all_completed()
            or (
                session.task_manager.pending_count() == 0
                and session.task_manager.remaining_count() == 1
                and self._has_substantive_final_text(evidence.final_text)
            )
        )
        substantive_final_text = self._has_substantive_final_text(evidence.final_text)

        items = [
            CompletionCheckItem(
                key="answered_user",
                label="回应原始问题",
                passed=bool(evidence.final_text),
                detail="最终回答需直接对应用户最初目标。",
            ),
            CompletionCheckItem(
                key="ignored_tool_failures",
                label="未忽略失败工具",
                passed=(
                    not strict_analysis_mode
                    or not evidence.unresolved_tool_failures
                    or any(
                        token in evidence.final_text.lower()
                        for token in ("失败", "报错", "error", "未完成", "超时")
                    )
                ),
                detail="若存在失败工具，需先处理或解释失败影响。",
            ),
            CompletionCheckItem(
                key="artifact_generated",
                label="承诺产物已生成",
                passed=not evidence.promised_artifact_missing,
                detail="若回答声称已生成图表/报告，应先看到对应产物事件。",
            ),
            CompletionCheckItem(
                key="not_transitional",
                label="不是过渡性结尾",
                passed=(
                    not evidence.transitional_output
                    or (all_tasks_completed and substantive_final_text)
                ),
                detail="不能只说下一步计划而未真正完成。",
            ),
            CompletionCheckItem(
                key="all_tasks_completed",
                label="所有任务已完成",
                passed=all_tasks_completed,
                detail="若存在未完成任务，需先完成或明确说明无法完成的原因。",
            ),
            CompletionCheckItem(
                key="pending_actions_resolved",
                label="没有未解决待处理动作",
                passed=(not strict_analysis_mode) or not unresolved_pending_actions,
                detail="待处理动作未清空时，不应直接结束当前轮。",
            ),
        ]
        missing_actions = [item.label for item in items if not item.passed]
        return CompletionCheckResult(
            turn_id=turn_id,
            attempt=attempt,
            passed=all(item.passed for item in items),
            items=items,
            missing_actions=missing_actions,
            evidence=evidence.model_dump(mode="json"),
        )

    @staticmethod
    def _has_substantive_final_text(final_text: str) -> bool:
        """判断最终文本是否已包含足够实质内容，而非一句过渡话术。"""
        normalized = str(final_text or "").strip()
        if len(normalized) >= 400:
            return True
        markers = ("## ", "### ", "|", "结论", "建议", "主要发现", "下一步建议")
        return sum(1 for marker in markers if marker in normalized) >= 2

    def _build_completion_evidence(
        self,
        session: Session,
        *,
        turn_id: str,
    ) -> CompletionEvidence:
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
        unresolved_tool_failures = [
            str(msg.get("content") or msg.get("message") or "工具执行失败").strip()
            for msg in messages
            if msg.get("event_type") == "tool_result" and msg.get("status") == "error"
        ]
        artifact_count = sum(
            1
            for msg in messages
            if str(msg.get("event_type", "")) in {"artifact", "image", "chart", "data"}
        )
        # 补充检测：code_session 通过 matplotlib 等生成的图表不会产生 artifact 事件，
        # 但工具结果中可能包含图表相关输出，应纳入统计避免误判为"产物未物化"
        _CHART_OUTPUT_KEYWORDS = (
            "savefig",
            "plt.show",
            "图表已保存",
            "chart_",
            "已导出",
            "自动导出",
            "图表产物",
        )
        code_chart_count = sum(
            1
            for msg in messages
            if str(msg.get("tool_name", "")) == "code_session"
            and any(kw in str(msg.get("content", "")) for kw in _CHART_OUTPUT_KEYWORDS)
        )
        artifact_count += code_chart_count
        promised_artifact_missing = (
            bool(_PROMISED_ARTIFACT_RE.search(final_text)) and artifact_count == 0
        )
        # 正则匹配但当前 turn 无产物事件时，验证产物是否已存在于工作区或压缩记忆中
        if promised_artifact_missing:
            # 第一层：检查工作区实际产物文件（最可靠）
            from nini.workspace.manager import WorkspaceManager

            ws = WorkspaceManager(session.id)
            if ws.list_artifacts():
                promised_artifact_missing = False
            # 第二层：检查压缩记忆中的产物生成记录
            elif session.compressed_context and _COMPRESSED_ARTIFACT_RE.search(
                session.compressed_context
            ):
                promised_artifact_missing = False
        user_confirmation_pending = bool(_USER_CONFIRMATION_RE.search(final_text))
        transitional_output = bool(_TRANSITIONAL_TEXT_RE.search(final_text)) and (
            not self._has_substantive_final_text(final_text)
        )

        if promised_artifact_missing:
            session.upsert_pending_action(
                action_type="artifact_promised_not_materialized",
                key=f"{turn_id}:artifact",
                status="pending",
                summary="回答承诺了图表、报告或附件，但当前轮未看到对应产物事件。",
                source_tool="completion_verifier",
                metadata={"turn_id": turn_id},
            )
        else:
            session.resolve_pending_action(
                action_type="artifact_promised_not_materialized",
                key=f"{turn_id}:artifact",
            )

        if user_confirmation_pending:
            session.upsert_pending_action(
                action_type="user_confirmation_pending",
                key=f"{turn_id}:confirmation",
                status="pending",
                summary="当前轮仍在等待用户确认后才能继续完成后续动作。",
                source_tool="completion_verifier",
                metadata={"turn_id": turn_id},
            )
        else:
            session.resolve_pending_action(
                action_type="user_confirmation_pending",
                key=f"{turn_id}:confirmation",
            )

        if transitional_output:
            session.upsert_pending_action(
                action_type="task_noop_blocked",
                key=f"{turn_id}:transitional",
                status="pending",
                summary="当前轮只描述了下一步计划，但尚未真正执行对应动作。",
                source_tool="completion_verifier",
                metadata={"turn_id": turn_id},
            )
        else:
            session.resolve_pending_action(
                action_type="task_noop_blocked",
                key=f"{turn_id}:transitional",
            )

        if any(token in final_text for token in ("失败", "报错", "error", "替代方案", "改用")):
            for item in session.list_pending_actions(action_type="tool_failure_unresolved"):
                metadata = item.get("metadata", {})
                if (
                    isinstance(metadata, dict)
                    and str(metadata.get("turn_id", "")).strip() == turn_id
                ):
                    session.resolve_pending_action(
                        action_type="tool_failure_unresolved",
                        key=str(item.get("key", "")).strip(),
                    )

        total_tasks = len(session.task_manager.tasks)
        remaining_tasks = (
            session.task_manager.remaining_count() if session.task_manager.has_tasks() else 0
        )
        task_completion_ratio = 1.0
        if total_tasks > 0:
            task_completion_ratio = max(
                0.0, min(1.0, (total_tasks - remaining_tasks) / total_tasks)
            )
        pending_actions = session.list_pending_actions(status="pending")

        # 兜底清理：所有任务完成时，自动清理残留的工具失败记录和脚本未执行记录
        # 理由：如果任务已全部完成，之前的失败已通过其他路径被克服，
        # 残留的失败记录不应阻塞会话结束
        if remaining_tasks == 0 and total_tasks > 0:
            session.clear_pending_actions(action_type="tool_failure_unresolved")
            session.clear_pending_actions(action_type="script_not_run")
            session.clear_pending_actions(action_type="artifact_promised_not_materialized")
            session.clear_pending_actions(action_type="task_noop_blocked")
            pending_actions = session.list_pending_actions(status="pending")

        blocking_pending_actions = [
            dict(item) for item in pending_actions if bool(item.get("blocking", True))
        ]

        return CompletionEvidence(
            turn_id=turn_id,
            final_text=final_text,
            unresolved_tool_failures=unresolved_tool_failures,
            promised_artifact_missing=promised_artifact_missing,
            user_confirmation_pending=user_confirmation_pending,
            transitional_output=transitional_output,
            pending_actions=pending_actions,
            blocking_pending_actions=blocking_pending_actions,
            remaining_tasks=remaining_tasks,
            task_completion_ratio=task_completion_ratio,
        )

    @staticmethod
    def _build_completion_recovery_prompt(
        completion: CompletionCheckResult,
        *,
        remaining_tasks: int = 0,
        recipe_mode: bool = False,
    ) -> str:
        missing = "；".join(completion.missing_actions) or "补齐完成条件"
        evidence = completion.evidence if isinstance(completion.evidence, dict) else {}
        raw_evidence_pending = evidence.get(
            "blocking_pending_actions", evidence.get("pending_actions", [])
        )
        evidence_pending = raw_evidence_pending if isinstance(raw_evidence_pending, list) else []
        followups: list[str] = []
        if any(
            isinstance(item, dict) and item.get("type") == "script_not_run"
            for item in evidence_pending
        ):
            followups.append("优先继续执行已创建但未成功运行的脚本。")
        if any(
            isinstance(item, dict) and item.get("type") == "artifact_promised_not_materialized"
            for item in evidence_pending
        ):
            followups.append("先生成刚才承诺的图表/报告/附件，或明确说明未生成的影响。")
        if any(
            isinstance(item, dict) and item.get("type") == "user_confirmation_pending"
            for item in evidence_pending
        ):
            followups.append("当前仍缺少用户确认，先发起确认或说明为何无法继续。")
        if recipe_mode:
            followups.append(
                "当前处于 Recipe 模式，不能停在继续向用户追问。若信息不足，请基于已提供输入、Recipe 默认字段和保守常见默认值继续完成，并在结果中显式列出假设。"
            )
        timeout_actions = [
            item
            for item in evidence_pending
            if isinstance(item, dict)
            and item.get("type") == "tool_failure_unresolved"
            and isinstance(item.get("metadata"), dict)
            and item["metadata"].get("failure_kind") == "timeout"
        ]
        for item in timeout_actions[:2]:
            metadata = item.get("metadata") if isinstance(item, dict) else {}
            purpose = str(metadata.get("purpose", "")).strip() if isinstance(metadata, dict) else ""
            if purpose:
                followups.append(f"处理 `{purpose}` 相关超时，选择更短路径重试或先解释其影响。")
            else:
                followups.append("存在超时失败，先重试可恢复步骤或解释超时对结论的影响。")
        prefix = ""
        if remaining_tasks > 0:
            prefix = f"还有 {remaining_tasks} 个任务尚未完成，请继续执行。"
        return (
            f"{prefix}请不要结束当前任务。你刚才的结果未通过完成校验，"
            f"需要优先补齐以下缺口：{missing}。"
            "如果已有工具失败，请明确处理或解释；如果缺少产物，请先生成；"
            "如果只是描述下一步，请立即执行对应动作。" + (" ".join(followups) if followups else "")
        )

    @staticmethod
    def _build_blocked_final_message(
        *,
        session: Session,
        blocked_state: BlockedState,
        completion: CompletionCheckResult | None,
    ) -> str:
        lines = [f"当前轮分析已暂停：{blocked_state.message}"]

        if completion and completion.missing_actions:
            lines.append(f"未满足的完成条件：{'；'.join(completion.missing_actions)}。")

        remaining_tasks = [
            task.title
            for task in session.task_manager.tasks
            if task.status in {"pending", "in_progress"}
        ]
        if remaining_tasks:
            lines.append("仍未完成的任务：")
            lines.extend(f"- {title}" for title in remaining_tasks)

        if blocked_state.suggested_action:
            lines.append(f"建议下一步：{blocked_state.suggested_action}")

        return "\n".join(lines).strip()

    @staticmethod
    def _handle_tool_result(
        *,
        session: Session,
        event: AgentEvent,
        turn_id: str,
        task_id: str | None,
        attempt_id: str | None,
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
            metadata: dict[str, Any] = {"turn_id": turn_id}
            failure_message = str(data.get("message", "") or "工具执行失败")
            failure_category, blocking = HarnessRunner._classify_tool_failure(
                tool_name=tool_name,
                message=failure_message,
                data=data,
            )
            if _TIMEOUT_RE.search(failure_message):
                metadata["failure_kind"] = "timeout"
                metadata["purpose"] = HarnessRunner._infer_timeout_purpose(
                    tool_name=tool_name, data=data
                )
            # 保存 recovery_hint，供 pending_actions 摘要和压缩后恢复使用
            result_payload = data.get("result") if isinstance(data.get("result"), dict) else None
            if result_payload:
                rh = str(result_payload.get("recovery_hint", "")).strip()[:200]
                if rh:
                    metadata["recovery_hint"] = rh
            elif isinstance(data.get("data"), dict):
                rh = str(data["data"].get("recovery_hint", "")).strip()[:200]
                if rh:
                    metadata["recovery_hint"] = rh
            session.upsert_pending_action(
                action_type="tool_failure_unresolved",
                key=signature,
                status="pending",
                summary=f"{tool_name} 失败：{failure_message}",
                source_tool=tool_name,
                blocking=blocking,
                failure_category=failure_category,
                metadata=metadata,
            )
        else:
            tool_error_counts[signature] = 0
            tool_failure_messages.pop(signature, None)
            recovered_tool_signatures.discard(signature)
            session.resolve_pending_action(action_type="tool_failure_unresolved", key=signature)
            for item in session.list_pending_actions(action_type="tool_failure_unresolved"):
                item_metadata = item.get("metadata")
                if not isinstance(item_metadata, dict):
                    continue
                if (
                    str(item.get("source_tool", "")).strip() == tool_name
                    and str(item_metadata.get("turn_id", "")).strip() == turn_id
                ):
                    session.resolve_pending_action(
                        action_type="tool_failure_unresolved",
                        key=str(item.get("key", "")).strip(),
                    )
            return None, None

        count = tool_error_counts[signature]
        if count >= 2 and signature in recovered_tool_signatures:
            return None, BlockedState(
                turn_id=turn_id,
                reason_code="tool_loop",
                message=f"工具 `{tool_name}` 连续失败，恢复后仍未推进，当前轮已阻塞。",
                recoverable=True,
                task_id=task_id,
                attempt_id=attempt_id,
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
    def _classify_tool_failure(
        *,
        tool_name: str,
        message: str,
        data: dict[str, Any],
    ) -> tuple[str, bool]:
        """返回失败分类与是否阻塞。"""
        normalized_message = str(message or "").strip()
        payload = data.get("data") if isinstance(data.get("data"), dict) else {}
        if tool_name in {"task_state", "task_write"}:
            result_payload = data.get("result")
            result_data = result_payload.get("data", {}) if isinstance(result_payload, dict) else {}
            no_op_ids = result_data.get("no_op_ids") if isinstance(result_data, dict) else None
            error_code = result_data.get("error_code") if isinstance(result_data, dict) else None
            if isinstance(no_op_ids, list) and no_op_ids:
                return "idempotent_conflict", False
            if (
                "任务列表已初始化且" in normalized_message
                and "无法重新初始化" in normalized_message
            ):
                return "idempotent_conflict", False
            if "无需重复设置" in normalized_message:
                return "idempotent_conflict", False
            if (
                isinstance(error_code, str)
                and error_code.startswith(("TASK_STATE_", "TASK_WRITE_"))
            ) or ("初始状态必须为 pending" in normalized_message):
                return "recoverable_input_misuse", False
        if tool_name == "workspace_session":
            error_code = str(payload.get("error_code", "")).strip()
            if error_code == "WORKSPACE_READ_BINARY_UNSUPPORTED":
                return "recoverable_input_misuse", False
        # 通用幂等/重复操作识别：DUPLICATE_* 和 ALREADY_* 前缀的 error_code
        # 表示操作已成功完成过，重复调用不是真正的失败
        # error_code 可能出现在多个层级：
        #   data.error_code（顶层）
        #   data.data.error_code（data 字段内）
        #   data.result.error_code（result 字段内）
        #   data.data.result.error_code（data 内的 result 字段）
        _error_code_candidates = [
            str(payload.get("error_code", "")).strip(),
            str(data.get("error_code", "")).strip(),
        ]
        result_payload = data.get("result") if isinstance(data.get("result"), dict) else None
        if result_payload:
            _error_code_candidates.append(str(result_payload.get("error_code", "")).strip())
        nested_result = payload.get("result") if isinstance(payload.get("result"), dict) else None
        if nested_result:
            _error_code_candidates.append(str(nested_result.get("error_code", "")).strip())
        generic_error_code = next((c for c in _error_code_candidates if c), "")
        if generic_error_code.startswith("DUPLICATE_") or generic_error_code.startswith("ALREADY_"):
            return "idempotent_conflict", False
        # Agent runner 的熔断错误：由于重复调用被阻止而触发的熔断，本质上也是幂等冲突
        if generic_error_code == "TOOL_CALL_CIRCUIT_BREAKER":
            return "idempotent_conflict", False
        return "blocking_failure", True

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

    @staticmethod
    def _infer_timeout_purpose(*, tool_name: str, data: dict[str, Any]) -> str:
        if tool_name == "code_session":
            result = data.get("result")
            if isinstance(result, dict):
                result_data = result.get("data")
                if isinstance(result_data, dict):
                    return str(result_data.get("purpose", "") or "").strip() or "analysis"
            return "analysis"
        if tool_name in {"export_report", "export_document", "report_session"}:
            return "export"
        if tool_name in {"chart_session", "export_chart"}:
            return "visualization"
        return "analysis"

    @staticmethod
    def _build_runtime_snapshot(
        *,
        session: Session,
        trace: HarnessTraceRecord,
    ) -> HarnessSessionSnapshot:
        selected_tools: list[str] = []
        for event in trace.events:
            if event.type != EventType.TOOL_CALL.value or not event.tool_name:
                continue
            tool_name = str(event.tool_name).strip()
            if tool_name and tool_name not in selected_tools:
                selected_tools.append(tool_name)

        pending_tasks = [
            task.title
            for task in session.task_manager.tasks
            if task.status in {"pending", "in_progress"}
        ]
        return HarnessSessionSnapshot(
            session_id=session.id,
            turn_id=trace.turn_id,
            run_id=trace.run_id,
            stop_reason=trace.blocked.reason_code if trace.blocked else trace.status,
            pending_actions=session.list_pending_actions(status="pending"),
            task_progress={
                "total": len(session.task_manager.tasks),
                "remaining": (
                    session.task_manager.remaining_count()
                    if session.task_manager.has_tasks()
                    else 0
                ),
                "pending_titles": pending_tasks[:10],
            },
            tool_failures=list(trace.failure_tags),
            selected_tools=selected_tools,
            compressed_rounds=int(session.compressed_rounds),
            token_usage={
                "input_tokens": int(trace.summary.get("input_tokens", 0) or 0),
                "output_tokens": int(trace.summary.get("output_tokens", 0) or 0),
                "estimated_cost_usd": float(trace.summary.get("estimated_cost_usd", 0.0) or 0.0),
            },
            trace_ref=trace.summary.get("trace_path") if isinstance(trace.summary, dict) else None,
        )

    @staticmethod
    def _current_attempt_id(session: Session, task_id: str | None) -> str | None:
        current_attempt_id = str(session.deep_task_state.get("current_attempt_id", "")).strip()
        if current_attempt_id:
            return current_attempt_id
        if not task_id:
            return None
        retry_count = int(session.deep_task_state.get("retry_count", 0) or 0)
        return f"{task_id}:workflow:{retry_count + 1}"

    @staticmethod
    def _finish_current_stage(trace: HarnessTraceRecord) -> None:
        if not trace.stage_history:
            return
        current = trace.stage_history[-1]
        if "ended_at" not in current:
            current["ended_at"] = _utc_now_iso()

    def _build_budget_warning_if_needed(
        self,
        *,
        trace: HarnessTraceRecord,
        task_id: str | None,
        recipe_id: str | None,
        metric: str,
        current_value: float,
        threshold: float,
        emitted_levels: set[tuple[str, str]],
        turn_id: str,
    ) -> AgentEvent | None:
        if not task_id or threshold <= 0 or current_value < threshold:
            return None
        warning_level = "critical" if current_value >= threshold * 1.5 else "warning"
        dedup_key = (metric, warning_level)
        if dedup_key in emitted_levels:
            return None
        emitted_levels.add(dedup_key)
        warning = HarnessBudgetWarning(
            task_id=task_id,
            metric=metric,  # type: ignore[arg-type]
            threshold=threshold,
            current_value=current_value,
            warning_level=warning_level,  # type: ignore[arg-type]
            message=f"deep task 预算接近或超过阈值：{metric}={current_value:.2f}，阈值={threshold:.2f}",
            recipe_id=recipe_id,
        )
        trace.budget_warnings.append(warning)
        event = eb.build_budget_warning_event(
            task_id=warning.task_id,
            metric=warning.metric,
            threshold=warning.threshold,
            current_value=warning.current_value,
            warning_level=warning.warning_level,
            message=warning.message,
            recipe_id=warning.recipe_id,
            turn_id=turn_id,
        )
        self._record_event(trace, event)
        return event

    @staticmethod
    def _build_task_metrics(
        trace: HarnessTraceRecord,
        *,
        recovery_count: int,
        tool_call_count: int,
        tool_call_sequence: list[ToolCallEntry] | None = None,
    ) -> HarnessTaskMetrics:
        step_durations_ms: dict[str, int] = {}
        for item in trace.stage_history:
            stage = str(item.get("stage", "")).strip() or "unknown"
            started_at = str(item.get("started_at", "")).strip()
            ended_at = str(item.get("ended_at", "")).strip()
            if not started_at or not ended_at:
                continue
            try:
                duration_ms = max(
                    0,
                    int(
                        (
                            datetime.fromisoformat(ended_at) - datetime.fromisoformat(started_at)
                        ).total_seconds()
                        * 1000
                    ),
                )
            except ValueError:
                continue
            step_durations_ms[stage] = step_durations_ms.get(stage, 0) + duration_ms

        return HarnessTaskMetrics(
            task_id=trace.task_id,
            recipe_id=trace.recipe_id,
            final_status=trace.status,
            total_duration_ms=(
                max(
                    0,
                    int(
                        (
                            datetime.fromisoformat(trace.finished_at)
                            - datetime.fromisoformat(trace.started_at)
                        ).total_seconds()
                        * 1000
                    ),
                )
                if trace.finished_at
                else 0
            ),
            step_durations_ms=step_durations_ms,
            recovery_count=recovery_count,
            tool_call_count=tool_call_count,
            tool_call_sequence=list(tool_call_sequence or []),
            failure_types=list(trace.failure_tags),
            budget_warnings=[item.model_copy(deep=True) for item in trace.budget_warnings],
        )


def _sanitize_event_data(data: dict[str, Any] | str | None) -> dict[str, Any] | str | None:
    """深度清洗事件数据，将 pandas 等非标准类型转为 Python 原生类型。"""
    if not isinstance(data, dict):
        return data
    return {_sanitize_value(k): _sanitize_value(v) for k, v in data.items()}


def _sanitize_value(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return {_sanitize_value(k): _sanitize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    return value
