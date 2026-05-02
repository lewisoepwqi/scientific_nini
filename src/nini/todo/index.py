"""TODO 模块公共入口。"""

from __future__ import annotations

from pathlib import Path

from nini.todo.dispatcher import TaskDispatcher
from nini.todo.hooks import LoggingTaskHook, TaskHook, TaskHookRegistry
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
from nini.todo.store import (
    InvalidTaskTransitionError,
    TaskConflictError,
    TaskDependencyError,
    TaskNotFoundError,
    TaskStore,
    TaskStoreError,
)


class TodoService:
    """面向现有 `nini` 代码的会话级任务服务。

    这里先用一个轻量 façade 包装底层 `TaskStore` / `TaskDispatcher`，
    让调用方统一传 `session_id`。后续把 `task_state`、`dispatch_agents`、
    `websocket` 接进来时，不需要知道具体存储细节。
    """

    def __init__(self, *, base_dir: str | Path | None = None) -> None:
        self._base_dir = Path(base_dir) if base_dir is not None else None
        self._dispatchers: dict[str, TaskDispatcher] = {}

    def _dispatcher(self, session_id: str) -> TaskDispatcher:
        normalized = str(session_id or "").strip()
        if not normalized:
            raise ValueError("session_id 不能为空")
        dispatcher = self._dispatchers.get(normalized)
        if dispatcher is not None:
            return dispatcher

        session_dir = Path(normalized)
        if self._base_dir is not None:
            session_dir = self._base_dir / normalized
        storage_path = session_dir / "todo_state.json"
        hooks = TaskHookRegistry()
        hooks.register(self._log_hook)
        dispatcher = TaskDispatcher(TaskStore(storage_path=storage_path, hook_registry=hooks))
        self._dispatchers[normalized] = dispatcher
        return dispatcher

    def _log_hook(self, event: TaskEvent, task: Task | None) -> None:
        """默认日志 hook。"""
        LoggingTaskHook()(event, task)

    def create_task(self, session_id: str, **kwargs) -> Task:
        kwargs.pop("actor_id", None)
        return self._dispatcher(session_id).create_task(**kwargs)

    def get_task(self, session_id: str, task_id: str) -> Task:
        return self._dispatcher(session_id).get_task(task_id)

    def list_tasks(self, session_id: str, *, status: TaskStatus | None = None) -> list[Task]:
        return self._dispatcher(session_id).list_tasks(status=status)

    def update_task(self, session_id: str, task_id: str, **kwargs) -> Task:
        kwargs.pop("actor_id", None)
        return self._dispatcher(session_id).update_task(task_id, **kwargs)

    def delete_task(self, session_id: str, task_id: str, **kwargs) -> Task:
        return self._dispatcher(session_id).delete_task(task_id, **kwargs)

    def claim_next_task(self, session_id: str, *, agent_id: str) -> Task | None:
        return self._dispatcher(session_id).claim_next_task(agent_id)

    def claim_task(self, session_id: str, task_id: str, *, agent_id: str) -> Task:
        return self._dispatcher(session_id).assign_task(task_id, agent_id)

    def release_task(self, session_id: str, task_id: str, *, agent_id: str, **kwargs) -> Task:
        return self._dispatcher(session_id).release_task(task_id, agent_id, **kwargs)

    def start_task(self, session_id: str, task_id: str, *, agent_id: str, **kwargs) -> Task:
        return self._dispatcher(session_id).mark_in_progress(task_id, agent_id, **kwargs)

    def complete_task(
        self,
        session_id: str,
        task_id: str,
        *,
        agent_id: str | None = None,
        **kwargs,
    ) -> Task:
        note = kwargs.get("note")
        return self._dispatcher(session_id).store.transition_task(
            task_id,
            to_status=TaskStatus.DONE,
            actor_id=agent_id,
            message=note,
        )

    def fail_task(
        self,
        session_id: str,
        task_id: str,
        *,
        agent_id: str | None = None,
        **kwargs,
    ) -> Task:
        note = kwargs.get("note")
        return self._dispatcher(session_id).store.transition_task(
            task_id,
            to_status=TaskStatus.FAILED,
            actor_id=agent_id,
            message=note,
        )

    def cancel_task(self, session_id: str, task_id: str, **kwargs) -> Task:
        return self._dispatcher(session_id).cancel_task(task_id, **kwargs)

    def list_events(self, session_id: str, *, task_id: str | None = None) -> list[TaskEvent]:
        return self._dispatcher(session_id).store.list_events(task_id=task_id)


__all__ = [
    "InvalidTaskTransitionError",
    "Task",
    "TaskConflictError",
    "TaskDependencyError",
    "TaskDispatcher",
    "TaskEvent",
    "TaskEventType",
    "TaskHook",
    "TaskHookRegistry",
    "TaskNotFoundError",
    "TaskStatus",
    "TaskStore",
    "TaskStoreError",
    "TodoService",
    "clone_event",
    "clone_task",
    "make_event_id",
    "make_task_id",
    "utc_now",
]
