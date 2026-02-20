"""任务管理器 —— 支持 LLM 自驱动任务生命周期。

LLM 通过 task_write 工具声明并更新任务列表，TaskManager 管理其状态机。
immutable 风格：所有变更操作返回新对象，不修改原对象。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

TaskStatus = Literal["pending", "in_progress", "completed"]


@dataclass(frozen=True)
class TaskItem:
    """单个分析任务。"""

    id: int  # 1-based，与前端 plan_step_id 对齐
    title: str
    status: TaskStatus = "pending"
    tool_hint: str | None = None
    action_id: str | None = None  # 格式 "task_{id}"，用于 TASK_ATTEMPT 事件关联

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "tool_hint": self.tool_hint,
            "action_id": self.action_id,
        }


@dataclass
class TaskManager:
    """管理会话内的任务列表。

    使用 immutable 风格：init_tasks/update_tasks 返回新的 TaskManager 实例。
    原实例保持不变，调用方用返回值替换 session.task_manager。
    """

    tasks: list[TaskItem] = field(default_factory=list)
    initialized: bool = False

    def init_tasks(self, raw_tasks: list[dict[str, Any]]) -> "TaskManager":
        """用完整任务列表初始化，返回新的 TaskManager。"""
        items: list[TaskItem] = []
        for t in raw_tasks:
            task_id = int(t.get("id", len(items) + 1))
            items.append(
                TaskItem(
                    id=task_id,
                    title=str(t.get("title", f"任务 {task_id}")),
                    status=t.get("status", "pending"),
                    tool_hint=t.get("tool_hint") or None,
                    action_id=f"task_{task_id}",
                )
            )
        return TaskManager(tasks=items, initialized=True)

    def update_tasks(self, raw_updates: list[dict[str, Any]]) -> "TaskManager":
        """按 id 更新部分任务状态，返回新的 TaskManager。未出现在 raw_updates 中的任务保持不变。"""
        update_map: dict[int, dict[str, Any]] = {int(t["id"]): t for t in raw_updates if "id" in t}
        new_tasks: list[TaskItem] = []
        for task in self.tasks:
            if task.id in update_map:
                upd = update_map[task.id]
                new_tasks.append(
                    TaskItem(
                        id=task.id,
                        title=str(upd.get("title", task.title)),
                        status=upd.get("status", task.status),
                        tool_hint=upd.get("tool_hint", task.tool_hint),
                        action_id=task.action_id,
                    )
                )
            else:
                new_tasks.append(task)
        return TaskManager(tasks=new_tasks, initialized=self.initialized)

    def all_completed(self) -> bool:
        """所有任务均已 completed（无任何 pending 或 in_progress）。"""
        return bool(self.tasks) and all(t.status == "completed" for t in self.tasks)

    def has_tasks(self) -> bool:
        """是否已声明了任务。"""
        return self.initialized and bool(self.tasks)

    def current_in_progress(self) -> TaskItem | None:
        """返回当前第一个 in_progress 状态的任务（用于 TASK_ATTEMPT 事件的 action_id 关联）。"""
        for t in self.tasks:
            if t.status == "in_progress":
                return t
        return None

    def to_analysis_plan_dict(self) -> dict[str, Any]:
        """转换为前端 ANALYSIS_PLAN 事件的 data 格式（兼容 store.ts 现有处理逻辑）。"""
        return {
            "steps": [
                {
                    "id": t.id,
                    "title": t.title,
                    "tool_hint": t.tool_hint,
                    "status": t.status,
                    "action_id": t.action_id,
                }
                for t in self.tasks
            ],
            "raw_text": "",
        }

    def pending_count(self) -> int:
        """待完成任务数。"""
        return sum(1 for t in self.tasks if t.status in ("pending", "in_progress"))
