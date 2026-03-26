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
    get_adaptive_tool_budget,
)
from nini.agent.session import Session
from nini.agent.components.tool_executor import summarize_tool_result_dict

logger = logging.getLogger(__name__)


def _resolve_ask_user_question_answer_summary(
    question_item: dict[str, Any],
    raw_answer: str,
) -> str:
    """将 ask_user_question 的原始答案映射为更适合回灌给模型的摘要文本。"""
    answer = str(raw_answer or "").strip()
    if not answer:
        return ""
    if answer == "已跳过":
        return "用户选择跳过此题"

    option_map: dict[str, str] = {}
    for raw_option in question_item.get("options", []) or []:
        if not isinstance(raw_option, dict):
            continue
        label = str(raw_option.get("label") or "").strip()
        description = str(raw_option.get("description") or "").strip()
        if not label:
            continue
        option_map[label] = description or label

    parts = [part.strip() for part in answer.split(",") if part.strip()]
    if not parts:
        return ""

    resolved = [option_map.get(part, part) for part in parts]
    return "；".join(resolved)


def _format_ask_user_question_tool_result_for_llm(content: Any, *, max_chars: int) -> str:
    """将 ask_user_question 的 tool_result 压缩为清晰的已回答摘要。"""
    raw_text = "" if content is None else str(content)
    try:
        parsed = _json.loads(raw_text) if isinstance(content, str) else content
    except _json.JSONDecodeError:
        parsed = None

    if not isinstance(parsed, dict):
        return compact_tool_content_for_preparation(content, max_chars=max_chars)

    data_obj = parsed.get("data")
    if not isinstance(data_obj, dict):
        return compact_tool_content_for_preparation(content, max_chars=max_chars)

    raw_questions = data_obj.get("questions")
    raw_answers = data_obj.get("answers")
    if not isinstance(raw_questions, list) or not isinstance(raw_answers, dict):
        return compact_tool_content_for_preparation(content, max_chars=max_chars)

    lines = ["ask_user_question 已完成，用户回答如下："]
    for idx, item in enumerate(raw_questions, start=1):
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        header = str(item.get("header") or "").strip()
        answer = ""
        for key in (question, header):
            if not key:
                continue
            value = raw_answers.get(key)
            if isinstance(value, str) and value.strip():
                answer = _resolve_ask_user_question_answer_summary(item, value)
                if answer:
                    break
        if not answer:
            continue
        title = header or question or f"问题 {idx}"
        if question and header and question != header:
            lines.append(f"- {title}：{question} -> {answer}")
        else:
            lines.append(f"- {title} -> {answer}")

    summary = "\n".join(lines).strip()
    if len(summary) > max_chars:
        return summary[:max_chars] + "...(截断)"
    return summary or compact_tool_content_for_preparation(content, max_chars=max_chars)


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


def _prepare_single_message_for_llm(
    msg: dict[str, Any],
    *,
    adaptive_max_chars: int,
) -> dict[str, Any] | None:
    """按 OpenAI 兼容 schema 重新构造单条消息。"""
    role = msg.get("role")
    event_type = msg.get("event_type")
    if role == "assistant" and (
        (isinstance(event_type, str) and event_type in NON_DIALOG_EVENT_TYPES)
        or event_type == "reasoning"
    ):
        return None

    if role == "user":
        return {"role": "user", "content": str(msg.get("content") or "")}

    if role == "assistant":
        tool_calls = msg.get("tool_calls")
        content = "" if msg.get("content") is None else str(msg.get("content") or "")
        if tool_calls:
            tool_names = {
                str(tool_call.get("function", {}).get("name") or "").strip()
                for tool_call in tool_calls
                if isinstance(tool_call, dict)
            }
            # ask_user_question 的“准备去提问”文案会强化模型再次提问，
            # 因此历史回放时仅保留 tool_calls 协议字段，不保留正文。
            if "ask_user_question" in tool_names:
                content = ""
        cleaned: dict[str, Any] = {
            "role": "assistant",
            "content": content,
        }
        if tool_calls:
            cleaned["tool_calls"] = tool_calls
        return cleaned

    if role == "tool":
        tool_name = str(msg.get("tool_name", "") or "").strip().lower()
        max_chars = (
            FETCH_URL_TOOL_CONTEXT_MAX_CHARS if tool_name == "fetch_url" else adaptive_max_chars
        )
        cleaned = {
            "role": "tool",
            "content": (
                _format_ask_user_question_tool_result_for_llm(
                    msg.get("content"),
                    max_chars=max_chars,
                )
                if tool_name == "ask_user_question"
                else compact_tool_content_for_preparation(
                    msg.get("content"),
                    max_chars=max_chars,
                )
            ),
        }
        tool_call_id = msg.get("tool_call_id")
        if tool_call_id:
            cleaned["tool_call_id"] = str(tool_call_id)
        return cleaned

    return None


def prepare_messages_for_llm(
    messages: list[dict[str, Any]],
    context_ratio: float = 0.0,
) -> list[dict[str, Any]]:
    """去掉 UI 噪音和大载荷字段，得到适合 LLM 的消息列表。

    Args:
        messages: 原始消息列表
        context_ratio: 当前 context 使用率（0.0 ~ 1.0），用于动态调整工具结果截断预算
    """
    # 根据 context 使用率计算工具结果预算
    adaptive_max_chars = get_adaptive_tool_budget(context_ratio)

    prepared: list[dict[str, Any]] = []
    for msg in messages:
        cleaned = _prepare_single_message_for_llm(msg, adaptive_max_chars=adaptive_max_chars)
        if cleaned is not None:
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
