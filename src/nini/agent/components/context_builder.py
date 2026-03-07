"""Context building logic for AgentRunner.

Handles message construction, knowledge injection, and context assembly
for LLM calls.
"""

from __future__ import annotations

import logging
from typing import Any

from nini.agent.components.context_agents_md import scan_agents_md
from nini.agent.components.context_dataset import build_dataset_context
from nini.agent.components.context_knowledge import fallback_knowledge_load, inject_knowledge
from nini.agent.components.context_memory import (
    build_analysis_memory_context,
    build_long_term_memory_context,
    build_research_profile_context,
)
from nini.agent.components.context_skills import (
    build_explicit_skill_context as build_explicit_skill_context_block,
    build_intent_runtime_context as build_intent_runtime_context_block,
    build_skill_runtime_resources_note,
    match_skills_by_context,
)
from nini.agent.components.context_utils import (
    filter_valid_messages,
    get_last_user_message,
    prepare_messages_for_llm,
    replace_arguments,
    sanitize_for_system_context,
    sanitize_reference_text,
)
from nini.agent.prompt_policy import (
    AGENTS_MD_MAX_CHARS,
    PDCA_DETAIL_BLOCK,
    compose_runtime_context_message,
    format_untrusted_context_block,
)
from nini.agent.prompts.scientific import get_system_prompt
from nini.agent.session import Session
from nini.capabilities import create_default_capabilities
from nini.config import settings
from nini.intent import default_intent_analyzer, optimized_intent_analyzer
from nini.knowledge.loader import KnowledgeLoader
from nini.memory.compression import list_session_analysis_memories
from nini.memory.research_profile import (
    DEFAULT_RESEARCH_PROFILE_ID,
    get_research_profile_manager,
)
from nini.utils.token_counter import count_messages_tokens

logger = logging.getLogger(__name__)


def _get_intent_analyzer():
    """获取配置的意图分析器。"""
    strategy = getattr(settings, "intent_strategy", "optimized_rules")
    if strategy == "optimized_rules":
        return optimized_intent_analyzer
    return default_intent_analyzer


def _get_context_intent_analyzer():
    """获取运行时上下文构建所需的兼容分析器。"""
    return default_intent_analyzer


class ContextBuilder:
    """Builds LLM context messages with knowledge injection and sanitization."""

    _agents_md_cache: str | None = None
    _agents_md_scanned: bool = False

    def __init__(
        self,
        knowledge_loader: KnowledgeLoader | None = None,
        skill_registry: Any = None,
    ) -> None:
        self._knowledge_loader = knowledge_loader or KnowledgeLoader(settings.knowledge_dir)
        self._skill_registry = skill_registry

    @property
    def inline_skill_max_count(self) -> int:
        """暴露统一的显式技能上限，供兼容调用方复用。"""
        from nini.agent.prompt_policy import INLINE_SKILL_MAX_COUNT

        return INLINE_SKILL_MAX_COUNT

    @property
    def auto_skill_max_count(self) -> int:
        """暴露统一的自动技能匹配上限，供兼容调用方复用。"""
        from nini.agent.prompt_policy import AUTO_SKILL_MAX_COUNT

        return AUTO_SKILL_MAX_COUNT

    async def build_messages_and_retrieval(
        self,
        session: Session,
        context_ratio: float = 0.0,
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        """Build messages for LLM and return retrieval event data.

        Args:
            session: 当前会话
            context_ratio: 上一轮 context 使用率（0.0 ~ 1.0），用于自适应截断预算
        """
        system_prompt = get_system_prompt()
        context_parts: list[str] = []
        retrieval_event: dict[str, Any] | None = None

        dataset_context, columns = build_dataset_context(session)
        if dataset_context:
            context_parts.append(dataset_context)

        last_user_msg = get_last_user_message(session)

        # --- 单次意图分析，结果用于 RAG/LTM 门控和上下文构建 ---
        _intent_analysis = None
        if last_user_msg:
            try:
                cap_dicts = [cap.to_dict() for cap in create_default_capabilities()]
                _intent_analysis = _get_intent_analyzer().analyze(
                    last_user_msg, capabilities=cap_dicts
                )
            except Exception as exc:
                logger.debug("意图预分析失败，保守兜底（启用 RAG）: %s", exc)

        intent_runtime_context = self.build_intent_runtime_context(
            last_user_msg, intent_analysis=_intent_analysis
        )
        if intent_runtime_context:
            context_parts.append(intent_runtime_context)

        explicit_skill_context = self.build_explicit_skill_context(last_user_msg)
        if explicit_skill_context:
            context_parts.append(explicit_skill_context)

        # 检测分析阶段，用于调整知识注入配额
        from nini.agent.components.analysis_stage_detector import (
            detect_current_stage,
            get_knowledge_max_chars,
        )

        current_stage = detect_current_stage(session)
        effective_knowledge_max_chars = get_knowledge_max_chars(
            settings.knowledge_max_chars, current_stage
        )

        _rag_needed = _intent_analysis.rag_needed if _intent_analysis is not None else True
        if last_user_msg and settings.enable_knowledge and _rag_needed:
            retrieval_event = await self._inject_knowledge(
                session=session,
                last_user_msg=last_user_msg,
                columns=columns,
                context_parts=context_parts,
                knowledge_max_chars=effective_knowledge_max_chars,
            )

        # 按意图类型条件注入 PDCA 详情（仅 DOMAIN_TASK 需要完整指南）
        if _intent_analysis is not None:
            from nini.intent.base import QueryType

            if _intent_analysis.query_type == QueryType.DOMAIN_TASK:
                context_parts.append(
                    format_untrusted_context_block("pdca_detail", PDCA_DETAIL_BLOCK)
                )

        agents_md_content = self._discover_agents_md()
        if agents_md_content:
            sanitized_agents = sanitize_reference_text(
                agents_md_content,
                max_len=AGENTS_MD_MAX_CHARS,
            )
            if sanitized_agents:
                context_parts.append(format_untrusted_context_block("agents_md", sanitized_agents))

        analysis_memory_context = build_analysis_memory_context(
            session.id,
            list_memories=list_session_analysis_memories,
        )
        if analysis_memory_context:
            context_parts.append(analysis_memory_context)

        # 注入跨会话长期记忆（以当前用户消息检索相关历史分析发现）
        _ltm_needed = _intent_analysis.ltm_needed if _intent_analysis is not None else True
        if last_user_msg and _ltm_needed:
            # 构建情境信息用于情境感知重排序
            ltm_context: dict[str, Any] = {}
            loaded_datasets = getattr(session, "loaded_datasets", {})
            if loaded_datasets:
                ltm_context["dataset_name"] = next(iter(loaded_datasets))
            long_term_memory_context = await build_long_term_memory_context(
                last_user_msg,
                context=ltm_context if ltm_context else None,
                top_k=3,
            )
            if long_term_memory_context:
                context_parts.append(long_term_memory_context)

        research_profile_context = build_research_profile_context(
            session,
            default_profile_id=DEFAULT_RESEARCH_PROFILE_ID,
            get_profile_manager=get_research_profile_manager,
        )
        if research_profile_context:
            context_parts.append(research_profile_context)

        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        if context_parts:
            messages.append(
                {
                    "role": "assistant",
                    "content": compose_runtime_context_message(context_parts),
                }
            )

        if getattr(session, "compressed_context", ""):
            messages.append(
                {
                    "role": "assistant",
                    "content": "[以下是之前对话的摘要]\n" + str(session.compressed_context).strip(),
                }
            )

        valid_messages = filter_valid_messages(session.messages)
        prepared_messages = prepare_messages_for_llm(valid_messages, context_ratio=context_ratio)

        if settings.auto_compress_enabled and prepared_messages:
            threshold = settings.auto_compress_threshold_tokens
            current_tokens = count_messages_tokens(messages + prepared_messages)
            if current_tokens > threshold:
                from nini.agent.components.context_compressor import sliding_window_trim

                prepared_messages = sliding_window_trim(
                    prepared_messages,
                    threshold,
                    base_tokens=count_messages_tokens(messages),
                )

        messages.extend(prepared_messages)
        return messages, retrieval_event

    async def _inject_knowledge(
        self,
        session: Session,
        last_user_msg: str,
        columns: list[str],
        context_parts: list[str],
        knowledge_max_chars: int | None = None,
    ) -> dict[str, Any] | None:
        """注入知识上下文。"""
        return await inject_knowledge(
            self._knowledge_loader,
            session,
            last_user_msg,
            columns,
            context_parts,
            knowledge_max_chars=knowledge_max_chars,
        )

    def _fallback_knowledge_load(
        self,
        last_user_msg: str,
        columns: list[str],
        context_parts: list[str],
    ) -> dict[str, Any] | None:
        """回退到旧知识检索逻辑。"""
        return fallback_knowledge_load(
            self._knowledge_loader, last_user_msg, columns, context_parts
        )

    def build_explicit_skill_context(self, user_message: str) -> str:
        """Build context for explicitly selected skills via /skill."""
        return build_explicit_skill_context_block(
            user_message,
            self._skill_registry,
            context_intent_analyzer=_get_context_intent_analyzer,
            runtime_resources_builder=self._build_skill_runtime_resources_note,
        )

    def build_intent_runtime_context(self, user_message: str, intent_analysis: Any = None) -> str:
        """Build lightweight intent analysis context."""
        return build_intent_runtime_context_block(
            user_message,
            self._skill_registry,
            intent_analyzer=_get_intent_analyzer,
            intent_analysis=intent_analysis,
        )

    def _match_skills_by_context(self, user_message: str) -> list[dict[str, Any]]:
        """Match Markdown Skills by checking user message against aliases, tags, and name."""
        return match_skills_by_context(
            user_message,
            self._skill_registry,
            context_intent_analyzer=_get_context_intent_analyzer,
        )

    def _build_skill_runtime_resources_note(self, skill_name: str) -> str:
        """Build skill runtime resources note."""
        return build_skill_runtime_resources_note(self._skill_registry, skill_name)

    @classmethod
    def _discover_agents_md(cls) -> str:
        """Discover and read AGENTS.md from project root."""
        if cls._agents_md_scanned:
            return cls._agents_md_cache or ""
        cls._agents_md_scanned = True
        combined = scan_agents_md(max_chars=AGENTS_MD_MAX_CHARS)
        cls._agents_md_cache = combined if combined else None
        return combined
