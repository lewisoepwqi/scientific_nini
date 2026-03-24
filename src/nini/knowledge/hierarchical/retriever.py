"""层次化知识检索器。

支持多路召回、RRF融合、重排序和上下文组装。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from nini.config import settings
from nini.knowledge.hierarchical.index import (
    ChunkNode,
    DocumentNode,
    HierarchicalIndex,
    SectionNode,
)
from nini.knowledge.hierarchical.router import QueryRouter

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


class HierarchicalKnowledgeRetriever:
    """层次化知识检索器。

    主入口类，整合查询路由、多路召回、融合和上下文组装。
    """

    def __init__(
        self,
        knowledge_dir: Any = None,
        storage_dir: Any = None,
    ) -> None:
        """初始化检索器。

        Args:
            knowledge_dir: 知识库目录
            storage_dir: 索引存储目录
        """
        self.index = HierarchicalIndex(knowledge_dir, storage_dir)
        self.router = QueryRouter()
        self.fusion = RRFFusion(k=settings.hierarchical_rrf_k)
        self.assembler = ContextAssembler(max_tokens=settings.knowledge_max_tokens)

        # 初始化时构建或加载索引
        self._initialized = False

    async def initialize(self) -> bool:
        """异步初始化索引。

        Returns:
            是否成功初始化
        """
        if self._initialized:
            return True

        # 在后台线程中执行
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self.index.build_or_load)
        self._initialized = result
        return result

    async def search(
        self,
        query: str,
        top_k: int | None = None,
        strategy: str | None = None,
    ) -> RetrievalOutput:
        """执行层次化知识检索。

        Args:
            query: 查询文本
            top_k: 返回结果数量（覆盖路由默认值）
            strategy: 检索策略（覆盖路由默认值）

        Returns:
            RetrievalOutput: 检索结果
        """
        if not self._initialized:
            await self.initialize()

        # 1. 查询路由
        plan, routing_metadata = self.router.route_with_metadata(query)

        # 使用覆盖参数
        if top_k is not None:
            plan.top_k = top_k
        if strategy is not None:
            plan.strategy = strategy

        # 2. 层次化检索
        results = self._hierarchical_search(query, plan)

        # 3. 上下文组装
        content = self.assembler.assemble(results, self.index)

        return RetrievalOutput(
            content=content,
            hits=results[: plan.top_k],
            total_found=len(results),
            routing_metadata=routing_metadata,
        )

    def _hierarchical_search(
        self,
        query: str,
        plan: Any,
    ) -> list[RetrievalResult]:
        """执行层次化检索。"""
        results: list[RetrievalResult] = []

        # 主要层级检索
        primary_results = self._search_at_level(query, plan.primary_level)
        results.extend(primary_results)

        # 辅助层级检索
        if plan.secondary_level:
            secondary_results = self._search_at_level(query, plan.secondary_level)
            results.extend(secondary_results)

        # 去重并按分数排序
        seen_ids = set()
        unique_results = []
        for r in results:
            if r.id not in seen_ids:
                seen_ids.add(r.id)
                unique_results.append(r)

        unique_results.sort(key=lambda x: x.score, reverse=True)
        return unique_results

    def _search_at_level(
        self,
        query: str,
        level: str,
    ) -> list[RetrievalResult]:
        """在指定层级搜索。"""
        query_lower = query.lower()
        results = []

        if level == "L0":
            # 文档级搜索（标题匹配）
            for doc_id, doc in self.index.l0_index.items():
                score = self._compute_bm25_score(query_lower, doc.title + " " + doc.summary)
                if score > 0:
                    results.append(
                        RetrievalResult(
                            id=doc_id,
                            content=doc.summary or doc.content[:500],
                            score=score,
                            level="L0",
                            source=doc.title,
                        )
                    )

        elif level == "L1":
            # 章节级搜索
            for section_id, section in self.index.l1_index.items():
                score = self._compute_bm25_score(
                    query_lower, section.title + " " + section.content[:1000]
                )
                if score > 0:
                    results.append(
                        RetrievalResult(
                            id=section_id,
                            content=f"## {section.title}\n{section.content[:800]}",
                            score=score,
                            level="L1",
                            source=section.title,
                        )
                    )

        elif level == "L2":
            # 段落级搜索
            for chunk_id, chunk in self.index.l2_index.items():
                score = self._compute_bm25_score(query_lower, chunk.content)
                if score > 0:
                    results.append(
                        RetrievalResult(
                            id=chunk_id,
                            content=chunk.content,
                            score=score,
                            level="L2",
                            source=f"段落 {chunk_id}",
                        )
                    )

        return results

    def _compute_bm25_score(self, query: str, document: str) -> float:
        """计算简化的 BM25 分数。

        实际实现应使用 rank_bm25 库。
        """
        # 简单的关键词匹配分数
        query_terms = query.split()
        doc_lower = document.lower()

        score = 0
        for term in query_terms:
            if term in doc_lower:
                score += 1

        return score / len(query_terms) if query_terms else 0
