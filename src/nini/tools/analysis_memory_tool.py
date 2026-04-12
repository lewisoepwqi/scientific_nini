"""分析记忆查询工具。

允许 LLM 主动检索当前会话的历史分析记忆，包括统计结果、发现和决策。
在长会话中，当早期分析结果从 context 中消失时，可通过此工具按需检索。
"""

from __future__ import annotations

from typing import Any

from nini.agent.session import resolve_session_resource_id
from nini.agent.session import Session
from nini.tools.base import Tool, ToolResult


class AnalysisMemoryTool(Tool):
    """分析记忆查询工具。

    支持两种操作：
    - list: 返回当前会话所有分析记忆的摘要（数据集名 + 条目数）
    - find: 按关键词和可选数据集名过滤，返回匹配的完整数值
    """

    @property
    def name(self) -> str:
        return "analysis_memory"

    @property
    def expose_to_llm(self) -> bool:
        return False

    @property
    def description(self) -> str:
        return (
            "查询当前会话的历史分析记忆（统计结果、关键发现、方法决策）。"
            "operation='list' 返回所有数据集的记忆摘要；"
            "operation='find' 按关键词检索具体数值（p 值、效应量等）。"
            "当需要引用之前分析的具体数值时使用此工具。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["list", "find"],
                    "description": "操作类型：list=列出所有记忆摘要，find=按关键词检索详细数值",
                },
                "keyword": {
                    "type": "string",
                    "description": "检索关键词，模糊匹配 finding.summary / statistic.test_name（operation='find' 时可选）",
                },
                "dataset_name": {
                    "type": "string",
                    "description": "过滤特定数据集（可选，为空时跨所有数据集检索）",
                },
            },
            "required": ["operation"],
        }

    async def execute(self, session: Session, **kwargs: Any) -> ToolResult:
        """执行分析记忆查询。"""
        import json

        from nini.memory.compression import list_session_analysis_memories

        operation = str(kwargs.get("operation", "list")).strip()
        keyword = str(kwargs.get("keyword", "") or "").strip().lower()
        dataset_filter = str(kwargs.get("dataset_name", "") or "").strip().lower()

        # find 操作优先使用 MemoryManager（跨会话长期记忆）；失败或未初始化时降级
        if operation == "find":
            try:
                from nini.memory.manager import get_memory_manager

                manager = get_memory_manager()
                if manager is not None:
                    raw = await manager.handle_tool_call(
                        "nini_memory_find",
                        {
                            "query": keyword,
                            "dataset_name": dataset_filter or None,
                            "top_k": 10,
                        },
                    )
                    parsed = json.loads(raw)
                    if parsed.get("success") and parsed.get("results"):
                        results = parsed["results"]
                        return ToolResult(
                            success=True,
                            message=f"从长期记忆中找到 {len(results)} 条匹配结果。",
                            data={"results": results},
                        )
            except Exception:
                pass  # 降级到原有路径

        memories = list_session_analysis_memories(resolve_session_resource_id(session))

        if operation == "list":
            return self._handle_list(memories)
        elif operation == "find":
            return self._handle_find(memories, keyword=keyword, dataset_filter=dataset_filter)
        else:
            return ToolResult(
                success=False,
                message=f"不支持的操作：{operation}，请使用 'list' 或 'find'",
            )

    def _handle_list(self, memories: list[Any]) -> ToolResult:
        """列出所有分析记忆的摘要。"""
        if not memories:
            return ToolResult(
                success=True,
                message="当前会话暂无分析记忆。",
                data={"memories": []},
            )

        summaries = []
        for mem in memories:
            summaries.append(
                {
                    "dataset_name": mem.dataset_name,
                    "findings": len(mem.findings),
                    "statistics": len(mem.statistics),
                    "decisions": len(mem.decisions),
                    "artifacts": len(mem.artifacts),
                }
            )

        return ToolResult(
            success=True,
            message=f"找到 {len(summaries)} 个数据集的分析记忆。",
            data={"memories": summaries},
        )

    def _handle_find(
        self,
        memories: list[Any],
        *,
        keyword: str,
        dataset_filter: str,
    ) -> ToolResult:
        """按关键词检索分析记忆详细数值。"""
        if not memories:
            return ToolResult(
                success=True,
                message="当前会话暂无分析记忆。",
                data={"results": []},
            )

        results: list[dict[str, Any]] = []

        for mem in memories:
            # 按数据集过滤
            if dataset_filter and dataset_filter not in mem.dataset_name.lower():
                continue

            matched_statistics = []
            for s in mem.statistics:
                test_name_lower = s.test_name.lower()
                if not keyword or keyword in test_name_lower:
                    entry: dict[str, Any] = {
                        "test_name": s.test_name,
                        "significant": s.significant,
                    }
                    if s.test_statistic is not None:
                        entry["test_statistic"] = s.test_statistic
                    if s.p_value is not None:
                        entry["p_value"] = s.p_value
                    if s.effect_size is not None:
                        entry["effect_size"] = s.effect_size
                        if s.effect_type:
                            entry["effect_type"] = s.effect_type
                    if s.degrees_of_freedom is not None:
                        entry["degrees_of_freedom"] = s.degrees_of_freedom
                    matched_statistics.append(entry)

            matched_findings = []
            for f in mem.findings:
                summary_lower = f.summary.lower()
                category_lower = f.category.lower()
                if not keyword or keyword in summary_lower or keyword in category_lower:
                    matched_findings.append(
                        {
                            "category": f.category,
                            "summary": f.summary,
                            "detail": f.detail,
                            "confidence": f.confidence,
                        }
                    )

            # 最多返回 5 条匹配结果
            if matched_statistics or matched_findings:
                results.append(
                    {
                        "dataset_name": mem.dataset_name,
                        "statistics": matched_statistics[:5],
                        "findings": matched_findings[:5],
                    }
                )

        if not results:
            hint = f"关键词 '{keyword}'" if keyword else "任意内容"
            ds_hint = f"数据集 '{dataset_filter}'" if dataset_filter else "所有数据集"
            return ToolResult(
                success=True,
                message=f"在 {ds_hint} 中未找到与 {hint} 匹配的分析记忆。",
                data={"results": []},
            )

        return ToolResult(
            success=True,
            message=f"找到 {len(results)} 个数据集的匹配结果。",
            data={"results": results},
        )
