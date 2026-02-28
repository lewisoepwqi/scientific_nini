"""混合检索器测试。

测试向量检索和关键词检索的混合搜索功能。
"""

import pytest
from unittest.mock import Mock, patch

from nini.knowledge.hybrid_retriever import (
    HybridRetriever,
    KeywordIndex,
    get_hybrid_retriever,
)
from nini.models.knowledge import (
    HybridSearchConfig,
    KnowledgeDocument,
)


class TestKeywordIndex:
    """关键词索引测试。"""

    def test_add_document(self):
        """测试添加文档。"""
        index = KeywordIndex()
        index.add_document(doc_id="doc1", content="这是一个测试文档", metadata={"title": "测试"})

        assert "doc1" in index.documents
        assert index.documents["doc1"]["content"] == "这是一个测试文档"
        assert index.documents["doc1"]["metadata"]["title"] == "测试"

    def test_search_simple(self):
        """测试简单搜索。"""
        index = KeywordIndex()
        index.add_document("doc1", "Python编程指南")
        index.add_document("doc2", "JavaScript开发手册")

        results = index.search("Python", top_k=5)

        assert len(results) > 0
        # search返回的是 (doc_id, score) 元组列表
        assert results[0][0] == "doc1"
        assert results[0][1] > 0

    def test_search_chinese(self):
        """测试中文搜索。"""
        index = KeywordIndex()
        index.add_document("doc1", "统计分析方法")
        index.add_document("doc2", "数据可视化技术")

        results = index.search("统计", top_k=5)

        assert len(results) > 0
        assert results[0][0] == "doc1"

    def test_remove_document(self):
        """测试删除文档。"""
        index = KeywordIndex()
        index.add_document("doc1", "测试内容")
        assert "doc1" in index.documents

        index.remove_document("doc1")
        assert "doc1" not in index.documents


class TestHybridRetrieverBasic:
    """混合检索器基础测试。"""

    @patch("nini.knowledge.hybrid_retriever.VectorKnowledgeStore")
    def test_initialization(self, mock_vector_store):
        """测试初始化。"""
        config = HybridSearchConfig(vector_weight=0.7, keyword_weight=0.3, top_k=10)
        retriever = HybridRetriever(config)

        assert retriever.config.vector_weight == 0.7
        assert retriever.config.keyword_weight == 0.3
        assert retriever.config.top_k == 10

    @patch("nini.knowledge.hybrid_retriever.VectorKnowledgeStore")
    def test_default_initialization(self, mock_vector_store):
        """测试默认初始化。"""
        retriever = HybridRetriever()

        assert retriever.config.vector_weight == 0.7
        assert retriever.config.keyword_weight == 0.3
        assert retriever.config.top_k == 5


class TestHybridSearchConfig:
    """混合搜索配置测试。"""

    def test_default_values(self):
        """测试默认值。"""
        config = HybridSearchConfig()

        assert config.vector_weight == 0.7
        assert config.keyword_weight == 0.3
        assert config.top_k == 5
        assert config.relevance_threshold == 0.5
        assert config.max_tokens == 2000

    def test_custom_values(self):
        """测试自定义值。"""
        config = HybridSearchConfig(
            vector_weight=0.8,
            keyword_weight=0.2,
            top_k=10,
            relevance_threshold=0.6,
            max_tokens=3000,
        )

        assert config.vector_weight == 0.8
        assert config.keyword_weight == 0.2
        assert config.top_k == 10
        assert config.relevance_threshold == 0.6
        assert config.max_tokens == 3000

    def test_weights_sum(self):
        """测试权重和应该接近1.0。"""
        config = HybridSearchConfig(vector_weight=0.6, keyword_weight=0.4)
        assert config.vector_weight + config.keyword_weight == 1.0


class TestGetHybridRetriever:
    """获取混合检索器单例测试。"""

    @pytest.mark.asyncio
    async def test_returns_retriever(self):
        """测试返回检索器实例。"""
        retriever = await get_hybrid_retriever()
        assert isinstance(retriever, HybridRetriever)

    @pytest.mark.asyncio
    async def test_returns_same_instance(self):
        """测试返回相同实例（单例模式）。"""
        retriever1 = await get_hybrid_retriever()
        retriever2 = await get_hybrid_retriever()
        assert retriever1 is retriever2


class TestKnowledgeDocumentCreation:
    """知识文档创建测试。"""

    def test_basic_creation(self):
        """测试基本创建。"""
        doc = KnowledgeDocument(
            id="doc-1",
            title="测试文档",
            content="这是测试内容",
            excerpt="这是摘要...",
            relevance_score=0.95,
            source_method="vector",
        )

        assert doc.id == "doc-1"
        assert doc.title == "测试文档"
        assert doc.content == "这是测试内容"
        assert doc.relevance_score == 0.95

    def test_default_values(self):
        """测试默认值。"""
        doc = KnowledgeDocument(id="doc-1", title="测试", content="内容")

        assert doc.relevance_score == 0.0
        assert doc.source_method == "vector"
        assert doc.metadata == {}
