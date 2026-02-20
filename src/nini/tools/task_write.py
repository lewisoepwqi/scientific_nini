"""task_write 技能 —— LLM 自驱动任务规划工具。

LLM 通过此工具声明分析任务列表并实时更新任务状态，
类似 Claude Code 的 TodoWrite，使任务规划对用户透明可见。
"""

from __future__ import annotations

import logging
from typing import Any

from nini.agent.session import Session
from nini.tools.base import Skill, SkillResult

logger = logging.getLogger(__name__)


class TaskWriteSkill(Skill):
    """管理分析任务列表。

    使用规范：
    - 开始分析前：mode="init" 声明全部任务（status 全为 pending）
    - 开始每个任务前：mode="update" 将该任务改为 in_progress
    - 完成每个任务后：mode="update" 将该任务改为 completed
    - 全部 completed 后：输出最终总结，不再调用任何工具
    """

    @property
    def name(self) -> str:
        return "task_write"

    @property
    def description(self) -> str:
        return (
            "管理分析任务列表。在开始多步分析前，用 mode='init' 声明全部任务；"
            "执行过程中用 mode='update' 实时更新任务状态（pending/in_progress/completed）。"
            "全部任务 completed 后，直接输出最终总结，不再调用其他工具。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["init", "update"],
                    "description": (
                        "init=初始化完整任务列表（首次调用，包含所有计划步骤）；"
                        "update=更新部分任务状态（仅包含状态有变化的任务）"
                    ),
                },
                "tasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {
                                "type": "integer",
                                "description": "任务 ID，从 1 开始，更新时与初始化时一致",
                            },
                            "title": {
                                "type": "string",
                                "description": "任务标题，简洁描述要完成的事情",
                            },
                            "status": {
                                "type": "string",
                                "enum": ["pending", "in_progress", "completed"],
                                "description": "任务状态",
                            },
                            "tool_hint": {
                                "type": "string",
                                "description": "（可选）预期使用的工具名称，如 t_test、create_chart",
                            },
                        },
                        "required": ["id", "status"],
                    },
                    "description": "任务列表。init 时提供全部任务；update 时仅提供状态变更的任务",
                    "minItems": 1,
                },
            },
            "required": ["mode", "tasks"],
        }

    @property
    def expose_to_llm(self) -> bool:
        return True

    @property
    def category(self) -> str:
        return "utility"

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        """执行任务列表管理。"""
        mode = str(kwargs.get("mode", "init")).strip()
        raw_tasks = kwargs.get("tasks", [])

        if not isinstance(raw_tasks, list) or not raw_tasks:
            return SkillResult(
                success=False,
                message="tasks 参数不能为空列表",
            )

        if mode == "init":
            return self._handle_init(session, raw_tasks)
        elif mode == "update":
            return self._handle_update(session, raw_tasks)
        else:
            return SkillResult(
                success=False,
                message=f"不支持的 mode: {mode}，请使用 init 或 update",
            )

    def _handle_init(self, session: Session, raw_tasks: list[dict[str, Any]]) -> SkillResult:
        """初始化任务列表。"""
        new_manager = session.task_manager.init_tasks(raw_tasks)
        session.task_manager = new_manager

        task_count = len(new_manager.tasks)
        logger.info(
            "task_write init: session=%s 声明了 %d 个任务",
            session.id,
            task_count,
        )

        return SkillResult(
            success=True,
            message=f"已声明 {task_count} 个分析任务，请按顺序执行并更新状态。",
            data={
                "mode": "init",
                "task_count": task_count,
                "tasks": [t.to_dict() for t in new_manager.tasks],
                "all_completed": False,
                "pending_count": task_count,
            },
            metadata={"is_task_write": True},
        )

    def _handle_update(self, session: Session, raw_tasks: list[dict[str, Any]]) -> SkillResult:
        """更新任务状态。"""
        if not session.task_manager.initialized:
            # 未初始化时，将 update 视为 init
            return self._handle_init(session, raw_tasks)

        new_manager = session.task_manager.update_tasks(raw_tasks)
        session.task_manager = new_manager

        updated_ids = [t.get("id") for t in raw_tasks if "id" in t]
        all_done = new_manager.all_completed()
        pending = new_manager.pending_count()

        logger.info(
            "task_write update: session=%s 更新任务 %s, all_completed=%s",
            session.id,
            updated_ids,
            all_done,
        )

        if all_done:
            message = (
                "所有任务已完成。请直接向用户输出最终分析总结，不要再调用任何工具。"
            )
        else:
            message = f"任务状态已更新，还有 {pending} 个任务待完成。"

        return SkillResult(
            success=True,
            message=message,
            data={
                "mode": "update",
                "updated_ids": updated_ids,
                "all_completed": all_done,
                "pending_count": pending,
                "tasks": [t.to_dict() for t in new_manager.tasks],
            },
            metadata={"is_task_write": True},
        )
