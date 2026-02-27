"""Nini MCP Server — 将 Function Skills 暴露为 MCP 工具供外部 Agent 调用。

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
_SERVER_VERSION = "0.1.0"
_SERVER_INSTRUCTIONS = (
    "Nini 是科研数据分析 AI Agent。"
    "提供统计检验（t 检验、ANOVA、相关性等）、可视化（Plotly 图表）、"
    "数据清洗、代码执行（Python / R 沙箱）、报告生成等工具。"
)


def _check_mcp_available() -> None:
    """检查 MCP SDK 是否可用，不可用时给出安装提示。"""
    if not _MCP_AVAILABLE:
        raise ImportError(
            "MCP SDK 未安装。请运行: pip install 'nini[mcp]' 或 pip install 'mcp>=1.0.0'"
        )


def _create_registry():  # noqa: ANN202
    """延迟创建默认技能注册中心，避免模块加载时的循环依赖。"""
    from nini.tools.registry import create_default_registry

    return create_default_registry()


def _create_session():  # noqa: ANN202
    """为每次 MCP 工具调用创建一个临时 Session。"""
    from nini.agent.session import Session

    return Session(session_id=f"mcp-{uuid.uuid4().hex[:8]}")


def create_mcp_server(registry: Any = None) -> "Server":
    """创建并配置 MCP Server 实例。

    Args:
        registry: 可选的 SkillRegistry 实例。若为 None，使用默认注册中心。

    Returns:
        配置完成的 mcp.server.lowlevel.Server 实例。
    """
    _check_mcp_available()

    if registry is None:
        registry = _create_registry()

    server = Server(_SERVER_NAME)

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        """列出所有暴露给 LLM 的 Function Skills。"""
        tools: list[types.Tool] = []
        for skill in registry._skills.values():
            if not skill.expose_to_llm:
                continue
            tools.append(
                types.Tool(
                    name=skill.name,
                    description=skill.description,
                    inputSchema=skill.parameters,
                )
            )
        return tools

    @server.call_tool()
    async def call_tool(
        name: str, arguments: dict[str, Any] | None
    ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        """执行指定 Function Skill 并返回结果。"""
        skill = registry.get(name)
        if skill is None:
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps(
                        {"success": False, "message": f"未知工具: {name}"},
                        ensure_ascii=False,
                    ),
                )
            ]

        session = _create_session()
        try:
            result = await registry.execute(name, session=session, **(arguments or {}))
        except Exception as exc:
            logger.error("MCP call_tool 执行失败: %s — %s", name, exc, exc_info=True)
            result = {"success": False, "message": f"执行失败: {exc}"}

        # 将结果序列化为 JSON 文本返回
        result_text = json.dumps(result, ensure_ascii=False, default=str)

        contents: list[types.TextContent | types.ImageContent | types.EmbeddedResource] = [
            types.TextContent(type="text", text=result_text)
        ]

        # 如果结果包含图表 JSON，额外返回一个结构化内容
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
        """列出可用资源（当前为空，后续可暴露 session datasets）。"""
        return []

    return server


async def run_stdio(registry: Any = None) -> None:
    """通过 stdio 传输运行 MCP Server。

    Args:
        registry: 可选的 SkillRegistry 实例。
    """
    _check_mcp_available()

    server = create_mcp_server(registry)

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


def main(registry: Any = None) -> None:
    """MCP Server 入口（同步包装器）。"""
    asyncio.run(run_stdio(registry))
