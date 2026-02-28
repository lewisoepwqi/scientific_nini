"""知识检索模型。

包含知识库搜索、文档管理和引用相关的 Pydantic 模型。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class KnowledgeDocument(BaseModel):
    """知识库文档。"""

    id: str
    title: str
    content: str
    excerpt: str = ""
    relevance_score: float = 0.0
    source_method: Literal["vector", "keyword", "hybrid"] = "vector"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    file_type: str = "txt"
    file_size: int = 0


class KnowledgeSearchResult(BaseModel):
    """知识库搜索结果。"""

    query: str
    results: list[KnowledgeDocument]
    total_count: int = 0
    search_method: Literal["vector", "keyword", "hybrid"] = "hybrid"
    search_time_ms: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "query": self.query,
            "results": [r.model_dump() for r in self.results],
            "total_count": self.total_count,
            "search_method": self.search_method,
            "search_time_ms": self.search_time_ms,
        }


class KnowledgeDocumentMetadata(BaseModel):
    """知识文档元数据（用于列表展示）。"""

    id: str
    title: str
    file_type: str
    file_size: int
    index_status: Literal["indexed", "indexing", "failed", "pending"] = "indexed"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    chunk_count: int = 0


class KnowledgeUploadRequest(BaseModel):
    """知识文档上传请求。"""

    title: Optional[str] = None
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    domain: str = "general"


class KnowledgeUploadResponse(BaseModel):
    """知识文档上传响应。"""

    success: bool
    document_id: Optional[str] = None
    message: str = ""
    index_status: Literal["indexed", "indexing", "failed"] = "indexing"


class CitationInfo(BaseModel):
    """引用信息。"""

    index: int  # 引用编号 [1], [2] 等
    document_id: str
    document_title: str
    excerpt: str
    relevance_score: float
    url: Optional[str] = None


class KnowledgeContext(BaseModel):
    """知识上下文（注入到 Agent prompt 中）。"""

    query: str
    documents: list[KnowledgeDocument]
    citations: list[CitationInfo]
    total_tokens: int = 0

    def format_for_prompt(self) -> str:
        """格式化为 Prompt 文本。"""
        lines = ["相关背景知识："]
        for i, doc in enumerate(self.documents, 1):
            lines.append(f"[{i}] {doc.title}:")
            lines.append(doc.excerpt)
            lines.append("")
        return "\n".join(lines)


class HybridSearchConfig(BaseModel):
    """混合检索配置。"""

    vector_weight: float = 0.7
    keyword_weight: float = 0.3
    top_k: int = 5
    relevance_threshold: float = 0.5
    max_tokens: int = 2000  # 知识上下文的最大 token 数


class DomainBoostConfig(BaseModel):
    """领域增强配置。"""

    enabled: bool = True
    boost_factor: float = 1.2  # 匹配领域的文档得分乘以该因子
    domains: list[str] = Field(default_factory=list)
