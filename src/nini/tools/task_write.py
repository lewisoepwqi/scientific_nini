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
    """管理分析任务列表（PDCA 闭环）。

    使用规范：
    - Plan：mode="init" 声明全部任务（最后一个任务应为「复盘与检查」）
    - Do：mode="update" 将当前任务标记为 in_progress（前一个会自动完成）
    - Check：执行「复盘与检查」任务，回顾所有结果，发现问题则修正
    - Act：复盘完成后输出最终总结
    """

    @property
    def name(self) -> str:
        return "task_write"

    @property
    def description(self) -> str:
        return (
            "管理分析任务列表（PDCA 闭环）。"
            "Plan：mode='init' 声明全部任务，最后一个任务应为「复盘与检查」；"
            "Do：mode='update' 标记当前任务为 in_progress（前一个任务自动完成）；"
            "Check：执行复盘任务时回顾所有结果并修正问题；"
            "Act：复盘完成后输出最终总结。"
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
                                "enum": [
                                    "pending",
                                    "in_progress",
                                    "completed",
                                    "failed",
                                    "skipped",
                                ],
                                "description": "任务状态：pending=待执行, in_progress=执行中, completed=已完成, failed=确认失败, skipped=因依赖失败跳过",
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
            message=f"已声明 {task_count} 个分析任务。请按顺序执行，最后通过复盘检查确认结果无误后再输出总结。",
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
        """更新任务状态。

        当某个任务被设为 in_progress 时，之前处于 in_progress 的任务会自动标记为 completed。
        """
        if not session.task_manager.initialized:
            # 未初始化时，将 update 视为 init
            return self._handle_init(session, raw_tasks)

        result = session.task_manager.update_tasks(raw_tasks)
        session.task_manager = result.manager

        updated_ids = [t.get("id") for t in raw_tasks if "id" in t]
        all_ids = updated_ids + result.auto_completed_ids
        all_done = result.manager.all_completed()
        pending = result.manager.pending_count()

        if result.auto_completed_ids:
            logger.info(
                "task_write update: session=%s 更新任务 %s, 自动完成任务 %s, all_completed=%s",
                session.id,
                updated_ids,
                result.auto_completed_ids,
                all_done,
            )
        else:
            logger.info(
                "task_write update: session=%s 更新任务 %s, all_completed=%s",
                session.id,
                updated_ids,
                all_done,
            )

        if all_done:
            message = (
                "所有任务已完成。请输出最终分析总结，不要再调用任何工具。"
                "注意：总结应基于复盘后的最终结论，确保结果准确无误。"
            )
        elif pending == 1:
            # 只剩最后一个任务（通常是"复盘与检查"）
            message = (
                f"还有 {pending} 个任务待完成。"
                "请开始最后的复盘检查：回顾前面所有步骤的结果，"
                "检查方法选择、统计结果、图表和结论是否正确，发现问题立即修正。"
            )
        else:
            message = f"任务状态已更新，还有 {pending} 个任务待完成。"

        return SkillResult(
            success=True,
            message=message,
            data={
                "mode": "update",
                "updated_ids": all_ids,
                "auto_completed_ids": result.auto_completed_ids,
                "all_completed": all_done,
                "pending_count": pending,
                "tasks": [t.to_dict() for t in result.manager.tasks],
            },
            metadata={"is_task_write": True},
        )
