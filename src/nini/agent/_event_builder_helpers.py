"""event_builders 内部辅助函数，不对外暴露。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from nini.agent.events import AgentEvent, EventType


def _make_event(
    event_type: EventType,
    data_model: BaseModel,
    turn_id: str | None,
    seq: int | None,
    extra: dict[str, Any] | None = None,
    **agent_event_kwargs: Any,
) -> AgentEvent:
    """标准事件构建辅助：Pydantic 模型 → AgentEvent。"""
    data = data_model.model_dump()
    if extra:
        data.update(extra)
    metadata: dict[str, Any] = {}
    if seq is not None:
        metadata["seq"] = seq
    return AgentEvent(
        type=event_type,
        data=data,
        turn_id=turn_id,
        metadata=metadata,
        **agent_event_kwargs,
    )


def _make_agent_event(
    event_type: EventType,
    data_model: BaseModel,
    event_type_tag: str,
    turn_id: str | None,
) -> AgentEvent:
    """Agent 子事件构建辅助：注入 event_type 标签字段。"""
    return AgentEvent(
        type=event_type,
        data={"event_type": event_type_tag, **data_model.model_dump()},
        turn_id=turn_id,
    )
