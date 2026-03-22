"""Markdown Tool 扫描与状态管理逻辑。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from nini.config import settings
from nini.tools.markdown_scanner import (
    get_markdown_tool_instruction,
    list_markdown_tool_runtime_resources,
    scan_markdown_tools,
)

logger = logging.getLogger(__name__)


class MarkdownToolRegistryOps:
    """管理 Markdown Skill 的扫描、状态覆盖与资源读取。"""

    def __init__(self, owner: Any) -> None:
        self._owner = owner

    def load_enabled_overrides(self) -> dict[str, bool]:
        """加载启用状态覆盖。"""
        path = settings.skills_state_path
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("读取 skills 状态文件失败，将忽略覆盖配置: %s", exc)
            return {}

        if not isinstance(payload, dict):
            return {}
        raw = payload.get("markdown_enabled")
        if not isinstance(raw, dict):
            return {}

        overrides: dict[str, bool] = {}
        for key, value in raw.items():
            if isinstance(key, str) and isinstance(value, bool):
                overrides[key] = value
        return overrides

    def save_enabled_overrides(self) -> None:
        """持久化启用状态覆盖。"""
        payload = {"markdown_enabled": self._owner._markdown_enabled_overrides}
        settings.skills_state_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def prune_enabled_overrides(self, markdown_names: set[str]) -> bool:
        """清理不存在的覆盖项。"""
        stale = [
            name for name in self._owner._markdown_enabled_overrides if name not in markdown_names
        ]
        if not stale:
            return False
        for name in stale:
            self._owner._markdown_enabled_overrides.pop(name, None)
        return True

    def list_markdown_tools(self) -> list[dict[str, Any]]:
        """列出 Markdown Skill。"""
        return list(self._owner._markdown_skills)

    def get_markdown_tool(self, name: str) -> dict[str, Any] | None:
        """按名称获取 Markdown Skill。"""
        for item in self._owner._markdown_skills:
            if item.get("name") == name:
                return dict(item)
        return None

    def get_tool_instruction(self, name: str) -> dict[str, Any] | None:
        """读取 Markdown Skill 指令正文。"""
        item = self.get_markdown_tool(name)
        if item is None:
            return None
        raw_location = str(item.get("location", "")).strip()
        if not raw_location:
            return None
        skill_path = Path(raw_location).expanduser().resolve()
        if not skill_path.exists() or not skill_path.is_file():
            return None
        payload = get_markdown_tool_instruction(skill_path)
        # 对外返回逻辑标识符而非服务端绝对路径，防止路径信息泄露
        skill_name = str(item.get("name", "")).strip()
        return {
            "name": skill_name,
            "instruction": payload["instruction"],
            "location": f"skill:{skill_name}",
            "metadata": dict(item.get("metadata") or {}),
        }

    def get_runtime_resources(self, name: str) -> dict[str, Any] | None:
        """读取 Markdown Skill 运行时资源目录。"""
        item = self.get_markdown_tool(name)
        if item is None:
            return None
        raw_location = str(item.get("location", "")).strip()
        if not raw_location:
            return None
        skill_path = Path(raw_location).expanduser().resolve()
        if not skill_path.exists() or not skill_path.is_file():
            return None
        return {
            "name": item.get("name"),
            "resource_root": str(skill_path.parent),
            "resources": list_markdown_tool_runtime_resources(skill_path),
        }

    def reload_markdown_tools(self, function_names: set[str]) -> list[dict[str, Any]]:
        """重新扫描 Markdown Skill 并应用启停覆盖。"""
        markdown_skills = scan_markdown_tools(settings.skills_search_dirs)
        deduped: list[dict[str, Any]] = []
        seen_markdown_names: set[str] = set()

        for skill in markdown_skills:
            if skill.name in seen_markdown_names:
                logger.warning(
                    "检测到同名 Markdown 技能，低优先级版本将被忽略: %s (%s)",
                    skill.name,
                    skill.location,
                )
                continue
            seen_markdown_names.add(skill.name)
            deduped.append(skill.to_dict())

        items: list[dict[str, Any]] = []
        markdown_names: set[str] = set()
        for item in deduped:
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            markdown_names.add(name)
            if name in function_names:
                item["enabled"] = False
                metadata = dict(item.get("metadata") or {})
                metadata["conflict_with"] = "function"
                item["metadata"] = metadata
                logger.warning("Markdown 技能与 Function Skill 同名，已禁用: %s", name)
            else:
                override_enabled = self._owner._markdown_enabled_overrides.get(name)
                if isinstance(override_enabled, bool):
                    item["enabled"] = override_enabled
            items.append(item)

        if self.prune_enabled_overrides(markdown_names):
            self.save_enabled_overrides()

        self._owner._markdown_skills = items
        return self.list_markdown_tools()

    def set_markdown_tool_enabled(self, name: str, enabled: bool) -> dict[str, Any] | None:
        """设置 Markdown Skill 的启用状态。"""
        if not self.get_markdown_tool(name):
            return None
        self._owner._markdown_enabled_overrides[name] = bool(enabled)
        self.save_enabled_overrides()
        self.reload_markdown_tools(set(self._owner._skills.keys()))
        self._owner.write_tools_snapshot()
        return self.get_markdown_tool(name)

    def remove_markdown_tool_override(self, name: str) -> None:
        """删除启停覆盖。"""
        removed = self._owner._markdown_enabled_overrides.pop(name, None)
        if removed is not None:
            self.save_enabled_overrides()

    def is_markdown_tool(self, skill_name: str) -> bool:
        """判断名称是否属于已扫描的 Markdown Skill。"""
        return any(item.get("name") == skill_name for item in self._owner._markdown_skills)
