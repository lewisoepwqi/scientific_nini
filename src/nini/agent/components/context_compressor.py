"""Context compression and sliding window logic for AgentRunner.

Handles automatic compression when context exceeds token thresholds
and sliding window trimming as a fallback mechanism.
"""

from __future__ import annotations

import logging
from typing import Any

from nini.agent.events import AgentEvent, EventType
from nini.agent.session import Session
from nini.agent import event_builders as eb
from nini.config import settings
from nini.memory.compression import compress_session_history_with_llm
from nini.utils.token_counter import count_messages_tokens

logger = logging.getLogger(__name__)


async def compress_session_context(
    session: Session,
    *,
    current_tokens: int,
    trigger: str,
    target_tokens: int | None = None,
) -> AgentEvent | None:
    """Compress session context and return an event describing the result.

    Args:
        session: The session to compress.
        current_tokens: Current token count before compression.
        trigger: The trigger reason (e.g., "threshold", "context_limit_error").
        target_tokens: 压缩目标 token 数。若为 None 则使用阈值的一半。

    Returns:
        A CONTEXT_COMPRESSED event if successful, None otherwise.
    """
    threshold = settings.auto_compress_threshold_tokens
    target = target_tokens if target_tokens is not None else threshold // 2
    min_messages = max(4, settings.memory_keep_recent_messages)
    logger.info(
        "自动压缩触发(%s): 当前 %d tokens, 目标 %d tokens",
        trigger,
        current_tokens,
        target,
    )
    try:
        # 根据当前 token 与目标的比例计算压缩比
        ratio = min(0.8, max(0.3, 1.0 - (target / current_tokens))) if current_tokens > 0 else 0.5
        result = await compress_session_history_with_llm(
            session,
            ratio=ratio,
            min_messages=min_messages,
        )
        if not result.get("success"):
            return None

        # 验证压缩效果——使用实际 token 数而非估算
        post_tokens = count_messages_tokens(session.messages)
        if post_tokens > target and len(session.messages) > min_messages:
            logger.warning(
                "首轮压缩后仍超限 (%d > %d)，执行二次压缩 (ratio=0.7)",
                post_tokens,
                target,
            )
            result2 = await compress_session_history_with_llm(
                session,
                ratio=0.7,
                min_messages=min_messages,
            )
            if result2.get("success"):
                result["archived_count"] = result.get("archived_count", 0) + result2.get(
                    "archived_count", 0
                )
                result["remaining_count"] = result2["remaining_count"]
                post_tokens = count_messages_tokens(session.messages)

        archived_count = result.get("archived_count", 0)
        remaining_count = result.get("remaining_count", 0)
        message = (
            f"检测到上下文超限，已自动压缩，归档了 {archived_count} 条消息"
            if trigger == "context_limit_error"
            else f"上下文已自动压缩，归档了 {archived_count} 条消息"
        )
        return eb.build_context_compressed_event(
            original_tokens=current_tokens,
            compressed_tokens=post_tokens,
            compression_ratio=calculate_compression_ratio(current_tokens, post_tokens),
            message=message,
            archived_count=archived_count,
            remaining_count=remaining_count,
            previous_tokens=current_tokens,
            trigger=trigger,
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
    context_window = getattr(session, "_model_context_window", None)
    threshold, target = get_compress_threshold_for_window(context_window)
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
        target_tokens=target,
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


def get_compress_threshold_for_window(context_window: int | None) -> tuple[int, int]:
    """根据模型上下文窗口大小返回 (threshold, target) 元组。

    FULL (>=64K)：使用窗口的 ~62% 作为压缩触发点，保留更多对话历史。
    STANDARD (16-64K)：~75%，与当前行为比例一致。
    COMPACT (<16K)：~75%，更早压缩保护小窗口。
    未知窗口时回退到 settings 中的固定值。
    """
    if context_window is None or context_window >= 64_000:
        # 按比例计算：触发点 = 窗口 * 62%，目标 = 触发点 * 50%
        # 128K → (79K, 40K)，200K → (124K, 62K)
        effective_window = context_window or 128_000
        threshold = int(effective_window * 0.62)
        target = int(threshold * 0.5)
        return (threshold, target)
    if context_window >= 16_000:
        return (24_000, 12_000)
    return (6_000, 3_000)


def sliding_window_trim(
    messages: list[dict[str, Any]],
    token_budget: int,
    base_tokens: int = 0,
    min_recent: int = 4,
) -> list[dict[str, Any]]:
    """Trim messages from oldest to fit within token budget.

    Preserves tool_call/tool_result pairs and keeps at least min_recent messages.
    使用预计算 token 数 + 减法实现 O(n) 复杂度（而非每次移除后重新计数全部消息）。

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

    # 预计算每条消息的 token 数，避免 O(n²) 重复计数
    msg_tokens = [count_messages_tokens([m]) for m in messages]
    current_total = base_tokens + sum(msg_tokens)

    if current_total <= token_budget:
        return messages

    # 构建 tool_call_id → 索引映射，确保配对移除
    tc_pair: dict[str, list[int]] = {}
    for i, msg in enumerate(messages):
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                tc_id = tc.get("id")
                if tc_id:
                    tc_pair.setdefault(tc_id, []).append(i)
        elif msg.get("role") == "tool" and msg.get("tool_call_id"):
            tc_pair.setdefault(msg["tool_call_id"], []).append(i)

    index_groups: dict[int, set[int]] = {}
    for indices in tc_pair.values():
        group = set(indices)
        for idx in indices:
            index_groups[idx] = group

    removed: set[int] = set()
    total = len(messages)
    protected = set(range(max(0, total - min_recent), total))

    for i in range(total):
        if current_total <= token_budget:
            break
        if i in removed or i in protected:
            continue

        to_remove = index_groups.get(i, {i})
        if to_remove & protected:
            continue
        for idx in to_remove:
            if idx not in removed:
                current_total -= msg_tokens[idx]
                removed.add(idx)

    return [m for i, m in enumerate(messages) if i not in removed]
