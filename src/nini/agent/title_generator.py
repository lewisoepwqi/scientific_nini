"""会话标题自动生成。

根据对话的前几条消息，使用 LLM 生成简短的会话标题。
"""

from __future__ import annotations

import logging
from typing import Any

from nini.agent.model_resolver import model_resolver

logger = logging.getLogger(__name__)

# 标题生成提示词
_TITLE_PROMPT = (
    "根据以下对话内容，生成一个简短的中文会话标题（8-15个字）。"
    "只输出标题本身，不要加引号或其他标点。\n\n"
)


async def generate_title(messages: list[dict[str, Any]]) -> str | None:
    """根据对话消息生成会话标题。

    Args:
        messages: 会话消息列表（取前几条用户和助手消息）

    Returns:
        生成的标题字符串，失败时返回 None。
    """
    logger.debug("开始生成会话标题，消息总数: %d", len(messages))

    # 提取前 4 条有内容的消息用于生成标题
    relevant: list[str] = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content")
        if (
            role in ("user", "assistant")
            and isinstance(content, str)
            and content.strip()
        ):
            prefix = "用户" if role == "user" else "助手"
            # 截取前 200 字避免过长
            relevant.append(f"{prefix}: {content.strip()[:200]}")
        if len(relevant) >= 4:
            break

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
        title = response.text.strip().strip("\"'\"\"''")
        # 限制标题长度
        if len(title) > 30:
            title = title[:30]
        if title:
            logger.info("会话标题生成成功: %s", title)
        else:
            logger.warning("LLM 返回空标题")
        return title or None
    except Exception as e:
        logger.warning("生成会话标题失败: %s", e)
        return None
