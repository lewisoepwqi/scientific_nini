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
            "适用于已经完成的统计结果摘要卡、交互式科研面板和自定义可视化。\n"
            "只能展示已得到的结果，不能代替统计检验、代码执行或“进行中”占位提示。\n"
            "最小示例：\n"
            '- 摘要卡片：{title: "分析摘要", html: "<div style=\'padding:16px\'>'
            '<h3>t = 2.45, p = 0.018</h3><p>效应量 d = 0.65</p></div>"}\n'
            '- 交互面板：{title: "数据概览", html: "<div>...</div>", '
            'description: "含 JavaScript 交互的统计面板"}\n'
            "参数约束：title 和 html 为必填；html 须为自包含片段（可含内联 CSS/JS）。"
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
        title = kwargs.get("title")
        html = kwargs.get("html")

        if not isinstance(title, str) or not title.strip():
            return ToolResult(success=False, message="缺少必填参数: title")
        if not isinstance(html, str) or not html.strip():
            return ToolResult(success=False, message="缺少必填参数: html")

        description = kwargs.get("description")
        normalized_description = description if isinstance(description, str) else None
        current_task = (
            session.task_manager.current_in_progress()
            if hasattr(session, "task_manager") and session.task_manager is not None
            else None
        )
        if current_task is not None:
            from nini.agent.tool_exposure_policy import tool_satisfies_tool_hint

            current_hint = getattr(current_task, "tool_hint", None)
            if not tool_satisfies_tool_hint("generate_widget", current_hint):
                return self.build_input_error(
                    message=(
                        f"当前仍有进行中的任务「{current_task.title}」，"
                        "generate_widget 只能展示已完成结果，不能代替实际分析执行。"
                    ),
                    payload={
                        "error_code": "WIDGET_RESULT_REQUIRED",
                        "active_task_id": getattr(current_task, "id", None),
                        "active_task_title": getattr(current_task, "title", ""),
                        "active_task_hint": current_hint,
                        "recovery_hint": (
                            "请先调用当前任务提示对应的真实执行工具，"
                            "待得到统计结果、图表或产物后再生成 widget。"
                        ),
                    },
                )
        return ToolResult(
            success=True,
            message=f"已生成内嵌组件：{title.strip()}",
            data={
                "title": title,
                "html": html,
                "description": normalized_description,
            },
        )
