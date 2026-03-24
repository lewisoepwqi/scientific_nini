"""工具发现工具：允许 LLM 按需查询隐藏工具的完整 schema。

当某工具被标记为 expose_to_llm=False 时，LLM 无法在工具列表中看到它，
但可以通过本工具按名称或关键词发现并获取其完整 schema，从而在同一轮对话中调用。
"""

from __future__ import annotations

import logging
from typing import Any

from nini.agent.session import Session
from nini.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)


class SearchToolsTool(Tool):
    """工具发现工具，使 LLM 能按需获取隐藏工具的 schema。

    支持两种查询形式：
    - select:name1,name2：按名称精确获取，适合已知工具名但 schema 不在 context 中的场景
    - 关键词搜索：对所有工具（含隐藏工具）的名称和 description 做不区分大小写子字符串匹配，
      返回最多 5 个结果

    获取 schema 后，LLM 可在同一轮对话中直接调用该工具。
    """

    def __init__(self, registry: Any) -> None:
        """初始化工具，通过构造函数注入 ToolRegistry 引用。

        Args:
            registry: ToolRegistry 实例，用于查询所有工具（含隐藏工具）
        """
        self._registry = registry

    @property
    def name(self) -> str:
        return "search_tools"

    @property
    def description(self) -> str:
        return (
            "按需发现并获取工具的完整 schema（包括当前工具列表中未显示的隐藏工具）。"
            "当需要使用某工具但它不在当前工具列表中时，通过此工具获取其 schema，"
            "然后即可在同一轮对话中调用该工具。"
            "支持两种查询：select:name1,name2（精确获取）或关键词搜索（匹配名称和描述）。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "查询字符串。两种形式：\n"
                        "1. select:name1,name2 —— 按工具名精确获取完整 schema"
                        "（如 select:t_test 或 select:t_test,anova）\n"
                        "2. 关键词 —— 对所有工具名称和描述做不区分大小写子字符串匹配，"
                        "返回最多 5 个结果"
                    ),
                }
            },
            "required": ["query"],
        }

    @property
    def expose_to_llm(self) -> bool:
        """search_tools 自身必须对 LLM 可见，是发现其他工具的入口。"""
        return True

    @property
    def category(self) -> str:
        return "other"

    async def execute(self, session: Session, **kwargs: Any) -> ToolResult:
        """执行工具查询。"""
        query: str = kwargs.get("query", "").strip()
        if not query:
            return ToolResult(success=False, message="query 不能为空")

        if query.lower().startswith("select:"):
            return self._select_by_names(query[len("select:") :])
        else:
            return self._keyword_search(query)

    def _select_by_names(self, names_str: str) -> ToolResult:
        """按工具名精确获取完整 schema。"""
        names = [n.strip() for n in names_str.split(",") if n.strip()]
        if not names:
            return ToolResult(success=False, message="select: 后必须提供工具名称")

        results: list[dict[str, Any]] = []
        for name in names:
            tool = self._registry.get(name)
            if tool is None:
                results.append(
                    {
                        "name": name,
                        "found": False,
                        "message": f"工具 '{name}' 未找到",
                    }
                )
            else:
                results.append(
                    {
                        "name": name,
                        "found": True,
                        "schema": tool.get_tool_definition(),
                    }
                )

        found_count = sum(1 for r in results if r.get("found"))
        message = f"找到 {found_count}/{len(names)} 个工具"
        return ToolResult(success=True, data={"tools": results}, message=message)

    def _keyword_search(self, keyword: str) -> ToolResult:
        """关键词搜索，匹配工具名称和描述，返回最多 5 个结果。"""
        keyword_lower = keyword.lower()
        matches: list[dict[str, Any]] = []

        for tool_name in self._registry.list_tools():
            tool = self._registry.get(tool_name)
            if tool is None:
                continue
            if keyword_lower in tool.name.lower() or keyword_lower in tool.description.lower():
                matches.append(
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "schema": tool.get_tool_definition(),
                    }
                )
                if len(matches) >= 5:
                    break

        if not matches:
            message = f"未找到与 '{keyword}' 匹配的工具"
        else:
            message = f"找到 {len(matches)} 个匹配工具"

        return ToolResult(success=True, data={"tools": matches}, message=message)
