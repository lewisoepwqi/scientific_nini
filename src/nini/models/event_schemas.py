"""WebSocket 事件数据结构定义。

为每种 WebSocket 事件类型定义严格的 Pydantic 模型，
确保前后端数据契约一致。
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from nini.models.risk import OutputLevel

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
    recipe_id: Optional[str] = Field(None, description="绑定的 Recipe 标识")
    task_id: Optional[str] = Field(None, description="deep task 标识")
    task_kind: Optional[str] = Field(None, description="任务类型")
    retry_count: Optional[int] = Field(None, description="当前重试次数")


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
    task_id: Optional[str] = Field(None, description="deep task 标识")
    attempt_id: Optional[str] = Field(None, description="尝试标识")
    note: Optional[str] = Field(None, description="备注")
    error: Optional[str] = Field(None, description="错误信息")


class RunContextDatasetSummary(BaseModel):
    """RUN_CONTEXT 事件中的数据集摘要。"""

    name: str = Field(..., description="数据集名称")
    rows: Optional[int] = Field(None, description="行数")
    columns: Optional[int] = Field(None, description="列数")


class RunContextArtifactSummary(BaseModel):
    """RUN_CONTEXT 事件中的产物摘要。"""

    name: str = Field(..., description="产物名称")
    artifact_type: Optional[str] = Field(None, description="产物类型")


class RunContextEventData(BaseModel):
    """RUN_CONTEXT 事件的数据结构。"""

    turn_id: str = Field(..., description="当前轮标识")
    datasets: list[RunContextDatasetSummary] = Field(default_factory=list, description="数据集摘要")
    artifacts: list[RunContextArtifactSummary] = Field(default_factory=list, description="产物摘要")
    tool_hints: list[str] = Field(default_factory=list, description="推荐工具提示")
    constraints: list[str] = Field(default_factory=list, description="关键约束")
    task_id: Optional[str] = Field(None, description="deep task 标识")
    recipe_id: Optional[str] = Field(None, description="Recipe 标识")


class CompletionCheckItemEventData(BaseModel):
    """COMPLETION_CHECK 单项结果。"""

    key: str = Field(..., description="检查项标识")
    label: str = Field(..., description="检查项标题")
    passed: bool = Field(..., description="是否通过")
    detail: str = Field("", description="检查说明")


class CompletionCheckEventData(BaseModel):
    """COMPLETION_CHECK 事件的数据结构。"""

    turn_id: str = Field(..., description="当前轮标识")
    passed: bool = Field(..., description="整体是否通过")
    attempt: int = Field(..., description="当前校验轮次")
    items: list[CompletionCheckItemEventData] = Field(
        default_factory=list, description="检查项列表"
    )
    missing_actions: list[str] = Field(default_factory=list, description="缺失动作")
    task_id: Optional[str] = Field(None, description="deep task 标识")


class BlockedEventData(BaseModel):
    """BLOCKED 事件的数据结构。"""

    turn_id: str = Field(..., description="当前轮标识")
    reason_code: str = Field(..., description="阻塞原因代码")
    message: str = Field(..., description="阻塞说明")
    recoverable: bool = Field(True, description="是否可恢复")
    task_id: Optional[str] = Field(None, description="deep task 标识")
    attempt_id: Optional[str] = Field(None, description="尝试标识")
    suggested_action: Optional[str] = Field(None, description="建议动作")


class BudgetWarningEventData(BaseModel):
    """BUDGET_WARNING 事件的数据结构。"""

    task_id: str = Field(..., description="deep task 标识")
    metric: Literal["tokens", "cost_usd", "tool_calls"] = Field(..., description="预算指标")
    threshold: float = Field(..., description="预算阈值")
    current_value: float = Field(..., description="当前值")
    warning_level: Literal["warning", "critical"] = Field(..., description="告警级别")
    message: str = Field(..., description="告警摘要")
    recipe_id: Optional[str] = Field(None, description="Recipe 标识")


# ---- Token 使用相关事件 ----


class TokenUsageEventData(BaseModel):
    """TOKEN_USAGE 事件的数据结构。"""

    input_tokens: int = Field(..., description="输入 token 数")
    output_tokens: int = Field(..., description="输出 token 数")
    model: str = Field(..., description="模型名称")
    cost_usd: Optional[float] = Field(None, description="成本（USD）")


class ModelFallbackEventData(BaseModel):
    """MODEL_FALLBACK 事件的数据结构。"""

    purpose: str = Field(default="chat", description="路由用途")
    attempt: int = Field(default=1, description="成功模型所在尝试序号（1-based）")
    from_provider_id: Optional[str] = Field(None, description="降级来源提供商 ID")
    from_provider_name: Optional[str] = Field(None, description="降级来源提供商名称")
    from_model: Optional[str] = Field(None, description="降级来源模型")
    to_provider_id: str = Field(..., description="实际生效提供商 ID")
    to_provider_name: str = Field(..., description="实际生效提供商名称")
    to_model: str = Field(..., description="实际生效模型")
    reason: Optional[str] = Field(None, description="触发降级的原因摘要")
    fallback_chain: list[dict[str, Any]] = Field(
        default_factory=list,
        description="按尝试顺序记录的降级轨迹",
    )


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
    output_level: Optional[OutputLevel] = Field(
        None, description="分片级输出等级（预留扩展，初期不启用）"
    )


class ErrorEventData(BaseModel):
    """ERROR 事件的数据结构。"""

    message: str = Field(..., description="错误消息")
    code: Optional[str] = Field(None, description="错误代码")


class DoneEventData(BaseModel):
    """DONE 事件的数据结构。"""

    reason: Literal["completed", "stopped", "error"] = Field("completed", description="结束原因")
    output_level: Optional[OutputLevel] = Field(None, description="本轮回复的综合输出等级")


class WorkspaceUpdateEventData(BaseModel):
    """WORKSPACE_UPDATE 事件的数据结构。"""

    action: Literal["add", "remove", "update"] = Field(..., description="操作类型")
    file_id: Optional[str] = Field(None, description="文件 ID")
    folder_id: Optional[str] = Field(None, description="文件夹 ID")
    recipe_id: Optional[str] = Field(None, description="绑定的 Recipe 标识")
    task_id: Optional[str] = Field(None, description="deep task 标识")
    attempt_id: Optional[str] = Field(None, description="尝试标识")
    initialized: Optional[bool] = Field(None, description="是否完成工作区初始化")


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
    task_kind: Optional[str] = Field(None, description="任务类型")
    recipe_id: Optional[str] = Field(None, description="绑定的 Recipe 标识")
    deep_task_state: Optional[dict[str, Any]] = Field(None, description="deep task 状态")


class StoppedEventData(BaseModel):
    """STOPPED 事件的数据结构。"""

    message: str = Field("已停止", description="停止消息")


class PongEventData(BaseModel):
    """PONG 事件的数据结构。"""

    timestamp: Optional[int] = Field(None, description="时间戳")


class IterationStartEventData(BaseModel):
    """ITERATION_START 事件的数据结构。"""

    iteration: int = Field(..., description="迭代次数")


class RetrievalEventData(BaseModel):
    """RETRIEVAL 事件的数据结构。"""

    query: str = Field("", description="检索查询")
    results: list[dict[str, Any]] = Field(default_factory=list, description="检索结果列表")


class ReasoningEventData(BaseModel):
    """REASONING 事件的数据结构（流式/简单格式）。"""

    content: str = Field(..., description="推理内容")
    reasoning_id: Optional[str] = Field(None, description="推理链 ID")
    reasoning_live: bool = Field(False, description="是否实时流式推理")


class ReasoningDataEventData(BaseModel):
    """REASONING 事件的数据结构（完整决策数据格式）。

    用于展示 Agent 的决策过程，提高可解释性。
    """

    step: str = Field(..., description="决策步骤，如 method_selection, parameter_selection")
    thought: str = Field(..., description="决策思路")
    rationale: str = Field(default="", description="决策理由")
    alternatives: list[str] = Field(default_factory=list, description="考虑过的替代方案")
    confidence: float = Field(default=1.0, description="决策置信度 (0-1)")
    context: dict[str, Any] = Field(default_factory=dict, description="额外上下文信息")
    # 可选字段
    reasoning_type: Optional[str] = Field(
        None, description="analysis | decision | planning | reflection"
    )
    reasoning_subtype: Optional[str] = Field(None, description="更细粒度的类型")
    confidence_score: Optional[float] = Field(None, description="0.0 - 1.0 的置信度分数")
    key_decisions: list[str] = Field(default_factory=list, description="关键决策点列表")
    parent_id: Optional[str] = Field(None, description="父推理节点 ID（用于链式关联）")
    references: list[dict[str, Any]] = Field(default_factory=list, description="引用数据来源")
    timestamp: Optional[str] = Field(None, description="ISO 格式时间戳")
    tags: list[str] = Field(
        default_factory=list, description="标签，如 [assumption_check, fallback]"
    )


# 问题类型枚举：与 deer-flow clarification_type 对齐
QuestionType = Literal[
    "missing_info",  # 缺少必要信息（文件路径、参数等）
    "ambiguous_requirement",  # 需求存在多种合理解释
    "approach_choice",  # 存在多种有效实现方案需用户选择
    "risk_confirmation",  # 即将执行破坏性/不可逆操作
    "suggestion",  # 有推荐方案但需用户确认
]


class AskUserQuestionEventData(BaseModel):
    """ASK_USER_QUESTION 事件的数据结构。"""

    questions: list[dict[str, Any]] = Field(
        ..., description="问题列表（每项可含 question_type 和 context 可选字段）"
    )


class ArtifactEventData(BaseModel):
    """ARTIFACT 事件的数据结构。"""

    artifact_id: str = Field(..., description="产物 ID")
    artifact_type: str = Field(..., description="产物类型")
    name: str = Field(..., description="产物名称")
    url: Optional[str] = Field(None, description="产物访问 URL")
    mime_type: Optional[str] = Field(None, description="MIME 类型")


class ChartEventData(BaseModel):
    """CHART 事件的数据结构。"""

    chart_id: str = Field(..., description="图表 ID")
    name: str = Field(..., description="图表名称")
    url: str = Field(..., description="图表访问 URL")
    chart_type: Optional[str] = Field(None, description="图表类型")


class DataEventData(BaseModel):
    """DATA 事件的数据结构。"""

    data_id: str = Field(..., description="数据 ID")
    name: str = Field(..., description="数据名称")
    url: str = Field(..., description="数据访问 URL")
    row_count: Optional[int] = Field(None, description="行数")
    column_count: Optional[int] = Field(None, description="列数")


class ImageEventData(BaseModel):
    """IMAGE 事件的数据结构。"""

    image_id: str = Field(..., description="图片 ID")
    name: str = Field(..., description="图片名称")
    url: str = Field(..., description="图片访问 URL")
    mime_type: Optional[str] = Field(None, description="MIME 类型")


class SkillStepEventData(BaseModel):
    """SKILL_STEP 事件的数据结构。

    用于 ContractRunner 步骤执行的 observability 事件，
    每步骤的 start / complete / failed / skipped / review_required 均发射此类事件。
    """

    skill_name: str = Field(..., description="Skill 名称")
    skill_version: str = Field("1", description="Skill 契约版本")
    step_id: str = Field(..., description="步骤 ID")
    step_name: str = Field(..., description="步骤显示名称")
    status: Literal["started", "completed", "failed", "skipped", "review_required"] = Field(
        ..., description="步骤状态"
    )
    layer: Optional[int] = Field(None, description="步骤所在的 DAG 层级（从 0 开始）")
    trust_level: Optional[str] = Field(None, description="步骤信任等级")
    output_level: Optional[str] = Field(None, description="步骤输出等级")
    input_summary: str = Field("", description="输入摘要")
    output_summary: str = Field("", description="输出摘要")
    error_message: Optional[str] = Field(None, description="错误信息（失败时）")
    duration_ms: Optional[int] = Field(None, description="步骤耗时（毫秒）")


class SkillSummaryEventData(BaseModel):
    """SKILL_SUMMARY 事件的数据结构。"""

    skill_name: str = Field(..., description="Skill 名称")
    total_steps: int = Field(..., description="总步骤数")
    completed_steps: int = Field(..., description="完成步骤数")
    skipped_steps: int = Field(..., description="跳过步骤数")
    failed_steps: int = Field(..., description="失败步骤数")
    total_duration_ms: int = Field(..., description="Skill 总耗时（毫秒）")
    overall_status: Literal["completed", "partial", "failed"] = Field(
        ..., description="Skill 整体执行状态"
    )
    trust_ceiling: Optional[str] = Field(None, description="Skill 契约信任上限")
    output_level: Optional[str] = Field(None, description="Skill 综合输出等级")


class ContextCompressedEventData(BaseModel):
    """CONTEXT_COMPRESSED 事件的数据结构。"""

    original_tokens: int = Field(..., description="原始 token 数")
    compressed_tokens: int = Field(..., description="压缩后 token 数")
    compression_ratio: float = Field(..., description="压缩比例")
    message: str = Field("", description="压缩消息")
    # 可选字段，用于详细压缩信息
    archived_count: Optional[int] = Field(None, description="归档消息数")
    remaining_count: Optional[int] = Field(None, description="剩余消息数")
    previous_tokens: Optional[int] = Field(None, description="压缩前 token 数（兼容字段）")
    trigger: Optional[str] = Field(None, description="触发原因")
