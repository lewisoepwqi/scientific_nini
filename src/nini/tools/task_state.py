"""任务状态基础工具。"""

from __future__ import annotations

from typing import Any

from nini.agent.session import Session
from nini.tools.base import Tool, ToolResult
from nini.tools.task_write import TaskWriteTool


class TaskStateTool(Tool):
    """统一任务状态读写接口。"""

    def __init__(self) -> None:
        self._delegate = TaskWriteTool()

    @property
    def name(self) -> str:
        return "task_state"

    @property
    def category(self) -> str:
        return "utility"

    @property
    def description(self) -> str:
        return (
            "统一管理任务状态。支持初始化(init)、更新(update)、查询全部任务(get)和查询当前任务(current)。\n"
            "最小示例：\n"
            "- 初始化任务：{operation: init, tasks: [{id: 1, title: 加载数据, status: pending}]}\n"
            "- 更新任务：{operation: update, tasks: [{id: 2, status: in_progress}]}\n"
            "- 查询全部：{operation: get}\n"
            "- 查询当前：{operation: current}\n"
            "参数约束：init/update 必须提供 tasks；init 中每个任务至少需要 id、title、status，"
            "update 中每个任务至少需要 id、status。"
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
                                "enum": [
                                    "pending",
                                    "in_progress",
                                    "completed",
                                    "failed",
                                    "skipped",
                                ],
                            },
                            "tool_hint": {"type": "string"},
                        },
                        "oneOf": [
                            {
                                "type": "object",
                                "required": ["id", "title", "status"],
                            },
                            {
                                "type": "object",
                                "required": ["id", "status"],
                            },
                        ],
                        "required": ["id", "status"],
                        "additionalProperties": False,
                    },
                    "description": "init/update 时传入的任务列表",
                },
            },
            "required": ["operation"],
            "additionalProperties": False,
            "oneOf": [
                {
                    "type": "object",
                    "properties": {"operation": {"const": "init"}},
                    "required": ["operation", "tasks"],
                },
                {
                    "type": "object",
                    "properties": {"operation": {"const": "update"}},
                    "required": ["operation", "tasks"],
                },
                {
                    "type": "object",
                    "properties": {"operation": {"const": "get"}},
                    "required": ["operation"],
                },
                {
                    "type": "object",
                    "properties": {"operation": {"const": "current"}},
                    "required": ["operation"],
                },
            ],
        }

    async def execute(self, session: Session, **kwargs: Any) -> ToolResult:
        operation = str(kwargs.get("operation", "")).strip()

        if operation in {"init", "update"}:
            tasks = kwargs.get("tasks", [])
            if not isinstance(tasks, list) or not tasks:
                return self._input_error(
                    operation=operation,
                    error_code="TASK_STATE_TASKS_REQUIRED",
                    message=f"{operation} 操作必须提供非空 tasks 列表",
                    expected_fields=["operation", "tasks"],
                    recovery_hint="请传入非空 tasks 列表；init 需声明全部任务，update 只传状态有变化的任务。",
                    minimal_example=self._minimal_example_for_operation(operation),
                )
            return await self._delegate.execute(session, mode=operation, tasks=tasks)

        if operation == "get":
            if not session.task_manager.initialized:
                return ToolResult(
                    success=True, message="当前尚未初始化任务列表", data={"tasks": []}
                )
            tasks = [task.to_dict() for task in session.task_manager.tasks]
            return ToolResult(
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
                return ToolResult(success=True, message="当前尚未初始化任务列表", data={})
            current = session.task_manager.current_in_progress()
            if current is None:
                return ToolResult(success=True, message="当前没有执行中的任务", data={})
            return ToolResult(
                success=True,
                message=f"当前执行中的任务是：{current.title}",
                data={
                    "task": current.to_dict(),
                    "pending_count": session.task_manager.pending_count(),
                    "all_completed": session.task_manager.all_completed(),
                },
            )

        return self._input_error(
            operation=operation,
            error_code="TASK_STATE_OPERATION_INVALID",
            message=f"不支持的 operation: {operation}",
            expected_fields=["operation"],
            recovery_hint="请将 operation 改为 init、update、get 或 current。",
            minimal_example=self._minimal_example_for_operation("init"),
        )

    def _input_error(
        self,
        *,
        operation: str,
        error_code: str,
        message: str,
        expected_fields: list[str],
        recovery_hint: str,
        minimal_example: str,
    ) -> ToolResult:
        payload = {
            "operation": operation,
            "error_code": error_code,
            "expected_fields": expected_fields,
            "recovery_hint": recovery_hint,
            "minimal_example": minimal_example,
        }
        return self.build_input_error(message=message, payload=payload)

    def _minimal_example_for_operation(self, operation: str) -> str:
        examples = {
            "init": (
                '{operation: "init", tasks: ['
                '{id: 1, title: "加载数据", status: "pending"}]}'
            ),
            "update": (
                '{operation: "update", tasks: ['
                '{id: 2, status: "in_progress"}]}'
            ),
            "get": '{operation: "get"}',
            "current": '{operation: "current"}',
        }
        return examples.get(operation, '{operation: "init", tasks: [{id: 1, title: "加载数据", status: "pending"}]}')
