"""领域知识层：根据对话上下文自动注入相关科研分析知识。

支持两种检索模式：
- 关键词匹配（默认，零依赖）
- 向量+关键词混合检索（需安装 llama-index-core）
"""

from nini.knowledge.loader import KnowledgeEntry, KnowledgeLoader

__all__ = ["KnowledgeEntry", "KnowledgeLoader"]
