"""生成内嵌 HTML 组件的工具。"""

from __future__ import annotations

from typing import Any

from nini.agent.session import Session
from nini.tools.base import Tool, ToolResult


class GenerateWidgetTool(Tool):
    """透传 AI 生成的 HTML 组件数据。"""

    @property
    def name(self) -> str:
        return "generate_widget"

    @property
    def category(self) -> str:
        return "visualization"

    @property
    def description(self) -> str:
        return (
            "生成可在聊天界面内嵌渲染的自包含 HTML 组件。"
            "适用于统计结果摘要卡、交互式科研面板和自定义可视化。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "组件标题，用于聊天界面展示。",
                },
                "html": {
                    "type": "string",
                    "description": "自包含 HTML 片段，可包含内联 CSS 与 JavaScript。",
                },
                "description": {
                    "type": "string",
                    "description": "组件用途说明，可选。",
                },
            },
            "required": ["title", "html"],
        }

    async def execute(self, session: Session, **kwargs: Any) -> ToolResult:
        _ = session
        title = kwargs.get("title")
        html = kwargs.get("html")

        if not isinstance(title, str) or not title.strip():
            return ToolResult(success=False, message="缺少必填参数: title")
        if not isinstance(html, str) or not html.strip():
            return ToolResult(success=False, message="缺少必填参数: html")

        description = kwargs.get("description")
        normalized_description = description if isinstance(description, str) else None
        return ToolResult(
            success=True,
            message=f"已生成内嵌组件：{title.strip()}",
            data={
                "title": title,
                "html": html,
                "description": normalized_description,
            },
        )
