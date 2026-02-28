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
from nini.models.knowledge import (
    HybridSearchConfig,
    KnowledgeDocument,
    KnowledgeSearchResult,
)

logger = logging.getLogger(__name__)


class KeywordIndex:
    """简单的关键词索引（基于 TF-IDF 概念简化版）。"""

    def __init__(self):
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
    """混合检索器（向量 + 关键词）。"""

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

        self.vector_store = VectorKnowledgeStore(
            knowledge_dir=knowledge_dir,
            storage_dir=storage_dir,
        )
        self.keyword_index = KeywordIndex()
        self._initialized = False

    async def initialize(self) -> None:
        """初始化检索器。"""
        if self._initialized:
            return

        try:
            await self.vector_store.initialize()
            self._initialized = True
            logger.info("混合检索器初始化完成")
        except Exception as e:
            logger.warning(f"向量存储初始化失败: {e}")
            # 关键词索引仍可使用
            self._initialized = True

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
    ) -> KnowledgeSearchResult:
        """执行混合检索。

        Args:
            query: 查询文本
            top_k: 返回结果数量
            domain: 领域过滤

        Returns:
            搜索结果
        """
        start_time = time.time()
        top_k = top_k or self.config.top_k

        # 向量检索
        vector_results = []
        if self.vector_store._initialized:
            try:
                vector_results = await self.vector_store.search(query, top_k=top_k * 2)
            except Exception as e:
                logger.warning(f"向量检索失败: {e}")

        # 关键词检索
        keyword_results = self.keyword_index.search(query, top_k=top_k * 2)

        # 合并结果（加权）
        combined_scores: dict[str, tuple[float, str]] = {}  # doc_id -> (score, source)

        # 添加向量结果
        max_vector_score = max((r[1] for r in vector_results), default=1.0) or 1.0
        for doc_id, score in vector_results:
            normalized_score = score / max_vector_score * self.config.vector_weight
            combined_scores[doc_id] = (normalized_score, "vector")

        # 添加关键词结果
        max_keyword_score = max((r[1] for r in keyword_results), default=1.0) or 1.0
        for doc_id, score in keyword_results:
            normalized_score = score / max_keyword_score * self.config.keyword_weight
            if doc_id in combined_scores:
                # 已在向量结果中，累加分数
                existing_score, _ = combined_scores[doc_id]
                combined_scores[doc_id] = (existing_score + normalized_score, "hybrid")
            else:
                combined_scores[doc_id] = (normalized_score, "keyword")

        # 按分数排序
        sorted_results = sorted(
            combined_scores.items(),
            key=lambda x: x[1][0],
            reverse=True,
        )[:top_k]

        # 构建文档列表
        documents = []
        for doc_id, (score, source) in sorted_results:
            # 从向量存储获取完整信息
            doc_info = None
            if self.vector_store._initialized:
                doc_info = await self.vector_store.get_document(doc_id)

            if doc_info:
                doc = KnowledgeDocument(
                    id=doc_id,
                    title=doc_info.get("metadata", {}).get("title", "未知文档"),
                    content=doc_info.get("content", ""),
                    excerpt=doc_info.get("content", "")[:200] + "...",
                    relevance_score=score,
                    source_method=source,  # type: ignore
                    metadata=doc_info.get("metadata", {}),
                )
            else:
                # 从关键词索引获取
                keyword_doc = self.keyword_index.documents.get(doc_id, {})
                doc = KnowledgeDocument(
                    id=doc_id,
                    title=keyword_doc.get("metadata", {}).get("title", "未知文档"),
                    content=keyword_doc.get("content", ""),
                    excerpt=keyword_doc.get("content", "")[:200] + "...",
                    relevance_score=score,
                    source_method=source,  # type: ignore
                    metadata=keyword_doc.get("metadata", {}),
                )

            documents.append(doc)

        search_time_ms = int((time.time() - start_time) * 1000)

        return KnowledgeSearchResult(
            query=query,
            results=documents,
            total_count=len(documents),
            search_method="hybrid",
            search_time_ms=search_time_ms,
        )


# 全局混合检索器实例
_hybrid_retriever: HybridRetriever | None = None


async def get_hybrid_retriever() -> HybridRetriever:
    """获取全局混合检索器实例。"""
    global _hybrid_retriever
    if _hybrid_retriever is None:
        _hybrid_retriever = HybridRetriever()
        await _hybrid_retriever.initialize()
    return _hybrid_retriever
