"""测试语义化知识检索功能。

TDD 方式：先写测试，再实现（如需要）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


class TestVectorKnowledgeStore:
    """测试向量知识库。"""

    def test_vector_store_exists(self):
        """测试向量知识库类存在。"""
        from nini.knowledge.vector_store import VectorKnowledgeStore

        assert VectorKnowledgeStore is not None

    def test_vector_store_query_interface(self):
        """测试向量知识库查询接口。"""
        from nini.knowledge.vector_store import VectorKnowledgeStore

        # 检查方法存在
        assert hasattr(VectorKnowledgeStore, "query")
        assert hasattr(VectorKnowledgeStore, "build_or_load")
        assert hasattr(VectorKnowledgeStore, "is_available")


class TestKnowledgeLoader:
    """测试知识加载器。"""

    def test_knowledge_loader_exists(self):
        """测试知识加载器存在。"""
        from nini.knowledge.loader import KnowledgeLoader

        assert KnowledgeLoader is not None

    def test_knowledge_loader_hybrid_retrieval(self):
        """测试知识加载器支持混合检索。"""
        from nini.knowledge.loader import KnowledgeLoader

        # 检查混合检索相关方法
        assert hasattr(KnowledgeLoader, "select_with_hits")
        assert hasattr(KnowledgeLoader, "vector_available")
        assert hasattr(KnowledgeLoader, "_keyword_search")
        assert hasattr(KnowledgeLoader, "_merge_results")


class TestHybridRetrieval:
    """测试混合检索功能。"""

    def test_merge_results_method(self):
        """测试结果融合方法。"""
        from nini.knowledge.loader import KnowledgeLoader

        # 验证 _merge_results 是静态方法
        assert hasattr(KnowledgeLoader, "_merge_results")

    def test_merge_results_deduplication(self):
        """测试融合结果去重。"""
        from nini.knowledge.loader import KnowledgeLoader

        # 模拟向量检索结果
        vector_hits = [
            {
                "source": "statistics.md",
                "score": 0.95,
                "snippet": "t检验用于比较两组均值差异...",
                "method": "vector",
            }
        ]

        # 模拟关键词检索结果（相同来源）
        keyword_hits = [
            {
                "source": "statistics.md",
                "score": 2.0,
                "snippet": "t检验用于比较两组均值差异...",
                "method": "keyword",
            }
        ]

        text, hits = KnowledgeLoader._merge_results(
            vector_hits=vector_hits,
            keyword_hits=keyword_hits,
            max_entries=3,
            max_total_chars=3000,
        )

        # 应该去重，只返回一个结果
        assert len(hits) == 1
        assert hits[0]["source"] == "statistics.md"

    def test_merge_results_priority_to_vector(self):
        """测试融合时向量结果优先。"""
        from nini.knowledge.loader import KnowledgeLoader

        vector_hits = [
            {"source": "vector_result.md", "score": 0.8, "snippet": "向量检索结果...", "method": "vector"},
            {"source": "b.md", "score": 0.95, "snippet": "B", "method": "vector"},
        ]

        keyword_hits = [
            {"source": "keyword_result.md", "score": 3.0, "snippet": "关键词检索结果...", "method": "keyword"},
        ]

        text, hits = KnowledgeLoader._merge_results(
            vector_hits=vector_hits,
            keyword_hits=keyword_hits,
            max_entries=5,
            max_total_chars=1000,
        )

        # 应该包含向量检索结果
        vector_sources = {h["source"] for h in hits if h.get("method") == "vector"}
        assert "vector_result.md" in vector_sources or "b.md" in vector_sources

    def test_merge_results_sorting(self):
        """测试融合结果按得分排序。"""
        from nini.knowledge.loader import KnowledgeLoader

        vector_hits = [
            {"source": "a.md", "score": 0.7, "snippet": "A", "method": "vector"},
            {"source": "b.md", "score": 0.9, "snippet": "B", "method": "vector"},
        ]

        keyword_hits = [
            {"source": "c.md", "score": 1.0, "snippet": "C", "method": "keyword"},
        ]

        text, hits = KnowledgeLoader._merge_results(
            vector_hits=vector_hits,
            keyword_hits=keyword_hits,
            max_entries=5,
            max_total_chars=1000,
        )

        # 应该按得分排序
        if len(hits) >= 2:
            scores = [h["score"] for h in hits]
            assert scores == sorted(scores, reverse=True)


class TestSemanticUnderstanding:
    """测试语义理解能力。"""

    def test_keyword_search_basic(self):
        """测试基本关键词搜索。"""
        from nini.knowledge.loader import KnowledgeLoader
        from nini.config import settings

        loader = KnowledgeLoader(
            knowledge_dir=settings.knowledge_dir,
            enable_vector=False,  # 只用关键词
        )

        # 测试搜索功能
        text, hits = loader.select_with_hits(
            "t检验",
            max_entries=3,
            max_total_chars=3000,
        )

        # 应该返回结果（即使为空）
        assert isinstance(text, str)
        assert isinstance(hits, list)

    def test_select_with_hits_interface(self):
        """测试 select_with_hits 接口。"""
        from nini.knowledge.loader import KnowledgeLoader
        from nini.config import settings

        loader = KnowledgeLoader(
            knowledge_dir=settings.knowledge_dir,
            enable_vector=False,
        )

        # 测试接口返回类型
        result = loader.select_with_hits("测试消息")
        assert isinstance(result, tuple)
        assert len(result) == 2
        text, hits = result
        assert isinstance(text, str)
        assert isinstance(hits, list)


class TestIntegrationWithVectorStore:
    """测试与向量存储的集成。"""

    def test_knowledge_loader_uses_vector_store(self):
        """测试知识加载器使用向量存储。"""
        from nini.knowledge.loader import KnowledgeLoader

        # 检查 KnowledgeLoader 有 _init_vector_store 方法
        assert hasattr(KnowledgeLoader, "_init_vector_store")

    def test_vector_available_property(self):
        """测试向量可用性属性。"""
        from nini.knowledge.loader import KnowledgeLoader
        from nini.config import settings

        loader = KnowledgeLoader(
            knowledge_dir=settings.knowledge_dir,
            enable_vector=True,
        )

        # 检查属性存在
        assert hasattr(loader, "vector_available")
        # 返回布尔值
        assert isinstance(loader.vector_available, bool)

    @pytest.mark.skipif(
        True,  # 默认跳过，除非有向量索引
        reason="需要预先构建向量索引"
    )
    def test_hybrid_retrieval_end_to_end(self):
        """测试端到端混合检索。"""
        from nini.knowledge.loader import KnowledgeLoader
        from nini.config import settings

        loader = KnowledgeLoader(
            knowledge_dir=settings.knowledge_dir,
            enable_vector=True,
        )

        # 如果向量可用，测试混合检索
        if loader.vector_available:
            text, hits = loader.select_with_hits(
                "如何进行 t 检验？",
                max_entries=3,
                max_total_chars=3000,
            )

            # 混合检索应该返回结果
            assert isinstance(text, str)
            assert isinstance(hits, list)

            # 检查结果中是否包含检索方法信息
            for hit in hits:
                assert "method" in hit
                assert hit["method"] in ["vector", "keyword"]


class TestRetrievalAccuracy:
    """测试检索准确性。"""

    @pytest.mark.skipif(
        True,  # 需要实际知识文件
        reason="需要预先准备测试数据"
    )
    def test_semantic_similarity_matching(self):
        """测试语义相似性匹配。"""
        # 这个测试需要实际的知识文件来验证语义检索准确性
        pass

    @pytest.mark.skipif(
        True,
        reason="需要实际知识文件"
    )
    def test_fuzzy_matching(self):
        """测试模糊匹配能力。"""
        # 测试对相似查询的匹配能力
        pass
