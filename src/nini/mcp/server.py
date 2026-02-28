"""Nini MCP Server — 将 Function Skills 和 Capabilities 暴露为 MCP 工具。

对齐 Nini 2.0 架构：Intent → Capability → Skill Runtime

通过 stdio 传输协议运行，可与 Claude Code / Codex CLI / OpenCode 等集成：

    claude mcp add nini -- python -m nini mcp

或独立运行：

    nini mcp
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)

# MCP SDK 版本要求 >= 1.0.0，作为可选依赖安装
_MCP_AVAILABLE = False
try:
    import mcp.server.stdio
    import mcp.types as types
    from mcp.server.lowlevel import NotificationOptions, Server
    from mcp.server.models import InitializationOptions

    _MCP_AVAILABLE = True
except ImportError:
    pass

_SERVER_NAME = "nini"
_SERVER_VERSION = "2.0.0"  # 对齐 Nini 2.0 架构
_SERVER_INSTRUCTIONS = (
    "Nini 是科研数据分析 AI Agent。\n"
    "\n"
    "架构层级：Intent Layer → Capability Layer → Skill Runtime\n"
    "\n"
    "主要能力：\n"
    "- 差异分析 (difference_analysis): t检验、ANOVA、非参数检验\n"
    "- 相关分析 (correlation_analysis): Pearson/Spearman相关\n"
    "- 数据探索、可视化、报告生成\n"
    "\n"
    "使用流程：\n"
    "1. 调用 analyze_intent 分析用户意图\n"
    "2. 调用 execute_capability 执行匹配的能力\n"
    "3. 或使用底层工具进行细粒度控制"
)


def _check_mcp_available() -> None:
    """检查 MCP SDK 是否可用，不可用时给出安装提示。"""
    if not _MCP_AVAILABLE:
        raise ImportError(
            "MCP SDK 未安装。请运行: pip install 'nini[mcp]' 或 pip install 'mcp>=1.0.0'"
        )


def _create_registry() -> Any:
    """延迟创建默认工具注册中心，避免模块加载时的循环依赖。"""
    from nini.tools.registry import create_default_tool_registry

    return create_default_tool_registry()


def _create_capability_registry() -> Any:
    """延迟创建 Capability 注册中心。"""
    from nini.capabilities import CapabilityRegistry, create_default_capabilities

    registry = CapabilityRegistry()
    for cap in create_default_capabilities():
        registry.register(cap)
    return registry


def _create_session() -> Any:
    """为每次 MCP 工具调用创建一个临时 Session。"""
    from nini.agent.session import Session

    return Session(session_id=f"mcp-{uuid.uuid4().hex[:8]}")


def create_mcp_server(
    registry: Any = None,
    capability_registry: Any = None,
) -> "Server":
    """创建并配置 MCP Server 实例。

    Args:
        registry: 可选的 SkillRegistry 实例。若为 None，使用默认注册中心。
        capability_registry: 可选的 CapabilityRegistry 实例。

    Returns:
        配置完成的 mcp.server.lowlevel.Server 实例。
    """
    _check_mcp_available()

    if registry is None:
        registry = _create_registry()
    if capability_registry is None:
        capability_registry = _create_capability_registry()

    server = Server(_SERVER_NAME)

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        """列出所有暴露给 LLM 的工具（Function Skills + 架构层工具）。"""
        tools: list[types.Tool] = []

        # 1. 添加架构层工具（Intent/Capability 层）
        tools.extend(_create_architecture_tools(capability_registry))

        # 2. 添加 Function Skills
        for tool_definition in registry.get_tool_definitions():
            function_def = tool_definition.get("function", {})
            tools.append(
                types.Tool(
                    name=str(function_def.get("name", "")),
                    description=str(function_def.get("description", "")),
                    inputSchema=function_def.get("parameters", {"type": "object", "properties": {}}),
                )
            )

        return tools

    @server.call_tool()
    async def call_tool(
        name: str, arguments: dict[str, Any] | None
    ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        """执行指定工具并返回结果。"""
        args = arguments or {}

        # 处理架构层工具
        if name in ("analyze_intent", "execute_capability", "list_capabilities"):
            result = await _handle_architecture_tool(name, args, capability_registry, registry)
        else:
            # 处理普通 Function Skill
            result = await _handle_skill_tool(name, args, registry)

        # 序列化结果
        result_text = json.dumps(result, ensure_ascii=False, default=str)
        contents: list[types.TextContent | types.ImageContent | types.EmbeddedResource] = [
            types.TextContent(type="text", text=result_text)
        ]

        # 如果结果包含图表 JSON，额外返回
        if isinstance(result, dict) and result.get("has_chart") and result.get("chart_data"):
            chart_json = json.dumps(result["chart_data"], ensure_ascii=False, default=str)
            contents.append(
                types.TextContent(
                    type="text",
                    text=f"[Plotly Chart JSON]\n{chart_json}",
                )
            )

        return contents

    @server.list_resources()
    async def list_resources() -> list[types.Resource]:
        """列出可用资源。"""
        return []

    @server.list_prompts()
    async def list_prompts() -> list[types.Prompt]:
        """列出可用提示模板。"""
        return [
            types.Prompt(
                name="scientific_analysis",
                description="科研数据分析的标准提示模板",
                arguments=[
                    types.PromptArgument(
                        name="research_domain",
                        description="研究领域",
                        required=False,
                    ),
                ],
            ),
        ]

    @server.get_prompt()
    async def get_prompt(name: str, arguments: dict[str, Any] | None) -> types.GetPromptResult:
        """获取提示模板。"""
        if name == "scientific_analysis":
            domain = arguments.get("research_domain", "general") if arguments else "general"
            return types.GetPromptResult(
                description="科研数据分析提示",
                messages=[
                    types.PromptMessage(
                        role="system",
                        content=types.TextContent(
                            type="text",
                            text=f"你是 Nini 科研数据分析助手。{'擅长' + domain + '领域。' if domain != 'general' else ''}"
                                 "请基于统计严谨性提供分析，自动检查前提假设，报告效应量和置信区间。",
                        ),
                    ),
                ],
            )
        raise ValueError(f"未知提示模板: {name}")

    return server


def _get_executable_capability_names(capability_registry: Any) -> list[str]:
    """获取可直接执行的能力名称列表。"""
    return [
        cap.name
        for cap in capability_registry.list_capabilities()
        if cap.supports_direct_execution()
    ]


def _create_architecture_tools(capability_registry: Any) -> list[types.Tool]:
    """创建架构层工具（Intent/Capability 层）。"""
    _check_mcp_available()
    executable_capabilities = _get_executable_capability_names(capability_registry)
    return [
        types.Tool(
            name="analyze_intent",
            description="分析用户意图，返回推荐的能力和技能",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_message": {
                        "type": "string",
                        "description": "用户输入的消息",
                    },
                    "analysis_mode": {
                        "type": "string",
                        "enum": ["rule", "hybrid"],
                        "description": "分析模式：rule=规则匹配, hybrid=规则+语义",
                        "default": "rule",
                    },
                },
                "required": ["user_message"],
            },
        ),
        types.Tool(
            name="list_capabilities",
            description="列出所有可用能力及其执行状态",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        types.Tool(
            name="execute_capability",
            description="直接执行指定能力",
            inputSchema={
                "type": "object",
                "properties": {
                    "capability_name": {
                        "type": "string",
                        "description": "能力名称",
                        "enum": executable_capabilities,
                    },
                    "params": {
                        "type": "object",
                        "description": "能力执行参数",
                    },
                },
                "required": ["capability_name", "params"],
            },
        ),
    ]


async def _handle_architecture_tool(
    name: str,
    args: dict[str, Any],
    capability_registry: Any,
    tool_registry: Any,
) -> dict[str, Any]:
    """处理架构层工具调用。"""
    from nini.agent.session import Session

    if name == "analyze_intent":
        user_message = args.get("user_message", "")
        analysis_mode = args.get("analysis_mode", "rule")

        # 获取 capabilities 和 skills
        capabilities = [cap.to_dict() for cap in capability_registry.list_capabilities()]

        # 执行意图分析
        from nini.intent import default_intent_analyzer

        analysis = default_intent_analyzer.analyze(
            user_message,
            capabilities=capabilities,
            semantic_skills=[],  # 简化为空列表
        )

        return {
            "success": True,
            "data": analysis.to_dict(),
        }

    elif name == "list_capabilities":
        caps = capability_registry.to_catalog()
        return {
            "success": True,
            "capabilities": caps,
            "count": len(caps),
        }

    elif name == "execute_capability":
        cap_name = args.get("capability_name")
        params = args.get("params", {})

        # 添加 session_id 到 params
        params["session_id"] = f"mcp-cap-{uuid.uuid4().hex[:8]}"

        try:
            session = _create_session()
            result = await capability_registry.execute(cap_name, session, params)
            return {
                "success": True,
                "capability": cap_name,
                "result": result.to_dict() if hasattr(result, "to_dict") else result,
            }
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
            }

    return {"success": False, "error": f"未知架构工具: {name}"}


async def _handle_skill_tool(
    name: str,
    args: dict[str, Any],
    registry: Any,
) -> dict[str, Any]:
    """处理普通技能工具调用。"""
    skill = registry.get(name)
    if skill is None:
        return {"success": False, "message": f"未知工具: {name}"}

    session = _create_session()
    try:
        result = await registry.execute(name, session=session, **args)
        if hasattr(result, "to_dict"):
            return result.to_dict()
        elif isinstance(result, dict):
            return result
        else:
            return {"success": True, "result": str(result)}
    except Exception as exc:
        logger.error("MCP call_tool 执行失败: %s — %s", name, exc, exc_info=True)
        return {"success": False, "message": f"执行失败: {exc}"}


async def run_stdio(
    registry: Any = None,
    capability_registry: Any = None,
) -> None:
    """通过 stdio 传输运行 MCP Server。

    Args:
        registry: 可选的 SkillRegistry 实例。
        capability_registry: 可选的 CapabilityRegistry 实例。
    """
    _check_mcp_available()

    server = create_mcp_server(registry, capability_registry)

    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name=_SERVER_NAME,
                server_version=_SERVER_VERSION,
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


def main(registry: Any = None, capability_registry: Any = None) -> None:
    """MCP Server 入口（同步包装器）。"""
    asyncio.run(run_stdio(registry, capability_registry))
