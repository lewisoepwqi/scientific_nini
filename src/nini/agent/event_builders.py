"""WebSocket 事件构造器 —— 使用严格的 Pydantic 模型确保数据契约。

此模块提供类型安全的事件构造函数，确保后端发送的事件数据
与前端的期望完全一致。
"""

from __future__ import annotations

import json
from typing import Any

from nini.agent._event_builder_helpers import _make_agent_event, _make_event
from nini.agent.events import AgentEvent, EventType
from nini.models.event_schemas import (
    AnalysisPlanEventData,
    AnalysisPlanStep,
    PlanProgressEventData,
    PlanStepUpdateEventData,
    TaskAttemptEventData,
    RunContextEventData,
    RunContextDatasetSummary,
    RunContextArtifactSummary,
    CompletionCheckEventData,
    CompletionCheckItemEventData,
    BlockedEventData,
    BudgetWarningEventData,
    TokenUsageEventData,
    ModelFallbackEventData,
    SessionTokenUsageEventData,
    ModelTokenUsageDetail,
    ToolCallEventData,
    ToolResultEventData,
    AgentStartEventData,
    AgentProgressEventData,
    AgentCompleteEventData,
    AgentErrorEventData,
    AgentStoppedEventData,
    TextEventData,
    ErrorEventData,
    DoneEventData,
    SessionEventData,
    SessionTitleEventData,
    WorkspaceUpdateEventData,
    CodeExecutionEventData,
    StoppedEventData,
    IterationStartEventData,
    RetrievalEventData,
    ReasoningEventData,
    ReasoningDataEventData,
    AskUserQuestionEventData,
    ArtifactEventData,
    ChartEventData,
    DataEventData,
    ImageEventData,
    ContextCompressedEventData,
)


def build_analysis_plan_event(
    steps: list[dict[str, Any]],
    raw_text: str = "",
    *,
    turn_id: str | None = None,
    seq: int | None = None,
    **extra,
) -> AgentEvent:
    """构造 ANALYSIS_PLAN 事件。

    Args:
        steps: 步骤列表，每项包含 id, title, tool_hint, status, action_id 等
        raw_text: 原始文本内容
        turn_id: 回合 ID，用于前端消息分组
        seq: 事件序号，用于前端乱序保护
        **extra: 额外字段（会被合并到数据中）

    Returns:
        AgentEvent: 类型安全的事件对象
    """
    # 使用 Pydantic 模型验证数据
    step_objects = []
    for step in steps:
        step_objects.append(
            AnalysisPlanStep(
                id=step.get("id", 0),
                title=step.get("title", ""),
                tool_hint=step.get("tool_hint"),
                status=step.get("status", "pending"),
                action_id=step.get("action_id"),
                raw_status=step.get("raw_status"),
                depends_on=list(step.get("depends_on") or []),
                executor=step.get("executor"),
                owner=step.get("owner"),
                input_refs=list(step.get("input_refs") or []),
                output_refs=list(step.get("output_refs") or []),
                handoff_contract=step.get("handoff_contract"),
                tool_profile=step.get("tool_profile"),
                failure_policy=step.get("failure_policy"),
                acceptance_checks=list(step.get("acceptance_checks") or []),
            )
        )

    event_data = AnalysisPlanEventData(
        steps=step_objects,
        raw_text=raw_text,
    )

    data = event_data.model_dump()
    data.update(extra)  # 合并额外字段

    metadata: dict[str, Any] = {}
    if seq is not None:
        metadata["seq"] = seq

    return AgentEvent(
        type=EventType.ANALYSIS_PLAN,
        data=data,
        turn_id=turn_id,
        metadata=metadata,
    )


def build_plan_step_update_event(
    step_id: int,
    status: str,
    error: str | None = None,
    *,
    turn_id: str | None = None,
    seq: int | None = None,
    **extra,
) -> AgentEvent:
    """构造 PLAN_STEP_UPDATE 事件。"""
    return _make_event(
        EventType.PLAN_STEP_UPDATE,
        PlanStepUpdateEventData(id=step_id, status=status, error=error),
        turn_id,
        seq,
        extra or None,
    )


def build_plan_progress_event(
    steps: list[dict[str, Any]],
    current_step_index: int,
    total_steps: int,
    step_title: str,
    step_status: str,
    next_hint: str | None = None,
    block_reason: str | None = None,
    *,
    turn_id: str | None = None,
    seq: int | None = None,
    **extra,
) -> AgentEvent:
    """构造 PLAN_PROGRESS 事件。"""
    step_objects = [
        AnalysisPlanStep(
            id=s.get("id", 0),
            title=s.get("title", ""),
            tool_hint=s.get("tool_hint"),
            status=s.get("status", "pending"),
            action_id=s.get("action_id"),
            raw_status=s.get("raw_status"),
            depends_on=list(s.get("depends_on") or []),
            executor=s.get("executor"),
            owner=s.get("owner"),
            input_refs=list(s.get("input_refs") or []),
            output_refs=list(s.get("output_refs") or []),
            handoff_contract=s.get("handoff_contract"),
            tool_profile=s.get("tool_profile"),
            failure_policy=s.get("failure_policy"),
            acceptance_checks=list(s.get("acceptance_checks") or []),
        )
        for s in steps
    ]

    event_data = PlanProgressEventData(
        steps=step_objects,
        current_step_index=current_step_index,
        total_steps=total_steps,
        step_title=step_title,
        step_status=step_status,
        next_hint=next_hint,
        block_reason=block_reason,
        recipe_id=None,
        task_id=None,
        task_kind=None,
        retry_count=None,
    )

    data = event_data.model_dump()
    data.update(extra)

    metadata: dict[str, Any] = {}
    if seq is not None:
        metadata["seq"] = seq

    return AgentEvent(
        type=EventType.PLAN_PROGRESS,
        data=data,
        turn_id=turn_id,
        metadata=metadata,
    )


def build_task_attempt_event(
    action_id: str | None,
    step_id: int | None,
    tool_name: str,
    attempt: int,
    max_attempts: int,
    status: str,
    note: str | None = None,
    error: str | None = None,
    *,
    turn_id: str | None = None,
    seq: int | None = None,
    **extra,
) -> AgentEvent:
    """构造 TASK_ATTEMPT 事件。"""
    return _make_event(
        EventType.TASK_ATTEMPT,
        TaskAttemptEventData(
            action_id=action_id or "",
            step_id=step_id or 0,
            tool_name=tool_name,
            attempt=attempt,
            max_attempts=max_attempts,
            status=status,  # type: ignore[arg-type]
            task_id=None,
            attempt_id=None,
            note=note,
            error=error,
        ),
        turn_id,
        seq,
        extra or None,
    )


def build_run_context_event(
    *,
    turn_id: str,
    datasets: list[dict[str, Any]] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
    tool_hints: list[str] | None = None,
    constraints: list[str] | None = None,
    **extra,
) -> AgentEvent:
    """构造 RUN_CONTEXT 事件。"""
    event_data = RunContextEventData(
        turn_id=turn_id,
        datasets=[
            RunContextDatasetSummary(
                name=str(item.get("name", "")),
                rows=item.get("rows"),
                columns=item.get("columns"),
            )
            for item in (datasets or [])
        ],
        artifacts=[
            RunContextArtifactSummary(
                name=str(item.get("name", "")),
                artifact_type=item.get("artifact_type"),
            )
            for item in (artifacts or [])
        ],
        tool_hints=[str(item) for item in (tool_hints or []) if str(item).strip()],
        constraints=[str(item) for item in (constraints or []) if str(item).strip()],
        task_id=None,
        recipe_id=None,
    )

    data = event_data.model_dump()
    data.update(extra)

    return AgentEvent(
        type=EventType.RUN_CONTEXT,
        data=data,
        turn_id=turn_id,
    )


def build_completion_check_event(
    *,
    turn_id: str,
    passed: bool,
    attempt: int,
    items: list[dict[str, Any]] | None = None,
    missing_actions: list[str] | None = None,
    **extra,
) -> AgentEvent:
    """构造 COMPLETION_CHECK 事件。"""
    event_data = CompletionCheckEventData(
        turn_id=turn_id,
        passed=passed,
        attempt=attempt,
        items=[
            CompletionCheckItemEventData(
                key=str(item.get("key", "")),
                label=str(item.get("label", "")),
                passed=bool(item.get("passed", False)),
                detail=str(item.get("detail", "")),
            )
            for item in (items or [])
        ],
        missing_actions=[str(item) for item in (missing_actions or []) if str(item).strip()],
        task_id=None,
    )

    data = event_data.model_dump()
    data.update(extra)

    return AgentEvent(
        type=EventType.COMPLETION_CHECK,
        data=data,
        turn_id=turn_id,
    )


def build_blocked_event(
    *,
    turn_id: str,
    reason_code: str,
    message: str,
    recoverable: bool = True,
    suggested_action: str | None = None,
    **extra,
) -> AgentEvent:
    """构造 BLOCKED 事件。"""
    return _make_event(
        EventType.BLOCKED,
        BlockedEventData(
            turn_id=turn_id,
            reason_code=reason_code,
            message=message,
            recoverable=recoverable,
            task_id=None,
            attempt_id=None,
            suggested_action=suggested_action,
        ),
        turn_id,
        None,
        extra or None,
    )


def build_budget_warning_event(
    *,
    task_id: str,
    metric: str,
    threshold: float,
    current_value: float,
    warning_level: str,
    message: str,
    recipe_id: str | None = None,
    turn_id: str | None = None,
    **extra,
) -> AgentEvent:
    """构造 BUDGET_WARNING 事件。"""
    return _make_event(
        EventType.BUDGET_WARNING,
        BudgetWarningEventData(
            task_id=task_id,
            metric=metric,  # type: ignore
            threshold=threshold,
            current_value=current_value,
            warning_level=warning_level,  # type: ignore
            message=message,
            recipe_id=recipe_id,
        ),
        turn_id,
        None,
        extra or None,
    )


def build_token_usage_event(
    input_tokens: int,
    output_tokens: int,
    model: str,
    cost_usd: float | None = None,
    *,
    turn_id: str | None = None,
    **extra,
) -> AgentEvent:
    """构造 TOKEN_USAGE 事件。"""
    return _make_event(
        EventType.TOKEN_USAGE,
        TokenUsageEventData(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=model,
            cost_usd=cost_usd,
        ),
        turn_id,
        None,
        extra or None,
    )


def build_model_fallback_event(
    *,
    purpose: str,
    attempt: int,
    to_provider_id: str,
    to_provider_name: str,
    to_model: str,
    from_provider_id: str | None = None,
    from_provider_name: str | None = None,
    from_model: str | None = None,
    reason: str | None = None,
    fallback_chain: list[dict[str, Any]] | None = None,
    turn_id: str | None = None,
    **extra,
) -> AgentEvent:
    """构造 MODEL_FALLBACK 事件。"""
    return _make_event(
        EventType.MODEL_FALLBACK,
        ModelFallbackEventData(
            purpose=purpose,
            attempt=attempt,
            from_provider_id=from_provider_id,
            from_provider_name=from_provider_name,
            from_model=from_model,
            to_provider_id=to_provider_id,
            to_provider_name=to_provider_name,
            to_model=to_model,
            reason=reason,
            fallback_chain=fallback_chain or [],
        ),
        turn_id,
        None,
        extra or None,
    )


def build_session_token_usage_event(
    session_id: str,
    input_tokens: int,
    output_tokens: int,
    total_tokens: int,
    estimated_cost_usd: float,
    estimated_cost_cny: float,
    model_breakdown: dict[str, Any],
    **extra,
) -> AgentEvent:
    """构造会话级别的 TOKEN_USAGE 事件。"""
    # 转换 model_breakdown
    breakdown = {}
    for model_id, info in model_breakdown.items():
        if isinstance(info, dict):
            breakdown[model_id] = ModelTokenUsageDetail(
                model_id=info.get("model_id", model_id),
                input_tokens=info.get("input_tokens", 0),
                output_tokens=info.get("output_tokens", 0),
                total_tokens=info.get("total_tokens", 0),
                cost_usd=info.get("cost_usd", 0.0),
                cost_cny=info.get("cost_cny", 0.0),
                call_count=info.get("call_count", 1),
            )

    event_data = SessionTokenUsageEventData(
        session_id=session_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=estimated_cost_usd,
        estimated_cost_cny=estimated_cost_cny,
        model_breakdown=breakdown,
    )

    data = event_data.model_dump()
    data.update(extra)

    return AgentEvent(
        type=EventType.TOKEN_USAGE,
        data=data,
    )


def build_tool_call_event(
    tool_call_id: str,
    name: str,
    arguments: dict[str, Any] | str,
    *,
    turn_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    **extra,
) -> AgentEvent:
    """构造 TOOL_CALL 事件。"""
    # 处理 arguments 可能是字符串的情况
    parsed_args = arguments
    if isinstance(arguments, str):
        try:
            parsed_args = json.loads(arguments)
        except json.JSONDecodeError:
            parsed_args = {"raw": arguments}

    event_data = ToolCallEventData(
        id=tool_call_id,
        name=name,
        arguments=parsed_args if isinstance(parsed_args, dict) else {},
    )

    data = event_data.model_dump()
    data.update(extra)

    return AgentEvent(
        type=EventType.TOOL_CALL,
        data=data,
        turn_id=turn_id,
        metadata=metadata or {},
        tool_call_id=tool_call_id,
        tool_name=name,
    )


def build_tool_result_event(
    tool_call_id: str,
    name: str,
    status: str,
    message: str,
    data: dict[str, Any] | None = None,
    *,
    turn_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    **extra,
) -> AgentEvent:
    """构造 TOOL_RESULT 事件。"""
    event_data = ToolResultEventData(
        id=tool_call_id,
        name=name,
        status=status,  # type: ignore
        message=message,
        data=data,
    )

    result_data = event_data.model_dump()
    result_data.update(extra)

    return AgentEvent(
        type=EventType.TOOL_RESULT,
        data=result_data,
        turn_id=turn_id,
        metadata=metadata or {},
        tool_call_id=tool_call_id,
        tool_name=name,
    )


def build_text_event(
    content: str, *, turn_id: str | None = None, metadata: dict[str, Any] | None = None, **extra
) -> AgentEvent:
    """构造 TEXT 事件。"""
    from nini.utils.markdown_fixups import fix_markdown_table_separator

    sanitized_content = (
        fix_markdown_table_separator(content) if isinstance(content, str) else content
    )
    event_data = TextEventData(content=sanitized_content, output_level=None)

    data = event_data.model_dump()
    data.update(extra)

    return AgentEvent(
        type=EventType.TEXT,
        data=data,
        turn_id=turn_id,
        metadata=metadata or {},
    )


def build_error_event(
    message: str, code: str | None = None, *, turn_id: str | None = None, **extra
) -> AgentEvent:
    """构造 ERROR 事件。"""
    return _make_event(
        EventType.ERROR, ErrorEventData(message=message, code=code), turn_id, None, extra or None
    )


def build_done_event(
    reason: str = "completed", *, turn_id: str | None = None, **extra
) -> AgentEvent:
    """构造 DONE 事件。"""
    return _make_event(EventType.DONE, DoneEventData(reason=reason), turn_id, None, extra or None)  # type: ignore


def build_session_event(session_id: str, **extra) -> AgentEvent:
    """构造 SESSION 事件。"""
    return _make_event(
        EventType.SESSION,
        SessionEventData(
            session_id=session_id, task_kind=None, recipe_id=None, deep_task_state=None
        ),
        None,
        None,
        extra or None,
    )


def build_session_title_event(session_id: str, title: str, **extra) -> AgentEvent:
    """构造 SESSION_TITLE 事件。"""
    return _make_event(
        EventType.SESSION_TITLE,
        SessionTitleEventData(session_id=session_id, title=title),
        None,
        None,
        extra or None,
    )


def build_workspace_update_event(
    action: str, file_id: str | None = None, folder_id: str | None = None, **extra
) -> AgentEvent:
    """构造 WORKSPACE_UPDATE 事件。"""
    return _make_event(
        EventType.WORKSPACE_UPDATE,
        WorkspaceUpdateEventData(action=action, file_id=file_id, folder_id=folder_id),  # type: ignore
        None,
        None,
        extra or None,
    )


def build_code_execution_event(
    execution_id: str, code: str, output: str, status: str, language: str, created_at: str, **extra
) -> AgentEvent:
    """构造 CODE_EXECUTION 事件。"""
    return _make_event(
        EventType.CODE_EXECUTION,
        CodeExecutionEventData(id=execution_id, code=code, output=output, status=status, language=language, created_at=created_at),  # type: ignore[arg-type]
        None,
        None,
        extra or None,
    )


def build_stopped_event(
    message: str = "已停止", *, turn_id: str | None = None, **extra
) -> AgentEvent:
    """构造 STOPPED 事件。"""
    return _make_event(
        EventType.STOPPED, StoppedEventData(message=message), turn_id, None, extra or None
    )


def build_iteration_start_event(iteration: int, **extra) -> AgentEvent:
    """构造 ITERATION_START 事件。"""
    return _make_event(
        EventType.ITERATION_START,
        IterationStartEventData(iteration=iteration),
        None,
        None,
        extra or None,
    )


def build_retrieval_event(
    query: str = "", results: list[dict[str, Any]] | None = None, **extra
) -> AgentEvent:
    """构造 RETRIEVAL 事件。"""
    return _make_event(
        EventType.RETRIEVAL,
        RetrievalEventData(query=query, results=results or []),
        None,
        None,
        extra or None,
    )


def build_reasoning_event(
    content: str,
    reasoning_id: str | None = None,
    reasoning_live: bool = False,
    *,
    turn_id: str | None = None,
    **extra,
) -> AgentEvent:
    """构造 REASONING 事件（流式/简单格式）。"""
    return _make_event(
        EventType.REASONING,
        ReasoningEventData(
            content=content, reasoning_id=reasoning_id, reasoning_live=reasoning_live
        ),
        turn_id,
        None,
        extra or None,
    )


def build_reasoning_data_event(
    step: str,
    thought: str,
    rationale: str = "",
    alternatives: list[str] | None = None,
    confidence: float = 1.0,
    *,
    turn_id: str | None = None,
    reasoning_type: str | None = None,
    reasoning_subtype: str | None = None,
    confidence_score: float | None = None,
    key_decisions: list[str] | None = None,
    parent_id: str | None = None,
    references: list[dict[str, Any]] | None = None,
    timestamp: str | None = None,
    tags: list[str] | None = None,
    **context: Any,
) -> AgentEvent:
    """构造 REASONING 事件（完整决策数据格式）。

    用于展示 Agent 的决策过程，提高可解释性。
    """
    event_data = ReasoningDataEventData(
        step=step,
        thought=thought,
        rationale=rationale,
        alternatives=alternatives or [],
        confidence=confidence,
        context=dict(context) if context else {},
        reasoning_type=reasoning_type,
        reasoning_subtype=reasoning_subtype,
        confidence_score=confidence_score,
        key_decisions=key_decisions or [],
        parent_id=parent_id,
        references=references or [],
        timestamp=timestamp,
        tags=tags or [],
    )

    data = event_data.model_dump()
    data.update(context)

    return AgentEvent(
        type=EventType.REASONING,
        data=data,
    )


def build_ask_user_question_event(
    questions: list[dict[str, Any]],
    *,
    turn_id: str | None = None,
    tool_call_id: str | None = None,
    tool_name: str | None = None,
    metadata: dict[str, Any] | None = None,
    **extra,
) -> AgentEvent:
    """构造 ASK_USER_QUESTION 事件。"""
    event_data = AskUserQuestionEventData(questions=questions)

    data = event_data.model_dump()
    data.update(extra)

    return AgentEvent(
        type=EventType.ASK_USER_QUESTION,
        data=data,
        turn_id=turn_id,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        metadata=metadata or {},
    )


def build_artifact_event(
    artifact_id: str,
    artifact_type: str,
    name: str,
    url: str | None = None,
    mime_type: str | None = None,
    **extra,
) -> AgentEvent:
    """构造 ARTIFACT 事件。"""
    return _make_event(
        EventType.ARTIFACT,
        ArtifactEventData(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            name=name,
            url=url,
            mime_type=mime_type,
        ),
        None,
        None,
        extra or None,
    )


def build_chart_event(
    chart_id: str, name: str, url: str, chart_type: str | None = None, **extra
) -> AgentEvent:
    """构造 CHART 事件。"""
    return _make_event(
        EventType.CHART,
        ChartEventData(chart_id=chart_id, name=name, url=url, chart_type=chart_type),
        None,
        None,
        extra or None,
    )


def build_data_event(
    data_id: str,
    name: str,
    url: str,
    row_count: int | None = None,
    column_count: int | None = None,
    **extra,
) -> AgentEvent:
    """构造 DATA 事件。"""
    return _make_event(
        EventType.DATA,
        DataEventData(
            data_id=data_id, name=name, url=url, row_count=row_count, column_count=column_count
        ),
        None,
        None,
        extra or None,
    )


def build_image_event(
    image_id: str, name: str, url: str, mime_type: str | None = None, **extra
) -> AgentEvent:
    """构造 IMAGE 事件。"""
    return _make_event(
        EventType.IMAGE,
        ImageEventData(image_id=image_id, name=name, url=url, mime_type=mime_type),
        None,
        None,
        extra or None,
    )


def build_context_compressed_event(
    original_tokens: int,
    compressed_tokens: int,
    compression_ratio: float,
    message: str = "",
    *,
    archived_count: int | None = None,
    remaining_count: int | None = None,
    previous_tokens: int | None = None,
    trigger: str | None = None,
    **extra,
) -> AgentEvent:
    """构造 CONTEXT_COMPRESSED 事件。"""
    return _make_event(
        EventType.CONTEXT_COMPRESSED,
        ContextCompressedEventData(
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            compression_ratio=compression_ratio,
            message=message,
            archived_count=archived_count,
            remaining_count=remaining_count,
            previous_tokens=previous_tokens,
            trigger=trigger,
        ),
        None,
        None,
        extra or None,
    )


def build_agent_start_event(
    agent_id: str,
    agent_name: str,
    task: str,
    attempt: int = 1,
    retry_count: int = 0,
    *,
    turn_id: str | None = None,
) -> AgentEvent:
    """构造 AGENT_START 事件。"""
    return _make_agent_event(
        EventType.AGENT_START,
        AgentStartEventData(
            agent_id=agent_id,
            agent_name=agent_name,
            task=task,
            attempt=attempt,
            retry_count=retry_count,
        ),
        "agent_start",
        turn_id,
    )


def build_agent_complete_event(
    agent_id: str,
    agent_name: str,
    summary: str,
    execution_time_ms: int,
    attempt: int = 1,
    retry_count: int = 0,
    *,
    turn_id: str | None = None,
) -> AgentEvent:
    """构造 AGENT_COMPLETE 事件。"""
    return _make_agent_event(
        EventType.AGENT_COMPLETE,
        AgentCompleteEventData(
            agent_id=agent_id,
            agent_name=agent_name,
            summary=summary,
            execution_time_ms=execution_time_ms,
            attempt=attempt,
            retry_count=retry_count,
        ),
        "agent_complete",
        turn_id,
    )


def build_agent_progress_event(
    agent_id: str,
    agent_name: str,
    phase: str,
    message: str,
    progress_hint: str | None = None,
    attempt: int = 1,
    retry_count: int = 0,
    *,
    turn_id: str | None = None,
) -> AgentEvent:
    """构造 AGENT_PROGRESS 事件。"""
    return _make_agent_event(
        EventType.AGENT_PROGRESS,
        AgentProgressEventData(
            agent_id=agent_id,
            agent_name=agent_name,
            phase=phase,
            message=message,
            progress_hint=progress_hint,
            attempt=attempt,
            retry_count=retry_count,
        ),
        "agent_progress",
        turn_id,
    )


def build_agent_error_event(
    agent_id: str,
    agent_name: str,
    error: str,
    execution_time_ms: int,
    attempt: int = 1,
    retry_count: int = 0,
    *,
    turn_id: str | None = None,
) -> AgentEvent:
    """构造 AGENT_ERROR 事件。"""
    return _make_agent_event(
        EventType.AGENT_ERROR,
        AgentErrorEventData(
            agent_id=agent_id,
            agent_name=agent_name,
            error=error,
            execution_time_ms=execution_time_ms,
            attempt=attempt,
            retry_count=retry_count,
        ),
        "agent_error",
        turn_id,
    )


def build_agent_stopped_event(
    agent_id: str,
    agent_name: str,
    reason: str,
    execution_time_ms: int,
    attempt: int = 1,
    retry_count: int = 0,
    *,
    turn_id: str | None = None,
) -> AgentEvent:
    """构造 AGENT_STOPPED 事件。"""
    return _make_agent_event(
        EventType.AGENT_STOPPED,
        AgentStoppedEventData(
            agent_id=agent_id,
            agent_name=agent_name,
            reason=reason,
            execution_time_ms=execution_time_ms,
            attempt=attempt,
            retry_count=retry_count,
        ),
        "agent_stopped",
        turn_id,
    )


# ---- Hypothesis-Driven 范式事件构造器（Phase 3）----


def build_hypothesis_generated_event(
    agent_id: str,
    hypotheses: list[dict[str, Any]],
) -> "AgentEvent":
    """构造 HYPOTHESIS_GENERATED 事件。

    Args:
        agent_id: 执行假设推理的 Agent ID
        hypotheses: 假设列表，每项含 id/content/confidence 字段
    """
    return AgentEvent(
        type=EventType.HYPOTHESIS_GENERATED,
        data={
            "event_type": "hypothesis_generated",
            "agent_id": agent_id,
            "hypotheses": hypotheses,
        },
    )


def build_evidence_collected_event(
    agent_id: str,
    hypothesis_id: str,
    evidence_type: str,
    evidence_content: str,
) -> "AgentEvent":
    """构造 EVIDENCE_COLLECTED 事件。

    Args:
        agent_id: 执行假设推理的 Agent ID
        hypothesis_id: 目标假设 ID
        evidence_type: "for" 或 "against"
        evidence_content: 证据内容
    """
    return AgentEvent(
        type=EventType.EVIDENCE_COLLECTED,
        data={
            "event_type": "evidence_collected",
            "agent_id": agent_id,
            "hypothesis_id": hypothesis_id,
            "evidence_type": evidence_type,
            "content": evidence_content,
        },
    )


def build_hypothesis_validated_event(
    agent_id: str,
    hypothesis_id: str,
    confidence: float,
) -> "AgentEvent":
    """构造 HYPOTHESIS_VALIDATED 事件。

    Args:
        agent_id: 执行假设推理的 Agent ID
        hypothesis_id: 被验证的假设 ID
        confidence: 当前置信度
    """
    return AgentEvent(
        type=EventType.HYPOTHESIS_VALIDATED,
        data={
            "event_type": "hypothesis_validated",
            "agent_id": agent_id,
            "hypothesis_id": hypothesis_id,
            "confidence": confidence,
        },
    )


def build_hypothesis_refuted_event(
    agent_id: str,
    hypothesis_id: str,
    reason: str,
) -> "AgentEvent":
    """构造 HYPOTHESIS_REFUTED 事件。

    Args:
        agent_id: 执行假设推理的 Agent ID
        hypothesis_id: 被证伪的假设 ID
        reason: 证伪原因
    """
    return AgentEvent(
        type=EventType.HYPOTHESIS_REFUTED,
        data={
            "event_type": "hypothesis_refuted",
            "agent_id": agent_id,
            "hypothesis_id": hypothesis_id,
            "reason": reason,
        },
    )


def build_paradigm_switched_event(
    agent_id: str,
    paradigm: str,
) -> "AgentEvent":
    """构造 PARADIGM_SWITCHED 事件。

    Args:
        agent_id: 执行范式切换的 Agent ID
        paradigm: 切换目标范式（如 "hypothesis_driven"）
    """
    return AgentEvent(
        type=EventType.PARADIGM_SWITCHED,
        data={
            "event_type": "paradigm_switched",
            "agent_id": agent_id,
            "paradigm": paradigm,
        },
    )
