"""工作区文件浏览工具。"""

from __future__ import annotations

from typing import Any

from nini.agent.session import Session
from nini.tools.base import Skill, SkillResult
from nini.workspace import WorkspaceManager


class ListWorkspaceFilesSkill(Skill):
    """列出当前会话工作区中的文件，供模型获取 path 与 download_url。"""

    @property
    def name(self) -> str:
        return "list_workspace_files"

    @property
    def category(self) -> str:
        return "utility"

    @property
    def description(self) -> str:
        return (
            "列出当前会话工作区中的文件，返回 name、kind、path 和 download_url。"
            "适合在生成报告或文章前获取图表、报告、文稿的实际下载链接。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "可选。按文件名或路径模糊搜索。",
                },
                "kinds": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["dataset", "document", "result", "artifact", "note"],
                    },
                    "description": "可选。按文件类型过滤；artifact/note 会自动兼容映射为 result/document。",
                },
                "path_prefix": {
                    "type": "string",
                    "description": "可选。仅返回指定相对路径前缀下的文件。",
                },
                "limit": {
                    "type": "integer",
                    "default": 50,
                    "minimum": 1,
                    "maximum": 200,
                    "description": "最多返回多少条记录。",
                },
            },
            "required": [],
        }

    @property
    def is_idempotent(self) -> bool:
        return True

    @property
    def typical_use_cases(self) -> list[str]:
        return [
            "获取图表产物的实际 download_url",
            "在生成文章前查询工作区中的报告或文稿文件",
            "按关键词过滤工作区文件，避免使用 run_code 探查目录",
        ]

    @property
    def output_types(self) -> list[str]:
        return ["file", "text"]

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        manager = WorkspaceManager(session.id)
        query = str(kwargs.get("query") or "").strip()
        path_prefix = str(kwargs.get("path_prefix") or "").strip().strip("/")
        limit_raw = kwargs.get("limit", 50)
        kinds_raw = kwargs.get("kinds")

        limit = 50
        if isinstance(limit_raw, int):
            limit = max(1, min(limit_raw, 200))

        kinds: set[str] | None = None
        if isinstance(kinds_raw, list):
            normalized = {
                {"artifact": "result", "note": "document"}.get(
                    str(item).strip(),
                    str(item).strip(),
                )
                for item in kinds_raw
                if str(item).strip() in {"dataset", "document", "result", "artifact", "note"}
            }
            if normalized:
                kinds = normalized

        files = (
            manager.search_files_with_paths(query)
            if query
            else manager.list_workspace_files_with_paths()
        )

        filtered: list[dict[str, Any]] = []
        for item in files:
            kind = str(item.get("kind", "")).strip()
            path = str(item.get("path", "")).strip()
            if kinds is not None and kind not in kinds:
                continue
            if path_prefix and not path.startswith(path_prefix):
                continue
            filtered.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "kind": kind,
                    "path": path,
                    "download_url": item.get("download_url"),
                    "folder": item.get("folder"),
                    "meta": item.get("meta") or {},
                }
            )

        limited = filtered[:limit]
        lines = [
            f"- [{entry['kind']}] {entry['name']} | path={entry['path'] or '(none)'} | url={entry['download_url']}"
            for entry in limited
        ]
        summary = "\n".join(lines) if lines else "(无匹配文件)"

        return SkillResult(
            success=True,
            message=f"已找到 {len(filtered)} 个工作区文件，返回 {len(limited)} 个。",
            data={
                "session_id": session.id,
                "matched_count": len(filtered),
                "returned_count": len(limited),
                "files": limited,
                "content": summary,
            },
        )
