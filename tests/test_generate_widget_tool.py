"""generate_widget 工具测试。"""

from __future__ import annotations

import asyncio

from nini.agent.session import Session
from nini.tools.generate_widget import GenerateWidgetTool
from nini.tools.registry import create_default_tool_registry


def test_generate_widget_tool_passes_through_payload() -> None:
    tool = GenerateWidgetTool()
    result = asyncio.run(
        tool.execute(
            Session(),
            title="统计摘要卡",
            html="<section><h1>结果</h1></section>",
            description="展示核心统计量",
        )
    )

    assert result.success is True
    assert result.data == {
        "title": "统计摘要卡",
        "html": "<section><h1>结果</h1></section>",
        "description": "展示核心统计量",
    }


def test_generate_widget_tool_requires_html() -> None:
    tool = GenerateWidgetTool()
    result = asyncio.run(tool.execute(Session(), title="统计摘要卡"))

    assert result.success is False
    assert result.message == "缺少必填参数: html"


def test_generate_widget_tool_is_registered_and_exposed() -> None:
    registry = create_default_tool_registry()

    assert registry.get("generate_widget") is not None
    names = {tool["function"]["name"] for tool in registry.get_tool_definitions()}
    assert "generate_widget" in names
