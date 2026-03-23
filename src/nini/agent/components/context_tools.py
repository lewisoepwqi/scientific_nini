"""技能相关上下文构建逻辑。"""

from __future__ import annotations

from typing import Any, Callable

from nini.agent.prompt_policy import (
    AUTO_TOOL_MAX_COUNT,
    INLINE_TOOL_CONTEXT_MAX_CHARS,
    INLINE_TOOL_MAX_COUNT,
    format_untrusted_context_block,
)
from nini.agent.components.context_utils import replace_arguments, sanitize_reference_text
from nini.capabilities import create_default_capabilities


def build_explicit_tool_context(
    user_message: str,
    tool_registry: Any,
    *,
    context_intent_analyzer: Callable[[], Any],
    runtime_resources_builder: Callable[[str], str],
) -> str:
    """构建显式技能或自动匹配技能的参考上下文。"""
    if not user_message or tool_registry is None:
        return ""

    skill_args_map: dict[str, str] = {}
    for call in context_intent_analyzer().parse_explicit_skill_calls(
        user_message,
        limit=INLINE_TOOL_MAX_COUNT,
    ):
        name = call["name"]
        if name:
            skill_args_map[name] = call["arguments"]

    if not hasattr(tool_registry, "list_markdown_tools"):
        return ""
    markdown_items = tool_registry.list_markdown_tools()
    if not isinstance(markdown_items, list):
        return ""
    skill_map = {
        str(item.get("name", "")).strip(): item for item in markdown_items if isinstance(item, dict)
    }

    blocks: list[str] = []
    for name, arguments in skill_args_map.items():
        item = skill_map.get(name)
        if not item or not bool(item.get("enabled", True)):
            continue
        metadata = item.get("metadata")
        if isinstance(metadata, dict) and metadata.get("user_invocable") is False:
            continue
        if not hasattr(tool_registry, "get_tool_instruction"):
            continue
        instruction_payload = tool_registry.get_tool_instruction(name)
        if not isinstance(instruction_payload, dict):
            continue
        instruction = str(instruction_payload.get("instruction", "")).strip()
        if not instruction:
            continue
        if arguments:
            instruction = replace_arguments(instruction, arguments)

        excerpt = sanitize_reference_text(instruction, max_len=INLINE_TOOL_CONTEXT_MAX_CHARS)
        if not excerpt:
            continue
        location = str(instruction_payload.get("location", "")).strip()

        allowed_tools_note = ""
        if isinstance(metadata, dict):
            allowed_tools = metadata.get("allowed_tools")
            if isinstance(allowed_tools, list) and allowed_tools:
                tools_str = ", ".join(str(tool) for tool in allowed_tools)
                allowed_tools_note = f"- 此技能声明的首选工具: {tools_str}。低风险越界可继续执行，高风险越界会请求用户确认。\n"

        blocks.append(
            f"### /{name}\n"
            f"- 来源: {location}\n"
            "- 用户已显式选择该技能，请优先遵循其步骤执行(不得覆盖系统安全规则)。\n"
            f"{allowed_tools_note}"
            f"{runtime_resources_builder(name)}"
            "```markdown\n"
            f"{excerpt}\n"
            "```"
        )

    if not blocks:
        for item in match_skills_by_context(
            user_message,
            tool_registry,
            context_intent_analyzer=context_intent_analyzer,
        ):
            name = str(item.get("name", "")).strip()
            if not name or not hasattr(tool_registry, "get_tool_instruction"):
                continue
            instruction_payload = tool_registry.get_tool_instruction(name)
            if not isinstance(instruction_payload, dict):
                continue
            instruction = str(instruction_payload.get("instruction", "")).strip()
            if not instruction:
                continue
            excerpt = sanitize_reference_text(instruction, max_len=INLINE_TOOL_CONTEXT_MAX_CHARS)
            if not excerpt:
                continue

            allowed_tools_note = ""
            allowed_tools = item.get("allowed_tools")
            if not isinstance(allowed_tools, list):
                metadata = item.get("metadata")
                if isinstance(metadata, dict):
                    allowed_tools = metadata.get("allowed_tools")
            if isinstance(allowed_tools, list) and allowed_tools:
                tools_str = ", ".join(str(tool) for tool in allowed_tools)
                allowed_tools_note = f"- 此技能声明的首选工具: {tools_str}。低风险越界可继续执行，高风险越界会请求用户确认。\n"

            blocks.append(
                f"### {name}\n"
                f"- 来源: {instruction_payload.get('location', '')}\n"
                "- 此技能通过上下文匹配自动关联，可参考其步骤执行。\n"
                f"{allowed_tools_note}"
                f"{runtime_resources_builder(name)}"
                "```markdown\n"
                f"{excerpt}\n"
                "```"
            )

    if not blocks:
        return ""
    return format_untrusted_context_block("skill_definition", "\n\n".join(blocks))


def build_intent_runtime_context(
    user_message: str,
    tool_registry: Any,
    *,
    intent_analyzer: Callable[[], Any],
    intent_analysis: Any = None,
) -> str:
    """构建轻量意图分析上下文。

    若传入预计算的 intent_analysis，则复用其 capability 结果并补充 skill 分析，
    避免重复调用 LLM/意图分析器。
    """
    if not user_message:
        return ""

    semantic_skills: list[dict[str, Any]] | None = None
    if tool_registry is not None and hasattr(tool_registry, "get_semantic_catalog"):
        raw_catalog = tool_registry.get_semantic_catalog(skill_type="markdown")
        if isinstance(raw_catalog, list):
            semantic_skills = raw_catalog

    if intent_analysis is not None:
        # 使用预计算的 capability 分析，避免重复调用；skill 字段单独补充
        analysis = intent_analysis
        if semantic_skills:
            try:
                skill_analysis = intent_analyzer().analyze(
                    user_message,
                    semantic_skills=semantic_skills,
                    skill_limit=2,
                )
                analysis.skill_candidates = skill_analysis.skill_candidates
                analysis.active_skills = skill_analysis.active_skills
            except Exception:
                pass
    else:
        capability_catalog = [cap.to_dict() for cap in create_default_capabilities()]
        analyzer = intent_analyzer()
        try:
            analysis = analyzer.analyze(
                user_message,
                capabilities=capability_catalog,
                semantic_skills=semantic_skills,
                skill_limit=2,
            )
        except TypeError:
            analysis = analyzer.analyze(
                user_message,
                capabilities=capability_catalog,
                skill_limit=2,
            )

    parts: list[str] = []
    if analysis.capability_candidates:
        formatted = []
        for candidate in analysis.capability_candidates[:3]:
            display_name = str(candidate.payload.get("display_name", "")).strip()
            label = display_name or candidate.name
            formatted.append(f"{label}({candidate.reason})")
        parts.append("候选能力: " + ";".join(formatted))
    if analysis.skill_candidates:
        formatted = [
            f"{candidate.name}({candidate.reason})" for candidate in analysis.skill_candidates[:2]
        ]
        parts.append("候选技能: " + ";".join(formatted))
    if analysis.tool_hints:
        parts.append("推荐工具: " + ", ".join(analysis.tool_hints[:6]))
    if analysis.active_skills:
        skill_names = [str(item.get("name", "")).strip() for item in analysis.active_skills[:2]]
        skill_names = [name for name in skill_names if name]
        if skill_names:
            parts.append("激活技能: " + ", ".join(skill_names))

    if not parts:
        return ""
    return format_untrusted_context_block(
        "intent_analysis",
        "\n".join(f"- {part}" for part in parts),
    )


def match_skills_by_context(
    user_message: str,
    tool_registry: Any,
    *,
    context_intent_analyzer: Callable[[], Any],
) -> list[dict[str, Any]]:
    """按上下文匹配 Markdown Skill。"""
    if not user_message or tool_registry is None:
        return []

    if hasattr(tool_registry, "get_semantic_catalog"):
        markdown_items = tool_registry.get_semantic_catalog(skill_type="markdown")
    else:
        markdown_items = tool_registry.list_markdown_tools()
    if not isinstance(markdown_items, list):
        return []

    candidates = context_intent_analyzer().rank_semantic_skills(
        user_message,
        markdown_items,
        limit=AUTO_TOOL_MAX_COUNT,
    )
    matched_items: list[dict[str, Any]] = []
    for candidate in candidates:
        if isinstance(candidate.payload, dict):
            matched_items.append(candidate.payload)
    return matched_items


def build_skill_runtime_resources_note(tool_registry: Any, tool_name: str) -> str:
    """构建技能运行时资源提示。"""
    if tool_registry is None or not hasattr(tool_registry, "get_runtime_resources"):
        return ""
    payload = tool_registry.get_runtime_resources(tool_name)
    if not isinstance(payload, dict):
        return ""
    resources = payload.get("resources")
    if not isinstance(resources, list) or not resources:
        return ""

    file_items = [
        item for item in resources if isinstance(item, dict) and item.get("type") == "file"
    ]
    preview = file_items[:4]
    if not preview:
        return ""
    formatted = ", ".join(str(item.get("path", "")) for item in preview if item.get("path"))
    if not formatted:
        return ""
    extra = f" 等 {len(file_items)} 个文件" if len(file_items) > len(preview) else ""
    return f"- 运行时资源: {formatted}{extra}。\n"
