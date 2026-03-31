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
from nini.agent.components.context_tools import (
    build_explicit_tool_context as build_explicit_tool_context_block,
    build_intent_runtime_context as build_intent_runtime_context_block,
    build_tool_runtime_resources_note,
    match_tools_by_context,
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
from nini.models.risk import ResearchPhase
from nini.tools.detect_phase import detect_phase_from_text
from nini.utils.token_counter import count_messages_tokens

logger = logging.getLogger(__name__)


_PHASE_SKILL_MAP: dict[ResearchPhase, tuple[str, ...]] = {
    ResearchPhase.EXPERIMENT_DESIGN: ("experiment-design-helper",),
    ResearchPhase.LITERATURE_REVIEW: ("literature-review",),
    ResearchPhase.PAPER_WRITING: ("writing-guide",),
}


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
        tool_registry: Any = None,
    ) -> None:
        self._knowledge_loader = knowledge_loader or KnowledgeLoader(settings.knowledge_dir)
        self._tool_registry = tool_registry

    @property
    def inline_tool_max_count(self) -> int:
        """暴露统一的显式技能上限，供兼容调用方复用。"""
        from nini.agent.prompt_policy import INLINE_TOOL_MAX_COUNT

        return INLINE_TOOL_MAX_COUNT

    @property
    def auto_tool_max_count(self) -> int:
        """暴露统一的自动技能匹配上限，供兼容调用方复用。"""
        from nini.agent.prompt_policy import AUTO_TOOL_MAX_COUNT

        return AUTO_TOOL_MAX_COUNT

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

        # 主动记忆推送：识别到 dataset 加载时，注入该 dataset 的历史记忆摘要
        loaded_datasets = getattr(session, "loaded_datasets", {})
        if loaded_datasets:
            first_dataset_name = next(iter(loaded_datasets))
            dataset_memory_context = await _build_dataset_history_memory(first_dataset_name)
            if dataset_memory_context:
                context_parts.append(dataset_memory_context)

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

        phase_runtime_context = self.build_phase_runtime_context(last_user_msg)
        if phase_runtime_context:
            context_parts.append(phase_runtime_context)

        harness_runtime_context = str(getattr(session, "harness_runtime_context", "") or "").strip()
        if harness_runtime_context:
            context_parts.append(
                format_untrusted_context_block("harness_summary", harness_runtime_context)
            )

        explicit_skill_context = self.build_explicit_tool_context(last_user_msg)
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

        # AGENTS.md 已移至 trusted system prompt，不在此注入 untrusted context

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
                # 粗略估算 token 数（按字符数 / 4 近似）
                estimated_tokens = len(long_term_memory_context) // 4
                logger.debug(
                    "长期记忆已注入: session_id=%s estimated_tokens=%d",
                    getattr(session, "id", "unknown"),
                    estimated_tokens,
                )
                context_parts.append(long_term_memory_context)
            else:
                logger.debug(
                    "长期记忆未注入（无相关条目）: session_id=%s",
                    getattr(session, "id", "unknown"),
                )

        research_profile_context = build_research_profile_context(
            session,
            default_profile_id=DEFAULT_RESEARCH_PROFILE_ID,
            get_profile_manager=get_research_profile_manager,
        )
        if research_profile_context:
            context_parts.append(research_profile_context)

        # 注入图表输出格式偏好（指导 LLM 选择 render_engine）
        pref = getattr(session, "chart_output_preference", None)
        if pref:
            pref_label = (
                "交互式（Plotly）" if pref == "interactive" else "静态图片（Matplotlib/PNG）"
            )
            context_parts.append(
                f"[图表输出偏好] 用户当前偏好：{pref_label}。生成图表时 render_engine 应选择对应值，无需再次询问。"
            )
        else:
            context_parts.append(
                "[图表输出偏好] 用户尚未表明偏好。首次生成图表前，必须调用 ask_user_question 询问："
                "是否需要可交互图表（可缩放/悬停）还是静态图片（PNG/SVG，适合发表/报告）。"
            )

        # 注入已完成数据概况提醒（防止压缩后 LLM 重复调用 dataset_catalog(profile)）
        completed_profiles: set[str] = getattr(session, "_completed_dataset_profiles", set())
        if completed_profiles:
            names = "、".join(f"'{n}'" for n in sorted(completed_profiles))
            context_parts.append(
                f"[已完成概况] 数据集 {names} 的概况已成功获取，"
                "禁止重复调用 dataset_catalog(profile)，请直接进行分析或输出结论。"
            )

        # 注入任务进度上下文（防止压缩后 LLM 丢失任务状态）
        if session.task_manager.has_tasks():
            tasks = session.task_manager.tasks
            remaining = session.task_manager.remaining_count()
            task_lines = [f"  - [{t.status}] {t.title}" for t in tasks]
            task_body = f"共 {len(tasks)} 个任务，还剩 {remaining} 个待完成。\n" + "\n".join(
                task_lines
            )
            context_parts.append(format_untrusted_context_block("task_progress", task_body))

        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        if context_parts:
            # 预算控制：按优先级裁剪，Skill 辅助资料不挤占对话历史
            from nini.agent.prompt_policy import trim_runtime_context_by_priority

            context_parts = trim_runtime_context_by_priority(context_parts)
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

    def build_explicit_tool_context(self, user_message: str) -> str:
        """Build context for explicitly selected skills via /skill."""
        return build_explicit_tool_context_block(
            user_message,
            self._tool_registry,
            context_intent_analyzer=_get_context_intent_analyzer,
            runtime_resources_builder=self._build_tool_runtime_resources_note,
        )

    def build_intent_runtime_context(self, user_message: str, intent_analysis: Any = None) -> str:
        """Build lightweight intent analysis context."""
        return build_intent_runtime_context_block(
            user_message,
            self._tool_registry,
            intent_analyzer=_get_intent_analyzer,
            intent_analysis=intent_analysis,
        )

    def build_phase_runtime_context(self, user_message: str) -> str:
        """构建研究阶段导航上下文。"""
        if not user_message:
            return ""

        current_phase, confidence, _matched_keywords = detect_phase_from_text(user_message)

        recommended_capabilities = [
            cap.name
            for cap in create_default_capabilities()
            if cap.phase == current_phase
            or (current_phase == ResearchPhase.DATA_ANALYSIS and cap.phase is None)
        ]
        recommended_skills = self._get_phase_matched_skills(current_phase)

        parts = [
            f"- current_phase: {current_phase.value}",
            f"- phase_confidence: {confidence:.2f}",
        ]
        if recommended_capabilities:
            parts.append("- recommended_capabilities: " + ", ".join(recommended_capabilities))
        if recommended_skills:
            parts.append("- recommended_skills: " + ", ".join(recommended_skills))

        return format_untrusted_context_block("phase_navigation", "\n".join(parts))

    def _match_tools_by_context(self, user_message: str) -> list[dict[str, Any]]:
        """Match Markdown Skills by checking user message against aliases, tags, and name."""
        return match_tools_by_context(
            user_message,
            self._tool_registry,
            context_intent_analyzer=_get_context_intent_analyzer,
        )

    def _build_tool_runtime_resources_note(self, tool_name: str) -> str:
        """Build skill runtime resources note."""
        return build_tool_runtime_resources_note(self._tool_registry, tool_name)

    def _get_phase_matched_skills(self, current_phase: ResearchPhase) -> list[str]:
        """返回与当前阶段匹配的 Markdown Skill 名称。"""
        if self._tool_registry is None or not hasattr(self._tool_registry, "list_markdown_tools"):
            return list(_PHASE_SKILL_MAP.get(current_phase, ()))

        markdown_items = self._tool_registry.list_markdown_tools()
        if not isinstance(markdown_items, list):
            return list(_PHASE_SKILL_MAP.get(current_phase, ()))

        enabled_names = {
            str(item.get("name", "")).strip()
            for item in markdown_items
            if isinstance(item, dict) and bool(item.get("enabled", True))
        }
        return [
            skill_name
            for skill_name in _PHASE_SKILL_MAP.get(current_phase, ())
            if skill_name in enabled_names
        ]

    @classmethod
    def _discover_agents_md(cls) -> str:
        """Discover and read AGENTS.md from project root."""
        if cls._agents_md_scanned:
            return cls._agents_md_cache or ""
        cls._agents_md_scanned = True
        combined = scan_agents_md(max_chars=AGENTS_MD_MAX_CHARS)
        cls._agents_md_cache = combined if combined else None
        return combined


async def _build_dataset_history_memory(dataset_name: str) -> str:
    """主动推送指定 dataset 的历史分析记忆摘要。

    当 ContextBuilder 识别到 dataset 加载时调用，通过 dataset_name 过滤
    LongTermMemoryStore 中的已有 finding/statistic 条目，格式化后注入上下文。
    若无历史记忆或检索失败则静默返回空字符串。
    """
    if not dataset_name or not dataset_name.strip():
        return ""
    try:
        from nini.memory.long_term_memory import (
            format_memories_for_context,
            get_long_term_memory_store,
        )
        from nini.agent.prompt_policy import format_untrusted_context_block

        store = get_long_term_memory_store()
        # 使用 dataset_name 作为查询，并通过 context 感知重排序过滤
        entries = await store.search(
            dataset_name,
            top_k=5,
            min_importance=0.4,
            context={"dataset_name": dataset_name},
        )
        if not entries:
            return ""
        text = format_memories_for_context(entries)
        if not text:
            return ""
        logger.debug(
            "主动记忆推送: dataset=%s injected_count=%d",
            dataset_name,
            len(entries),
        )
        return format_untrusted_context_block(
            "long_term_memory",
            f"[数据集 {dataset_name} 历史分析记忆]\n{text}",
        )
    except Exception:
        logger.debug("主动记忆推送失败，忽略", exc_info=True)
        return ""
