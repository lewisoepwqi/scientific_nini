"""记忆与研究画像上下文逻辑。"""

from __future__ import annotations

from typing import Any, Callable

from nini.agent.prompt_policy import format_untrusted_context_block


def build_analysis_memory_context(
    session_id: str,
    *,
    list_memories: Callable[[str], list[Any]],
) -> str:
    """构建分析记忆上下文。"""
    analysis_memories = list_memories(session_id)
    if not analysis_memories:
        return ""

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
    """构建研究画像上下文。"""
    profile_id = (
        str(getattr(session, "research_profile_id", default_profile_id) or "").strip()
        or default_profile_id
    )
    profile_manager = get_profile_manager()
    research_profile = profile_manager.get_or_create_sync(profile_id)
    if hasattr(research_profile, "domain"):
        profile_prompt = profile_manager.get_research_profile_prompt(research_profile).strip()
    else:
        profile_prompt = ""
    if not profile_prompt:
        return ""
    return format_untrusted_context_block("research_profile", profile_prompt)
