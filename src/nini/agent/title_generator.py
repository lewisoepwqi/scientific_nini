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
    "根据以下对话内容，生成一个中文会话标题。\n"
    "硬性要求：\n"
    "1. 只输出 1 行标题，不要解释、不要思考过程、不要代码块、不要前后缀。\n"
    "2. 标题控制在 8-12 个中文字符内，绝对不要超过 15 个中文字符。\n"
    "3. 禁止输出“标题：”“会话标题：”“你好”“请问”“好的”等空泛词。\n"
    "4. 若信息不足，请输出“数据分析讨论”。\n\n"
)


_EDGE_CHARS = " \t\r\n\"'“”‘’《》【】()（）[]「」"
_TITLE_PREFIX_RE = re.compile(r"^(标题|会话标题|主题|title)[:：\s-]*", re.IGNORECASE)
_CODE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`]+`")
_URL_RE = re.compile(r"https?://\S+")
_SENTENCE_SPLIT_RE = re.compile(r"[。！？.!?\n]+")
_LEADING_FILLER_RE = re.compile(
    r"^(?:你好|您好|嗨|哈喽|hi|hello|请问|请|麻烦你|麻烦|帮我|请帮我|请帮忙|"
    r"可以|能否|想请你|我想请你|我想让你|帮忙)[，,、\s]*",
    re.IGNORECASE,
)
_GENERIC_TITLES = {
    "你好",
    "您好",
    "嗨",
    "哈喽",
    "hi",
    "hello",
    "请问",
    "帮我",
    "麻烦",
    "开始",
    "继续",
    "好的",
    "谢谢",
}
_TITLE_HARD_LIMIT = 15
_TITLE_MAX_TOKENS = 50
_TITLE_RETRY_MAX_TOKENS = 120


def _collect_relevant_messages(messages: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """优先提取前几条有内容的用户消息，必要时再补助手消息。"""
    relevant: list[tuple[str, str]] = []
    assistant_buffer: list[tuple[str, str]] = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content")
        if role in ("user", "assistant") and isinstance(content, str):
            stripped = content.strip()
            if stripped:
                if role == "user":
                    relevant.append((role, stripped))
                    if len(relevant) >= 2:
                        break
                else:
                    assistant_buffer.append((role, stripped))
    if len(relevant) < 2:
        for item in assistant_buffer:
            relevant.append(item)
            if len(relevant) >= 2:
                break
    return relevant


def _normalize_title(raw: str) -> str:
    """规范化标题文本，去除前后噪音。"""
    text = raw.strip()
    if not text:
        return ""
    text = _TITLE_PREFIX_RE.sub("", text)
    text = text.strip(_EDGE_CHARS)
    text = text.splitlines()[0].strip()
    text = re.split(r"[。！？.!?]", text, maxsplit=1)[0].strip()
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


def _strip_leading_filler(text: str) -> str:
    """去掉寒暄或客套开头，保留真正任务主体。"""
    stripped = text.strip()
    while stripped:
        updated = _LEADING_FILLER_RE.sub("", stripped, count=1).strip()
        if updated == stripped:
            break
        stripped = updated
    return stripped


def _is_generic_title(text: str) -> bool:
    """判断标题是否过于空泛。"""
    normalized = text.strip().lower()
    if not normalized:
        return True
    if normalized in _GENERIC_TITLES:
        return True
    if any(
        marker in normalized
        for marker in ("可以帮你", "有什么可以帮你", "有什么能帮你", "请问有什么")
    ):
        return True
    return len(normalized) <= 4 and normalized in {"好的", "收到", "在吗", "你好啊"}


def _score_fallback_candidate(text: str, role: str, index: int) -> tuple[int, int, int]:
    """为规则回退候选标题打分，优先挑选信息量更高的用户消息。"""
    length_score = min(len(text), 30)
    role_score = 20 if role == "user" else 0
    position_score = max(0, 10 - index)
    return (role_score + length_score + position_score, role_score, -index)


def _trim_title_length(text: str, *, limit: int = _TITLE_HARD_LIMIT) -> str:
    """按标题语义优先裁剪长度，避免简单硬截断。"""
    normalized = _normalize_title(text)
    if not normalized:
        return ""
    if len(normalized) <= limit:
        return normalized

    splitters = (" - ", "｜", "|", "：", ":", "，", ",", "、", "（", "(")
    for splitter in splitters:
        head = normalized.split(splitter, 1)[0].strip(_EDGE_CHARS + " ，,、：:")
        if head and len(head) <= limit:
            return head

    for idx in range(limit, max(3, limit - 4), -1):
        candidate = normalized[:idx].rstrip(_EDGE_CHARS + " ，,、：:")
        if candidate:
            return candidate
    return normalized[:limit].rstrip(_EDGE_CHARS + " ，,、：:")


def _fallback_title(messages: list[dict[str, Any]]) -> str | None:
    """当 LLM 结果为空时，基于用户消息构造标题。"""
    candidates: list[tuple[tuple[int, int, int], str]] = []
    for index, msg in enumerate(messages):
        role = str(msg.get("role") or "")
        content = msg.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str):
            continue
        cleaned = _clean_message(content)
        if not cleaned:
            continue
        parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(cleaned) if p.strip()]
        if not parts:
            parts = [cleaned]
        for part in parts[:2]:
            normalized = _trim_title_length(_strip_leading_filler(part))
            if not normalized or _is_generic_title(normalized):
                continue
            candidates.append((_score_fallback_candidate(normalized, role, index), normalized))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


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
    max_messages: int = 2,
    max_content_chars: int = 100,
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

    # 标题更依赖用户意图，默认只取前 1-2 条短消息，降低跑题概率
    relevant_msgs = _collect_relevant_messages(messages)
    logger.debug("过滤后的相关消息数: %d", len(relevant_msgs))

    if not relevant_msgs:
        logger.debug("没有可用的消息内容，跳过标题生成")
        return None

    default_prompt = _build_title_prompt(relevant_msgs, max_messages=2, max_content_chars=80)
    retry_prompt = _build_title_prompt(relevant_msgs, max_messages=1, max_content_chars=60)
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
            title = _trim_title_length(raw_title)
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
