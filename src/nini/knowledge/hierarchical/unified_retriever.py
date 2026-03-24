"""统一检索接口。

整合层次化索引、查询路由、缓存、重排序等功能。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from nini.config import settings
from nini.knowledge.hierarchical.cache import RetrievalCache
from nini.knowledge.hierarchical.index import HierarchicalIndex
from nini.knowledge.hierarchical.parser import DocumentNode, SectionNode, ChunkNode
from nini.knowledge.hierarchical.retriever import ContextAssembler, RRFFusion
from nini.knowledge.hierarchical.reranker import CrossEncoderReranker, NoOpReranker
from nini.knowledge.hierarchical.router import QueryRouter

logger = logging.getLogger(__name__)


@dataclass
class UnifiedRetrievalResult:
    """统一检索结果。"""

    content: str  # 组装后的上下文文本
    hits: list[dict[str, Any]]  # 命中详情
    total_found: int  # 总共找到的结果数
    query_time_ms: float  # 查询耗时
    routing_info: dict[str, Any] = field(default_factory=dict)  # 路由信息
    cache_hit: bool = False  # 是否缓存命中


class UnifiedRetriever:
    """统一检索器。

    整合所有检索组件的主入口类。
    """

    def __init__(
        self,
        knowledge_dir: Path | None = None,
        storage_dir: Path | None = None,
    ) -> None:
        """初始化统一检索器。

        Args:
            knowledge_dir: 知识库目录
            storage_dir: 索引存储目录
        """
        self.index = HierarchicalIndex(knowledge_dir, storage_dir)
        self.router = QueryRouter()
        self.cache = RetrievalCache()
        self.fusion = RRFFusion(k=settings.hierarchical_rrf_k)
        self.assembler = ContextAssembler(max_tokens=settings.knowledge_max_tokens)

        # 重排序器（延迟初始化）
        self._reranker: CrossEncoderReranker | None = None
        self._reranker_initialized = False

        # 长期记忆存储引用（可选）
        self._memory_store: Any = None

        self._initialized = False

    async def initialize(self) -> bool:
        """异步初始化检索器。

        Returns:
            是否成功初始化
        """
        if self._initialized:
            return True

        try:
            import asyncio

            # 在后台线程中构建或加载索引
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self.index.build_or_load)

            if not result:
                logger.warning("层次化索引初始化失败")
                return False

            self._initialized = True
            logger.info("统一检索器初始化完成")
            return True

        except Exception as e:
            logger.error(f"初始化统一检索器失败: {e}")
            return False

    async def _get_reranker(self) -> CrossEncoderReranker | NoOpReranker:
        """获取重排序器（延迟初始化）。"""
        if not self._reranker_initialized:
            self._reranker = CrossEncoderReranker()
            await self._reranker.initialize()
            self._reranker_initialized = True

        if self._reranker and self._reranker.is_available:
            return self._reranker
        return NoOpReranker()

    def set_memory_store(self, memory_store: Any) -> None:
        """设置长期记忆存储。

        Args:
            memory_store: 长期记忆存储实例
        """
        self._memory_store = memory_store

    async def search(
        self,
        query: str,
        top_k: int = 5,
        enable_cache: bool = True,
        enable_rerank: bool = True,
    ) -> UnifiedRetrievalResult:
        """执行统一检索。

        Args:
            query: 查询文本
            top_k: 返回结果数量
            enable_cache: 是否使用缓存
            enable_rerank: 是否启用重排序

        Returns:
            UnifiedRetrievalResult: 检索结果
        """
        import time

        start_time = time.time()
        cache_key: str | None = None

        if not self._initialized:
            await self.initialize()

        # 1. 检查缓存
        if enable_cache:
            cache_key = RetrievalCache.generate_key(query, top_k=top_k)
            cached_result = self.cache.get(cache_key)
            if cached_result:
                return UnifiedRetrievalResult(
                    content=cached_result["content"],
                    hits=cached_result["hits"],
                    total_found=cached_result["total_found"],
                    query_time_ms=(time.time() - start_time) * 1000,
                    routing_info=cached_result.get("routing_info", {}),
                    cache_hit=True,
                )

        # 2. 查询路由
        plan, routing_metadata = self.router.route_with_metadata(query)

        # 3. 多路检索
        candidates = await self._multi_source_retrieve(query, plan)

        # 4. 重排序
        final_hits: list[dict[str, Any]]
        if enable_rerank and len(candidates) > 0:
            reranker = await self._get_reranker()
            reranked = await reranker.rerank(
                query,
                candidates,
                top_n=top_k,
            )
            final_hits = [
                {
                    "id": r.id,
                    "content": r.content,
                    "score": r.rerank_score,
                    "source": r.source,
                    "level": r.level,
                    "metadata": r.metadata,
                }
                for r in reranked
            ]
        else:
            final_hits = candidates[:top_k]

        # 5. 上下文组装
        from nini.knowledge.hierarchical.retriever import RetrievalResult

        retrieval_results = [
            RetrievalResult(
                id=str(h.get("id", "")),
                content=str(h.get("content", "")),
                score=float(h.get("score", 0.0)),
                level=str(h.get("level", "")),
                source=str(h.get("source", "")),
                metadata=(
                    cast(dict[str, Any], h.get("metadata", {}))
                    if isinstance(h.get("metadata"), dict)
                    else {}
                ),
            )
            for h in final_hits
        ]
        context = self.assembler.assemble(retrieval_results, self.index)

        # 6. 保存到缓存
        result_data = {
            "content": context,
            "hits": final_hits,
            "total_found": len(candidates),
            "routing_info": routing_metadata,
        }
        if enable_cache and cache_key is not None:
            self.cache.set(cache_key, result_data)

        query_time_ms = (time.time() - start_time) * 1000

        return UnifiedRetrievalResult(
            content=context,
            hits=final_hits,
            total_found=len(candidates),
            query_time_ms=query_time_ms,
            routing_info=routing_metadata,
            cache_hit=False,
        )

    async def _multi_source_retrieve(
        self,
        query: str,
        plan: Any,
    ) -> list[dict[str, Any]]:
        """多路检索：知识库 + 长期记忆。

        Args:
            query: 查询文本
            plan: 路由计划

        Returns:
            候选结果列表
        """
        candidates = []

        # 知识库检索
        kb_results = self._search_knowledge_base(query, plan)
        candidates.extend(kb_results)

        # 长期记忆检索
        if self._memory_store:
            memory_results = await self._search_memory(query)
            candidates.extend(memory_results)

        # 去重并排序
        seen_ids = set()
        unique_candidates = []
        for c in candidates:
            if c["id"] not in seen_ids:
                seen_ids.add(c["id"])
                unique_candidates.append(c)

        unique_candidates.sort(key=lambda x: x["score"], reverse=True)
        return unique_candidates

    def _search_knowledge_base(self, query: str, plan: Any) -> list[dict[str, Any]]:
        """搜索知识库。"""
        results = []
        query_lower = query.lower()

        # 主要层级检索
        results.extend(self._search_at_level(query_lower, plan.primary_level))

        # 辅助层级检索
        if plan.secondary_level:
            results.extend(self._search_at_level(query_lower, plan.secondary_level))

        return results

    def _search_at_level(self, query: str, level: str) -> list[dict[str, Any]]:
        """在指定层级搜索。"""
        results = []

        if level == "L0":
            for doc_id, doc in self.index.l0_index.items():
                score = self._compute_score(query, doc.title + " " + (doc.summary or ""))
                if score > 0:
                    results.append(
                        {
                            "id": doc_id,
                            "content": doc.summary or doc.content[:500],
                            "score": score,
                            "level": "L0",
                            "source": doc.title,
                            "metadata": {"file_path": str(doc.file_path)},
                        }
                    )

        elif level == "L1":
            for section_id, section in self.index.l1_index.items():
                score = self._compute_score(query, section.title + " " + section.content[:500])
                if score > 0:
                    results.append(
                        {
                            "id": section_id,
                            "content": f"## {section.title}\n{section.content[:800]}",
                            "score": score,
                            "level": "L1",
                            "source": section.title,
                            "metadata": {"parent_doc": section.parent_doc_id},
                        }
                    )

        elif level == "L2":
            for chunk_id, chunk in self.index.l2_index.items():
                score = self._compute_score(query, chunk.content)
                if score > 0:
                    results.append(
                        {
                            "id": chunk_id,
                            "content": chunk.content,
                            "score": score,
                            "level": "L2",
                            "source": f"段落 {chunk_id}",
                            "metadata": {"parent_section": chunk.parent_section_id},
                        }
                    )

        return results

    async def _search_memory(self, query: str) -> list[dict[str, Any]]:
        """搜索长期记忆。"""
        if not self._memory_store:
            return []

        try:
            # 调用长期记忆存储的搜索方法
            memory_results = await self._memory_store.search(query, top_k=3)
            return [
                {
                    "id": f"memory:{m.id}",
                    "content": m.content,
                    "score": m.importance_score * 0.8,  # 记忆权重略低
                    "level": "L2",
                    "source": f"历史分析 - {m.summary[:30]}",
                    "metadata": {
                        "memory_type": m.memory_type,
                        "source_session": m.source_session_id,
                    },
                }
                for m in memory_results
            ]
        except Exception as e:
            logger.warning(f"长期记忆检索失败: {e}")
            return []

    def _compute_score(self, query: str, document: str) -> float:
        """计算简单相关性分数。"""
        query_terms = query.split()
        doc_lower = document.lower()

        score = 0
        for term in query_terms:
            if term in doc_lower:
                score += 1

        return score / len(query_terms) if query_terms else 0

    def get_stats(self) -> dict[str, Any]:
        """获取检索器统计信息。"""
        return {
            "index": self.index.get_stats(),
            "cache": self.cache.get_stats(),
            "initialized": self._initialized,
        }
