"""工具适配器 —— 将 Nini 技能转换为多种工具定义格式。

支持的目标格式：
- OpenAI Function Calling（现有格式，向后兼容）
- MCP（Model Context Protocol）Tool Definition
- Claude Code Markdown Skill
"""

from __future__ import annotations

from typing import Any

from nini.tools.base import Skill
from nini.tools.manifest import SkillManifest, export_to_claude_code
from nini.tools.markdown_scanner import MarkdownSkill

# ---------------------------------------------------------------------------
# OpenAI Function Calling 格式
# ---------------------------------------------------------------------------


def to_openai_tool(skill: Skill) -> dict[str, Any]:
    """将 Skill 转换为 OpenAI Function Calling 格式。

    等价于 ``skill.get_tool_definition()``，但作为独立函数更适合批量转换。
    """
    return {
        "type": "function",
        "function": {
            "name": skill.name,
            "description": skill.description,
            "parameters": skill.parameters,
        },
    }


# ---------------------------------------------------------------------------
# MCP Tool Definition 格式
# ---------------------------------------------------------------------------


def to_mcp_tool(skill: Skill) -> dict[str, Any]:
    """将 Skill 转换为 MCP (Model Context Protocol) Tool 定义。

    MCP Tool 格式参考: https://modelcontextprotocol.io/docs/concepts/tools

    返回的字典可直接用于 MCP Server 的 tools/list 响应。
    """
    return {
        "name": skill.name,
        "description": skill.description,
        "inputSchema": skill.parameters,
    }


def to_mcp_tool_from_markdown(md_skill: MarkdownSkill) -> dict[str, Any]:
    """将 MarkdownSkill 转换为 MCP Tool 定义（提示词类型）。"""
    return {
        "name": md_skill.name,
        "description": md_skill.description,
        "inputSchema": {"type": "object", "properties": {}},
    }


# ---------------------------------------------------------------------------
# Claude Code Markdown Skill 格式
# ---------------------------------------------------------------------------


def to_claude_code_skill(skill: Skill) -> str:
    """将 Skill 转换为 Claude Code 兼容的 Markdown Skill 描述。

    通过 SkillManifest 中转，生成可读的 Markdown 文档。
    """
    manifest = skill.to_manifest()
    return export_to_claude_code(manifest)


def to_claude_code_skill_from_markdown(md_skill: MarkdownSkill) -> str:
    """将 MarkdownSkill 转换为 Claude Code 兼容的 Markdown Skill 描述。"""
    manifest = md_skill.to_manifest()
    return export_to_claude_code(manifest)


# ---------------------------------------------------------------------------
# 批量转换
# ---------------------------------------------------------------------------


class ToolAdapter:
    """统一的工具格式适配器。

    用法::

        adapter = ToolAdapter(registry)
        openai_tools = adapter.to_openai_tools()
        mcp_tools = adapter.to_mcp_tools()
        claude_code_md = adapter.to_claude_code_markdown()
    """

    def __init__(self, registry: Any) -> None:
        """初始化适配器。

        Args:
            registry: SkillRegistry 实例。
        """
        self._registry = registry

    def to_openai_tools(self, *, exposed_only: bool = True) -> list[dict[str, Any]]:
        """导出为 OpenAI Function Calling 工具列表。

        Args:
            exposed_only: 仅包含 expose_to_llm=True 的技能（默认 True）。
        """
        skills = self._registry._skills.values()
        if exposed_only:
            skills = [s for s in skills if s.expose_to_llm]
        return [to_openai_tool(s) for s in skills]

    def to_mcp_tools(self) -> list[dict[str, Any]]:
        """导出为 MCP Tool 定义列表（包含 Function + Markdown 技能）。"""
        tools: list[dict[str, Any]] = []

        # Function Skills
        for skill in self._registry._skills.values():
            tools.append(to_mcp_tool(skill))

        # Markdown Skills（仅启用的）
        for md_dict in self._registry._markdown_skills:
            if md_dict.get("enabled", True):
                tools.append(
                    {
                        "name": md_dict["name"],
                        "description": md_dict.get("description", ""),
                        "inputSchema": {"type": "object", "properties": {}},
                    }
                )

        return tools

    def to_claude_code_markdown(self) -> str:
        """导出所有技能为 Claude Code 格式的 Markdown 文档。"""
        manifests: list[SkillManifest] = []

        for skill in self._registry._skills.values():
            manifests.append(skill.to_manifest())

        for md_dict in self._registry._markdown_skills:
            if md_dict.get("enabled", True):
                manifests.append(
                    SkillManifest(
                        name=md_dict["name"],
                        description=md_dict.get("description", ""),
                        category=md_dict.get("category", "other"),
                    )
                )

        from nini.tools.manifest import export_all_skills_markdown

        return export_all_skills_markdown(manifests)
