"""会话压缩服务。

将长会话前半段历史归档到磁盘，并写入压缩摘要供后续上下文注入。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nini.agent.session import Session
from nini.config import settings


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
    """压缩会话历史并返回执行结果。"""
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
        "archive_path": str(archive_path),
        "archived_count": len(archived),
        "remaining_count": len(remaining),
        "compressed_rounds": session.compressed_rounds,
        "last_compressed_at": session.last_compressed_at,
    }

