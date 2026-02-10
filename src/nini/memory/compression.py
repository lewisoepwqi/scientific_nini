"""会话压缩服务。

将长会话前半段历史归档到磁盘，并写入压缩摘要供后续上下文注入。
支持两种摘要模式：
- 轻量摘要（默认）：纯文本提取，不调用 LLM
- LLM 摘要：调用大模型生成 ≤500 字中文摘要，保留关键上下文
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nini.agent.session import Session
from nini.config import settings

logger = logging.getLogger(__name__)

_LLM_SUMMARY_PROMPT = (
    "你是一位专业的科研助手。请将以下对话历史压缩为一段简洁的中文摘要，"
    "保留关键信息（用户需求、分析方法、数据集、关键结论、待解决问题），"
    "摘要不超过 500 字。只输出摘要内容，不要添加额外说明。\n\n"
    "对话历史：\n{conversation}"
)


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _trim_text(value: Any, *, max_len: int = 180) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text


def _summarize_messages(messages: list[dict[str, Any]], *, max_items: int = 20) -> str:
    """生成轻量摘要，避免再引入一次模型调用。"""
    lines: list[str] = []
    for msg in messages[:max_items]:
        role = str(msg.get("role", "")).strip() or "unknown"
        if role == "tool":
            tool_id = _trim_text(msg.get("tool_call_id", ""), max_len=32)
            content = _trim_text(msg.get("content", ""), max_len=140)
            lines.append(f"- [tool:{tool_id}] {content}")
            continue

        content = _trim_text(msg.get("content", ""), max_len=140)
        if role == "assistant" and msg.get("tool_calls"):
            tool_calls = msg.get("tool_calls", [])
            if isinstance(tool_calls, list) and tool_calls:
                names = []
                for item in tool_calls[:4]:
                    if isinstance(item, dict):
                        func = item.get("function", {})
                        if isinstance(func, dict):
                            name = str(func.get("name", "")).strip()
                            if name:
                                names.append(name)
                if names:
                    lines.append(f"- [assistant] 调用了工具: {', '.join(names)}")
                    if content:
                        lines.append(f"- [assistant] {content}")
                    continue
        lines.append(f"- [{role}] {content}")

    if len(messages) > max_items:
        lines.append(f"- ... 其余 {len(messages) - max_items} 条消息已省略")

    return "\n".join(lines).strip()


def _format_messages_for_llm(messages: list[dict[str, Any]], *, max_chars: int = 8000) -> str:
    """将消息列表格式化为 LLM 可读的对话文本。"""
    lines: list[str] = []
    total_chars = 0
    for msg in messages:
        role = str(msg.get("role", "")).strip() or "unknown"
        content = str(msg.get("content", "")).strip()

        if role == "tool":
            content = _trim_text(content, max_len=200)
            line = f"[工具结果] {content}"
        elif role == "assistant" and msg.get("tool_calls"):
            tool_calls = msg.get("tool_calls", [])
            names = []
            for item in (tool_calls or [])[:4]:
                if isinstance(item, dict):
                    func = item.get("function", {})
                    if isinstance(func, dict):
                        name = str(func.get("name", "")).strip()
                        if name:
                            names.append(name)
            tool_info = f"（调用工具: {', '.join(names)}）" if names else ""
            text = _trim_text(content, max_len=300) if content else ""
            line = f"[助手]{tool_info} {text}".strip()
        elif role == "user":
            line = f"[用户] {_trim_text(content, max_len=500)}"
        elif role == "assistant":
            line = f"[助手] {_trim_text(content, max_len=500)}"
        else:
            line = f"[{role}] {_trim_text(content, max_len=200)}"

        if total_chars + len(line) > max_chars:
            lines.append("... (后续消息已省略)")
            break
        lines.append(line)
        total_chars += len(line)

    return "\n".join(lines)


async def _llm_summarize(messages: list[dict[str, Any]]) -> str | None:
    """调用 LLM 生成对话摘要。失败时返回 None。"""
    try:
        from nini.agent.model_resolver import model_resolver

        conversation_text = _format_messages_for_llm(messages)
        prompt = _LLM_SUMMARY_PROMPT.format(conversation=conversation_text)

        response = await model_resolver.chat_complete(
            [{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=800,
        )
        summary = response.text.strip()
        if summary:
            # 确保不超过 500 字
            if len(summary) > 500:
                summary = summary[:500] + "..."
            logger.info("LLM 对话摘要生成成功 (%d 字)", len(summary))
            return summary
    except Exception:
        logger.warning("LLM 对话摘要生成失败，回退到轻量摘要", exc_info=True)
    return None


def _archive_messages(session_id: str, messages: list[dict[str, Any]]) -> Path:
    archive_dir = settings.sessions_dir / session_id / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / f"compressed_{_now_ts()}.json"
    archive_path.write_text(
        json.dumps(messages, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return archive_path


def compress_session_history(
    session: Session,
    *,
    ratio: float = 0.5,
    min_messages: int = 4,
) -> dict[str, Any]:
    """压缩会话历史并返回执行结果（轻量摘要模式）。"""
    total = len(session.messages)
    if total < min_messages:
        return {
            "success": False,
            "message": f"消息数量不足，至少需要 {min_messages} 条消息才可压缩",
            "archived_count": 0,
            "remaining_count": total,
        }

    ratio = min(max(ratio, 0.1), 0.9)
    archive_count = max(min_messages, int(total * ratio))
    if archive_count >= total:
        archive_count = max(total - 1, 1)

    archived = session.messages[:archive_count]
    remaining = session.messages[archive_count:]
    if not archived:
        return {
            "success": False,
            "message": "没有可归档的消息",
            "archived_count": 0,
            "remaining_count": total,
        }

    summary = _summarize_messages(archived)
    archive_path = _archive_messages(session.id, archived)

    session.messages = remaining
    session._rewrite_conversation_memory()
    session.set_compressed_context(summary)

    return {
        "success": True,
        "message": "会话压缩完成",
        "summary": summary,
        "summary_mode": "lightweight",
        "archive_path": str(archive_path),
        "archived_count": len(archived),
        "remaining_count": len(remaining),
        "compressed_rounds": session.compressed_rounds,
        "last_compressed_at": session.last_compressed_at,
    }


async def compress_session_history_with_llm(
    session: Session,
    *,
    ratio: float = 0.5,
    min_messages: int = 4,
) -> dict[str, Any]:
    """压缩会话历史（LLM 摘要模式）。

    优先使用 LLM 生成高质量中文摘要，失败时自动回退到轻量摘要。
    """
    total = len(session.messages)
    if total < min_messages:
        return {
            "success": False,
            "message": f"消息数量不足，至少需要 {min_messages} 条消息才可压缩",
            "archived_count": 0,
            "remaining_count": total,
        }

    ratio = min(max(ratio, 0.1), 0.9)
    archive_count = max(min_messages, int(total * ratio))
    if archive_count >= total:
        archive_count = max(total - 1, 1)

    archived = session.messages[:archive_count]
    remaining = session.messages[archive_count:]
    if not archived:
        return {
            "success": False,
            "message": "没有可归档的消息",
            "archived_count": 0,
            "remaining_count": total,
        }

    # 尝试 LLM 摘要
    summary = await _llm_summarize(archived)
    summary_mode = "llm"
    if summary is None:
        summary = _summarize_messages(archived)
        summary_mode = "lightweight"

    archive_path = _archive_messages(session.id, archived)

    session.messages = remaining
    session._rewrite_conversation_memory()
    session.set_compressed_context(summary)

    return {
        "success": True,
        "message": "会话压缩完成",
        "summary": summary,
        "summary_mode": summary_mode,
        "archive_path": str(archive_path),
        "archived_count": len(archived),
        "remaining_count": len(remaining),
        "compressed_rounds": session.compressed_rounds,
        "last_compressed_at": session.last_compressed_at,
    }
