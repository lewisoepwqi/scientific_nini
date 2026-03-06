"""知识注入上下文逻辑。"""

from __future__ import annotations

import logging
from typing import Any

from nini.agent.prompt_policy import format_untrusted_context_block
from nini.agent.components.context_utils import sanitize_reference_text
from nini.config import settings
from nini.memory.research_profile import get_research_profile_manager

logger = logging.getLogger(__name__)


async def inject_knowledge(
    knowledge_loader: Any,
    session: Any,
    last_user_msg: str,
    columns: list[str],
    context_parts: list[str],
) -> dict[str, Any] | None:
    """注入知识上下文，优先使用新检索链路，失败时回退。"""
    retrieval_event: dict[str, Any] | None = None
    try:
        from nini.knowledge.context_injector import inject_knowledge_to_prompt

        research_profile = None
        try:
            profile_manager = get_research_profile_manager()
            if session.research_profile_id:
                profile = profile_manager.load_sync(session.research_profile_id)
                if profile:
                    research_profile = {
                        "domain": profile.domain,
                        "research_domains": profile.research_domains,
                    }
        except Exception as exc:
            logger.debug("加载研究画像用于知识增强失败: %s", exc)

        profile_domain: str | None = None
        if isinstance(research_profile, dict):
            raw_domain = research_profile.get("domain")
            if isinstance(raw_domain, str) and raw_domain.strip():
                profile_domain = raw_domain.strip()

        _, knowledge_context = await inject_knowledge_to_prompt(
            query=last_user_msg,
            system_prompt="",
            domain=profile_domain,
            research_profile=research_profile,
        )

        if knowledge_context.documents:
            knowledge_text = knowledge_context.format_for_prompt()
            sanitized_knowledge = sanitize_reference_text(
                knowledge_text,
                max_len=settings.knowledge_max_chars,
            )
            context_parts.append(
                format_untrusted_context_block(
                    "knowledge_reference",
                    sanitized_knowledge,
                )
            )
            retrieval_event = {
                "query": last_user_msg,
                "results": [
                    {
                        "source": doc.title,
                        "score": doc.relevance_score,
                        "snippet": doc.excerpt,
                    }
                    for doc in knowledge_context.documents
                ],
                "mode": "hybrid",
            }
        else:
            retrieval_event = fallback_knowledge_load(
                knowledge_loader, last_user_msg, columns, context_parts
            )
    except Exception as exc:
        logger.debug("新知识注入失败，回退到旧检索器: %s", exc, exc_info=True)
        retrieval_event = fallback_knowledge_load(
            knowledge_loader, last_user_msg, columns, context_parts
        )

    return retrieval_event


def fallback_knowledge_load(
    knowledge_loader: Any,
    last_user_msg: str,
    columns: list[str],
    context_parts: list[str],
) -> dict[str, Any] | None:
    """回退到旧的知识加载逻辑。"""
    retrieval_event: dict[str, Any] | None = None

    if hasattr(knowledge_loader, "select_with_hits"):
        knowledge_text, retrieval_hits = knowledge_loader.select_with_hits(
            last_user_msg,
            dataset_columns=columns or None,
            max_entries=settings.knowledge_max_entries,
            max_total_chars=settings.knowledge_max_chars,
        )
    else:
        knowledge_text = knowledge_loader.select(
            last_user_msg,
            dataset_columns=columns or None,
            max_entries=settings.knowledge_max_entries,
            max_total_chars=settings.knowledge_max_chars,
        )
        retrieval_hits = []

    if knowledge_text:
        sanitized_knowledge = sanitize_reference_text(
            knowledge_text,
            max_len=settings.knowledge_max_chars,
        )
        context_parts.append(
            format_untrusted_context_block(
                "knowledge_reference",
                sanitized_knowledge,
            )
        )
    if retrieval_hits:
        retrieval_event = {
            "query": last_user_msg,
            "results": retrieval_hits,
            "mode": "hybrid" if getattr(knowledge_loader, "vector_available", False) else "keyword",
        }
    return retrieval_event
