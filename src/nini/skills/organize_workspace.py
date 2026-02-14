"""工作区整理技能。"""

from __future__ import annotations

from typing import Any

from nini.agent.session import Session
from nini.skills.base import Skill, SkillResult
from nini.workspace import WorkspaceManager


class OrganizeWorkspaceSkill(Skill):
    """允许 Agent 创建文件夹并移动文件到目标文件夹。"""

    @property
    def name(self) -> str:
        return "organize_workspace"

    @property
    def category(self) -> str:
        return "utility"

    @property
    def description(self) -> str:
        return "创建工作区文件夹并移动文件，用于整理数据集/产物/笔记。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "create_folders": {
                    "type": "array",
                    "description": "要创建的文件夹列表",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "文件夹名称"},
                            "parent": {
                                "type": ["string", "null"],
                                "description": "可选，父文件夹 ID",
                            },
                        },
                        "required": ["name"],
                    },
                },
                "moves": {
                    "type": "array",
                    "description": "文件移动操作列表",
                    "items": {
                        "type": "object",
                        "properties": {
                            "file_id": {"type": "string", "description": "待移动文件 ID"},
                            "folder_id": {
                                "type": ["string", "null"],
                                "description": "目标文件夹 ID，null 表示移动到根目录",
                            },
                            "folder_name": {
                                "type": "string",
                                "description": "目标文件夹名称（与 folder_id 二选一）",
                            },
                        },
                        "required": ["file_id"],
                    },
                },
                "auto_create_folder": {
                    "type": "boolean",
                    "default": False,
                    "description": "当按 folder_name 移动但文件夹不存在时，是否自动创建",
                },
            },
            "required": [],
        }

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        manager = WorkspaceManager(session.id)
        create_folders = kwargs.get("create_folders") or []
        moves = kwargs.get("moves") or []
        auto_create = bool(kwargs.get("auto_create_folder", False))

        if not isinstance(create_folders, list) or not isinstance(moves, list):
            return SkillResult(
                success=False, message="参数格式错误：create_folders 与 moves 必须为数组"
            )
        if not create_folders and not moves:
            return SkillResult(success=False, message="请至少提供 create_folders 或 moves 中的一项")

        errors: list[str] = []
        created: list[dict[str, Any]] = []
        reused: list[dict[str, Any]] = []
        moved: list[dict[str, Any]] = []

        existing_folders = manager.list_folders()
        folder_by_name: dict[tuple[str, str | None], str] = {}
        for folder in existing_folders:
            name = str(folder.get("name", "")).strip()
            if not name:
                continue
            parent = folder.get("parent")
            parent_id = str(parent) if isinstance(parent, str) and parent else None
            folder_id = str(folder.get("id", "")).strip()
            if folder_id:
                folder_by_name[(name, parent_id)] = folder_id

        for idx, item in enumerate(create_folders):
            if not isinstance(item, dict):
                errors.append(f"create_folders[{idx}] 必须是对象")
                continue
            raw_name = item.get("name")
            if not isinstance(raw_name, str) or not raw_name.strip():
                errors.append(f"create_folders[{idx}] 缺少有效的 name")
                continue
            name = raw_name.strip()
            raw_parent = item.get("parent")
            parent = (
                str(raw_parent).strip()
                if isinstance(raw_parent, str) and raw_parent.strip()
                else None
            )
            key = (name, parent)
            exists = folder_by_name.get(key)
            if exists:
                reused.append({"name": name, "parent": parent, "id": exists})
                continue
            folder = manager.create_folder(name=name, parent=parent)
            folder_id = str(folder.get("id", "")).strip()
            if folder_id:
                folder_by_name[key] = folder_id
            created.append(folder)

        for idx, item in enumerate(moves):
            if not isinstance(item, dict):
                errors.append(f"moves[{idx}] 必须是对象")
                continue

            file_id = item.get("file_id")
            if not isinstance(file_id, str) or not file_id.strip():
                errors.append(f"moves[{idx}] 缺少有效的 file_id")
                continue

            folder_id: str | None = None
            if "folder_id" in item:
                raw_folder_id = item.get("folder_id")
                if raw_folder_id is None:
                    folder_id = None
                elif isinstance(raw_folder_id, str) and raw_folder_id.strip():
                    folder_id = raw_folder_id.strip()
                else:
                    errors.append(f"moves[{idx}] 的 folder_id 无效")
                    continue
            elif isinstance(item.get("folder_name"), str) and item["folder_name"].strip():
                folder_name = item["folder_name"].strip()
                parent = None
                key = (folder_name, parent)
                folder_id = folder_by_name.get(key)
                if folder_id is None and auto_create:
                    folder = manager.create_folder(name=folder_name, parent=parent)
                    folder_id = str(folder.get("id", "")).strip() or None
                    if folder_id:
                        folder_by_name[key] = folder_id
                        created.append(folder)
                if folder_id is None:
                    errors.append(f"moves[{idx}] 指定的 folder_name 不存在: {folder_name}")
                    continue

            updated = manager.move_file(file_id.strip(), folder_id)
            if updated is None:
                errors.append(f"moves[{idx}] 文件不存在: {file_id}")
                continue
            moved.append(
                {
                    "file_id": file_id.strip(),
                    "folder_id": folder_id,
                    "file_name": updated.get("name"),
                }
            )

        summary = (
            f"已创建 {len(created)} 个文件夹，"
            f"复用 {len(reused)} 个文件夹，"
            f"移动 {len(moved)} 个文件"
        )
        if errors:
            summary += f"，失败 {len(errors)} 个操作"

        return SkillResult(
            success=len(errors) == 0,
            message=summary,
            data={
                "created_folders": created,
                "reused_folders": reused,
                "moved_files": moved,
                "errors": errors,
            },
        )
