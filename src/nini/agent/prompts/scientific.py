"""科研领域系统 Prompt。"""

from __future__ import annotations

from nini.agent.prompts.builder import build_system_prompt


def get_system_prompt(
    *,
    context_window: int | None = None,
    intent_hints: set[str] | None = None,
) -> str:
    """获取格式化后的系统 Prompt。

    Args:
        context_window: 模型上下文窗口大小，用于自动选择 prompt profile
        intent_hints: 意图关键词集合，用于条件注入相关策略组件
    """
    return build_system_prompt(context_window=context_window, intent_hints=intent_hints)
