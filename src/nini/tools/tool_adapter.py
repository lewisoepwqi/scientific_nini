"""工具适配器 —— 将 Nini 工具转换为多种工具定义格式。

支持的目标格式：
- OpenAI Function Calling（现有格式，向后兼容）
- MCP（Model Context Protocol）Tool Definition
- Claude Code Markdown Skill

执行路由：
- 若 MarkdownTool.metadata 中存在 "contract" 键，路由至 ContractRunner 执行
- 否则走现有提示词注入路径（保持向后兼容）
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from nini.tools.base import Tool
from nini.tools.manifest import ToolManifest, export_to_claude_code
from nini.tools.markdown_scanner import MarkdownTool

if TYPE_CHECKING:
    from nini.models.skill_contract import ContractResult
    from nini.skills.contract_runner import EventCallback

# ---------------------------------------------------------------------------
# OpenAI Function Calling 格式
# ---------------------------------------------------------------------------


def to_openai_tool(tool: Tool) -> dict[str, Any]:
    """将 Tool 转换为 OpenAI Function Calling 格式。

    等价于 ``tool.get_tool_definition()``，但作为独立函数更适合批量转换。
    """
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


# ---------------------------------------------------------------------------
# MCP Tool Definition 格式
# ---------------------------------------------------------------------------


def to_mcp_tool(tool: Tool) -> dict[str, Any]:
    """将 Tool 转换为 MCP (Model Context Protocol) Tool 定义。

    MCP Tool 格式参考: https://modelcontextprotocol.io/docs/concepts/tools

    返回的字典可直接用于 MCP Server 的 tools/list 响应。
    """
    return {
        "name": tool.name,
        "description": tool.description,
        "inputSchema": tool.parameters,
    }


def to_mcp_tool_from_markdown(md_skill: MarkdownTool) -> dict[str, Any]:
    """将 MarkdownTool 转换为 MCP Tool 定义（提示词类型）。"""
    return {
        "name": md_skill.name,
        "description": md_skill.description,
        "inputSchema": {"type": "object", "properties": {}},
    }


# ---------------------------------------------------------------------------
# Claude Code Markdown Skill 格式
# ---------------------------------------------------------------------------


def to_claude_code_skill(tool: Tool) -> str:
    """将 Tool 转换为 Claude Code 兼容的 Markdown Skill 描述。

    通过 ToolManifest 中转，生成可读的 Markdown 文档。
    """
    manifest = tool.to_manifest()
    return export_to_claude_code(manifest)


def to_claude_code_skill_from_markdown(md_skill: MarkdownTool) -> str:
    """将 MarkdownTool 转换为 Claude Code 兼容的 Markdown Skill 描述。"""
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
            registry: ToolRegistry 实例。
        """
        self._registry = registry

    def to_openai_tools(self, *, exposed_only: bool = True) -> list[dict[str, Any]]:
        """导出为 OpenAI Function Calling 工具列表。

        Args:
            exposed_only: 仅包含 expose_to_llm=True 的技能（默认 True）。
        """
        skills = self._registry._tools.values()
        if exposed_only:
            allowlist = getattr(self._registry, "_llm_exposed_function_tools", None)
            if allowlist is not None:
                skills = [s for s in skills if s.name in allowlist]
            else:
                skills = [s for s in skills if s.expose_to_llm]
        return [to_openai_tool(s) for s in skills]

    def to_mcp_tools(self) -> list[dict[str, Any]]:
        """导出为 MCP Tool 定义列表（包含 Function + Markdown 技能）。"""
        tools: list[dict[str, Any]] = []

        # Function Skills
        for skill in self._registry._tools.values():
            tools.append(to_mcp_tool(skill))

        # Markdown Skills（仅启用的）
        for md_dict in self._registry._markdown_tools:
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
        manifests: list[ToolManifest] = []

        for skill in self._registry._tools.values():
            manifests.append(skill.to_manifest())

        for md_dict in self._registry._markdown_tools:
            if md_dict.get("enabled", True):
                manifests.append(
                    ToolManifest(
                        name=md_dict["name"],
                        description=md_dict.get("description", ""),
                        category=md_dict.get("category", "other"),
                        brief_description=md_dict.get("brief_description", ""),
                        research_domain=md_dict.get("research_domain", "general"),
                        difficulty_level=md_dict.get("difficulty_level", "intermediate"),
                        typical_use_cases=md_dict.get("typical_use_cases", []),
                    )
                )

        from nini.tools.manifest import export_all_tools_markdown

        return export_all_tools_markdown(manifests)


# ---------------------------------------------------------------------------
# 契约路由执行（contract vs. 现有提示词注入路径）
# ---------------------------------------------------------------------------


def has_contract(md_skill: MarkdownTool) -> bool:
    """判断 MarkdownTool 是否携带 SkillContract。"""
    return "contract" in md_skill.metadata


async def execute_with_contract(
    md_skill: MarkdownTool,
    session: Any,
    callback: "EventCallback",
    inputs: dict[str, Any] | None = None,
) -> "ContractResult":
    """使用 ContractRunner 执行携带 contract 的 MarkdownTool。

    调用方需先用 ``has_contract(md_skill)`` 确认存在 contract。
    若 metadata["contract"] 不是 SkillContract 实例，将抛出 TypeError。
    """
    from nini.models.skill_contract import SkillContract
    from nini.skills.contract_runner import ContractRunner

    contract = md_skill.metadata["contract"]
    if not isinstance(contract, SkillContract):
        raise TypeError(
            f"metadata['contract'] 类型错误：期望 SkillContract，实际为 {type(contract).__name__}"
        )

    runner = ContractRunner(contract=contract, skill_name=md_skill.name, callback=callback)
    return await runner.run(session=session, inputs=inputs or {})
