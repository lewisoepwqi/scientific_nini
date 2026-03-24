"""领域知识层：根据对话上下文自动注入相关科研分析知识。

支持多种检索模式（通过 settings.knowledge_strategy 配置）：
- bm25: 本地 BM25 检索（默认，零外部依赖）
- keyword: 纯关键词匹配
- vector: 向量语义检索（需安装 llama-index-core）
- hybrid: 向量 + 关键词混合检索
"""

from nini.knowledge.loader import KnowledgeEntry, KnowledgeLoader

# 导出 BM25 检索器（本地优先）
try:
    from nini.knowledge.local_bm25 import LocalBM25Retriever

    _bm25_available = True
except ImportError:
    _bm25_available = False
    LocalBM25Retriever = None  # type: ignore

__all__ = ["KnowledgeEntry", "KnowledgeLoader"]

if _bm25_available:
    __all__.append("LocalBM25Retriever")
