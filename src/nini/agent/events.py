"""Agent 事件相关定义。

包含事件类型、事件数据结构和推理数据。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class EventType(str, Enum):
    """Agent 事件类型。"""

    TEXT = "text"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    RETRIEVAL = "retrieval"
    CHART = "chart"
    DATA = "data"
    ARTIFACT = "artifact"
    IMAGE = "image"
    ITERATION_START = "iteration_start"
    DONE = "done"
    ERROR = "error"
    REASONING = "reasoning"  # 推理事件，展示决策过程
    CONTEXT_COMPRESSED = "context_compressed"  # 上下文自动压缩通知


@dataclass
class AgentEvent:
    """Agent 推送的事件。"""

    type: EventType
    data: Any = None
    # 用于工具调用追踪
    tool_call_id: str | None = None
    tool_name: str | None = None
    # 用于前端消息分组
    turn_id: str | None = None
    # 事件元数据（如 run_code 执行意图）
    metadata: dict[str, Any] = field(default_factory=dict)
    # 时间戳
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ReasoningData:
    """推理事件数据结构。

    用于展示 Agent 的决策过程，提高可解释性。
    """

    step: str  # 决策步骤，如 "method_selection", "parameter_selection", "chart_selection"
    thought: str  # 决策思路
    rationale: str  # 决策理由
    alternatives: list[str] = field(default_factory=list)  # 考虑过的替代方案
    confidence: float = 1.0  # 决策置信度 (0-1)
    context: dict[str, Any] = field(default_factory=dict)  # 额外上下文信息

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "step": self.step,
            "thought": self.thought,
            "rationale": self.rationale,
            "alternatives": self.alternatives,
            "confidence": self.confidence,
            "context": self.context,
        }


class ReasoningStep:
    """预定义的推理步骤类型。"""

    METHOD_SELECTION = "method_selection"
    PARAMETER_SELECTION = "parameter_selection"
    CHART_SELECTION = "chart_selection"
    ASSUMPTION_CHECK = "assumption_check"
    FALLBACK_DECISION = "fallback_decision"
    DATA_INTERPRETATION = "data_interpretation"


def create_reasoning_event(
    step: str,
    thought: str,
    rationale: str = "",
    alternatives: list[str] | None = None,
    confidence: float = 1.0,
    **context: Any,
) -> AgentEvent:
    """创建推理事件的便捷函数。

    Args:
        step: 决策步骤
        thought: 决策思路
        rationale: 决策理由
        alternatives: 替代方案列表
        confidence: 置信度
        **context: 额外上下文

    Returns:
        AgentEvent: 推理事件
    """
    reasoning_data = ReasoningData(
        step=step,
        thought=thought,
        rationale=rationale,
        alternatives=alternatives or [],
        confidence=confidence,
        context=context,
    )

    return AgentEvent(
        type=EventType.REASONING,
        data=reasoning_data.to_dict(),
    )
