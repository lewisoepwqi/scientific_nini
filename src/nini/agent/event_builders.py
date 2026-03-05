"""WebSocket 事件构造器 —— 使用严格的 Pydantic 模型确保数据契约。

此模块提供类型安全的事件构造函数，确保后端发送的事件数据
与前端的期望完全一致。
"""

from __future__ import annotations

from typing import Any

from nini.agent.events import AgentEvent, EventType
from nini.models.event_schemas import (
    AnalysisPlanEventData,
    AnalysisPlanStep,
    PlanProgressEventData,
    PlanStepUpdateEventData,
    TaskAttemptEventData,
    TokenUsageEventData,
    SessionTokenUsageEventData,
    ModelTokenUsageDetail,
    ToolCallEventData,
    ToolResultEventData,
    TextEventData,
    ErrorEventData,
    DoneEventData,
    SessionEventData,
    SessionTitleEventData,
    WorkspaceUpdateEventData,
    CodeExecutionEventData,
    StoppedEventData,
)


def build_analysis_plan_event(
    steps: list[dict[str, Any]],
    raw_text: str = "",
    **extra
) -> AgentEvent:
    """构造 ANALYSIS_PLAN 事件。

    Args:
        steps: 步骤列表，每项包含 id, title, tool_hint, status, action_id 等
        raw_text: 原始文本内容
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
            )
        )

    event_data = AnalysisPlanEventData(
        steps=step_objects,
        raw_text=raw_text,
    )

    data = event_data.model_dump()
    data.update(extra)  # 合并额外字段

    return AgentEvent(
        type=EventType.ANALYSIS_PLAN,
        data=data,
    )


def build_plan_step_update_event(
    step_id: int,
    status: str,
    error: str | None = None,
    **extra
) -> AgentEvent:
    """构造 PLAN_STEP_UPDATE 事件。"""
    event_data = PlanStepUpdateEventData(
        id=step_id,
        status=status,
        error=error,
    )

    data = event_data.model_dump()
    data.update(extra)

    return AgentEvent(
        type=EventType.PLAN_STEP_UPDATE,
        data=data,
    )


def build_plan_progress_event(
    steps: list[dict[str, Any]],
    current_step_index: int,
    total_steps: int,
    step_title: str,
    step_status: str,
    next_hint: str | None = None,
    block_reason: str | None = None,
    **extra
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
    )

    data = event_data.model_dump()
    data.update(extra)

    return AgentEvent(
        type=EventType.PLAN_PROGRESS,
        data=data,
    )


def build_task_attempt_event(
    action_id: str,
    step_id: int,
    tool_name: str,
    attempt: int,
    max_attempts: int,
    status: str,
    note: str | None = None,
    error: str | None = None,
    **extra
) -> AgentEvent:
    """构造 TASK_ATTEMPT 事件。"""
    event_data = TaskAttemptEventData(
        action_id=action_id,
        step_id=step_id,
        tool_name=tool_name,
        attempt=attempt,
        max_attempts=max_attempts,
        status=status,  # type: ignore
        note=note,
        error=error,
    )

    data = event_data.model_dump()
    data.update(extra)

    return AgentEvent(
        type=EventType.TASK_ATTEMPT,
        data=data,
    )


def build_token_usage_event(
    input_tokens: int,
    output_tokens: int,
    model: str,
    cost_usd: float | None = None,
    **extra
) -> AgentEvent:
    """构造 TOKEN_USAGE 事件。"""
    event_data = TokenUsageEventData(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model=model,
        cost_usd=cost_usd,
    )

    data = event_data.model_dump()
    data.update(extra)

    return AgentEvent(
        type=EventType.TOKEN_USAGE,
        data=data,
    )


def build_session_token_usage_event(
    session_id: str,
    input_tokens: int,
    output_tokens: int,
    total_tokens: int,
    estimated_cost_usd: float,
    estimated_cost_cny: float,
    model_breakdown: dict[str, Any],
    **extra
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
    arguments: dict[str, Any],
    **extra
) -> AgentEvent:
    """构造 TOOL_CALL 事件。"""
    event_data = ToolCallEventData(
        id=tool_call_id,
        name=name,
        arguments=arguments,
    )

    data = event_data.model_dump()
    data.update(extra)

    return AgentEvent(
        type=EventType.TOOL_CALL,
        data=data,
        tool_call_id=tool_call_id,
        tool_name=name,
    )


def build_tool_result_event(
    tool_call_id: str,
    name: str,
    status: str,
    message: str,
    data: dict[str, Any] | None = None,
    **extra
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
        tool_call_id=tool_call_id,
        tool_name=name,
    )


def build_text_event(content: str, **extra) -> AgentEvent:
    """构造 TEXT 事件。"""
    event_data = TextEventData(content=content)

    data = event_data.model_dump()
    data.update(extra)

    return AgentEvent(
        type=EventType.TEXT,
        data=data,
    )


def build_error_event(message: str, code: str | None = None, **extra) -> AgentEvent:
    """构造 ERROR 事件。"""
    event_data = ErrorEventData(message=message, code=code)

    data = event_data.model_dump()
    data.update(extra)

    return AgentEvent(
        type=EventType.ERROR,
        data=data,
    )


def build_done_event(reason: str = "completed", **extra) -> AgentEvent:
    """构造 DONE 事件。"""
    event_data = DoneEventData(reason=reason)  # type: ignore

    data = event_data.model_dump()
    data.update(extra)

    return AgentEvent(
        type=EventType.DONE,
        data=data,
    )


def build_session_event(session_id: str, **extra) -> AgentEvent:
    """构造 SESSION 事件。"""
    event_data = SessionEventData(session_id=session_id)

    data = event_data.model_dump()
    data.update(extra)

    return AgentEvent(
        type=EventType.SESSION,
        data=data,
    )


def build_session_title_event(session_id: str, title: str, **extra) -> AgentEvent:
    """构造 SESSION_TITLE 事件。"""
    event_data = SessionTitleEventData(
        session_id=session_id,
        title=title,
    )

    data = event_data.model_dump()
    data.update(extra)

    return AgentEvent(
        type=EventType.SESSION_TITLE,
        data=data,
    )


def build_workspace_update_event(
    action: str,
    file_id: str | None = None,
    folder_id: str | None = None,
    **extra
) -> AgentEvent:
    """构造 WORKSPACE_UPDATE 事件。"""
    event_data = WorkspaceUpdateEventData(
        action=action,  # type: ignore
        file_id=file_id,
        folder_id=folder_id,
    )

    data = event_data.model_dump()
    data.update(extra)

    return AgentEvent(
        type=EventType.WORKSPACE_UPDATE,
        data=data,
    )


def build_code_execution_event(
    execution_id: str,
    code: str,
    output: str,
    status: str,
    language: str,
    created_at: str,
    **extra
) -> AgentEvent:
    """构造 CODE_EXECUTION 事件。"""
    event_data = CodeExecutionEventData(
        id=execution_id,
        code=code,
        output=output,
        status=status,  # type: ignore
        language=language,
        created_at=created_at,
    )

    data = event_data.model_dump()
    data.update(extra)

    return AgentEvent(
        type=EventType.CODE_EXECUTION,
        data=data,
    )


def build_stopped_event(message: str = "已停止", **extra) -> AgentEvent:
    """构造 STOPPED 事件。"""
    event_data = StoppedEventData(message=message)

    data = event_data.model_dump()
    data.update(extra)

    return AgentEvent(
        type=EventType.STOPPED,
        data=data,
    )
