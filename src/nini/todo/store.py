"""TODO 状态存储与生命周期校验。"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from threading import RLock
from typing import Any, cast

from nini.todo.hooks import TaskHookRegistry
from nini.todo.models import (
    Task,
    TaskEvent,
    TaskEventType,
    TaskStatus,
    clone_event,
    clone_task,
    make_event_id,
    make_task_id,
    utc_now,
)


class TaskStoreError(Exception):
    """TODO 存储基类异常。"""


class TaskNotFoundError(TaskStoreError):
    """任务不存在。"""


class TaskConflictError(TaskStoreError):
    """任务冲突，例如被其他 Agent 认领。"""


class InvalidTaskTransitionError(TaskStoreError):
    """任务状态迁移非法。"""


class TaskDependencyError(TaskStoreError):
    """任务依赖不满足。"""


_UNSET = object()

_ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {TaskStatus.ASSIGNED, TaskStatus.CANCELLED},
    TaskStatus.ASSIGNED: {
        TaskStatus.PENDING,
        TaskStatus.IN_PROGRESS,
        TaskStatus.CANCELLED,
    },
    TaskStatus.IN_PROGRESS: {
        TaskStatus.PENDING,
        TaskStatus.DONE,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.DONE: set(),
    TaskStatus.FAILED: set(),
    TaskStatus.CANCELLED: set(),
}

_STATUS_TO_EVENT: dict[TaskStatus, TaskEventType] = {
    TaskStatus.ASSIGNED: TaskEventType.CLAIMED,
    TaskStatus.IN_PROGRESS: TaskEventType.STARTED,
    TaskStatus.DONE: TaskEventType.COMPLETED,
    TaskStatus.FAILED: TaskEventType.FAILED,
    TaskStatus.CANCELLED: TaskEventType.CANCELLED,
}


class TaskStore:
    """任务快照存储。

    当前实现使用内存字典 + 可选 JSON 文件落盘，作为后续接入
    `Session` / WebSocket / SQLite 的最小可运行核心。
    """

    def __init__(
        self,
        *,
        storage_path: str | Path | None = None,
        hook_registry: TaskHookRegistry | None = None,
    ) -> None:
        self._storage_path = Path(storage_path) if storage_path else None
        self._hooks = hook_registry or TaskHookRegistry()
        self._lock = RLock()
        self._tasks: dict[str, Task] = {}
        self._events: list[TaskEvent] = []
        self._load()

    @property
    def hook_registry(self) -> TaskHookRegistry:
        """返回 hook 注册器。"""
        return self._hooks

    def create_task(
        self,
        *,
        title: str,
        description: str = "",
        task_id: str | None = None,
        dependency_ids: list[str] | None = None,
        priority: int | None = None,
        deadline_at: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> Task:
        """创建任务。"""
        normalized_title = str(title or "").strip()
        if not normalized_title:
            raise ValueError("任务标题不能为空")

        with self._lock:
            task = Task(
                task_id=str(task_id or make_task_id()),
                title=normalized_title,
                description=str(description or ""),
                dependency_ids=[
                    str(item).strip() for item in (dependency_ids or []) if str(item).strip()
                ],
                priority=priority,
                deadline_at=deadline_at,
                metadata=dict(metadata or {}),
            )
            self._ensure_dependencies_exist(task.dependency_ids)
            if task.task_id in self._tasks:
                raise TaskConflictError(f"任务已存在: {task.task_id}")
            self._tasks[task.task_id] = task
            event = self._append_event_locked(
                task,
                event_type=TaskEventType.CREATED,
                actor_id=None,
                from_status=None,
                to_status=task.status,
                message="创建任务",
            )
            self._persist_locked()
            safe_task = clone_task(task)
            safe_event = clone_event(event)

        self._hooks.emit(safe_event, safe_task)
        return safe_task

    def get_task(self, task_id: str) -> Task:
        """读取单个任务。"""
        with self._lock:
            task = self._tasks.get(str(task_id).strip())
            if task is None:
                raise TaskNotFoundError(f"任务不存在: {task_id}")
            return clone_task(task)

    def list_tasks(
        self,
        *,
        status: TaskStatus | None = None,
        assigned_agent_id: str | None = None,
        include_cancelled: bool = True,
    ) -> list[Task]:
        """列出任务。"""
        with self._lock:
            items = list(self._tasks.values())
            if status is not None:
                items = [item for item in items if item.status == status]
            if assigned_agent_id is not None:
                normalized_agent_id = str(assigned_agent_id).strip()
                items = [
                    item for item in items if (item.assigned_agent_id or "") == normalized_agent_id
                ]
            if not include_cancelled:
                items = [item for item in items if item.status != TaskStatus.CANCELLED]
            items.sort(key=self._task_sort_key)
            return [clone_task(item) for item in items]

    def list_events(self, *, task_id: str | None = None) -> list[TaskEvent]:
        """列出事件日志。"""
        with self._lock:
            items = self._events
            if task_id:
                normalized_task_id = str(task_id).strip()
                items = [item for item in items if item.task_id == normalized_task_id]
            return [clone_event(item) for item in items]

    def update_task(
        self,
        task_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        dependency_ids: list[str] | None = None,
        priority: int | None | object = _UNSET,
        deadline_at: Any = _UNSET,
        metadata: dict[str, Any] | None = None,
        actor_id: str | None = None,
        message: str | None = None,
    ) -> Task:
        """更新任务元数据，不改变生命周期状态。"""
        with self._lock:
            task = self._require_task_locked(task_id)
            new_dependencies = (
                [str(item).strip() for item in dependency_ids if str(item).strip()]
                if dependency_ids is not None
                else list(task.dependency_ids)
            )
            self._ensure_dependencies_exist(new_dependencies, allow_task_id=task.task_id)
            now = utc_now()
            next_priority = task.priority if priority is _UNSET else cast(int | None, priority)
            updated = replace(
                task,
                title=str(title).strip() if title is not None else task.title,
                description=str(description) if description is not None else task.description,
                dependency_ids=new_dependencies,
                priority=next_priority,
                deadline_at=task.deadline_at if deadline_at is _UNSET else deadline_at,
                metadata=(dict(metadata) if metadata is not None else dict(task.metadata)),
                updated_at=now,
            )
            if not updated.title:
                raise ValueError("任务标题不能为空")
            self._tasks[task.task_id] = updated
            event = self._append_event_locked(
                updated,
                event_type=TaskEventType.UPDATED,
                actor_id=actor_id,
                from_status=task.status,
                to_status=updated.status,
                message=message or "更新任务元数据",
            )
            self._persist_locked()
            safe_task = clone_task(updated)
            safe_event = clone_event(event)

        self._hooks.emit(safe_event, safe_task)
        return safe_task

    def delete_task(self, task_id: str, *, actor_id: str | None = None) -> Task:
        """删除任务。

        仅用于管理场景；运行时更推荐使用 cancel 保留审计轨迹。
        """
        with self._lock:
            task = self._require_task_locked(task_id)
            if task.status in {TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS}:
                raise TaskConflictError(f"执行中的任务不可删除: {task.task_id}")
            removed = self._tasks.pop(task.task_id)
            event = self._append_event_locked(
                removed,
                event_type=TaskEventType.DELETED,
                actor_id=actor_id,
                from_status=removed.status,
                to_status=None,
                message="删除任务",
            )
            self._persist_locked()
            safe_task = clone_task(removed)
            safe_event = clone_event(event)

        self._hooks.emit(safe_event, safe_task)
        return safe_task

    def claim_task(
        self,
        task_id: str,
        *,
        agent_id: str,
        message: str | None = None,
    ) -> Task:
        """认领任务。"""
        return self.transition_task(
            task_id,
            to_status=TaskStatus.ASSIGNED,
            actor_id=agent_id,
            message=message or "认领任务",
        )

    def release_task(
        self,
        task_id: str,
        *,
        agent_id: str,
        message: str | None = None,
    ) -> Task:
        """释放任务回到待处理。"""
        return self.transition_task(
            task_id,
            to_status=TaskStatus.PENDING,
            actor_id=agent_id,
            message=message or "释放任务",
        )

    def start_task(
        self,
        task_id: str,
        *,
        agent_id: str,
        message: str | None = None,
    ) -> Task:
        """开始执行任务。"""
        return self.transition_task(
            task_id,
            to_status=TaskStatus.IN_PROGRESS,
            actor_id=agent_id,
            message=message or "开始执行任务",
        )

    def complete_task(
        self,
        task_id: str,
        *,
        agent_id: str,
        message: str | None = None,
    ) -> Task:
        """完成任务。"""
        return self.transition_task(
            task_id,
            to_status=TaskStatus.DONE,
            actor_id=agent_id,
            message=message or "完成任务",
        )

    def fail_task(
        self,
        task_id: str,
        *,
        agent_id: str,
        message: str | None = None,
    ) -> Task:
        """标记任务失败。"""
        return self.transition_task(
            task_id,
            to_status=TaskStatus.FAILED,
            actor_id=agent_id,
            message=message or "任务执行失败",
        )

    def cancel_task(
        self,
        task_id: str,
        *,
        actor_id: str | None = None,
        message: str | None = None,
    ) -> Task:
        """取消任务。"""
        return self.transition_task(
            task_id,
            to_status=TaskStatus.CANCELLED,
            actor_id=actor_id,
            message=message or "取消任务",
        )

    def transition_task(
        self,
        task_id: str,
        *,
        to_status: TaskStatus,
        actor_id: str | None = None,
        message: str | None = None,
    ) -> Task:
        """执行状态迁移。"""
        with self._lock:
            current = self._require_task_locked(task_id)
            if current.status == to_status:
                normalized_actor = self._normalize_actor(actor_id)
                owner = self._normalize_actor(current.assigned_agent_id)
                if (
                    to_status in {TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS}
                    and owner
                    and normalized_actor
                    and owner != normalized_actor
                ):
                    raise TaskConflictError(f"任务已被其他 Agent 认领: {current.task_id} ({owner})")
                return clone_task(current)

            self._validate_transition_locked(current, to_status, actor_id=actor_id)
            now = utc_now()
            assigned_agent_id = current.assigned_agent_id
            assigned_at = current.assigned_at
            started_at = current.started_at
            finished_at = current.finished_at

            if to_status == TaskStatus.ASSIGNED:
                assigned_agent_id = self._normalize_actor(actor_id)
                assigned_at = now
                started_at = None
                finished_at = None
            elif to_status == TaskStatus.PENDING:
                assigned_agent_id = None
                assigned_at = None
                started_at = None
                finished_at = None
            elif to_status == TaskStatus.IN_PROGRESS:
                assigned_agent_id = self._normalize_actor(actor_id) or assigned_agent_id
                assigned_at = assigned_at or now
                started_at = now
                finished_at = None
            elif to_status in {TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.CANCELLED}:
                finished_at = now

            updated = replace(
                current,
                status=to_status,
                assigned_agent_id=assigned_agent_id,
                assigned_at=assigned_at,
                started_at=started_at,
                finished_at=finished_at,
                updated_at=now,
            )
            self._tasks[updated.task_id] = updated
            event = self._append_event_locked(
                updated,
                event_type=self._event_type_for_transition(current.status, to_status),
                actor_id=actor_id,
                from_status=current.status,
                to_status=to_status,
                message=message,
            )
            self._persist_locked()
            safe_task = clone_task(updated)
            safe_event = clone_event(event)

        self._hooks.emit(safe_event, safe_task)
        return safe_task

    def dependencies_satisfied(self, task_id: str) -> bool:
        """检查某任务依赖是否全部完成。"""
        with self._lock:
            task = self._require_task_locked(task_id)
            return self._dependencies_satisfied_locked(task)

    def list_ready_tasks(self) -> list[Task]:
        """列出当前可认领的任务。"""
        with self._lock:
            ready = [
                clone_task(task)
                for task in self._tasks.values()
                if task.status == TaskStatus.PENDING and self._dependencies_satisfied_locked(task)
            ]
            ready.sort(key=self._task_sort_key)
            return ready

    def to_dict(self) -> dict[str, Any]:
        """导出完整快照。"""
        with self._lock:
            return {
                "tasks": [task.to_dict() for task in self.list_tasks()],
                "events": [event.to_dict() for event in self.list_events()],
            }

    def _load(self) -> None:
        if self._storage_path is None or not self._storage_path.exists():
            return
        payload = json.loads(self._storage_path.read_text(encoding="utf-8"))
        tasks = payload.get("tasks", [])
        events = payload.get("events", [])
        self._tasks = {}
        self._events = []
        for raw in tasks:
            task = Task.from_dict(raw)
            self._tasks[task.task_id] = task
        for raw in events:
            self._events.append(TaskEvent.from_dict(raw))

    def _persist_locked(self) -> None:
        if self._storage_path is None:
            return
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "tasks": [task.to_dict() for task in self._tasks.values()],
            "events": [event.to_dict() for event in self._events],
        }
        self._storage_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _require_task_locked(self, task_id: str) -> Task:
        normalized = str(task_id).strip()
        task = self._tasks.get(normalized)
        if task is None:
            raise TaskNotFoundError(f"任务不存在: {task_id}")
        return task

    def _ensure_dependencies_exist(
        self,
        dependency_ids: list[str],
        *,
        allow_task_id: str | None = None,
    ) -> None:
        seen: set[str] = set()
        for dep_id in dependency_ids:
            if dep_id == allow_task_id:
                raise TaskDependencyError("任务不能依赖自身")
            if dep_id in seen:
                raise TaskDependencyError(f"任务依赖重复: {dep_id}")
            if dep_id not in self._tasks:
                raise TaskDependencyError(f"依赖任务不存在: {dep_id}")
            seen.add(dep_id)

    def _dependencies_satisfied_locked(self, task: Task) -> bool:
        for dep_id in task.dependency_ids:
            dep = self._tasks.get(dep_id)
            if dep is None or dep.status != TaskStatus.DONE:
                return False
        return True

    def _validate_transition_locked(
        self,
        task: Task,
        to_status: TaskStatus,
        *,
        actor_id: str | None,
    ) -> None:
        allowed = _ALLOWED_TRANSITIONS.get(task.status, set())
        if to_status not in allowed:
            raise InvalidTaskTransitionError(
                f"非法状态迁移: {task.status.value} -> {to_status.value}"
            )
        normalized_actor = self._normalize_actor(actor_id)

        if to_status == TaskStatus.ASSIGNED:
            if not normalized_actor:
                raise InvalidTaskTransitionError("认领任务必须提供 agent_id")
            if not self._dependencies_satisfied_locked(task):
                raise TaskDependencyError(f"任务依赖未满足: {task.task_id}")

        if task.status in {TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS}:
            owner = self._normalize_actor(task.assigned_agent_id)
            if owner and normalized_actor and owner != normalized_actor:
                raise TaskConflictError(f"任务已被其他 Agent 认领: {task.task_id} ({owner})")

        if to_status == TaskStatus.IN_PROGRESS and not (task.assigned_agent_id or normalized_actor):
            raise InvalidTaskTransitionError("开始执行前必须先认领任务")

    def _append_event_locked(
        self,
        task: Task,
        *,
        event_type: TaskEventType,
        actor_id: str | None,
        from_status: TaskStatus | None,
        to_status: TaskStatus | None,
        message: str | None,
    ) -> TaskEvent:
        event = TaskEvent(
            event_id=make_event_id(),
            task_id=task.task_id,
            event_type=event_type,
            actor_id=self._normalize_actor(actor_id),
            from_status=from_status,
            to_status=to_status,
            message=message,
            payload={
                "title": task.title,
                "assigned_agent_id": task.assigned_agent_id,
                "dependency_ids": list(task.dependency_ids),
            },
        )
        self._events.append(event)
        return event

    @staticmethod
    def _event_type_for_transition(
        from_status: TaskStatus,
        to_status: TaskStatus,
    ) -> TaskEventType:
        if (
            from_status in {TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS}
            and to_status == TaskStatus.PENDING
        ):
            return TaskEventType.RELEASED
        return _STATUS_TO_EVENT.get(to_status, TaskEventType.UPDATED)

    @staticmethod
    def _normalize_actor(actor_id: str | None) -> str | None:
        if actor_id is None:
            return None
        text = str(actor_id).strip()
        return text or None

    @staticmethod
    def _task_sort_key(task: Task) -> tuple[int, int, str]:
        priority = task.priority if task.priority is not None else 10_000
        created_ts = int(task.created_at.timestamp())
        return (priority, created_ts, task.task_id)
