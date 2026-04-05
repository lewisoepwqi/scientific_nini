"""Agent ReAct 循环检测守卫。

通过对每轮 tool_calls 计算顺序无关的 md5 fingerprint，
在滑动窗口内统计重复次数，实现三级响应策略：
  - NORMAL：未检测到循环，正常继续
  - WARN：检测到重复（≥ warn_threshold），注入警告消息
  - FORCE_STOP：检测到严重循环（≥ hard_limit），强制终止
"""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict, deque
from enum import Enum
from typing import Any


class LoopGuardDecision(Enum):
    """循环检测结果枚举。"""

    NORMAL = "normal"
    WARN = "warn"
    FORCE_STOP = "force_stop"


def _hash_tool_calls(tool_calls: list[dict[str, Any]]) -> str:
    """对 tool_calls 列表计算顺序无关的 md5 fingerprint（前 12 位）。

    先按 (name, json(args, sort_keys=True)) 排序，再整体序列化后取 md5，
    确保相同工具调用的不同排列产生相同 fingerprint。
    """
    # 提取并规范化每个工具调用的 (name, args_json) 元组
    normalized: list[tuple[str, str]] = []
    for tc in tool_calls:
        func = tc.get("function", {})
        name = str(func.get("name", ""))
        raw_args = func.get("arguments", "{}")
        # 尝试解析参数并重新序列化以规范化格式
        try:
            parsed_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        except (json.JSONDecodeError, TypeError):
            parsed_args = raw_args
        args_json = json.dumps(parsed_args, sort_keys=True, ensure_ascii=False)
        normalized.append((name, args_json))

    # 按 (name, args_json) 排序使结果顺序无关
    normalized.sort(key=lambda x: (x[0], x[1]))
    serialized = json.dumps(normalized, ensure_ascii=False)
    return hashlib.md5(serialized.encode()).hexdigest()[:12]


def _extract_tool_names(tool_calls: list[dict[str, Any]]) -> list[str]:
    """从 tool_calls 列表中提取工具名称。"""
    names: list[str] = []
    for tc in tool_calls:
        name = str(tc.get("function", {}).get("name", "")).strip()
        if name:
            names.append(name)
    return names


# 工具名称到循环反思提示的映射
_LOOP_REFLECTION_HINTS: dict[str, str] = {
    "dataset_catalog": "你在反复查看数据概况，请直接进入分析步骤。",
    "dataset_transform": "你在反复清洗数据，请检查转换是否已生效，然后继续下一步。",
    "stat_test": "你在反复执行统计检验，请检查前提假设是否满足，或换用其他方法。",
    "stat_model": "你在反复拟合模型，请检查模型假设或简化模型结构。",
    "code_session": "代码反复执行，请检查错误关键线索、简化逻辑或拆分步骤。",
    "preview_data": "你在反复预览数据，请直接进入分析步骤。",
    "data_summary": "你在反复查看数据摘要，请直接进入分析步骤。",
}


def build_loop_warn_message(tool_names: list[str]) -> str:
    """根据循环中涉及的工具名称，生成定制化的循环警告消息。

    Args:
        tool_names: 循环中重复调用的工具名称列表

    Returns:
        包含通用警告和工具特定反思提示的消息
    """
    base = (
        "⚠️ 注意：你已重复调用了相同的工具组合多次，这可能表明你陷入了循环。"
        "继续重复相同的工具调用将导致任务被强制终止。"
    )

    # 收集匹配到的工具特定提示（去重、保持顺序）
    specific_hints: list[str] = []
    seen: set[str] = set()
    for name in tool_names:
        hint = _LOOP_REFLECTION_HINTS.get(name)
        if hint and hint not in seen:
            specific_hints.append(hint)
            seen.add(hint)

    if specific_hints:
        hints_text = "\n".join(f"- {h}" for h in specific_hints)
        return f"{base}\n具体建议：\n{hints_text}"

    # 无特定提示时使用通用反思建议
    return f"{base}\n" "请仔细反思当前状态，尝试换一种方法解决问题，或直接给出你目前能得出的结论。"


class LoopGuard:
    """ReAct 循环重复检测器。

    维护每个 session 的 fingerprint 滑动窗口，检测重复工具调用模式。
    使用 OrderedDict 实现 LRU 缓存，最多保留 max_sessions 个 session 状态。

    Attributes:
        warn_threshold: fingerprint 出现达到此次数时返回 WARN
        hard_limit: fingerprint 出现达到此次数时返回 FORCE_STOP
        window_size: 每个 session 的滑动窗口大小（保留最近 N 次 fingerprint）
        max_sessions: LRU 缓存最大 session 数量
    """

    def __init__(
        self,
        warn_threshold: int = 4,
        hard_limit: int = 5,
        window_size: int = 20,
        max_sessions: int = 100,
    ) -> None:
        self._warn_threshold = warn_threshold
        self._hard_limit = hard_limit
        self._window_size = window_size
        self._max_sessions = max_sessions
        # LRU 缓存：session_id -> deque[fingerprint]
        # OrderedDict 维护访问顺序，最近访问的移到末尾
        self._cache: OrderedDict[str, deque[str]] = OrderedDict()

    def check(
        self, tool_calls: list[dict[str, Any]], session_id: str
    ) -> tuple[LoopGuardDecision, list[str]]:
        """检查当前 tool_calls 是否构成循环，返回决策及重复工具名称。

        将当前 tool_calls 的 fingerprint 加入滑动窗口后，统计该 fingerprint
        在窗口内的出现次数，按阈值返回 NORMAL / WARN / FORCE_STOP。

        Args:
            tool_calls: 本轮 LLM 返回的工具调用列表
            session_id: 会话 ID，用于隔离不同会话的检测状态

        Returns:
            (决策枚举值, 重复的工具名称列表)；NORMAL 时工具名列表为空
        """
        # 获取或初始化该 session 的滑动窗口
        window = self._get_or_create_window(session_id)

        # 计算当前轮的 fingerprint 并加入窗口
        fp = _hash_tool_calls(tool_calls)
        window.append(fp)
        # 窗口满时自动从左侧淘汰最旧记录（deque maxlen 控制）

        # 统计当前 fingerprint 在窗口内的出现次数
        count = sum(1 for f in window if f == fp)

        # 提取工具名称，仅在 WARN/FORCE_STOP 时返回
        if count >= self._hard_limit:
            tool_names = _extract_tool_names(tool_calls)
            return LoopGuardDecision.FORCE_STOP, tool_names
        if count >= self._warn_threshold:
            tool_names = _extract_tool_names(tool_calls)
            return LoopGuardDecision.WARN, tool_names
        return LoopGuardDecision.NORMAL, []

    def _get_or_create_window(self, session_id: str) -> deque[str]:
        """获取或创建 session 对应的滑动窗口，并更新 LRU 顺序。"""
        if session_id in self._cache:
            # 将已存在的 session 移到末尾（标记为最近访问）
            self._cache.move_to_end(session_id)
            return self._cache[session_id]

        # 新 session：若缓存已满，淘汰最久未访问的（队首）
        if len(self._cache) >= self._max_sessions:
            self._cache.popitem(last=False)

        window: deque[str] = deque(maxlen=self._window_size)
        self._cache[session_id] = window
        return window
