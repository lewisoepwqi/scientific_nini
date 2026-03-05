"""工作区会话基础工具。"""

from __future__ import annotations

from typing import Any

from nini.agent.session import Session
from nini.tools.base import Skill, SkillResult
from nini.tools.edit_file import EditFile
from nini.tools.fetch_url import FetchURLSkill
from nini.tools.organize_workspace import OrganizeWorkspaceSkill
from nini.tools.workspace_files import ListWorkspaceFilesSkill


class WorkspaceSessionSkill(Skill):
    """统一工作区读写与抓取入口。"""

    def __init__(self) -> None:
        self._edit = EditFile()
        self._fetch = FetchURLSkill()
        self._organize = OrganizeWorkspaceSkill()
        self._list = ListWorkspaceFilesSkill()

    @property
    def name(self) -> str:
        return "workspace_session"

    @property
    def category(self) -> str:
        return "utility"

    @property
    def description(self) -> str:
        return "统一管理工作区文件列表、读取、写入、编辑、整理和 URL 抓取。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["list", "read", "write", "append", "edit", "organize", "fetch_url"],
                },
            },
            "required": ["operation"],
            "additionalProperties": True,
        }

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        operation = str(kwargs.get("operation", "")).strip()
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
        return SkillResult(success=False, message=f"不支持的 operation: {operation}")
