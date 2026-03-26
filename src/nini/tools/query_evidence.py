"""证据链查询工具。"""

from __future__ import annotations

from typing import Any

from nini.agent.session import Session
from nini.tools.base import Tool, ToolResult


class QueryEvidenceTool(Tool):
    """查询当前会话中的证据链。"""

    @property
    def name(self) -> str:
        return "query_evidence"

    @property
    def description(self) -> str:
        return "按结论或关键词查询当前会话中的证据链，返回匹配节点及其上游数据来源。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "要检索的结论文本、关键词或来源标识",
                }
            },
            "required": ["query"],
            "additionalProperties": False,
        }

    @property
    def category(self) -> str:
        return "other"

    async def execute(self, session: Session, **kwargs: Any) -> ToolResult:
        query = str(kwargs.get("query", "") or "").strip()
        if not query:
            return ToolResult(success=False, message="query 不能为空")

        collector = getattr(session, "evidence_collector", None)
        if collector is None or not collector.chain.nodes:
            return ToolResult(
                success=True,
                message="当前会话暂无证据链记录。",
                data={"matches": [], "chains": []},
            )

        matches = collector.find_nodes(query, node_type="conclusion")
        if not matches:
            matches = collector.find_nodes(query)

        if not matches:
            return ToolResult(
                success=True,
                message=f"未找到与 '{query}' 相关的证据链。",
                data={"matches": [], "chains": []},
            )

        chains = [collector.get_chain_for(node.id).model_dump(mode="json") for node in matches]
        return ToolResult(
            success=True,
            message=f"找到 {len(matches)} 条与 '{query}' 相关的证据链。",
            data={
                "matches": [node.model_dump(mode="json") for node in matches],
                "chains": chains,
            },
        )
