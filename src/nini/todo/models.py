"""TODO 模块的数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4


def utc_now() -> datetime:
    """返回当前 UTC 时间。"""
    return datetime.now(timezone.utc)


def make_task_id() -> str:
    """生成任务标识。"""
    return f"task_{uuid4().hex[:12]}"


def make_event_id() -> str:
    """生成事件标识。"""
    return f"evt_{uuid4().hex[:12]}"


class TaskStatus(StrEnum):
    """任务生命周期状态。"""

    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskEventType(StrEnum):
    """任务事件类型。"""

    CREATED = "created"
    UPDATED = "updated"
    CLAIMED = "claimed"
    RELEASED = "released"
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DELETED = "deleted"


@dataclass(slots=True)
class Task:
    """单个任务快照。"""

    task_id: str
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    assigned_agent_id: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    assigned_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    priority: int | None = None
    dependency_ids: list[str] = field(default_factory=list)
    deadline_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def assignee_id(self) -> str | None:
        """兼容旧命名。"""
        return self.assigned_agent_id

    @property
    def assignee_id(self) -> str | None:
        """兼容统一任务模型命名。"""
        return self.assigned_agent_id

    def to_dict(self) -> dict[str, Any]:
        """序列化为 JSON 友好的字典。"""
        return {
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "assigned_agent_id": self.assigned_agent_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "assigned_at": self.assigned_at.isoformat() if self.assigned_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "priority": self.priority,
            "dependency_ids": list(self.dependency_ids),
            "deadline_at": self.deadline_at.isoformat() if self.deadline_at else None,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Task":
        """从字典反序列化。"""
        return cls(
            task_id=str(payload.get("task_id") or make_task_id()),
            title=str(payload.get("title") or "").strip(),
            description=str(payload.get("description") or ""),
            status=TaskStatus(str(payload.get("status") or TaskStatus.PENDING.value)),
            assigned_agent_id=_optional_str(payload.get("assigned_agent_id")),
            created_at=_parse_datetime(payload.get("created_at")) or utc_now(),
            updated_at=_parse_datetime(payload.get("updated_at")) or utc_now(),
            assigned_at=_parse_datetime(payload.get("assigned_at")),
            started_at=_parse_datetime(payload.get("started_at")),
            finished_at=_parse_datetime(payload.get("finished_at")),
            priority=_parse_optional_int(payload.get("priority")),
            dependency_ids=[
                str(item).strip()
                for item in payload.get("dependency_ids", []) or []
                if str(item).strip()
            ],
            deadline_at=_parse_datetime(payload.get("deadline_at")),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass(slots=True)
class TaskEvent:
    """任务事件审计记录。"""

    event_id: str
    task_id: str
    event_type: TaskEventType
    actor_id: str | None
    occurred_at: datetime = field(default_factory=utc_now)
    from_status: TaskStatus | None = None
    to_status: TaskStatus | None = None
    message: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """序列化为 JSON 友好的字典。"""
        return {
            "event_id": self.event_id,
            "task_id": self.task_id,
            "event_type": self.event_type.value,
            "actor_id": self.actor_id,
            "occurred_at": self.occurred_at.isoformat(),
            "from_status": self.from_status.value if self.from_status else None,
            "to_status": self.to_status.value if self.to_status else None,
            "message": self.message,
            "payload": dict(self.payload),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TaskEvent":
        """从字典反序列化。"""
        return cls(
            event_id=str(payload.get("event_id") or make_event_id()),
            task_id=str(payload.get("task_id") or "").strip(),
            event_type=TaskEventType(str(payload.get("event_type") or TaskEventType.UPDATED.value)),
            actor_id=_optional_str(payload.get("actor_id")),
            occurred_at=_parse_datetime(payload.get("occurred_at")) or utc_now(),
            from_status=_parse_status(payload.get("from_status")),
            to_status=_parse_status(payload.get("to_status")),
            message=_optional_str(payload.get("message")),
            payload=dict(payload.get("payload") or {}),
        )


def clone_task(task: Task) -> Task:
    """返回任务的防御性副本。"""
    return Task.from_dict(task.to_dict())


def clone_event(event: TaskEvent) -> TaskEvent:
    """返回事件的防御性副本。"""
    return TaskEvent.from_dict(event.to_dict())


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_status(value: Any) -> TaskStatus | None:
    if value is None or value == "":
        return None
    return TaskStatus(str(value))
