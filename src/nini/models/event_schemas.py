"""WebSocket 事件数据结构定义。

为每种 WebSocket 事件类型定义严格的 Pydantic 模型，
确保前后端数据契约一致。
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ---- 分析计划相关事件 ----


class AnalysisPlanStep(BaseModel):
    """分析计划步骤。"""

    id: int = Field(..., description="步骤 ID（1-based）")
    title: str = Field(..., description="步骤标题")
    tool_hint: Optional[str] = Field(None, description="推荐工具提示")
    status: Literal["pending", "in_progress", "completed", "failed", "skipped"] = Field(
        "pending", description="步骤状态"
    )
    action_id: Optional[str] = Field(None, description="动作 ID，用于任务关联")
    raw_status: Optional[str] = Field(None, description="后端原始状态")


class AnalysisPlanEventData(BaseModel):
    """ANALYSIS_PLAN 事件的数据结构。"""

    steps: list[AnalysisPlanStep] = Field(..., description="分析步骤列表")
    raw_text: str = Field("", description="原始文本内容")


class PlanStepUpdateEventData(BaseModel):
    """PLAN_STEP_UPDATE 事件的数据结构。"""

    id: int = Field(..., description="步骤 ID")
    status: str = Field(..., description="新状态")
    error: Optional[str] = Field(None, description="错误信息（如果失败）")


class PlanProgressEventData(BaseModel):
    """PLAN_PROGRESS 事件的数据结构。"""

    steps: list[AnalysisPlanStep] = Field(..., description="所有步骤")
    current_step_index: int = Field(..., description="当前步骤索引（1-based）")
    total_steps: int = Field(..., description="总步骤数")
    step_title: str = Field(..., description="当前步骤标题")
    step_status: str = Field(..., description="当前步骤状态")
    next_hint: Optional[str] = Field(None, description="下一步提示")
    block_reason: Optional[str] = Field(None, description="阻塞原因")


class TaskAttemptEventData(BaseModel):
    """TASK_ATTEMPT 事件的数据结构。"""

    action_id: str = Field(..., description="动作 ID")
    step_id: int = Field(..., description="步骤 ID")
    tool_name: str = Field(..., description="工具名称")
    attempt: int = Field(..., description="当前尝试次数")
    max_attempts: int = Field(..., description="最大尝试次数")
    status: Literal["in_progress", "retrying", "success", "failed"] = Field(
        ..., description="尝试状态"
    )
    note: Optional[str] = Field(None, description="备注")
    error: Optional[str] = Field(None, description="错误信息")


# ---- Token 使用相关事件 ----


class TokenUsageEventData(BaseModel):
    """TOKEN_USAGE 事件的数据结构。"""

    input_tokens: int = Field(..., description="输入 token 数")
    output_tokens: int = Field(..., description="输出 token 数")
    model: str = Field(..., description="模型名称")
    cost_usd: Optional[float] = Field(None, description="成本（USD）")


class ModelTokenUsageDetail(BaseModel):
    """单个模型的 token 使用详情。"""

    model_id: str = Field(..., description="模型 ID")
    input_tokens: int = Field(..., description="输入 token 数")
    output_tokens: int = Field(..., description="输出 token 数")
    total_tokens: int = Field(..., description="总 token 数")
    cost_usd: float = Field(..., description="成本（USD）")
    cost_cny: float = Field(..., description="成本（CNY）")
    call_count: int = Field(..., description="调用次数")


class SessionTokenUsageEventData(BaseModel):
    """会话级别 TOKEN_USAGE 事件的数据结构。"""

    session_id: str = Field(..., description="会话 ID")
    input_tokens: int = Field(..., description="总输入 token 数")
    output_tokens: int = Field(..., description="总输出 token 数")
    total_tokens: int = Field(..., description="总 token 数")
    estimated_cost_usd: float = Field(..., description="预估成本（USD）")
    estimated_cost_cny: float = Field(..., description="预估成本（CNY）")
    model_breakdown: dict[str, ModelTokenUsageDetail] = Field(
        default_factory=dict, description="各模型使用详情"
    )


# ---- 工具调用相关事件 ----


class ToolCallEventData(BaseModel):
    """TOOL_CALL 事件的数据结构。"""

    id: str = Field(..., description="工具调用 ID")
    name: str = Field(..., description="工具名称")
    arguments: dict[str, Any] = Field(default_factory=dict, description="参数")


class ToolResultEventData(BaseModel):
    """TOOL_RESULT 事件的数据结构。"""

    id: str = Field(..., description="工具调用 ID")
    name: str = Field(..., description="工具名称")
    status: Literal["success", "error"] = Field(..., description="执行状态")
    message: str = Field(..., description="结果消息")
    data: Optional[dict[str, Any]] = Field(None, description="结果数据")


# ---- 其他事件 ----


class TextEventData(BaseModel):
    """TEXT 事件的数据结构。"""

    content: str = Field(..., description="文本内容")


class ErrorEventData(BaseModel):
    """ERROR 事件的数据结构。"""

    message: str = Field(..., description="错误消息")
    code: Optional[str] = Field(None, description="错误代码")


class DoneEventData(BaseModel):
    """DONE 事件的数据结构。"""

    reason: Literal["completed", "stopped", "error"] = Field(
        "completed", description="结束原因"
    )


class WorkspaceUpdateEventData(BaseModel):
    """WORKSPACE_UPDATE 事件的数据结构。"""

    action: Literal["add", "remove", "update"] = Field(..., description="操作类型")
    file_id: Optional[str] = Field(None, description="文件 ID")
    folder_id: Optional[str] = Field(None, description="文件夹 ID")


class SessionTitleEventData(BaseModel):
    """SESSION_TITLE 事件的数据结构。"""

    session_id: str = Field(..., description="会话 ID")
    title: str = Field(..., description="生成的标题")


class CodeExecutionEventData(BaseModel):
    """CODE_EXECUTION 事件的数据结构。"""

    id: str = Field(..., description="执行记录 ID")
    code: str = Field(..., description="执行的代码")
    output: str = Field(..., description="输出结果")
    status: Literal["success", "error"] = Field(..., description="执行状态")
    language: str = Field(..., description="编程语言")
    created_at: str = Field(..., description="创建时间")


class SessionEventData(BaseModel):
    """SESSION 事件的数据结构。"""

    session_id: str = Field(..., description="会话 ID")


class StoppedEventData(BaseModel):
    """STOPPED 事件的数据结构。"""

    message: str = Field("已停止", description="停止消息")


class PongEventData(BaseModel):
    """PONG 事件的数据结构。"""

    timestamp: Optional[int] = Field(None, description="时间戳")
