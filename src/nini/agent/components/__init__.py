"""AgentRunner components for Nini 2.0.

This package contains modular components extracted from the monolithic runner.py
to improve maintainability and testability.
"""

from nini.agent.components.context_builder import (
    ContextBuilder,
    filter_valid_messages,
    get_last_user_message,
    prepare_messages_for_llm,
    replace_arguments,
    sanitize_for_system_context,
    sanitize_reference_text,
)
from nini.agent.components.context_compressor import (
    compress_session_context,
    force_auto_compress,
    maybe_auto_compress,
    sliding_window_trim,
)
from nini.agent.components.reasoning_tracker import (
    ReasoningChainTracker,
    calculate_confidence_score,
    detect_key_decisions,
    detect_reasoning_type,
)
from nini.agent.components.tool_executor import (
    compact_tool_content,
    execute_tool,
    extract_reference_excerpt,
    parse_tool_arguments,
    serialize_tool_result_for_memory,
    summarize_nested_dict,
    summarize_tool_result_dict,
)

__all__ = [
    # Context Builder
    "ContextBuilder",
    "get_last_user_message",
    "sanitize_for_system_context",
    "sanitize_reference_text",
    "filter_valid_messages",
    "prepare_messages_for_llm",
    "replace_arguments",
    # Context Compressor
    "maybe_auto_compress",
    "force_auto_compress",
    "compress_session_context",
    "sliding_window_trim",
    # Reasoning Tracker
    "ReasoningChainTracker",
    "detect_reasoning_type",
    "detect_key_decisions",
    "calculate_confidence_score",
    # Tool Executor
    "execute_tool",
    "parse_tool_arguments",
    "serialize_tool_result_for_memory",
    "compact_tool_content",
    "summarize_tool_result_dict",
    "extract_reference_excerpt",
    "summarize_nested_dict",
]
