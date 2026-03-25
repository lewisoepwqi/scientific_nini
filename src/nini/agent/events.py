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
    ANALYSIS_PLAN = "analysis_plan"  # 结构化分析步骤列表
    PLAN_STEP_UPDATE = "plan_step_update"  # 单步状态变更
    PLAN_PROGRESS = "plan_progress"  # 顶部计划进度（含当前步骤/下一步提示）
    TASK_ATTEMPT = "task_attempt"  # 任务执行尝试（含重试轨迹）
    CONTEXT_COMPRESSED = "context_compressed"  # 上下文自动压缩通知
    ASK_USER_QUESTION = "ask_user_question"  # 等待用户问答输入
    TOKEN_USAGE = "token_usage"  # Token 使用量更新
    MODEL_FALLBACK = "model_fallback"  # 模型自动降级通知
    RUN_CONTEXT = "run_context"  # 当前轮 harness 运行上下文摘要
    COMPLETION_CHECK = "completion_check"  # 完成前结构化校验结果
    BLOCKED = "blocked"  # harness 阻塞状态
    BUDGET_WARNING = "budget_warning"  # deep task 预算告警

    # WebSocket 专用事件类型
    WORKSPACE_UPDATE = "workspace_update"  # 通知前端刷新工作区
    CODE_EXECUTION = "code_execution"  # 代码执行结果推送
    STOPPED = "stopped"  # 停止请求响应
    SESSION = "session"  # 返回 session_id
    PONG = "pong"  # WebSocket 保活响应
    SESSION_TITLE = "session_title"  # 自动生成会话标题
    TRIAL_EXPIRED = "trial_expired"  # 试用期已到期，阻断消息处理
    TRIAL_ACTIVATED = "trial_activated"  # 首次消息触发试用激活

    # 多 Agent 协作事件类型
    AGENT_START = "agent_start"  # 子 Agent 开始执行
    AGENT_PROGRESS = "agent_progress"  # 子 Agent 执行进度（Phase 2 payload 规划）
    AGENT_COMPLETE = "agent_complete"  # 子 Agent 成功完成
    AGENT_ERROR = "agent_error"  # 子 Agent 执行失败（含超时）
    WORKFLOW_STATUS = "workflow_status"  # 工作流整体状态（Phase 2 payload 规划）

    # Hypothesis-Driven 范式事件类型（Phase 3）
    HYPOTHESIS_GENERATED = "hypothesis_generated"  # LLM 生成初始假设
    EVIDENCE_COLLECTED = "evidence_collected"  # 工具调用收集到证据
    HYPOTHESIS_VALIDATED = "hypothesis_validated"  # 假设被证实
    HYPOTHESIS_REFUTED = "hypothesis_refuted"  # 假设被证伪
    HYPOTHESIS_REVISED = "hypothesis_revised"  # 假设被修正为新版本
    PARADIGM_SWITCHED = "paradigm_switched"  # 执行路径切换为 Hypothesis-Driven


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
    # 新增字段（向后兼容，可选）
    reasoning_type: str | None = None  # "analysis" | "decision" | "planning" | "reflection"
    reasoning_subtype: str | None = None  # 更细粒度的类型
    confidence_score: float | None = None  # 0.0 - 1.0 的置信度分数
    key_decisions: list[str] = field(default_factory=list)  # 关键决策点列表
    parent_id: str | None = None  # 父推理节点 ID（用于链式关联）
    references: list[dict[str, Any]] = field(default_factory=list)  # 引用数据来源
    timestamp: str | None = None  # ISO 格式时间戳
    tags: list[str] = field(default_factory=list)  # 标签，如 ["assumption_check", "fallback"]

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        result = {
            "step": self.step,
            "thought": self.thought,
            "rationale": self.rationale,
            "alternatives": self.alternatives,
            "confidence": self.confidence,
            "context": self.context,
        }
        # 添加新字段（如果存在）
        if self.reasoning_type:
            result["reasoning_type"] = self.reasoning_type
        if self.reasoning_subtype:
            result["reasoning_subtype"] = self.reasoning_subtype
        if self.confidence_score is not None:
            result["confidence_score"] = self.confidence_score
        if self.key_decisions:
            result["key_decisions"] = self.key_decisions
        if self.parent_id:
            result["parent_id"] = self.parent_id
        if self.references:
            result["references"] = self.references
        if self.timestamp:
            result["timestamp"] = self.timestamp
        if self.tags:
            result["tags"] = self.tags
        return result


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

    使用 event_builders 构建类型安全的推理事件。

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
    from nini.agent import event_builders as eb

    return eb.build_reasoning_data_event(
        step=step,
        thought=thought,
        rationale=rationale,
        alternatives=alternatives or [],
        confidence=confidence,
        **context,
    )
