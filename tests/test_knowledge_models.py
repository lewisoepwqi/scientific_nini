"""知识检索模型测试。"""

import pytest
from datetime import datetime, timezone
from nini.models.knowledge import (
    KnowledgeDocument,
    KnowledgeSearchResult,
    KnowledgeDocumentMetadata,
    CitationInfo,
    KnowledgeContext,
    HybridSearchConfig,
    DomainBoostConfig,
)


class TestKnowledgeDocument:
    """KnowledgeDocument 模型测试。"""

    def test_basic_creation(self):
        """测试基本创建。"""
        doc = KnowledgeDocument(
            id="doc-1",
            title="测试文档",
            content="这是测试内容",
            excerpt="这是测试...",
            relevance_score=0.95,
            source_method="vector",
        )
        assert doc.id == "doc-1"
        assert doc.title == "测试文档"
        assert doc.content == "这是测试内容"
        assert doc.excerpt == "这是测试..."
        assert doc.relevance_score == 0.95
        assert doc.source_method == "vector"

    def test_default_values(self):
        """测试默认值。"""
        doc = KnowledgeDocument(
            id="doc-1",
            title="测试文档",
            content="内容",
        )
        assert doc.relevance_score == 0.0
        assert doc.source_method == "vector"
        assert doc.metadata == {}
        assert doc.file_type == "txt"
        assert doc.file_size == 0


class TestKnowledgeSearchResult:
    """KnowledgeSearchResult 模型测试。"""

    def test_basic_creation(self):
        """测试基本创建。"""
        doc1 = KnowledgeDocument(
            id="doc-1",
            title="文档1",
            content="内容1",
            relevance_score=0.9,
        )
        doc2 = KnowledgeDocument(
            id="doc-2",
            title="文档2",
            content="内容2",
            relevance_score=0.8,
        )
        result = KnowledgeSearchResult(
            query="测试查询",
            results=[doc1, doc2],
            total_count=2,
            search_method="hybrid",
            search_time_ms=150,
        )
        assert result.query == "测试查询"
        assert len(result.results) == 2
        assert result.total_count == 2
        assert result.search_method == "hybrid"
        assert result.search_time_ms == 150

    def test_to_dict(self):
        """测试转换为字典。"""
        doc = KnowledgeDocument(
            id="doc-1",
            title="文档1",
            content="内容1",
            relevance_score=0.9,
        )
        result = KnowledgeSearchResult(
            query="测试查询",
            results=[doc],
            total_count=1,
            search_method="hybrid",
        )
        data = result.to_dict()
        assert data["query"] == "测试查询"
        assert data["total_count"] == 1
        assert data["search_method"] == "hybrid"
        assert len(data["results"]) == 1


class TestCitationInfo:
    """CitationInfo 模型测试。"""

    def test_basic_creation(self):
        """测试基本创建。"""
        citation = CitationInfo(
            index=1,
            document_id="doc-1",
            document_title="测试文档",
            excerpt="这是引用内容",
            relevance_score=0.95,
        )
        assert citation.index == 1
        assert citation.document_id == "doc-1"
        assert citation.document_title == "测试文档"
        assert citation.excerpt == "这是引用内容"
        assert citation.relevance_score == 0.95


class TestKnowledgeContext:
    """KnowledgeContext 模型测试。"""

    def test_format_for_prompt(self):
        """测试格式化 Prompt。"""
        doc = KnowledgeDocument(
            id="doc-1",
            title="测试文档",
            content="内容",
            excerpt="这是摘录",
        )
        citation = CitationInfo(
            index=1,
            document_id="doc-1",
            document_title="测试文档",
            excerpt="这是摘录",
            relevance_score=0.95,
        )
        context = KnowledgeContext(
            query="测试查询",
            documents=[doc],
            citations=[citation],
            total_tokens=100,
        )
        prompt = context.format_for_prompt()
        assert "相关背景知识" in prompt
        assert "[1] 测试文档" in prompt
        assert "这是摘录" in prompt


class TestHybridSearchConfig:
    """HybridSearchConfig 模型测试。"""

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
            relevance_threshold=0.7,
            max_tokens=3000,
        )
        assert config.vector_weight == 0.8
        assert config.keyword_weight == 0.2
        assert config.top_k == 10
        assert config.relevance_threshold == 0.7
        assert config.max_tokens == 3000


class TestDomainBoostConfig:
    """DomainBoostConfig 模型测试。"""

    def test_default_values(self):
        """测试默认值。"""
        config = DomainBoostConfig()
        assert config.enabled is True
        assert config.boost_factor == 1.2
        assert config.domains == []

    def test_custom_values(self):
        """测试自定义值。"""
        config = DomainBoostConfig(
            enabled=False,
            boost_factor=1.5,
            domains=["biology", "medicine"],
        )
        assert config.enabled is False
        assert config.boost_factor == 1.5
        assert config.domains == ["biology", "medicine"]
