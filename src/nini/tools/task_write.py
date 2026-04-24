"""task_write 技能 —— LLM 自驱动任务规划工具。

LLM 通过此工具声明分析任务列表并实时更新任务状态，
类似 Claude Code 的 TodoWrite，使任务规划对用户透明可见。
"""

from __future__ import annotations

import logging
from typing import Any

from nini.agent.task_manager import TaskManager
from nini.agent.session import Session
from nini.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)

_TASK_STATUS_ENUM = ["pending", "in_progress", "completed", "failed", "blocked", "skipped"]


def _task_metadata_properties() -> dict[str, Any]:
    """任务扩展元数据字段。"""
    return {
        "executor": {
            "type": "string",
            "enum": ["main_agent", "subagent", "local_tool"],
            "description": "（可选）执行器类型",
        },
        "owner": {
            "type": "string",
            "description": "（可选）责任归属，如 main、data_cleaner、statistician",
        },
        "input_refs": {
            "type": "array",
            "items": {"type": "string"},
            "description": "（可选）任务输入引用列表，如 dataset:raw.v1",
        },
        "output_refs": {
            "type": "array",
            "items": {"type": "string"},
            "description": "（可选）任务输出引用列表，如 dataset:cleaned.v1",
        },
        "handoff_contract": {
            "type": "object",
            "description": "（可选）任务交接契约，供下游任务消费",
        },
        "tool_profile": {
            "type": "string",
            "description": "（可选）子 Agent 工具档位，如 analysis_execution",
        },
        "failure_policy": {
            "type": "string",
            "enum": ["stop_pipeline", "allow_partial", "retryable"],
            "description": "（可选）失败处理策略",
        },
        "acceptance_checks": {
            "type": "array",
            "items": {"type": "string"},
            "description": "（可选）主 Agent 验收检查项",
        },
    }


def _build_init_task_item_schema() -> dict[str, Any]:
    """构造 init 分支的任务项 schema。"""
    return {
        "type": "object",
        "properties": {
            "id": {
                "type": "integer",
                "description": "任务 ID，从 1 开始，初始化后保持稳定",
            },
            "title": {
                "type": "string",
                "description": "任务标题，简洁描述要完成的事情",
            },
            "status": {
                "type": "string",
                "enum": ["pending"],
                "description": (
                    "任务初始状态。init 只允许 pending；若模型误传其他状态，"
                    "运行时也会自动按 pending 归一化。"
                ),
            },
            "tool_hint": {
                "type": "string",
                "description": "（可选）预期使用的工具名称，如 t_test、create_chart",
            },
            "depends_on": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "（可选）依赖的前置任务 ID 列表",
            },
            **_task_metadata_properties(),
        },
        "required": ["id", "title", "status"],
        "additionalProperties": False,
    }


def _build_update_task_item_schema() -> dict[str, Any]:
    """构造 update 分支的任务项 schema。"""
    return {
        "type": "object",
        "properties": {
            "id": {
                "type": "integer",
                "description": "任务 ID，从 1 开始，更新时与初始化时一致",
            },
            "title": {
                "type": "string",
                "description": "（可选）更新后的任务标题",
            },
            "status": {
                "type": "string",
                "enum": _TASK_STATUS_ENUM,
                "description": (
                    "任务状态：pending=待执行, in_progress=执行中, "
                    "completed=已完成, failed=确认失败, skipped=因依赖失败跳过"
                ),
            },
            "tool_hint": {
                "type": "string",
                "description": "（可选）预期使用的工具名称，如 t_test、create_chart",
            },
            **_task_metadata_properties(),
        },
        "required": ["id", "status"],
        "additionalProperties": False,
    }


def _build_generic_task_item_schema() -> dict[str, Any]:
    """构造顶层通用任务项 schema，兼容 provider 对顶层 properties 的依赖。"""
    return {
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
                "enum": _TASK_STATUS_ENUM,
                "description": (
                    "任务状态：pending=待执行, in_progress=执行中, "
                    "completed=已完成, failed=确认失败, skipped=因依赖失败跳过"
                ),
            },
            "tool_hint": {
                "type": "string",
                "description": "（可选）预期使用的工具名称，如 t_test、create_chart",
            },
            "depends_on": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "（可选）依赖的前置任务 ID 列表",
            },
            **_task_metadata_properties(),
        },
        "required": ["id", "status"],
        "additionalProperties": False,
    }


class TaskWriteTool(Tool):
    """管理分析任务列表（PDCA 闭环）。

    使用规范：
    - Plan：mode="init" 声明全部任务（最后一个任务应为「复盘与检查」）
    - Do：mode="update" 显式更新当前任务状态（例如 pending → in_progress）
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
            "init 只声明任务，不会自动开始执行，所有任务初始状态都应为 pending；"
            "Do：mode='update' 显式更新任务状态（例如将某任务标记为 in_progress 或 completed）；"
            "Check：执行复盘任务时回顾所有结果并修正问题；"
            "Act：复盘完成后输出最终总结。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        init_task_items = _build_init_task_item_schema()
        update_task_items = _build_update_task_item_schema()
        generic_task_items = _build_generic_task_item_schema()
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
                    "items": generic_task_items,
                    "description": (
                        "任务列表。init 时提供全部任务且初始状态必须为 pending；"
                        "update 时仅提供状态变更的任务。"
                    ),
                    "minItems": 1,
                },
            },
            "required": ["mode", "tasks"],
            "additionalProperties": False,
            "oneOf": [
                {
                    "type": "object",
                    "properties": {
                        "mode": {
                            "type": "string",
                            "const": "init",
                            "description": "初始化完整任务列表（首次调用，包含所有计划步骤）",
                        },
                        "tasks": {
                            "type": "array",
                            "items": init_task_items,
                            "description": "完整任务列表。init 只声明任务，所有任务初始状态必须为 pending",
                            "minItems": 1,
                        },
                    },
                    "required": ["mode", "tasks"],
                    "additionalProperties": False,
                },
                {
                    "type": "object",
                    "properties": {
                        "mode": {
                            "type": "string",
                            "const": "update",
                            "description": "更新部分任务状态（仅包含状态有变化的任务）",
                        },
                        "tasks": {
                            "type": "array",
                            "items": update_task_items,
                            "description": "状态变更任务列表。update 时只传状态有变化的任务",
                            "minItems": 1,
                        },
                    },
                    "required": ["mode", "tasks"],
                    "additionalProperties": False,
                },
            ],
        }

    def _input_error(
        self,
        *,
        mode: str,
        error_code: str,
        message: str,
        expected_fields: list[str],
        recovery_hint: str,
        minimal_example: str,
    ) -> ToolResult:
        payload = {
            "mode": mode,
            "error_code": error_code,
            "expected_fields": expected_fields,
            "recovery_hint": recovery_hint,
            "minimal_example": minimal_example,
        }
        return self.build_input_error(message=message, payload=payload)

    def _minimal_example_for_mode(self, mode: str) -> str:
        examples = {
            "init": '{mode: "init", tasks: [{id: 1, title: "加载数据", status: "pending"}]}',
            "update": '{mode: "update", tasks: [{id: 1, status: "in_progress"}]}',
        }
        return examples.get(
            mode, '{mode: "init", tasks: [{id: 1, title: "加载数据", status: "pending"}]}'
        )

    @property
    def expose_to_llm(self) -> bool:
        return True

    @property
    def category(self) -> str:
        return "utility"

    async def execute(self, session: Session, **kwargs: Any) -> ToolResult:
        """执行任务列表管理。"""
        mode = str(kwargs.get("mode", "")).strip()
        raw_tasks = kwargs.get("tasks", [])

        if not mode:
            return self._input_error(
                mode=mode,
                error_code="TASK_WRITE_MODE_REQUIRED",
                message="缺少 mode，请指定 init 或 update",
                expected_fields=["mode", "tasks"],
                recovery_hint="首次声明任务列表用 init，后续状态推进用 update。",
                minimal_example=self._minimal_example_for_mode("init"),
            )

        if not isinstance(raw_tasks, list) or not raw_tasks:
            return self._input_error(
                mode=mode,
                error_code="TASK_WRITE_TASKS_REQUIRED",
                message="tasks 参数不能为空列表",
                expected_fields=["mode", "tasks"],
                recovery_hint="请传入非空 tasks 列表；init 需声明全部任务，update 只传状态有变化的任务。",
                minimal_example=self._minimal_example_for_mode(mode),
            )

        if mode == "init":
            return self._handle_init(session, raw_tasks)
        elif mode == "update":
            return self._handle_update(session, raw_tasks)
        else:
            return self._input_error(
                mode=mode,
                error_code="TASK_WRITE_MODE_INVALID",
                message=f"不支持的 mode: {mode}，请使用 init 或 update",
                expected_fields=["mode", "tasks"],
                recovery_hint="请将 mode 改为 init 或 update。",
                minimal_example=self._minimal_example_for_mode("init"),
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
                        f"请继续执行当前任务。"
                    ),
                )

        normalization = TaskManager.normalize_init_task_payload(raw_tasks)
        new_manager = session.task_manager.init_tasks(normalization.tasks)

        task_count = len(new_manager.tasks)
        first_task = new_manager.tasks[0] if new_manager.tasks else None

        session.task_manager = new_manager
        logger.info(
            "task_write init: session=%s 声明了 %d 个任务，等待模型显式推进状态，归一化任务=%s",
            session.id,
            task_count,
            normalization.normalized_task_ids,
        )

        # 由模型显式推进任务状态，避免运行时替模型隐式修改任务板
        warning_prefix = ""
        if normalization.normalized_task_ids:
            warning_prefix = (
                f"已将任务{','.join(str(task_id) for task_id in normalization.normalized_task_ids)}"
                "的初始状态归一化为 pending。"
            )
        dependency_prefix = ""
        if normalization.normalized_dependencies:
            normalized_dep_ids = "、".join(
                f"任务{item['task_id']}" for item in normalization.normalized_dependencies
            )
            dependency_prefix = f"已按高置信线性流水线补全 {normalized_dep_ids} 的 depends_on。"
        warning_suffix = ""
        if normalization.normalization_warnings:
            warning_suffix = "检测到依赖歧义，系统未自动改写任务图，请后续按当前任务顺序谨慎推进。"
        if first_task:
            tool_hint_text = f"（可使用 {first_task.tool_hint}）" if first_task.tool_hint else ""
            # 注意：不要再写"再执行对应的分析操作"这类串行模板指令，否则
            # 当 LLM 在同一批次并行调用 task_state(init) 与分析工具时，会在下一轮
            # 盲目重复执行已成功的分析工具（触发 DUPLICATE_*_CALL 守卫）。
            message = (
                warning_prefix + dependency_prefix + f"已声明 {task_count} 个分析任务。"
                f"建议从任务1「{first_task.title}」开始{tool_hint_text}，"
                f"请将其标为 in_progress。"
                "若本批次已并行调用过对应分析工具，请直接复用其结果推进下一步，"
                "不要重复调用同一工具。" + warning_suffix
            )
        else:
            message = (
                f"{warning_prefix}{dependency_prefix}已声明 {task_count} 个分析任务。"
                f"{warning_suffix}"
            )

        return ToolResult(
            success=True,
            message=message,
            data={
                "mode": "init",
                "task_count": task_count,
                "tasks": [t.to_dict() for t in new_manager.tasks],
                "all_completed": False,
                "pending_count": task_count,
                "normalized_task_ids": normalization.normalized_task_ids,
                "normalized_dependencies": normalization.normalized_dependencies,
                "normalization_warnings": normalization.normalization_warnings,
            },
            metadata={
                "is_task_write": True,
                "normalized_task_ids": normalization.normalized_task_ids,
                "normalized_dependencies": normalization.normalized_dependencies,
                "normalization_warnings": normalization.normalization_warnings,
            },
        )

    def _handle_update(self, session: Session, raw_tasks: list[dict[str, Any]]) -> ToolResult:
        """更新任务状态。"""
        if not session.task_manager.initialized:
            return self._input_error(
                mode="update",
                error_code="TASK_WRITE_NOT_INITIALIZED",
                message=("任务列表尚未初始化。请先声明完整任务列表，再更新状态。"),
                expected_fields=["mode", "tasks"],
                recovery_hint="请先用 init 声明完整任务列表，再用 update 推进状态。",
                minimal_example=self._minimal_example_for_mode("init"),
            )

        result = session.task_manager.update_tasks(raw_tasks)
        session.task_manager = result.manager

        updated_ids = [t.get("id") for t in raw_tasks if "id" in t]
        all_ids = updated_ids + result.auto_completed_ids
        all_done = result.manager.all_completed()
        # 用 pending_count() 代替 remaining_count()，in_progress 不计入"待开始"
        pending = result.manager.pending_count()

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
            parts = [f"{no_op_desc}已处于请求的状态。"]
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
                    f"当前任务：任务{current_in_progress.id}「{current_in_progress.title}」（进行中）。"
                )
            message = "".join(parts)
        elif all_done:
            message = (
                "所有任务已完成。请输出最终分析总结，不要再调用任何工具。"
                "注意：总结应基于复盘后的最终结论，确保结果准确无误。"
            )
        elif current_in_progress and pending == 0:
            # 最后一个任务（通常是"汇总结论"或"复盘检查"）：
            # 视为隐式自动完成——避免模型陷入"先 call 再总结"的两步循环。
            session.pending_auto_complete_task_id = current_in_progress.id
            message = (
                f"所有前序任务已完成，当前仅剩任务{current_in_progress.id}"
                f"「{current_in_progress.title}」。"
                "请**直接输出最终分析总结**，引用已生成的图表 artifact；"
                "本任务会在你回复后由系统自动标记为 completed，"
                "**不要再调用 task_state**。"
            )
        elif current_in_progress:
            hint_text = (
                f"（可使用 {current_in_progress.tool_hint}）"
                if current_in_progress.tool_hint
                else ""
            )
            next_pending = next((t for t in result.manager.tasks if t.status == "pending"), None)
            transition_reminder = ""
            if next_pending:
                transition_reminder = (
                    f" 完成后请先调用 task_state 将本任务标为 completed、"
                    f"再将任务{next_pending.id}「{next_pending.title}」标为 in_progress，"
                    "以解锁下一阶段工具。"
                )
            else:
                transition_reminder = " 完成后请调用 task_state 将本任务标为 completed。"
            message = (
                f"任务{current_in_progress.id}「{current_in_progress.title}」已标记为进行中"
                f"{hint_text}。"
                f"请直接执行分析操作，还有 {pending} 个任务待开始。"
                f"{transition_reminder}"
            )
        else:
            next_pending = next((t for t in result.manager.tasks if t.status == "pending"), None)
            if next_pending:
                message = (
                    f"任务状态已更新，还有 {pending} 个任务待开始。"
                    f"下一步：将「{next_pending.title}」标记为 in_progress 再执行。"
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
