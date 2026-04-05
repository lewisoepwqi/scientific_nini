"""混合检索器。

结合向量检索和关键词检索，提供更准确的知识库查询结果。
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any

from nini.knowledge.vector_store import VectorKnowledgeStore
from nini.memory.long_term_memory import (
    format_memories_for_context,
    search_long_term_memories,
)
from nini.models.knowledge import (
    HybridSearchConfig,
    KnowledgeDocument,
    KnowledgeSearchResult,
)

logger = logging.getLogger(__name__)


class KeywordIndex:
    """简单的关键词索引（基于 TF-IDF 概念简化版）。"""

    def __init__(self) -> None:
        self.documents: dict[str, dict[str, Any]] = {}
        self.word_docs: dict[str, set[str]] = {}

    def add_document(
        self, doc_id: str, content: str, metadata: dict[str, Any] | None = None
    ) -> None:
        """添加文档到索引。"""
        words = self._tokenize(content)
        word_freq: dict[str, int] = {}
        for word in words:
            word_freq[word] = word_freq.get(word, 0) + 1

        self.documents[doc_id] = {
            "content": content,
            "word_freq": word_freq,
            "metadata": metadata or {},
        }

        for word in set(words):
            if word not in self.word_docs:
                self.word_docs[word] = set()
            self.word_docs[word].add(doc_id)

    def remove_document(self, doc_id: str) -> None:
        """从索引中移除文档。"""
        if doc_id not in self.documents:
            return

        doc = self.documents[doc_id]
        for word in doc["word_freq"]:
            if word in self.word_docs:
                self.word_docs[word].discard(doc_id)

        del self.documents[doc_id]

    def search(self, query: str, top_k: int = 5) -> list[tuple[str, float]]:
        """搜索文档，返回 (doc_id, score) 列表。"""
        query_words = self._tokenize(query)
        if not query_words:
            return []

        scores: dict[str, float] = {}
        for word in query_words:
            if word in self.word_docs:
                for doc_id in self.word_docs[word]:
                    if doc_id not in scores:
                        scores[doc_id] = 0.0
                    # 简单词频评分
                    doc_freq = self.documents[doc_id]["word_freq"].get(word, 0)
                    scores[doc_id] += doc_freq

        # 归一化（按文档长度）
        for doc_id in scores:
            doc_len = sum(self.documents[doc_id]["word_freq"].values())
            if doc_len > 0:
                scores[doc_id] /= doc_len

        # 按得分排序
        sorted_results = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_results[:top_k]

    def _tokenize(self, text: str) -> list[str]:
        """分词（简化版）。"""
        # 转换为小写，提取字母数字中文字符
        text = text.lower()
        # 中文分词：按字符分割
        chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
        # 英文分词：按单词分割
        english_words = re.findall(r"[a-z0-9]+", text)
        return chinese_chars + english_words


class HybridRetriever:
    """混合检索器（向量 + BM25 + 关键词 TF-IDF）。"""

    def __init__(
        self,
        config: HybridSearchConfig | None = None,
        knowledge_dir: Path | None = None,
        storage_dir: Path | None = None,
    ):
        """初始化混合检索器。

        Args:
            config: 混合检索配置
            knowledge_dir: 知识库目录
            storage_dir: 向量存储目录
        """
        from nini.config import settings

        self.config = config or HybridSearchConfig()

        # 使用提供的路径或从 settings 获取
        if knowledge_dir is None:
            knowledge_dir = settings.knowledge_dir
        if storage_dir is None:
            storage_dir = settings.knowledge_dir / "vector_store"

        self._knowledge_dir = knowledge_dir
        self.vector_store = VectorKnowledgeStore(
            knowledge_dir=knowledge_dir,
            storage_dir=storage_dir,
        )
        # TF-IDF 关键词索引（用于动态添加/删除文档回退）
        self.keyword_index = KeywordIndex()
        # BM25 检索器（文件级知识库，懒初始化）
        self._bm25_retriever: Any = None
        self._bm25_available = False
        self._initialized = False

    async def initialize(self) -> None:
        """初始化检索器。"""
        if self._initialized:
            return

        try:
            await self.vector_store.initialize()
        except Exception as e:
            logger.warning(f"向量存储初始化失败: {e}")

        # 初始化 BM25 检索器（同步，在线程池中执行）
        try:
            from nini.knowledge.local_bm25 import LocalBM25Retriever

            bm25 = LocalBM25Retriever(
                knowledge_dir=self._knowledge_dir,
                cache_dir=self._knowledge_dir / ".bm25_cache",
            )
            # BM25 初始化本身是轻量同步流程；避免在线程池中调度后出现挂起。
            success = bm25.initialize()
            if success:
                self._bm25_retriever = bm25
                self._bm25_available = True
                logger.info("BM25 检索器初始化完成")
            else:
                logger.warning("BM25 初始化失败，回退到 TF-IDF")
        except Exception as e:
            logger.warning("BM25 初始化失败，回退到 TF-IDF: %s", e)

        self._initialized = True
        logger.info("混合检索器初始化完成")

    async def add_document(
        self,
        doc_id: str,
        content: str,
        title: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """添加文档到索引。

        Args:
            doc_id: 文档 ID
            content: 文档内容
            title: 文档标题
            metadata: 元数据

        Returns:
            是否成功
        """
        try:
            # 添加到关键词索引
            self.keyword_index.add_document(doc_id, content, metadata)

            # 添加到向量索引
            if self.vector_store._initialized:
                doc_metadata = metadata or {}
                doc_metadata["title"] = title
                await self.vector_store.add_document(doc_id, content, doc_metadata)

            return True
        except Exception as e:
            logger.error(f"添加文档失败: {e}")
            return False

    async def remove_document(self, doc_id: str) -> bool:
        """从索引中移除文档。

        Args:
            doc_id: 文档 ID

        Returns:
            是否成功
        """
        try:
            self.keyword_index.remove_document(doc_id)
            if self.vector_store._initialized:
                await self.vector_store.remove_document(doc_id)
            return True
        except Exception as e:
            logger.error(f"移除文档失败: {e}")
            return False

    async def search(
        self,
        query: str,
        top_k: int | None = None,
        domain: str | None = None,
        include_long_term_memory: bool = True,
    ) -> KnowledgeSearchResult:
        """执行混合检索。

        Args:
            query: 查询文本
            top_k: 返回结果数量
            domain: 领域过滤
            include_long_term_memory: 是否包含长期记忆检索

        Returns:
            搜索结果
        """
        start_time = time.time()
        top_k = top_k or self.config.top_k

        # 向量检索
        vector_results: list[tuple[str, float]] = []
        if self.vector_store._initialized:
            try:
                vector_results = await self.vector_store.search(query, top_k=top_k * 2)
            except Exception as e:
                logger.warning(f"向量检索失败: {e}")

        # BM25 检索（文件级知识库）
        bm25_results: list[tuple[str, float]] = []
        if self._bm25_available and self._bm25_retriever is not None:
            try:
                import asyncio

                _, bm25_raw = await asyncio.get_running_loop().run_in_executor(
                    None, self._bm25_retriever.search, query, top_k * 2
                )
                bm25_results = [(r["id"], float(r["score"])) for r in bm25_raw]
            except Exception as e:
                logger.warning(f"BM25 检索失败: {e}")

        # TF-IDF 关键词检索（动态添加文档的补充）
        keyword_results = self.keyword_index.search(query, top_k=top_k * 2)

        # RRF 融合（Reciprocal Rank Fusion，k=60）
        def _rrf(rank: int, k: int = 60) -> float:
            """计算 RRF 分数。"""
            return 1.0 / (k + rank + 1)

        rrf_scores: dict[str, float] = {}
        source_map: dict[str, str] = {}

        for rank, (doc_id, _) in enumerate(vector_results):
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + _rrf(rank)
            source_map[doc_id] = "vector"

        for rank, (doc_id, _) in enumerate(bm25_results):
            prev = rrf_scores.get(doc_id, 0.0)
            rrf_scores[doc_id] = prev + _rrf(rank)
            # 标记来源：已在向量结果则变为 hybrid；BM25 属于关键词检索，映射为 "keyword"
            source_map[doc_id] = "hybrid" if doc_id in source_map else "keyword"

        for rank, (doc_id, _) in enumerate(keyword_results):
            prev = rrf_scores.get(doc_id, 0.0)
            rrf_scores[doc_id] = prev + _rrf(rank)
            if doc_id not in source_map:
                source_map[doc_id] = "keyword"
            elif source_map[doc_id] != "hybrid":
                source_map[doc_id] = "hybrid"

        sorted_results = sorted(
            rrf_scores.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:top_k]

        # 构建文档列表
        documents = []
        for doc_id, score in sorted_results:
            source = source_map.get(doc_id, "hybrid")
            # 从向量存储获取完整信息
            doc_info = None
            if self.vector_store._initialized:
                doc_info = await self.vector_store.get_document(doc_id)

            if doc_info:
                # 尝试多个位置获取标题：metadata.title > title字段 > doc_id
                metadata = doc_info.get("metadata", {})
                title = metadata.get("title") or doc_info.get("title") or doc_id
                doc = KnowledgeDocument(
                    id=doc_id,
                    title=title,
                    content=doc_info.get("content", ""),
                    excerpt=doc_info.get("content", "")[:200] + "...",
                    relevance_score=score,
                    source_method=source,  # type: ignore
                    metadata=metadata,
                )
            else:
                # 从关键词索引获取
                keyword_doc = self.keyword_index.documents.get(doc_id, {})
                metadata = keyword_doc.get("metadata", {})
                title = metadata.get("title") or keyword_doc.get("title") or doc_id
                doc = KnowledgeDocument(
                    id=doc_id,
                    title=title,
                    content=keyword_doc.get("content", ""),
                    excerpt=keyword_doc.get("content", "")[:200] + "...",
                    relevance_score=score,
                    source_method=source,  # type: ignore
                    metadata=metadata,
                )

            documents.append(doc)

        # 长期记忆检索
        long_term_memories = []
        if include_long_term_memory:
            try:
                long_term_memories = await search_long_term_memories(
                    query,
                    top_k=min(3, top_k),
                )
            except Exception as e:
                logger.warning(f"长期记忆检索失败: {e}")

        search_time_ms = int((time.time() - start_time) * 1000)

        result = KnowledgeSearchResult(
            query=query,
            results=documents,
            total_count=len(documents),
            search_method="hybrid",
            search_time_ms=search_time_ms,
        )

        # 添加长期记忆到结果
        if long_term_memories:
            result.metadata = {"long_term_memories": long_term_memories}

        logger.info(
            "混合检索完成: query=%s results=%d duration_ms=%d",
            query,
            len(documents),
            search_time_ms,
        )
        return result

    async def rebuild_index(self) -> bool:
        """重建索引。

        Returns:
            是否成功
        """
        try:
            if self.vector_store._initialized:
                await self.vector_store.rebuild_index()
            logger.info("索引重建完成")
            return True
        except Exception as e:
            logger.error(f"重建索引失败: {e}")
            return False

    async def get_status(self) -> dict[str, Any]:
        """获取检索器状态。

        Returns:
            状态信息
        """
        status: dict[str, Any] = {
            "vector_store_available": self.vector_store._initialized,
            "keyword_index_documents": len(self.keyword_index.documents),
            "bm25_available": self._bm25_available,
        }
        if self._bm25_available and self._bm25_retriever is not None:
            status["bm25_stats"] = self._bm25_retriever.get_stats()
        return status


# 全局混合检索器实例
_hybrid_retriever: HybridRetriever | None = None


async def get_hybrid_retriever() -> HybridRetriever:
    """获取全局混合检索器实例。"""
    global _hybrid_retriever
    if _hybrid_retriever is None:
        _hybrid_retriever = HybridRetriever()
        await _hybrid_retriever.initialize()
    return _hybrid_retriever
