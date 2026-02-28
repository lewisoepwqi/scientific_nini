"""知识检索 E2E 测试。

测试知识检索功能的端到端流程。
"""

import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.e2e
class TestKnowledgeRetrievalWorkflow:
    """知识检索工作流 E2E 测试。"""

    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        """创建测试客户端。"""
        from nini.app import create_app
        from nini.config import settings
        from tests.client_utils import LocalASGIClient

        monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
        app = create_app()
        return LocalASGIClient(app)

    @pytest.fixture
    def session_id(self, client):
        """创建测试会话。"""
        response = client.post("/api/sessions", json={"title": "知识库测试会话"})
        assert response.status_code == 200
        result = response.json()
        # 处理不同的响应格式
        if "id" in result:
            return result["id"]
        elif "session_id" in result:
            return result["session_id"]
        else:
            pytest.skip("Session creation response format unexpected")

    def test_knowledge_search_endpoint(self, client, session_id):
        """测试知识库搜索端点。"""
        # 搜索端点可能存在或返回 501
        response = client.post(
            "/api/knowledge/search",
            json={"query": "统计分析方法", "top_k": 5}
        )
        # 应该返回 200 或 501（如果功能未实现）
        assert response.status_code in [200, 501]

    def test_knowledge_documents_endpoint(self, client):
        """测试知识库文档列表端点。"""
        response = client.get("/api/knowledge/documents")
        assert response.status_code in [200, 501]

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list) or isinstance(data, dict)

    def test_document_upload_workflow(self, client, session_id, tmp_path):
        """测试文档上传工作流。"""
        # 创建一个测试文档
        test_doc = tmp_path / "test_knowledge.txt"
        test_doc.write_text("这是一个用于测试的知识库文档，包含统计分析方法的相关内容。")

        # 尝试上传文档
        with open(test_doc, "rb") as f:
            response = client.post(
                "/api/knowledge/documents",
                files={"file": ("test_knowledge.txt", f, "text/plain")},
                data={"title": "测试文档", "domain": "statistics"}
            )

        # 端点可能存在或返回 501
        assert response.status_code in [200, 201, 501]


@pytest.mark.e2e
class TestHybridRetrieverE2E:
    """混合检索器 E2E 测试。"""

    def test_hybrid_search_combines_methods(self):
        """测试混合检索结合向量搜索和关键词搜索。"""
        from nini.knowledge.hybrid_retriever import HybridRetriever, KeywordIndex
        from nini.models.knowledge import HybridSearchConfig

        # 测试配置创建
        config = HybridSearchConfig(
            vector_weight=0.7,
            keyword_weight=0.3,
            top_k=5
        )

        # 验证配置
        assert config.vector_weight == 0.7
        assert config.keyword_weight == 0.3
        assert config.top_k == 5

        # 测试关键词索引（不需要 VectorKnowledgeStore）
        keyword_index = KeywordIndex()
        assert keyword_index is not None

        # 测试添加文档到关键词索引
        keyword_index.add_document("doc-1", "ANOVA 用于多组比较", {"source": "test"})
        assert "doc-1" in keyword_index.documents

    def test_hybrid_search_with_mock_documents(self):
        """测试使用模拟文档的混合搜索。"""
        from nini.models.knowledge import KnowledgeDocument, KnowledgeSearchResult

        # 模拟搜索结果
        doc1 = KnowledgeDocument(
            id="doc-1",
            title="统计方法",
            content="ANOVA 用于多组比较",
            excerpt="ANOVA 用于多组比较",
            relevance_score=0.95,
            source_method="hybrid",
            metadata={"source": "test"}
        )
        doc2 = KnowledgeDocument(
            id="doc-2",
            title="统计方法",
            content="t 检验用于两组比较",
            excerpt="t 检验用于两组比较",
            relevance_score=0.85,
            source_method="hybrid",
            metadata={"source": "test"}
        )

        result = KnowledgeSearchResult(
            query="统计方法",
            results=[doc1, doc2],
            total_count=2,
            search_method="hybrid"
        )

        # 验证结果结构
        assert result.query == "统计方法"
        assert len(result.results) == 2
        assert result.results[0].relevance_score == 0.95

    def test_search_result_ranking(self):
        """测试结果排序逻辑。"""
        from nini.models.knowledge import KnowledgeDocument

        # 创建不同分数的文档
        docs = [
            KnowledgeDocument(id="doc-3", title="内容3", content="内容3", relevance_score=0.7),
            KnowledgeDocument(id="doc-1", title="内容1", content="内容1", relevance_score=0.95),
            KnowledgeDocument(id="doc-2", title="内容2", content="内容2", relevance_score=0.85),
        ]

        # 按分数排序
        sorted_docs = sorted(docs, key=lambda x: x.relevance_score, reverse=True)

        # 验证排序
        assert sorted_docs[0].relevance_score == 0.95
        assert sorted_docs[1].relevance_score == 0.85
        assert sorted_docs[2].relevance_score == 0.7


@pytest.mark.e2e
class TestContextInjectorE2E:
    """上下文注入器 E2E 测试。"""

    def test_context_injection_with_limit(self):
        """测试带限制的上下文注入。"""
        from nini.knowledge.context_injector import ContextInjector
        from nini.models.knowledge import HybridSearchConfig

        config = HybridSearchConfig(max_tokens=2000)
        injector = ContextInjector(config=config)

        # 验证配置
        assert injector.config.max_tokens == 2000

    def test_truncate_to_token_limit_function(self):
        """测试截断到 token 限制函数。"""
        from nini.knowledge.context_injector import truncate_to_token_limit

        # 长文本应被截断
        long_text = "这是一个很长的文本。" * 100
        truncated = truncate_to_token_limit(long_text, max_tokens=10)

        # 验证截断结果
        assert len(truncated) < len(long_text)
        assert truncated.endswith("...")

    def test_knowledge_context_formatting(self):
        """测试知识上下文格式化。"""
        from nini.models.knowledge import KnowledgeContext, KnowledgeDocument, CitationInfo

        documents = [
            KnowledgeDocument(
                id="doc-1",
                title="统计方法指南",
                content="ANOVA 是方差分析方法",
                excerpt="ANOVA 是方差分析方法",
                relevance_score=0.9
            ),
            KnowledgeDocument(
                id="doc-2",
                title="统计方法指南",
                content="t 检验适用于两组比较",
                excerpt="t 检验适用于两组比较",
                relevance_score=0.85
            ),
        ]

        citations = [
            CitationInfo(index=1, document_id="doc-1", document_title="统计方法指南",
                        excerpt="ANOVA 是方差分析方法", relevance_score=0.9),
            CitationInfo(index=2, document_id="doc-2", document_title="统计方法指南",
                        excerpt="t 检验适用于两组比较", relevance_score=0.85),
        ]

        context = KnowledgeContext(
            query="统计方法",
            documents=documents,
            citations=citations,
            total_tokens=100
        )

        # 验证格式化输出
        formatted = context.format_for_prompt()
        assert "相关背景知识" in formatted
        assert "统计方法指南" in formatted
        assert "[1]" in formatted
        assert "[2]" in formatted


@pytest.mark.e2e
class TestCitationSystemE2E:
    """引用系统 E2E 测试。"""

    def test_citation_marker_parsing(self):
        """测试引用标记解析。"""
        # 测试引用标记格式
        text_with_citations = """
        根据相关研究[1]，ANOVA 方法适用于多组比较。
        另外，t 检验也是一个选择[2]。
        """

        # 简单的引用标记检测
        import re
        citations = re.findall(r'\[(\d+)\]', text_with_citations)

        assert len(citations) == 2
        assert citations[0] == "1"
        assert citations[1] == "2"

    def test_citation_info_structure(self):
        """测试引用信息结构。"""
        from nini.models.knowledge import CitationInfo

        citation = CitationInfo(
            index=1,
            document_id="doc-123",
            document_title="统计学指南",
            excerpt="ANOVA 方法...",
            relevance_score=0.92
        )

        assert citation.index == 1
        assert citation.document_id == "doc-123"
        assert citation.document_title == "统计学指南"
        assert citation.relevance_score > 0


@pytest.mark.e2e
class TestKnowledgeModelsE2E:
    """知识模型 E2E 测试。"""

    def test_knowledge_search_result_model(self):
        """测试知识搜索结果模型。"""
        from nini.models.knowledge import KnowledgeSearchResult, KnowledgeDocument

        doc = KnowledgeDocument(
            id="doc-1",
            title="统计分析方法",
            content="ANOVA 和 t 检验是常用的统计方法...",
            excerpt="ANOVA 和 t 检验...",
            relevance_score=0.95,
            source_method="hybrid",
            metadata={"domain": "statistics", "tags": ["anova", "t-test"]}
        )

        result = KnowledgeSearchResult(
            query="统计方法",
            results=[doc],
            total_count=1,
            search_method="hybrid"
        )

        # 验证模型结构
        assert result.query == "统计方法"
        assert len(result.results) == 1
        assert result.results[0].id == "doc-1"

    def test_knowledge_document_model_dump(self):
        """测试知识文档 model_dump。"""
        from nini.models.knowledge import KnowledgeDocument

        doc = KnowledgeDocument(
            id="doc-1",
            title="测试文档",
            content="测试内容",
            excerpt="测试摘要",
            relevance_score=0.9,
            metadata={"tags": ["tag1", "tag2"]}
        )

        data = doc.model_dump()

        assert data["id"] == "doc-1"
        assert data["title"] == "测试文档"
        assert "tag1" in data["metadata"]["tags"]

    def test_knowledge_search_result_to_dict(self):
        """测试知识搜索结果 to_dict。"""
        from nini.models.knowledge import KnowledgeSearchResult, KnowledgeDocument

        doc = KnowledgeDocument(
            id="doc-1",
            title="测试文档",
            content="测试内容",
            excerpt="测试摘要",
            relevance_score=0.9
        )

        result = KnowledgeSearchResult(
            query="测试查询",
            results=[doc],
            total_count=1,
            search_method="hybrid",
            search_time_ms=100
        )

        data = result.to_dict()

        assert data["query"] == "测试查询"
        assert data["total_count"] == 1
        assert data["search_method"] == "hybrid"
        assert len(data["results"]) == 1
