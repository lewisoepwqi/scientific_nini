"""工作区会话基础工具。"""

from __future__ import annotations

from typing import Any

from nini.agent.session import Session
from nini.tools.base import Tool, ToolResult
from nini.tools.edit_file import EditFile
from nini.tools.fetch_url import FetchURLTool
from nini.tools.organize_workspace import OrganizeWorkspaceTool
from nini.tools.workspace_files import ListWorkspaceFilesTool


class WorkspaceSessionTool(Tool):
    """统一工作区读写与抓取入口。"""

    _OPERATIONS = ("list", "read", "write", "append", "edit", "organize", "fetch_url")

    def __init__(self) -> None:
        self._edit = EditFile()
        self._fetch = FetchURLTool()
        self._organize = OrganizeWorkspaceTool()
        self._list = ListWorkspaceFilesTool()

    @property
    def name(self) -> str:
        return "workspace_session"

    @property
    def category(self) -> str:
        return "utility"

    @property
    def description(self) -> str:
        return (
            "统一管理工作区文件列表、读取、写入、编辑、整理和 URL 抓取。"
            "最小示例："
            '1) 列表: {"operation":"list","query":"report"}；'
            '2) 读取: {"operation":"read","file_path":"notes/a.md"}；'
            '3) 写入: {"operation":"write","file_path":"notes/a.md","content":"..."}。'
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": list(self._OPERATIONS)},
                "query": {"type": "string"},
                "kinds": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["dataset", "document", "result", "artifact", "note"],
                    },
                },
                "path_prefix": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                "file_path": {"type": "string", "description": "工作区相对路径"},
                "encoding": {"type": "string", "default": "utf-8"},
                "content": {"type": "string"},
                "create_if_missing": {"type": "boolean", "default": True},
                "old_string": {"type": "string"},
                "new_string": {"type": "string"},
                "start_line": {"type": "integer", "minimum": 1},
                "end_line": {"type": "integer", "minimum": 1},
                "create_folders": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "moves": {
                    "type": "array",
                    "items": {"type": "object"},
                },
                "auto_create_folder": {"type": "boolean", "default": False},
                "url": {"type": "string"},
                "save_to": {"type": "string"},
            },
            "required": ["operation"],
            "additionalProperties": False,
        }

    async def execute(self, session: Session, **kwargs: Any) -> ToolResult:
        operation = str(kwargs.get("operation", "")).strip()
        validation_error = self._validate_operation_args(operation, kwargs)
        if validation_error is not None:
            return validation_error

        if operation == "list":
            return await self._list.execute(
                session,
                query=kwargs.get("query"),
                kinds=kwargs.get("kinds"),
                path_prefix=kwargs.get("path_prefix"),
                limit=kwargs.get("limit", 50),
            )
        if operation in {"read", "write", "append", "edit"}:
            return await self._edit.execute(
                session,
                file_path=kwargs.get("file_path"),
                operation=operation,
                content=kwargs.get("content"),
                old_string=kwargs.get("old_string"),
                new_string=kwargs.get("new_string"),
                start_line=kwargs.get("start_line"),
                end_line=kwargs.get("end_line"),
                encoding=kwargs.get("encoding", "utf-8"),
                create_if_missing=kwargs.get("create_if_missing", True),
            )
        if operation == "organize":
            return await self._organize.execute(
                session,
                create_folders=kwargs.get("create_folders") or [],
                moves=kwargs.get("moves") or [],
                auto_create_folder=kwargs.get("auto_create_folder", False),
            )
        if operation == "fetch_url":
            result = await self._fetch.execute(session, url=kwargs.get("url"))
            if not result.success:
                return result
            save_to = kwargs.get("save_to")
            if isinstance(save_to, str) and save_to.strip() and isinstance(result.data, dict):
                content = str(result.data.get("content", ""))
                write_result = await self._edit.execute(
                    session,
                    file_path=save_to.strip(),
                    operation="write",
                    content=content,
                    create_if_missing=True,
                )
                if not write_result.success:
                    return write_result
                result.data["saved_file"] = {
                    "path": save_to.strip(),
                    "resource_type": "file",
                }
            return result
        return self._invalid_operation_result(operation)

    def _validate_operation_args(self, operation: str, kwargs: dict[str, Any]) -> ToolResult | None:
        if not operation:
            return self._missing_operation_result(kwargs)
        if operation not in self._OPERATIONS:
            return self._invalid_operation_result(operation)

        required_fields: dict[str, tuple[str, ...]] = {
            "list": (),
            "read": ("file_path",),
            "write": ("file_path", "content"),
            "append": ("file_path", "content"),
            "edit": ("file_path",),
            "organize": (),
            "fetch_url": ("url",),
        }

        missing: list[str] = []
        for field in required_fields.get(operation, ()):
            value = kwargs.get(field)
            if isinstance(value, str):
                if not value.strip():
                    missing.append(field)
            elif value is None:
                missing.append(field)

        if not missing:
            return None

        return ToolResult(
            success=False,
            message=f"operation='{operation}' 缺少必要参数: {', '.join(missing)}",
            data={
                "error_code": "WORKSPACE_OPERATION_ARGS_MISSING",
                "operation": operation,
                "missing_fields": missing,
                "expected_operations": list(self._OPERATIONS),
                "recovery_hint": self._recovery_hint_for_operation(operation),
            },
            metadata={
                "error_code": "WORKSPACE_OPERATION_ARGS_MISSING",
                "operation": operation,
                "missing_fields": missing,
            },
        )

    def _missing_operation_result(self, kwargs: dict[str, Any]) -> ToolResult:
        provided_fields = sorted(
            key for key, value in kwargs.items() if key != "operation" and value is not None
        )
        return ToolResult(
            success=False,
            message="workspace_session 缺少 operation 参数。",
            data={
                "error_code": "WORKSPACE_OPERATION_REQUIRED",
                "expected_operations": list(self._OPERATIONS),
                "provided_fields": provided_fields,
                "recovery_hint": (
                    "请显式提供 operation，例如 "
                    '{"operation":"list"} 或 {"operation":"read","file_path":"notes/a.md"}。'
                ),
            },
            metadata={
                "error_code": "WORKSPACE_OPERATION_REQUIRED",
                "provided_fields": provided_fields,
            },
        )

    def _invalid_operation_result(self, operation: str) -> ToolResult:
        return ToolResult(
            success=False,
            message=f"不支持的 operation: {operation}",
            data={
                "error_code": "WORKSPACE_OPERATION_UNSUPPORTED",
                "expected_operations": list(self._OPERATIONS),
                "recovery_hint": (
                    "可用 operation: "
                    + ", ".join(self._OPERATIONS)
                    + "。例如先调用 {'operation':'list'} 获取 path。"
                ),
            },
            metadata={
                "error_code": "WORKSPACE_OPERATION_UNSUPPORTED",
                "operation": operation,
            },
        )

    def _recovery_hint_for_operation(self, operation: str) -> str:
        if operation == "read":
            return "read 需要 file_path，例如 {'operation':'read','file_path':'notes/a.md'}。"
        if operation in {"write", "append"}:
            return (
                f"{operation} 需要 file_path 和 content，"
                f"例如 {{'operation':'{operation}','file_path':'notes/a.md','content':'...'}}。"
            )
        if operation == "fetch_url":
            return (
                "fetch_url 需要 url，例如 {'operation':'fetch_url','url':'https://example.com'}。"
            )
        return "请根据 operation 补齐必要参数。"
