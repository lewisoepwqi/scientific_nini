"""task_write 技能 —— LLM 自驱动任务规划工具。

LLM 通过此工具声明分析任务列表并实时更新任务状态，
类似 Claude Code 的 TodoWrite，使任务规划对用户透明可见。
"""

from __future__ import annotations

import logging
from typing import Any

from nini.agent.session import Session
from nini.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)


class TaskWriteTool(Tool):
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

    async def execute(self, session: Session, **kwargs: Any) -> ToolResult:
        """执行任务列表管理。"""
        mode = str(kwargs.get("mode", "init")).strip()
        raw_tasks = kwargs.get("tasks", [])

        if not isinstance(raw_tasks, list) or not raw_tasks:
            return ToolResult(
                success=False,
                message="tasks 参数不能为空列表",
            )

        if mode == "init":
            return self._handle_init(session, raw_tasks)
        elif mode == "update":
            return self._handle_update(session, raw_tasks)
        else:
            return ToolResult(
                success=False,
                message=f"不支持的 mode: {mode}，请使用 init 或 update",
            )

    def _handle_init(self, session: Session, raw_tasks: list[dict[str, Any]]) -> ToolResult:
        """初始化任务列表。"""
        # 已有进行中任务时拒绝重置，避免 LLM 丢失执行进度
        if session.task_manager.initialized:
            in_progress = session.task_manager.current_in_progress()
            if in_progress:
                return ToolResult(
                    success=False,
                    message=(
                        f"任务列表已初始化且「{in_progress.title}」正在执行中，无法重新初始化。"
                        f"请继续执行当前任务，完成后调用 "
                        f"task_state(operation='update', tasks=[{{id:{in_progress.id}, status:'completed'}}]) "
                        f"推进到下一步。"
                    ),
                )

        new_manager = session.task_manager.init_tasks(raw_tasks)

        task_count = len(new_manager.tasks)
        first_task = new_manager.tasks[0] if new_manager.tasks else None

        # 自动将第一个任务设为 in_progress，省去 LLM 额外调用 task_state 的步骤
        if first_task:
            auto_start = new_manager.update_tasks([{"id": first_task.id, "status": "in_progress"}])
            new_manager = auto_start.manager
            first_task = new_manager.tasks[0]

        session.task_manager = new_manager
        logger.info(
            "task_write init: session=%s 声明了 %d 个任务，任务1 已自动开始",
            session.id,
            task_count,
        )

        # 引导 LLM 直接调用分析工具，而非再调 task_state
        if first_task:
            tool_hint = first_task.tool_hint or "dataset_catalog、code_session、stat_test"
            message = (
                f"已声明 {task_count} 个分析任务，"
                f"任务1「{first_task.title}」已自动开始。"
                f"请立即调用对应的分析工具（如 {tool_hint}）执行该任务，不要输出文本。"
            )
        else:
            message = f"已声明 {task_count} 个分析任务。"

        return ToolResult(
            success=True,
            message=message,
            data={
                "mode": "init",
                "task_count": task_count,
                "tasks": [t.to_dict() for t in new_manager.tasks],
                "all_completed": False,
                "pending_count": max(task_count - 1, 0),
            },
            metadata={"is_task_write": True},
        )

    def _handle_update(self, session: Session, raw_tasks: list[dict[str, Any]]) -> ToolResult:
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
        # 用 pending_count() 代替 remaining_count()，in_progress 不计入"待开始"
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

        # 消息中明确说明当前进行中任务，避免 LLM 误判更新未生效
        current_in_progress = result.manager.current_in_progress()

        # 检测无操作重复调用：任务状态未实际变化时返回差异化消息，打破 LLM 循环
        if result.no_op_ids:
            no_op_desc = "、".join(
                f"任务{t.id}「{t.title}」" for t in result.manager.tasks if t.id in result.no_op_ids
            )
            parts = [f"{no_op_desc}已处于请求的状态，无需重复设置。"]
            # 同时报告实际变更的任务，避免 LLM 忽视同批次的成功更新
            actually_changed = [tid for tid in updated_ids if tid not in result.no_op_ids]
            all_changed_ids = actually_changed + result.auto_completed_ids
            if all_changed_ids:
                changed_descs = [
                    f"任务{t.id}「{t.title}」→{t.status}"
                    for t in result.manager.tasks
                    if t.id in all_changed_ids
                ]
                if changed_descs:
                    parts.append(f"同时已更新：{'、'.join(changed_descs)}。")
            if current_in_progress:
                parts.append(
                    f"请直接调用对应的分析工具执行任务{current_in_progress.id}"
                    f"「{current_in_progress.title}」。"
                )
            else:
                parts.append("请直接调用对应的分析工具执行任务。")
            message = "".join(parts)
        elif all_done:
            message = (
                "所有任务已完成。请输出最终分析总结，不要再调用任何工具。"
                "注意：总结应基于复盘后的最终结论，确保结果准确无误。"
            )
        elif current_in_progress and pending == 0:
            # 只剩当前执行中任务（通常是"复盘与检查"或"汇总结论"）
            message = (
                f"所有前序任务已完成，当前仅剩任务{current_in_progress.id}"
                f"「{current_in_progress.title}」。"
                "请直接检查前面的结果是否有明显错误，如有则修正，如无则直接输出最终总结。"
                "不要再调用 task_state，不要重复列举已完成的任务。"
            )
        elif current_in_progress:
            message = (
                f"任务{current_in_progress.id}「{current_in_progress.title}」已标记为进行中。"
                f"请立即调用对应工具执行该任务，完成后再调用 task_state(operation='update') 推进下一步。"
                f"（还有 {pending} 个任务待开始）"
            )
        else:
            message = f"任务状态已更新，还有 {pending} 个任务待开始。"

        return ToolResult(
            success=True,
            message=message,
            data={
                "mode": "update",
                "updated_ids": all_ids,
                "auto_completed_ids": result.auto_completed_ids,
                "no_op_ids": result.no_op_ids,
                "all_completed": all_done,
                "pending_count": pending,
                "tasks": [t.to_dict() for t in result.manager.tasks],
            },
            metadata={"is_task_write": True},
        )
