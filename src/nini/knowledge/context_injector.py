"""知识上下文注入器。

自动将知识库检索结果注入到 Agent 的上下文中。
"""

from __future__ import annotations

import logging
from typing import Any

from nini.knowledge.hybrid_retriever import get_hybrid_retriever
from nini.models.knowledge import (
    CitationInfo,
    DomainBoostConfig,
    HybridSearchConfig,
    KnowledgeContext,
    KnowledgeDocument,
)
from nini.utils.token_counter import count_tokens

logger = logging.getLogger(__name__)

# 提示词模板
KNOWLEDGE_PROMPT_TEMPLATE = """相关背景知识：
{context}

请基于以上背景知识回答用户问题。如果使用到某条知识，请在相关语句后添加引用标记（如 [1], [2]）。
"""


def truncate_to_token_limit(text: str, max_tokens: int) -> str:
    """将文本截断到指定 token 数以内。

    Args:
        text: 原始文本
        max_tokens: 最大 token 数

    Returns:
        截断后的文本
    """
    tokens = count_tokens(text)
    if tokens <= max_tokens:
        return text

    # 简单截断：按比例减少字符数
    ratio = max_tokens / tokens
    target_chars = int(len(text) * ratio * 0.9)  # 留一些余量
    return text[:target_chars] + "..."


class ContextInjector:
    """知识上下文注入器。"""

    def __init__(self, config: HybridSearchConfig | None = None):
        """初始化注入器。

        Args:
            config: 检索配置
        """
        self.config = config or HybridSearchConfig()

    async def inject_knowledge(
        self,
        query: str,
        system_prompt: str,
        domain: str | None = None,
        research_profile: dict[str, Any] | None = None,
    ) -> tuple[str, KnowledgeContext]:
        """将知识注入到系统提示词中。

        Args:
            query: 用户查询
            system_prompt: 原始系统提示词
            domain: 领域偏好
            research_profile: 研究画像

        Returns:
            (增强后的系统提示词, 知识上下文)
        """
        try:
            # 获取混合检索器
            retriever = await get_hybrid_retriever()

            # 执行检索
            search_result = await retriever.search(
                query,
                top_k=self.config.top_k,
                domain=domain,
            )

            if not search_result.results:
                # 没有检索结果，返回原始提示词
                return system_prompt, KnowledgeContext(
                    query=query,
                    documents=[],
                    citations=[],
                    total_tokens=0,
                )

            # 应用领域增强
            documents = self._apply_domain_boost(
                search_result.results,
                domain,
                research_profile,
            )

            # 构建引用信息
            citations = []
            for i, doc in enumerate(documents, 1):
                citations.append(
                    CitationInfo(
                        index=i,
                        document_id=doc.id,
                        document_title=doc.title,
                        excerpt=doc.excerpt,
                        relevance_score=doc.relevance_score,
                    )
                )

            # 构建知识上下文
            context_parts = []
            for i, doc in enumerate(documents, 1):
                excerpt = truncate_to_token_limit(
                    doc.excerpt,
                    self.config.max_tokens // len(documents),
                )
                context_parts.append(f"[{i}] {doc.title}:\n{excerpt}")

            knowledge_context_str = "\n\n".join(context_parts)

            # 计算总 token 数
            total_tokens = count_tokens(knowledge_context_str)

            # 如果超过限制，进一步截断
            kept_docs = len(documents)
            if total_tokens > self.config.max_tokens:
                # 只保留最重要的文档
                while total_tokens > self.config.max_tokens and kept_docs > 1:
                    kept_docs -= 1
                    context_parts = []
                    for i, doc in enumerate(documents[:kept_docs], 1):
                        excerpt = truncate_to_token_limit(
                            doc.excerpt,
                            self.config.max_tokens // kept_docs,
                        )
                        context_parts.append(f"[{i}] {doc.title}:\n{excerpt}")
                    knowledge_context_str = "\n\n".join(context_parts)
                    total_tokens = count_tokens(knowledge_context_str)

            # 构建增强后的系统提示词
            enhanced_prompt = f"""{system_prompt}

相关背景知识：
{knowledge_context_str}

请基于以上背景知识回答用户问题。如果使用到某条知识，请在相关语句后添加引用标记（如 [1], [2]）。
"""

            knowledge_context = KnowledgeContext(
                query=query,
                documents=documents[:kept_docs],
                citations=citations[:kept_docs],
                total_tokens=total_tokens,
            )

            return enhanced_prompt, knowledge_context

        except Exception as e:
            logger.warning(f"知识注入失败: {e}")
            # 返回原始提示词
            return system_prompt, KnowledgeContext(
                query=query,
                documents=[],
                citations=[],
                total_tokens=0,
            )

    def _apply_domain_boost(
        self,
        documents: list[KnowledgeDocument],
        domain: str | None,
        research_profile: dict[str, Any] | None,
    ) -> list[KnowledgeDocument]:
        """应用领域增强。

        Args:
            documents: 文档列表
            domain: 当前领域
            research_profile: 研究画像

        Returns:
            增强后的文档列表（已排序）
        """
        if not domain and not research_profile:
            return documents

        # 获取用户偏好的领域列表
        preferred_domains: list[str] = []
        if research_profile:
            preferred_domains = research_profile.get("research_domains", [])
            if research_profile.get("domain"):
                preferred_domains.insert(0, research_profile["domain"])

        if domain:
            preferred_domains.insert(0, domain)

        if not preferred_domains:
            return documents

        # 对匹配领域的文档进行加分
        boosted_docs = []
        for doc in documents:
            score = doc.relevance_score
            doc_domain = doc.metadata.get("domain", "")
            doc_tags = doc.metadata.get("tags", [])

            # 检查是否匹配偏好领域
            for pref_domain in preferred_domains:
                if pref_domain and (
                    pref_domain.lower() in doc_domain.lower()
                    or any(pref_domain.lower() in tag.lower() for tag in doc_tags)
                ):
                    score *= 1.2  # 提升 20%
                    break

            boosted_docs.append((doc, score))

        # 重新排序
        boosted_docs.sort(key=lambda x: x[1], reverse=True)

        # 更新分数并返回
        result = []
        for doc, score in boosted_docs:
            doc.relevance_score = score
            result.append(doc)

        return result


# 全局注入器实例
_context_injector: ContextInjector | None = None


async def get_context_injector() -> ContextInjector:
    """获取全局上下文注入器实例。"""
    global _context_injector
    if _context_injector is None:
        _context_injector = ContextInjector()
    return _context_injector


async def inject_knowledge_to_prompt(
    query: str,
    system_prompt: str,
    domain: str | None = None,
    research_profile: dict[str, Any] | None = None,
) -> tuple[str, KnowledgeContext]:
    """便捷函数：注入知识到提示词。

    Args:
        query: 用户查询
        system_prompt: 原始系统提示词
        domain: 领域偏好
        research_profile: 研究画像

    Returns:
        (增强后的系统提示词, 知识上下文)
    """
    injector = await get_context_injector()
    return await injector.inject_knowledge(
        query,
        system_prompt,
        domain,
        research_profile,
    )
