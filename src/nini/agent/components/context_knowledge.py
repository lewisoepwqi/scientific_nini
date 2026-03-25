"""知识注入上下文逻辑。"""

from __future__ import annotations

import logging
from typing import Any

from nini.agent.prompt_policy import format_untrusted_context_block
from nini.agent.components.context_utils import sanitize_reference_text
from nini.config import settings
from nini.evidence import normalize_source_record
from nini.memory.research_profile import get_research_profile_manager

logger = logging.getLogger(__name__)


async def inject_knowledge(
    knowledge_loader: Any,
    session: Any,
    last_user_msg: str,
    columns: list[str],
    context_parts: list[str],
    knowledge_max_chars: int | None = None,
) -> dict[str, Any] | None:
    """注入知识上下文，优先使用新检索链路，失败时回退。

    Args:
        knowledge_loader: 知识加载器
        session: 当前会话
        last_user_msg: 最后一条用户消息
        columns: 数据集列名列表
        context_parts: 上下文部分列表（原地追加）
        knowledge_max_chars: 知识注入最大字符数，为 None 时使用全局配置
    """
    effective_max_chars = (
        knowledge_max_chars if knowledge_max_chars is not None else settings.knowledge_max_chars
    )
    retrieval_event: dict[str, Any] | None = None
    use_context_injector = bool(getattr(knowledge_loader, "supports_context_injector", False))

    if not use_context_injector:
        return fallback_knowledge_load(knowledge_loader, last_user_msg, columns, context_parts)

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
                max_len=effective_max_chars,
            )
            context_parts.append(
                format_untrusted_context_block(
                    "knowledge_reference",
                    sanitized_knowledge,
                )
            )
            retrieval_event = {
                "query": last_user_msg,
                "results": [_build_retrieval_result(doc) for doc in knowledge_context.documents],
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
        normalized_hits = [_build_retrieval_result(item) for item in retrieval_hits]
        retrieval_event = {
            "query": last_user_msg,
            "results": normalized_hits,
            "mode": "hybrid" if getattr(knowledge_loader, "vector_available", False) else "keyword",
        }
    return retrieval_event


def _build_retrieval_result(raw: Any) -> dict[str, Any]:
    """构建带最小溯源字段的检索结果。"""
    if hasattr(raw, "model_dump"):
        payload = raw.model_dump(mode="json")
        source_record = normalize_source_record(raw)
    elif isinstance(raw, dict):
        payload = dict(raw)
        source_record = normalize_source_record(payload)
    else:
        payload = {"source": str(raw)}
        source_record = normalize_source_record(payload)
    result = {
        "source": source_record.title,
        "score": payload.get("relevance_score", payload.get("score")),
        "snippet": payload.get("excerpt", payload.get("snippet", "")),
        "source_id": source_record.source_id,
        "source_type": source_record.source_type,
        "acquisition_method": source_record.acquisition_method,
        "accessed_at": (
            source_record.accessed_at.isoformat() if source_record.accessed_at is not None else None
        ),
        "source_time": (
            source_record.source_time.isoformat() if source_record.source_time is not None else None
        ),
        "stable_ref": source_record.stable_ref,
        "document_id": source_record.document_id,
        "resource_id": source_record.resource_id,
        "source_url": source_record.url,
        "claim_id": payload.get("claim_id"),
        "verification_status": payload.get("verification_status", "pending_verification"),
        "reason_summary": payload.get(
            "reason_summary",
            "仅表示已检索来源，尚未完成结论校验。",
        ),
        "conflict_summary": payload.get("conflict_summary"),
    }
    return {key: value for key, value in result.items() if value is not None}
