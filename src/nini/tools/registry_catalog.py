"""ToolRegistry 目录与快照逻辑。"""

from __future__ import annotations

from typing import Any

from nini.config import settings
from nini.tools.markdown_scanner import render_skills_snapshot


class ToolCatalogOps:
    """聚合 Function Tool 与 Markdown Skill 目录。"""

    def __init__(self, owner: Any) -> None:
        self._owner = owner

    def get_skill_index(self, name: str) -> dict[str, Any] | None:
        """获取 Markdown Skill 的索引层元数据。"""
        item = self._owner.get_markdown_skill(name)
        if item is None:
            return None
        return {
            "name": item.get("name"),
            "type": item.get("type", "markdown"),
            "description": item.get("description", ""),
            "brief_description": item.get("brief_description", ""),
            "category": item.get("category", "other"),
            "research_domain": item.get("research_domain", "general"),
            "difficulty_level": item.get("difficulty_level", "intermediate"),
            "typical_use_cases": item.get("typical_use_cases", []),
            "location": item.get("location", ""),
            "enabled": bool(item.get("enabled", True)),
            "metadata": dict(item.get("metadata") or {}),
        }

    def get_semantic_catalog(self, skill_type: str | None = None) -> list[dict[str, Any]]:
        """返回适用于语义检索的轻量目录。"""
        catalog = self.list_skill_catalog(skill_type=skill_type)
        semantic_items: list[dict[str, Any]] = []
        for item in catalog:
            metadata = dict(item.get("metadata") or {})
            semantic_items.append(
                {
                    "name": item.get("name", ""),
                    "type": item.get("type", "unknown"),
                    "description": item.get("description", ""),
                    "brief_description": item.get("brief_description", ""),
                    "category": item.get("category", "other"),
                    "research_domain": item.get("research_domain", "general"),
                    "difficulty_level": item.get("difficulty_level", "intermediate"),
                    "typical_use_cases": item.get("typical_use_cases", []),
                    "enabled": bool(item.get("enabled", True)),
                    "expose_to_llm": bool(item.get("expose_to_llm", True)),
                    "user_invocable": bool(
                        item.get(
                            "user_invocable",
                            metadata.get("user_invocable", True),
                        )
                    ),
                    "disable_model_invocation": bool(
                        item.get(
                            "disable_model_invocation",
                            metadata.get("disable_model_invocation", False),
                        )
                    ),
                    "aliases": metadata.get("aliases", []),
                    "tags": metadata.get("tags", []),
                    "allowed_tools": metadata.get("allowed_tools", []),
                    "location": item.get("location", ""),
                }
            )
        return semantic_items

    def list_skill_catalog(self, skill_type: str | None = None) -> list[dict[str, Any]]:
        """返回聚合后的技能目录。"""
        all_items = self._owner.list_function_skills() + self._owner.list_markdown_skills()
        if skill_type:
            normalized_type = skill_type.strip().lower()
            if normalized_type in {"function", "markdown"}:
                return [item for item in all_items if item.get("type") == normalized_type]
        return all_items

    def list_tools_catalog(self) -> list[dict[str, Any]]:
        """返回可执行 Function Tool 目录。"""
        return self._owner.list_function_skills()

    def list_markdown_skill_catalog(self) -> list[dict[str, Any]]:
        """返回 Markdown Skill 目录。"""
        return self._owner.list_markdown_skills()

    def write_skills_snapshot(self) -> None:
        """将聚合目录写入快照文件。"""
        content = render_skills_snapshot(
            self._owner.list_function_skills(),
            self._owner.list_markdown_skills(),
        )
        settings.skills_snapshot_path.write_text(content, encoding="utf-8")
