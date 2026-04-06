"""TODO 调度入口。"""

from __future__ import annotations

from nini.todo.models import Task, TaskStatus
from nini.todo.store import TaskStore


class TaskDispatcher:
    """面向 Agent worker 的任务协同入口。"""

    def __init__(self, store: TaskStore) -> None:
        self._store = store

    @property
    def store(self) -> TaskStore:
        """暴露底层 store，便于兼容层按需读取。"""
        return self._store

    def create_task(
        self,
        *,
        title: str,
        description: str = "",
        dependency_ids: list[str] | None = None,
        priority: int | None = None,
        metadata: dict | None = None,
    ) -> Task:
        """创建任务。"""
        return self._store.create_task(
            title=title,
            description=description,
            dependency_ids=dependency_ids,
            priority=priority,
            metadata=metadata,
        )

    def get_task(self, task_id: str) -> Task:
        """读取任务。"""
        return self._store.get_task(task_id)

    def list_tasks(self, *, status: TaskStatus | None = None) -> list[Task]:
        """列出任务。"""
        return self._store.list_tasks(status=status)

    def update_task(self, task_id: str, **kwargs) -> Task:
        """更新任务元数据。"""
        return self._store.update_task(task_id, **kwargs)

    def delete_task(self, task_id: str, *, actor_id: str | None = None) -> Task:
        """删除任务。"""
        return self._store.delete_task(task_id, actor_id=actor_id)

    def list_ready_tasks(self) -> list[Task]:
        """返回当前依赖已满足且可认领的任务。"""
        return self._store.list_ready_tasks()

    def claim_next_task(self, agent_id: str) -> Task | None:
        """认领下一个可执行任务。"""
        for task in self.list_ready_tasks():
            return self._store.claim_task(task.task_id, agent_id=agent_id)
        return None

    def assign_task(self, task_id: str, agent_id: str) -> Task:
        """显式认领指定任务。"""
        return self._store.claim_task(task_id, agent_id=agent_id)

    def release_task(self, task_id: str, agent_id: str, *, reason: str | None = None) -> Task:
        """释放任务。"""
        return self._store.release_task(task_id, agent_id=agent_id, message=reason)

    def mark_in_progress(
        self,
        task_id: str,
        agent_id: str,
        *,
        note: str | None = None,
    ) -> Task:
        """标记任务开始执行。"""
        return self._store.start_task(task_id, agent_id=agent_id, message=note)

    def mark_done(self, task_id: str, agent_id: str, *, note: str | None = None) -> Task:
        """标记任务完成。"""
        return self._store.complete_task(task_id, agent_id=agent_id, message=note)

    def mark_failed(self, task_id: str, agent_id: str, *, note: str | None = None) -> Task:
        """标记任务失败。"""
        return self._store.fail_task(task_id, agent_id=agent_id, message=note)

    def cancel_task(self, task_id: str, *, actor_id: str | None = None, note: str | None = None) -> Task:
        """取消任务。"""
        return self._store.cancel_task(task_id, actor_id=actor_id, message=note)

    # TODO: 后续在这里接入 dispatch_agents / spawner，使子 Agent 先 claim 再执行。

