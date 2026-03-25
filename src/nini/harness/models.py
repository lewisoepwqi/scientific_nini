"""Harness 运行与 trace 数据模型。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    """返回 UTC ISO 时间。"""
    return datetime.now(timezone.utc).isoformat()


class HarnessDatasetSummary(BaseModel):
    """运行时数据集摘要。"""

    name: str
    rows: int | None = None
    columns: int | None = None


class HarnessArtifactSummary(BaseModel):
    """运行时产物摘要。"""

    name: str
    artifact_type: str | None = None


class HarnessRunContext(BaseModel):
    """一次运行的上下文摘要。"""

    turn_id: str
    datasets: list[HarnessDatasetSummary] = Field(default_factory=list)
    artifacts: list[HarnessArtifactSummary] = Field(default_factory=list)
    tool_hints: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    task_id: str | None = None
    recipe_id: str | None = None

    def to_runtime_block(self) -> str:
        """转换为 runtime context 摘要块。"""
        lines: list[str] = ["[Harness 运行摘要]"]
        if self.datasets:
            dataset_desc = "；".join(
                f"{item.name}（{item.rows or '?'} 行 / {item.columns or '?'} 列）"
                for item in self.datasets
            )
            lines.append(f"- 当前数据集：{dataset_desc}")
        if self.artifacts:
            artifact_desc = "；".join(
                f"{item.name}（{item.artifact_type or 'unknown'}）" for item in self.artifacts
            )
            lines.append(f"- 已有产物：{artifact_desc}")
        if self.tool_hints:
            lines.append(f"- 推荐工具：{', '.join(self.tool_hints)}")
        if self.constraints:
            lines.append(f"- 关键约束：{'；'.join(self.constraints)}")
        return "\n".join(lines)


class CompletionCheckItem(BaseModel):
    """完成前校验单项。"""

    key: str
    label: str
    passed: bool
    detail: str = ""


class CompletionCheckResult(BaseModel):
    """完成前校验结果。"""

    turn_id: str
    attempt: int
    passed: bool
    items: list[CompletionCheckItem] = Field(default_factory=list)
    missing_actions: list[str] = Field(default_factory=list)


class BlockedState(BaseModel):
    """阻塞状态。"""

    turn_id: str
    reason_code: str
    message: str
    recoverable: bool = True
    suggested_action: str | None = None
    task_id: str | None = None
    attempt_id: str | None = None


class HarnessBudgetWarning(BaseModel):
    """任务级预算告警。"""

    task_id: str
    metric: Literal["tokens", "cost_usd", "tool_calls"]
    threshold: float
    current_value: float
    warning_level: Literal["warning", "critical"]
    message: str
    recipe_id: str | None = None
    timestamp: str = Field(default_factory=utc_now_iso)


class HarnessTaskMetrics(BaseModel):
    """deep task 关键指标摘要。"""

    task_id: str | None = None
    recipe_id: str | None = None
    final_status: str = "completed"
    total_duration_ms: int = 0
    step_durations_ms: dict[str, int] = Field(default_factory=dict)
    recovery_count: int = 0
    tool_call_count: int = 0
    failure_types: list[str] = Field(default_factory=list)
    budget_warnings: list[HarnessBudgetWarning] = Field(default_factory=list)


class HarnessTraceEvent(BaseModel):
    """写入 trace 的事件快照。"""

    type: str
    turn_id: str | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None
    data: dict[str, Any] | str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=utc_now_iso)


class HarnessTraceRecord(BaseModel):
    """一次 harness 运行完整 trace。"""

    run_id: str
    session_id: str
    turn_id: str
    user_message: str
    run_context: HarnessRunContext
    task_id: str | None = None
    recipe_id: str | None = None
    stage_history: list[dict[str, Any]] = Field(default_factory=list)
    events: list[HarnessTraceEvent] = Field(default_factory=list)
    completion_checks: list[CompletionCheckResult] = Field(default_factory=list)
    blocked: BlockedState | None = None
    failure_tags: list[str] = Field(default_factory=list)
    budget_warnings: list[HarnessBudgetWarning] = Field(default_factory=list)
    task_metrics: HarnessTaskMetrics | None = None
    status: Literal["completed", "blocked", "stopped", "error"] = "completed"
    summary: dict[str, Any] = Field(default_factory=dict)
    started_at: str = Field(default_factory=utc_now_iso)
    finished_at: str | None = None


class HarnessRunSummary(BaseModel):
    """SQLite 中的 trace 摘要。"""

    run_id: str
    session_id: str
    turn_id: str
    task_id: str | None = None
    recipe_id: str | None = None
    status: str
    failure_tags: list[str] = Field(default_factory=list)
    recovery_count: int = 0
    budget_warning_count: int = 0
    duration_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    trace_path: str
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
