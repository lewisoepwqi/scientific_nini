"""会话标题自动生成。

根据对话的前几条消息，使用 LLM 生成简短的会话标题。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from nini.agent.model_resolver import model_resolver

logger = logging.getLogger(__name__)

# 标题生成提示词
_TITLE_PROMPT = (
    "根据以下对话内容，生成一个简短的中文会话标题（8-15个字）。"
    "只输出标题本身，不要加引号或其他标点。\n\n"
)


_EDGE_CHARS = " \t\r\n\"'“”‘’《》【】()（）[]「」"
_TITLE_PREFIX_RE = re.compile(r"^(标题|会话标题|主题|title)[:：\s-]*", re.IGNORECASE)
_CODE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`]+`")
_URL_RE = re.compile(r"https?://\S+")
_SENTENCE_SPLIT_RE = re.compile(r"[。！？.!?\n]+")
_TITLE_MAX_TOKENS = 50
_TITLE_RETRY_MAX_TOKENS = 120


def _collect_relevant_messages(messages: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """提取前几条有内容的用户/助手消息。"""
    relevant: list[tuple[str, str]] = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content")
        if role in ("user", "assistant") and isinstance(content, str):
            stripped = content.strip()
            if stripped:
                relevant.append((role, stripped))
        if len(relevant) >= 4:
            break
    return relevant


def _normalize_title(raw: str) -> str:
    """规范化标题文本，去除前后噪音。"""
    text = raw.strip()
    if not text:
        return ""
    text = _TITLE_PREFIX_RE.sub("", text)
    text = text.strip(_EDGE_CHARS)
    text = re.sub(r"\s+", " ", text).strip()
    if not re.search(r"[\w\u4e00-\u9fff]", text):
        return ""
    return text


def _clean_message(content: str) -> str:
    """清理消息内容，去掉代码块、内联代码与链接。"""
    text = content.strip()
    if not text:
        return ""
    text = _CODE_BLOCK_RE.sub(" ", text)
    text = _INLINE_CODE_RE.sub(" ", text)
    text = _URL_RE.sub(" ", text)
    text = text.replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _fallback_title(messages: list[dict[str, Any]]) -> str | None:
    """当 LLM 结果为空时，基于用户消息构造标题。"""
    candidate = ""
    for msg in messages:
        if msg.get("role") == "user" and isinstance(msg.get("content"), str):
            candidate = msg["content"]
            break
    if not candidate:
        for msg in messages:
            if isinstance(msg.get("content"), str):
                candidate = msg["content"]
                break
    cleaned = _clean_message(candidate)
    if not cleaned:
        return None
    parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(cleaned) if p.strip()]
    if parts:
        cleaned = parts[0]
    cleaned = _normalize_title(cleaned)
    if not cleaned:
        return None
    if len(cleaned) > 30:
        cleaned = cleaned[:30]
    return cleaned


def _preview_text(text: str, max_len: int = 120) -> str:
    """生成单行预览文本，避免日志被长内容刷屏。"""
    single_line = text.replace("\r", " ").replace("\n", " ")
    compact = re.sub(r"\s+", " ", single_line).strip()
    if len(compact) > max_len:
        return compact[:max_len] + "..."
    return compact


def _build_title_prompt(
    relevant_msgs: list[tuple[str, str]],
    *,
    max_messages: int = 4,
    max_content_chars: int = 200,
) -> str:
    """构建标题生成提示词。"""
    relevant: list[str] = []
    for role, content in relevant_msgs[:max_messages]:
        prefix = "用户" if role == "user" else "助手"
        relevant.append(f"{prefix}: {content[:max_content_chars]}")
    return _TITLE_PROMPT + "\n".join(relevant)


async def generate_title(messages: list[dict[str, Any]]) -> str | None:
    """根据对话消息生成会话标题。

    Args:
        messages: 会话消息列表（取前几条用户和助手消息）

    Returns:
        生成的标题字符串，失败时返回 None。
    """
    logger.debug("开始生成会话标题，消息总数: %d", len(messages))

    # 提取前 4 条有内容的消息用于生成标题
    relevant_msgs = _collect_relevant_messages(messages)
    logger.debug("过滤后的相关消息数: %d", len(relevant_msgs))

    if not relevant_msgs:
        logger.debug("没有可用的消息内容，跳过标题生成")
        return None

    default_prompt = _build_title_prompt(relevant_msgs, max_messages=4, max_content_chars=200)
    retry_prompt = _build_title_prompt(relevant_msgs, max_messages=2, max_content_chars=100)
    strategies = [
        ("default", default_prompt, _TITLE_MAX_TOKENS),
        ("length_retry", retry_prompt, _TITLE_RETRY_MAX_TOKENS),
    ]
    logger.debug("标题生成默认提示词长度: %d 字符", len(default_prompt))

    try:
        last_empty_reason = "unknown"
        last_finish_reason: str | None = None
        for idx, (strategy_name, prompt, max_tokens) in enumerate(strategies):
            response = await model_resolver.chat_complete(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=max_tokens,
                purpose="title_generation",
            )
            raw_title = response.text or ""
            finish_reason = getattr(response, "finish_reason", None)
            finish_reasons = getattr(response, "finish_reasons", [])
            usage = getattr(response, "usage", {})
            tool_calls = getattr(response, "tool_calls", [])
            title = _normalize_title(raw_title)
            # 限制标题长度
            if len(title) > 30:
                title = title[:30]
            if title:
                logger.info(
                    "会话标题生成成功: %s (strategy=%s, raw_len=%d, finish_reason=%s)",
                    title,
                    strategy_name,
                    len(raw_title),
                    finish_reason,
                )
                return title
            if tool_calls:
                empty_reason = "tool_calls_only"
            elif not raw_title.strip():
                empty_reason = "raw_empty"
            else:
                empty_reason = "normalized_empty"
            last_empty_reason = empty_reason
            last_finish_reason = str(finish_reason) if finish_reason is not None else None
            logger.warning(
                "会话标题为空: reason=%s, finish_reason=%s, finish_reasons=%s, usage=%s, "
                "raw_len=%d, raw_preview=%s, strategy=%s",
                empty_reason,
                finish_reason,
                finish_reasons,
                usage,
                len(raw_title),
                _preview_text(raw_title),
                strategy_name,
            )
            should_retry = (
                idx == 0
                and empty_reason == "raw_empty"
                and str(finish_reason or "").lower() == "length"
            )
            if should_retry:
                logger.info(
                    "检测到标题输出被长度限制截断，触发重试: next_strategy=%s, next_max_tokens=%d",
                    strategies[idx + 1][0],
                    strategies[idx + 1][2],
                )
                continue
            break
        fallback = _fallback_title(messages)
        if fallback:
            logger.info(
                "LLM 标题为空，已使用回退标题: %s (reason=%s, finish_reason=%s)",
                fallback,
                last_empty_reason,
                last_finish_reason,
            )
            return fallback
        logger.warning("LLM 返回空标题，且回退失败")
        return None
    except Exception as e:
        logger.warning("生成会话标题失败: %s", e)
        return None
