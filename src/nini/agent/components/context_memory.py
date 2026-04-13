"""记忆与研究画像上下文逻辑。"""

from __future__ import annotations

import logging
from typing import Any, Callable

from nini.agent.prompt_policy import format_untrusted_context_block

logger = logging.getLogger(__name__)


async def build_long_term_memory_context(
    query: str,
    *,
    context: dict[str, Any] | None = None,
    top_k: int = 3,
) -> str:
    """检索并构建跨会话长期记忆上下文。

    以当前用户消息为查询，从 LongTermMemoryStore 检索相关历史分析发现，
    格式化后以不可信标签包裹注入运行时上下文。

    Args:
        query: 用于检索的查询文本（通常为当前用户消息）
        context: 情境信息，支持 dataset_name/analysis_type 用于情境感知重排序
        top_k: 最多返回条数

    Returns:
        格式化的长期记忆上下文字符串，无可用记忆时返回空字符串
    """
    if not query or not query.strip():
        return ""

    # MemoryManager 优先路径（SQLite FTS5）；失败或未初始化时降级
    try:
        from nini.memory.manager import build_memory_context_block, get_memory_manager

        mm = get_memory_manager()
        if mm is not None:
            raw = await mm.prefetch_all(query)
            if raw:
                return build_memory_context_block(raw)
    except Exception:
        logger.debug("MemoryManager.prefetch_all 失败，降级到旧路径", exc_info=True)

    return ""


def build_analysis_memory_context(
    session_id: str,
    *,
    list_memories: Callable[[str], list[Any]],
) -> str:
    """构建分析记忆上下文。

    当记忆条目较少时（总计 ≤ 8 条），注入完整详情；
    超出阈值时切换为摘要模式，引导 LLM 主动调用 analysis_memory 工具检索。
    """
    analysis_memories = list_memories(session_id)
    if not analysis_memories:
        return ""

    # 统计总条目数以决定注入模式
    total_entries = sum(len(m.statistics) + len(m.findings) for m in analysis_memories)

    if total_entries > 8:
        # 摘要模式：仅注入数据集名和条目数，引导 LLM 按需检索
        summary_lines = [
            "分析记忆摘要（条目较多，可调用 analysis_memory(operation='find') 检索具体数值）："
        ]
        for memory in analysis_memories:
            summary_lines.append(
                f"- {memory.dataset_name}: {len(memory.findings)} 项发现，"
                f"{len(memory.statistics)} 项统计结果，{len(memory.decisions)} 项决策"
            )
        return format_untrusted_context_block("analysis_memory", "\n".join(summary_lines))

    # 完整模式：注入所有记忆详情
    mem_parts: list[str] = []
    for memory in analysis_memories:
        prompt = memory.get_context_prompt()
        if prompt:
            mem_parts.append(f"### 数据集: {memory.dataset_name}\n{prompt}")
    if not mem_parts:
        return ""

    return format_untrusted_context_block("analysis_memory", "\n\n".join(mem_parts))


def build_research_profile_context(
    session: Any,
    *,
    default_profile_id: str,
    get_profile_manager: Callable[[], Any],
) -> str:
    """构建研究画像上下文。

    优先从 Markdown 叙述层（{profile_id}_profile.md）读取注入文本，
    兼具 AUTO（结构化摘要）、AGENT（分析习惯）、USER（备注）三段内容，
    信息密度高于原有的 get_research_profile_prompt() 生成方式。
    MD 文件不存在时自动回退到 JSON 生成方式，保证向后兼容。
    """
    profile_id = (
        str(getattr(session, "research_profile_id", default_profile_id) or "").strip()
        or default_profile_id
    )

    # 优先读取 Markdown 叙述层
    try:
        from nini.memory.profile_narrative import get_profile_narrative_manager

        narrative_text = get_profile_narrative_manager().get_narrative_for_context(profile_id)
        if narrative_text.strip():
            return format_untrusted_context_block("research_profile", narrative_text)
    except Exception:
        logger.warning("读取画像叙述层失败，回退到 JSON 生成方式", exc_info=True)

    # 回退：从 JSON 字段实时生成文本
    profile_manager = get_profile_manager()
    research_profile = profile_manager.get_or_create_sync(profile_id)
    if hasattr(research_profile, "domain"):
        profile_prompt = profile_manager.get_research_profile_prompt(research_profile).strip()
    else:
        profile_prompt = ""
    if not profile_prompt:
        return ""
    return format_untrusted_context_block("research_profile", profile_prompt)
