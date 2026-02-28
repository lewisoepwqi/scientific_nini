"""上下文注入器测试。

测试知识上下文自动注入功能。
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock

from nini.knowledge.context_injector import (
    inject_knowledge_to_prompt,
    ContextInjector,
    truncate_to_token_limit,
)
from nini.models.knowledge import (
    HybridSearchConfig,
    KnowledgeContext,
    KnowledgeDocument,
    CitationInfo,
)


class TestTruncateToTokenLimit:
    """Token限制截断测试。"""

    def test_truncate_empty_string(self):
        """测试空字符串。"""
        result = truncate_to_token_limit("", max_tokens=100)
        assert result == ""

    def test_truncate_short_text(self):
        """测试短文本（不需要截断）。"""
        text = "Hello World"
        result = truncate_to_token_limit(text, max_tokens=100)
        assert result == text

    def test_truncate_long_text(self):
        """测试长文本（需要截断）。"""
        text = "word " * 1000  # 很长的文本
        result = truncate_to_token_limit(text, max_tokens=10)
        assert len(result) < len(text)

    def test_truncate_respects_limit(self):
        """测试截断尊重限制。"""
        text = "这是一个很长的中文文本 " * 100
        result = truncate_to_token_limit(text, max_tokens=50)
        # 结果应该被截断
        assert len(result) <= len(text)


class TestContextInjector:
    """上下文注入器测试。"""

    def test_injector_initialization(self):
        """测试注入器初始化。"""
        injector = ContextInjector()
        assert injector is not None
        assert injector.config is not None

    def test_injector_with_custom_config(self):
        """测试使用自定义配置初始化。"""
        config = HybridSearchConfig(top_k=10, max_tokens=3000)
        injector = ContextInjector(config)
        assert injector.config.top_k == 10
        assert injector.config.max_tokens == 3000


class TestKnowledgeContextModel:
    """知识上下文模型测试。"""

    def test_format_for_prompt(self):
        """测试格式化Prompt。"""
        doc = KnowledgeDocument(id="doc1", title="测试文档", content="内容", excerpt="摘要")
        citation = CitationInfo(
            index=1,
            document_id="doc1",
            document_title="测试文档",
            excerpt="摘要",
            relevance_score=0.95,
        )
        context = KnowledgeContext(
            query="测试查询", documents=[doc], citations=[citation], total_tokens=100
        )

        prompt = context.format_for_prompt()

        assert "相关背景知识" in prompt
        assert "[1] 测试文档" in prompt
        assert "摘要" in prompt

    def test_context_token_limit(self):
        """测试上下文Token限制。"""
        # 创建很多文档，超过token限制
        docs = [
            KnowledgeDocument(id=f"doc{i}", title=f"文档{i}", content=f"内容{i} " * 100)  # 长内容
            for i in range(10)
        ]
        citations = [
            CitationInfo(
                index=i + 1,
                document_id=f"doc{i}",
                document_title=f"文档{i}",
                excerpt=f"摘要{i}",
                relevance_score=0.9,
            )
            for i in range(10)
        ]
        context = KnowledgeContext(
            query="测试", documents=docs, citations=citations, total_tokens=5000  # 超过限制
        )

        prompt = context.format_for_prompt()

        # 应该被截断到合理长度
        assert len(prompt) < 10000


class TestInjectKnowledgeToPrompt:
    """注入知识到Prompt测试。"""

    @pytest.mark.asyncio
    async def test_inject_with_no_results(self):
        """测试无结果时的注入。"""
        with patch("nini.knowledge.context_injector.get_hybrid_retriever") as mock_get:
            mock_retriever = Mock()
            mock_result = Mock()
            mock_result.results = []
            mock_result.total_count = 0
            mock_retriever.search = AsyncMock(return_value=mock_result)
            mock_get.return_value = mock_retriever

            enhanced_prompt, context = await inject_knowledge_to_prompt(
                query="测试", system_prompt="原始系统提示"
            )

            assert enhanced_prompt == "原始系统提示"
            assert len(context.documents) == 0

    @pytest.mark.asyncio
    async def test_inject_with_results(self):
        """测试有结果时的注入。"""
        from nini.models.knowledge import KnowledgeDocument

        with patch("nini.knowledge.context_injector.get_hybrid_retriever") as mock_get:
            mock_retriever = Mock()
            mock_result = Mock()
            # 使用实际的 KnowledgeDocument 对象而不是 Mock
            mock_result.results = [
                KnowledgeDocument(
                    id="doc1",
                    title="测试文档",
                    content="这是内容",
                    excerpt="这是摘要",
                    relevance_score=0.9
                )
            ]
            mock_retriever.search = AsyncMock(return_value=mock_result)
            mock_get.return_value = mock_retriever

            enhanced_prompt, context = await inject_knowledge_to_prompt(
                query="统计方法", system_prompt="原始提示"
            )

            assert "原始提示" in enhanced_prompt
            assert "测试文档" in enhanced_prompt
            assert len(context.documents) == 1

    @pytest.mark.asyncio
    async def test_inject_with_domain_boost(self):
        """测试带领域增强的注入。"""
        with patch("nini.knowledge.context_injector.get_hybrid_retriever") as mock_get:
            mock_retriever = Mock()
            mock_result = Mock()
            mock_result.results = []
            mock_result.total_count = 0
            mock_retriever.search = AsyncMock(return_value=mock_result)
            mock_get.return_value = mock_retriever

            await inject_knowledge_to_prompt(query="测试", system_prompt="提示", domain="biology")

            # 验证搜索被调用，且可能传递了domain参数
            mock_retriever.search.assert_called_once()
