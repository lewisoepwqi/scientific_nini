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
_TITLE_PREFIX_RE = re.compile(r"^(标题|会话标题|主题|title)[:：\\s-]*", re.IGNORECASE)
_CODE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`]+`")
_URL_RE = re.compile(r"https?://\\S+")
_SENTENCE_SPLIT_RE = re.compile(r"[。！？.!?\n]+")


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
    relevant: list[str] = []
    for role, content in relevant_msgs:
        prefix = "用户" if role == "user" else "助手"
        # 截取前 200 字避免过长
        relevant.append(f"{prefix}: {content[:200]}")

    logger.debug("过滤后的相关消息数: %d", len(relevant))

    if not relevant:
        logger.debug("没有可用的消息内容，跳过标题生成")
        return None

    prompt = _TITLE_PROMPT + "\n".join(relevant)
    logger.debug("标题生成提示词长度: %d 字符", len(prompt))

    try:
        response = await model_resolver.chat_complete(
            [{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=50,
        )
        title = _normalize_title(response.text)
        # 限制标题长度
        if len(title) > 30:
            title = title[:30]
        if title:
            logger.info("会话标题生成成功: %s", title)
            return title
        fallback = _fallback_title(messages)
        if fallback:
            logger.info("LLM 标题为空，已使用回退标题: %s", fallback)
            return fallback
        logger.warning("LLM 返回空标题，且回退失败")
        return None
    except Exception as e:
        logger.warning("生成会话标题失败: %s", e)
        return None
