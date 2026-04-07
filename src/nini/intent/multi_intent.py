"""多意图检测模块 —— 规则驱动的复合查询拆分。

支持两类复合查询：
- 顺序（"先…然后…"/"首先…其次…"）→ is_sequential=True
- 并行（"同时"/"另外还"/"以及同时"）→ is_parallel=True

无多意图时返回 None，不引入 Embedding 或外部 NLU。
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# 顺序标记正则：要求"先"后有明确连接词，避免单独"先"误触发
_SEQUENTIAL_MARKERS = re.compile(r"先.{0,10}(然后|再|接着|之后)|首先.{0,10}(其次|然后|再)")

# 并行标记正则（移除"顺便"——主从关系，非独立并行）
_PARALLEL_MARKERS = re.compile(r"同时|另外还|以及同时")

# 有标点时按标点分割
_SENTENCE_SPLIT = re.compile(r"[，。；！？,.;!?]+")

# 无标点时按连接词分割（用于顺序查询）
_CONNECTOR_SPLIT = re.compile(r"然后|接着|之后|再(?=\S)|其次")

# 无标点时按并列连接词分割（用于并行查询）
_PARALLEL_CONNECTOR_SPLIT = re.compile(r"和|以及|并且")


@dataclass
class MultiIntentResult:
    """多意图检测结果，携带分类元信息。"""

    intents: list[str]    # 拆分后的子意图列表（长度 >= 2）
    is_parallel: bool     # True 表示各子意图可并行执行
    is_sequential: bool   # True 表示各子意图需顺序执行


def detect_multi_intent(query: str) -> MultiIntentResult | None:
    """检测查询中是否包含多个意图。

    Args:
        query: 用户输入的查询字符串

    Returns:
        MultiIntentResult（含子意图列表和并/串行标记），或 None（无多意图）
    """
    if not query or not query.strip():
        return None

    is_sequential = bool(_SEQUENTIAL_MARKERS.search(query))
    is_parallel = bool(_PARALLEL_MARKERS.search(query))

    if not is_sequential and not is_parallel:
        return None

    # 策略 1：有标点时按标点分割
    parts = _SENTENCE_SPLIT.split(query)
    parts = [p.strip() for p in parts if p.strip() and len(p.strip()) > 3]
    if len(parts) >= 2:
        return MultiIntentResult(intents=parts, is_parallel=is_parallel, is_sequential=is_sequential)

    # 策略 2：无标点时按连接词分割
    if is_sequential:
        parts = _CONNECTOR_SPLIT.split(query)
        parts = [p.strip() for p in parts if p.strip() and len(p.strip()) > 3]
        if len(parts) >= 2:
            return MultiIntentResult(intents=parts, is_parallel=is_parallel, is_sequential=is_sequential)

    # 策略 3：并行查询无标点时按并列连接词分割
    if is_parallel:
        parts = _PARALLEL_CONNECTOR_SPLIT.split(query)
        parts = [p.strip() for p in parts if p.strip() and len(p.strip()) > 3]
        if len(parts) >= 2:
            return MultiIntentResult(intents=parts, is_parallel=is_parallel, is_sequential=is_sequential)

    return None
