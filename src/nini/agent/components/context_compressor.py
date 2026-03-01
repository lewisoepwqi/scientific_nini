"""Context compression and sliding window logic for AgentRunner.

Handles automatic compression when context exceeds token thresholds
and sliding window trimming as a fallback mechanism.
"""

from __future__ import annotations

import logging
from typing import Any

from nini.agent.events import AgentEvent, EventType
from nini.agent.session import Session
from nini.config import settings
from nini.memory.compression import compress_session_history_with_llm
from nini.utils.token_counter import count_messages_tokens

logger = logging.getLogger(__name__)


async def compress_session_context(
    session: Session,
    *,
    current_tokens: int,
    trigger: str,
) -> AgentEvent | None:
    """Compress session context and return an event describing the result.

    Args:
        session: The session to compress.
        current_tokens: Current token count before compression.
        trigger: The trigger reason (e.g., "threshold", "context_limit_error").

    Returns:
        A CONTEXT_COMPRESSED event if successful, None otherwise.
    """
    threshold = settings.auto_compress_threshold_tokens
    logger.info(
        "自动压缩触发(%s): 当前 %d tokens, 阈值 %d tokens",
        trigger,
        current_tokens,
        threshold,
    )
    try:
        result = await compress_session_history_with_llm(session, ratio=0.5, min_messages=4)
        if result.get("success"):
            archived_count = result.get("archived_count", 0)
            remaining_count = result.get("remaining_count", 0)
            message = (
                f"检测到上下文超限，已自动压缩，归档了 {archived_count} 条消息"
                if trigger == "context_limit_error"
                else f"上下文已自动压缩，归档了 {archived_count} 条消息"
            )
            return AgentEvent(
                type=EventType.CONTEXT_COMPRESSED,
                data={
                    "archived_count": archived_count,
                    "remaining_count": remaining_count,
                    "previous_tokens": current_tokens,
                    "trigger": trigger,
                    "message": message,
                },
            )
    except Exception as exc:
        logger.warning("自动压缩失败(%s): %s", trigger, exc, exc_info=True)
    return None


async def maybe_auto_compress(
    session: Session,
    *,
    current_tokens: int | None = None,
) -> AgentEvent | None:
    """Check if context exceeds threshold and auto-compress if needed.

    Args:
        session: The session to check and potentially compress.
        current_tokens: Optional pre-computed token count. If None, will be calculated.

    Returns:
        A CONTEXT_COMPRESSED event if compression occurred, None otherwise.
    """
    if not settings.auto_compress_enabled:
        return None
    threshold = settings.auto_compress_threshold_tokens
    measured_tokens = (
        int(current_tokens)
        if current_tokens is not None
        else count_messages_tokens(session.messages)
    )
    if measured_tokens <= threshold:
        return None
    return await compress_session_context(
        session,
        current_tokens=measured_tokens,
        trigger="threshold",
    )


async def force_auto_compress(
    session: Session,
    *,
    current_tokens: int,
) -> AgentEvent | None:
    """Force compression regardless of threshold (for context limit recovery).

    Args:
        session: The session to compress.
        current_tokens: Current token count.

    Returns:
        A CONTEXT_COMPRESSED event if successful, None otherwise.
    """
    if not settings.auto_compress_enabled:
        return None
    return await compress_session_context(
        session,
        current_tokens=int(current_tokens),
        trigger="context_limit_error",
    )


def calculate_compression_ratio(
    original_tokens: int,
    compressed_tokens: int,
) -> float:
    """Calculate the compression ratio achieved.

    Args:
        original_tokens: Token count before compression.
        compressed_tokens: Token count after compression.

    Returns:
        The compression ratio (0.0 to 1.0, higher is more compressed).
    """
    if original_tokens <= 0:
        return 0.0
    ratio = 1.0 - (compressed_tokens / original_tokens)
    return max(0.0, min(1.0, ratio))


def sliding_window_trim(
    messages: list[dict[str, Any]],
    token_budget: int,
    base_tokens: int = 0,
    min_recent: int = 4,
) -> list[dict[str, Any]]:
    """Trim messages from oldest to fit within token budget.

    Preserves tool_call/tool_result pairs and keeps at least min_recent messages.

    Args:
        messages: List of messages to trim.
        token_budget: Maximum tokens allowed.
        base_tokens: Token count of base/context messages not in the list.
        min_recent: Minimum number of recent messages to preserve.

    Returns:
        Trimmed message list fitting within token budget.
    """
    if not messages:
        return messages

    # Build tool_call_id -> index mapping to ensure paired removal
    tc_pair: dict[str, list[int]] = {}
    for i, msg in enumerate(messages):
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                tc_id = tc.get("id")
                if tc_id:
                    tc_pair.setdefault(tc_id, []).append(i)
        elif msg.get("role") == "tool" and msg.get("tool_call_id"):
            tc_pair.setdefault(msg["tool_call_id"], []).append(i)

    # Which indices must be removed together
    index_groups: dict[int, set[int]] = {}
    for indices in tc_pair.values():
        group = set(indices)
        for idx in indices:
            index_groups[idx] = group

    removed: set[int] = set()
    total = len(messages)
    protected = set(range(max(0, total - min_recent), total))

    for i in range(total):
        current = base_tokens + count_messages_tokens(
            [m for j, m in enumerate(messages) if j not in removed]
        )
        if current <= token_budget:
            break
        if i in removed or i in protected:
            continue

        # Remove this index and its pair
        to_remove = index_groups.get(i, {i})
        if to_remove & protected:
            continue
        removed |= to_remove

    return [m for i, m in enumerate(messages) if i not in removed]
