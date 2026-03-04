"""任务状态基础工具。"""

from __future__ import annotations

from typing import Any

from nini.agent.session import Session
from nini.tools.base import Skill, SkillResult
from nini.tools.task_write import TaskWriteSkill


class TaskStateSkill(Skill):
    """统一任务状态读写接口。"""

    def __init__(self) -> None:
        self._delegate = TaskWriteSkill()

    @property
    def name(self) -> str:
        return "task_state"

    @property
    def category(self) -> str:
        return "utility"

    @property
    def description(self) -> str:
        return (
            "统一管理任务状态。支持初始化(init)、更新(update)、查询全部任务(get)和查询当前任务(current)。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["init", "update", "get", "current"],
                    "description": "任务状态操作类型",
                },
                "tasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "title": {"type": "string"},
                            "status": {
                                "type": "string",
                                "enum": ["pending", "in_progress", "completed", "failed", "skipped"],
                            },
                            "tool_hint": {"type": "string"},
                        },
                        "required": ["id", "status"],
                    },
                    "description": "init/update 时传入的任务列表",
                },
            },
            "required": ["operation"],
        }

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        operation = str(kwargs.get("operation", "")).strip()

        if operation in {"init", "update"}:
            tasks = kwargs.get("tasks", [])
            return await self._delegate.execute(session, mode=operation, tasks=tasks)

        if operation == "get":
            if not session.task_manager.initialized:
                return SkillResult(success=True, message="当前尚未初始化任务列表", data={"tasks": []})
            tasks = [task.to_dict() for task in session.task_manager.tasks]
            return SkillResult(
                success=True,
                message=f"当前共有 {len(tasks)} 个任务",
                data={
                    "tasks": tasks,
                    "pending_count": session.task_manager.pending_count(),
                    "all_completed": session.task_manager.all_completed(),
                },
            )

        if operation == "current":
            if not session.task_manager.initialized:
                return SkillResult(success=True, message="当前尚未初始化任务列表", data={})
            current = session.task_manager.current_in_progress()
            if current is None:
                return SkillResult(success=True, message="当前没有执行中的任务", data={})
            return SkillResult(
                success=True,
                message=f"当前执行中的任务是：{current.title}",
                data={
                    "task": current.to_dict(),
                    "pending_count": session.task_manager.pending_count(),
                    "all_completed": session.task_manager.all_completed(),
                },
            )

        return SkillResult(success=False, message=f"不支持的 operation: {operation}")
