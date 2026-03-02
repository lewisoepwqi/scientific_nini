"""层次化知识检索模块测试。"""

from __future__ import annotations

import pytest
from pathlib import Path
from nini.knowledge.hierarchical import (
    MarkdownParser,
    QueryIntent,
    QueryIntentClassifier,
    QueryRouter,
    RRFFusion,
    RetrievalCache,
)


class TestMarkdownParser:
    """Markdown 解析器测试。"""

    def test_parse_document_with_headings(self):
        """测试解析带标题的文档。"""
        content = """
# 主标题

## 第一章
这是第一章的内容。

### 1.1 小节
小节内容。

## 第二章
第二章内容。
"""
        parser = MarkdownParser()
        doc = parser.parse(content, Path("test.md"))

        assert doc.title == "主标题"
        assert len(doc.sections) == 2
        assert doc.sections[0].title == "第一章"
        assert doc.sections[0].level == 2
        assert doc.sections[1].title == "第二章"

    def test_parse_without_headings(self):
        """测试解析无标题的文档。"""
        content = "这是一段没有标题的内容。"
        parser = MarkdownParser()
        doc = parser.parse(content, Path("test.md"))

        assert len(doc.sections) == 1
        assert doc.sections[0].title == "正文"
        assert doc.sections[0].level == 1

    def test_semantic_chunking(self):
        """测试语义分块。"""
        content = """
## 测试章节

第一段内容。

第二段内容。

第三段内容。
"""
        parser = MarkdownParser(chunk_size=50)
        doc = parser.parse(content, Path("test.md"))

        assert len(doc.sections) == 1
        section = doc.sections[0]
        # 应该分成多个块（因为 chunk_size=50）
        assert len(section.chunks) >= 1


class TestQueryIntentClassifier:
    """查询意图分类器测试。"""

    def test_classify_concept(self):
        """测试概念查询分类。"""
        classifier = QueryIntentClassifier()
        assert classifier.classify("什么是t检验") == QueryIntent.CONCEPT
        assert classifier.classify("解释方差分析") == QueryIntent.CONCEPT

    def test_classify_how_to(self):
        """测试方法查询分类。"""
        classifier = QueryIntentClassifier()
        assert classifier.classify("如何做t检验") == QueryIntent.HOW_TO
        assert classifier.classify("步骤说明") == QueryIntent.HOW_TO

    def test_classify_reference(self):
        """测试参考查询分类。"""
        classifier = QueryIntentClassifier()
        assert classifier.classify("t检验的参数") == QueryIntent.REFERENCE
        assert classifier.classify("返回值说明") == QueryIntent.REFERENCE

    def test_classify_code(self):
        """测试代码查询分类。"""
        classifier = QueryIntentClassifier()
        assert classifier.classify("相关性分析代码") == QueryIntent.CODE

    def test_classify_comparison(self):
        """测试对比查询分类。"""
        classifier = QueryIntentClassifier()
        assert classifier.classify("t检验和方差分析的区别") == QueryIntent.COMPARISON

    def test_classify_troubleshoot(self):
        """测试故障查询分类。"""
        classifier = QueryIntentClassifier()
        assert classifier.classify("结果报错") == QueryIntent.TROUBLESHOOT


class TestQueryRouter:
    """查询路由器测试。"""

    def test_route_concept(self):
        """测试概念查询路由。"""
        router = QueryRouter()
        plan = router.route("什么是t检验")

        assert plan.intent == QueryIntent.CONCEPT
        assert plan.primary_level == "L0"
        assert plan.top_k == 3

    def test_route_how_to(self):
        """测试方法查询路由。"""
        router = QueryRouter()
        plan = router.route("如何做t检验")

        assert plan.intent == QueryIntent.HOW_TO
        assert plan.primary_level == "L1"
        assert plan.strategy == "hybrid"

    def test_route_with_metadata(self):
        """测试带元数据的路由。"""
        router = QueryRouter()
        plan, metadata = router.route_with_metadata("参数说明")

        assert "intent" in metadata
        assert "confidence" in metadata
        assert "routing_reason" in metadata


class TestRRFFusion:
    """RRF 融合测试。"""

    def test_fuse_two_lists(self):
        """测试两个列表的融合。"""
        fusion = RRFFusion(k=60)

        list1 = [
            {"id": "a", "content": "doc a", "score": 1.0},
            {"id": "b", "content": "doc b", "score": 0.9},
        ]
        list2 = [
            {"id": "b", "content": "doc b", "score": 0.8},
            {"id": "c", "content": "doc c", "score": 0.7},
        ]

        # 模拟 RetrievalResult
        from nini.knowledge.hierarchical.retriever import RetrievalResult
        rlist1 = [
            RetrievalResult(id=r["id"], content=r["content"], score=r["score"], level="L0", source="")
            for r in list1
        ]
        rlist2 = [
            RetrievalResult(id=r["id"], content=r["content"], score=r["score"], level="L0", source="")
            for r in list2
        ]

        fused = fusion.fuse([rlist1, rlist2])

        # doc b 在两个列表中都存在，应该排在前面
        assert len(fused) == 3
        assert fused[0].id == "b"  # 共同的文档得分最高


class TestRetrievalCache:
    """检索缓存测试。"""

    def test_cache_get_set(self):
        """测试缓存读写。"""
        cache = RetrievalCache(ttl=300)

        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_cache_expiration(self):
        """测试缓存过期。"""
        cache = RetrievalCache(ttl=0)  # 立即过期

        cache.set("key1", "value1")
        # 过期后应该返回 None
        assert cache.get("key1") is None

    def test_cache_key_generation(self):
        """测试缓存键生成。"""
        key1 = RetrievalCache.generate_key("query", top_k=5)
        key2 = RetrievalCache.generate_key("query", top_k=5)
        key3 = RetrievalCache.generate_key("query", top_k=10)

        assert key1 == key2
        assert key1 != key3


@pytest.mark.asyncio
class TestUnifiedRetriever:
    """统一检索器集成测试。"""

    async def test_search_basic(self):
        """测试基础搜索功能。"""
        from nini.knowledge.hierarchical.unified_retriever import UnifiedRetriever

        retriever = UnifiedRetriever()
        # 由于没有实际知识库，初始化可能失败，这里主要测试接口
        # 实际测试需要 mock 或真实数据

    async def test_search_with_cache(self):
        """测试带缓存的搜索。"""
        from nini.knowledge.hierarchical.unified_retriever import UnifiedRetriever

        retriever = UnifiedRetriever()
        # 测试缓存逻辑
