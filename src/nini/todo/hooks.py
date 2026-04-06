"""TODO 生命周期 Hook。"""

from __future__ import annotations

import logging
from collections.abc import Callable

from nini.todo.models import Task, TaskEvent, clone_event, clone_task

logger = logging.getLogger(__name__)

TaskHook = Callable[[TaskEvent, Task | None], None]


class TaskHookRegistry:
    """任务事件订阅器。"""

    def __init__(self) -> None:
        self._hooks: list[TaskHook] = []

    def register(self, hook: TaskHook) -> None:
        """注册 hook。"""
        if hook not in self._hooks:
            self._hooks.append(hook)

    def unregister(self, hook: TaskHook) -> None:
        """移除 hook。"""
        self._hooks = [item for item in self._hooks if item is not hook]

    def emit(self, event: TaskEvent, task: Task | None) -> None:
        """广播事件。"""
        safe_event = clone_event(event)
        safe_task = clone_task(task) if task is not None else None
        for hook in list(self._hooks):
            try:
                hook(safe_event, safe_task)
            except Exception:
                logger.warning("任务 hook 执行失败", exc_info=True)


class LoggingTaskHook:
    """默认日志 hook。"""

    def __call__(self, event: TaskEvent, task: Task | None) -> None:
        logger.info(
            "todo event: task=%s type=%s from=%s to=%s actor=%s",
            event.task_id,
            event.event_type.value,
            event.from_status.value if event.from_status else None,
            event.to_status.value if event.to_status else None,
            event.actor_id,
        )
