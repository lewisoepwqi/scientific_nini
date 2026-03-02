"""层次化知识检索模块。

基于 PageIndex 思想的三级索引架构（文档/章节/段落），
支持查询意图路由、多路召回和重排序。
"""

from nini.knowledge.hierarchical.parser import MarkdownParser
from nini.knowledge.hierarchical.index import (
    ChunkNode,
    DocumentNode,
    HierarchicalIndex,
    SectionNode,
)
from nini.knowledge.hierarchical.router import QueryIntent, QueryIntentClassifier, QueryRouter
from nini.knowledge.hierarchical.retriever import ContextAssembler, RRFFusion
from nini.knowledge.hierarchical.reranker import CrossEncoderReranker, RankedResult
from nini.knowledge.hierarchical.cache import RetrievalCache
from nini.knowledge.hierarchical.unified_retriever import UnifiedRetriever, UnifiedRetrievalResult
from nini.knowledge.hierarchical.adapter import (
    HierarchicalKnowledgeAdapter,
    create_knowledge_adapter,
)

__all__ = [
    # Parser
    "MarkdownParser",
    # Index
    "HierarchicalIndex",
    "DocumentNode",
    "SectionNode",
    "ChunkNode",
    # Router
    "QueryIntent",
    "QueryIntentClassifier",
    "QueryRouter",
    # Retriever
    "RRFFusion",
    "ContextAssembler",
    # Reranker
    "CrossEncoderReranker",
    "RankedResult",
    # Cache
    "RetrievalCache",
    # Unified
    "UnifiedRetriever",
    "UnifiedRetrievalResult",
    # Adapter
    "HierarchicalKnowledgeAdapter",
    "create_knowledge_adapter",
]
