"""上下文构建通用工具函数。"""

from __future__ import annotations

import json as _json
import logging
import re
from typing import Any

from nini.agent.prompt_policy import (
    DEFAULT_TOOL_CONTEXT_MAX_CHARS,
    FETCH_URL_TOOL_CONTEXT_MAX_CHARS,
    NON_DIALOG_EVENT_TYPES,
    SANITIZE_MAX_LEN,
    SUSPICIOUS_CONTEXT_PATTERNS,
)
from nini.agent.session import Session
from nini.agent.components.tool_executor import summarize_tool_result_dict

logger = logging.getLogger(__name__)


def get_last_user_message(session: Session) -> str:
    """提取最后一条用户消息。"""
    for msg in reversed(session.messages):
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str) and content:
            return content
    return ""


def sanitize_for_system_context(value: Any, *, max_len: int = SANITIZE_MAX_LEN) -> str:
    """清洗动态文本，避免注入到系统上下文时污染提示。"""
    text = str(value).replace("\r", " ").replace("\n", " ").replace("\t", " ")
    text = re.sub(r"\s+", " ", text).strip()
    text = (
        text.replace("\\", "\\\\")
        .replace("`", "\\`")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("<", "\\<")
        .replace(">", "\\>")
    )
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text or "(空)"


def sanitize_reference_text(text: str, *, max_len: int) -> str:
    """过滤参考文本中的可疑覆写指令并裁剪长度。"""
    safe_lines: list[str] = []
    filtered = 0
    for raw_line in str(text).splitlines():
        line = sanitize_for_system_context(raw_line, max_len=240)
        line_lower = line.lower()
        if any(pattern in line_lower for pattern in SUSPICIOUS_CONTEXT_PATTERNS):
            filtered += 1
            continue
        safe_lines.append(line)

    if filtered:
        safe_lines.append(f"[已过滤 {filtered} 行可疑指令文本]")

    merged = "\n".join(safe_lines).strip() or "[参考文本为空]"
    if len(merged) > max_len:
        return merged[:max_len] + "..."
    return merged


def filter_valid_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """移除缺失 tool response 的 assistant tool_calls 消息。"""
    tool_call_ids: set[str] = set()
    tool_responses: set[str] = set()

    for msg in messages:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            for tool_call in msg["tool_calls"]:
                tool_call_id = tool_call.get("id")
                if tool_call_id:
                    tool_call_ids.add(tool_call_id)
        elif msg.get("role") == "tool" and msg.get("tool_call_id"):
            tool_responses.add(msg["tool_call_id"])

    missing_responses = tool_call_ids - tool_responses
    if missing_responses:
        logger.warning(
            "过滤掉 %d 条不完整的 tool_calls 消息: %s",
            len(missing_responses),
            missing_responses,
        )

    valid_messages: list[dict[str, Any]] = []
    for msg in messages:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            msg_tool_ids = {
                tool_call.get("id") for tool_call in msg["tool_calls"] if tool_call.get("id")
            }
            if msg_tool_ids & missing_responses:
                continue
        valid_messages.append(msg)
    return valid_messages


def compact_tool_content_for_preparation(content: Any, *, max_chars: int) -> str:
    """压缩工具结果，过滤超大字段后再截断。"""
    text = "" if content is None else str(content)
    if isinstance(content, str):
        stripped = content.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                parsed = _json.loads(stripped)
                if isinstance(parsed, dict):
                    text = _json.dumps(
                        summarize_tool_result_dict(parsed),
                        ensure_ascii=False,
                        default=str,
                    )
            except _json.JSONDecodeError:
                pass

    if len(text) > max_chars:
        return text[:max_chars] + "...(截断)"
    return text


def prepare_messages_for_llm(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """去掉 UI 噪音和大载荷字段，得到适合 LLM 的消息列表。"""
    prepared: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role")
        event_type = msg.get("event_type")
        if (
            role == "assistant"
            and isinstance(event_type, str)
            and event_type in NON_DIALOG_EVENT_TYPES
        ):
            continue

        cleaned = dict(msg)
        cleaned.pop("event_type", None)
        cleaned.pop("chart_data", None)
        cleaned.pop("data_preview", None)
        cleaned.pop("artifacts", None)
        cleaned.pop("images", None)

        if role == "tool":
            tool_name = str(cleaned.get("tool_name", "") or "").strip().lower()
            max_chars = (
                FETCH_URL_TOOL_CONTEXT_MAX_CHARS
                if tool_name == "fetch_url"
                else DEFAULT_TOOL_CONTEXT_MAX_CHARS
            )
            cleaned.pop("tool_name", None)
            cleaned.pop("status", None)
            cleaned.pop("intent", None)
            cleaned.pop("execution_id", None)
            cleaned["content"] = compact_tool_content_for_preparation(
                cleaned.get("content"),
                max_chars=max_chars,
            )
        prepared.append(cleaned)
    return prepared


def replace_arguments(text: str, arguments: str) -> str:
    """替换技能文档里的 `$ARGUMENTS` 和 `$1..$9` 占位符。"""
    text = text.replace("$ARGUMENTS", arguments)
    tokens = arguments.split() if arguments else []
    for index in range(9, 0, -1):
        placeholder = f"${index}"
        replacement = tokens[index - 1] if index <= len(tokens) else ""
        text = text.replace(placeholder, replacement)
    return text
