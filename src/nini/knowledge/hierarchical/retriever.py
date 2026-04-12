"""层次化知识检索器。

支持多路召回、RRF融合、重排序和上下文组装。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from nini.knowledge.hierarchical.index import (
    HierarchicalIndex,
)

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """检索结果项。"""

    id: str
    content: str
    score: float
    level: str  # L0, L1, L2
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalOutput:
    """检索输出。"""

    content: str
    hits: list[RetrievalResult]
    total_found: int
    routing_metadata: dict[str, Any] = field(default_factory=dict)


class RRFFusion:
    """Reciprocal Rank Fusion 结果融合。

    使用 RRF 算法融合多个检索源的结果。
    """

    def __init__(self, k: int = 60):
        """初始化 RRF 融合器。

        Args:
            k: RRF 常数，默认 60
        """
        self.k = k

    def fuse(self, results_list: list[list[RetrievalResult]]) -> list[RetrievalResult]:
        """融合多个结果列表。

        Args:
            results_list: 多个检索结果列表

        Returns:
            融合后的结果列表
        """
        if not results_list:
            return []

        scores: dict[str, float] = {}
        result_map: dict[str, RetrievalResult] = {}

        for results in results_list:
            for rank, result in enumerate(results, start=1):
                doc_id = result.id

                # RRF 分数计算
                rrf_score = 1.0 / (self.k + rank)
                scores[doc_id] = scores.get(doc_id, 0) + rrf_score

                # 保留最高质量的结果对象
                if doc_id not in result_map or result.score > result_map[doc_id].score:
                    result_map[doc_id] = result

        # 按总分排序
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

        # 更新分数并返回
        fused_results = []
        for doc_id in sorted_ids:
            result = result_map[doc_id]
            fused_result = RetrievalResult(
                id=result.id,
                content=result.content,
                score=scores[doc_id],  # 使用 RRF 总分
                level=result.level,
                source=result.source,
                metadata={**result.metadata, "rrf_score": scores[doc_id]},
            )
            fused_results.append(fused_result)

        return fused_results


class ContextAssembler:
    """上下文组装器。

    将检索结果组装成连贯的上下文文本。
    """

    def __init__(self, max_tokens: int = 3000):
        """初始化组装器。

        Args:
            max_tokens: 最大 token 数（粗略估计）
        """
        self.max_tokens = max_tokens

    def assemble(
        self,
        results: list[RetrievalResult],
        hierarchical_index: HierarchicalIndex | None = None,
    ) -> str:
        """组装检索结果为上下文文本。

        Args:
            results: 检索结果列表
            hierarchical_index: 层次化索引（用于获取上下文）

        Returns:
            组装后的上下文文本
        """
        if not results:
            return ""

        parts = []
        total_chars = 0
        max_chars = self.max_tokens * 4  # 粗略估计：1 token ≈ 4 字符

        for i, result in enumerate(results, 1):
            content = result.content

            # 如果需要，添加上下文
            if hierarchical_index and result.level == "L2":
                content = self._enrich_with_context(result, hierarchical_index)

            # 格式化结果
            formatted = f"[{i}] {result.source}\n{content}\n"

            if total_chars + len(formatted) > max_chars:
                # 截断
                remaining = max_chars - total_chars
                if remaining > 100:
                    truncated = formatted[:remaining] + "\n..."
                    parts.append(truncated)
                break

            parts.append(formatted)
            total_chars += len(formatted)

        return "\n".join(parts)

    def _enrich_with_context(
        self,
        result: RetrievalResult,
        index: HierarchicalIndex,
    ) -> str:
        """为 L2 结果添加上下文。"""
        # 获取父章节信息
        parent_id = index.get_parent(result.id)
        if not parent_id:
            return result.content

        section = index.get_section(parent_id)
        if not section:
            return result.content

        # 添加章节标题作为上下文
        return f"## {section.title}\n{result.content}"
