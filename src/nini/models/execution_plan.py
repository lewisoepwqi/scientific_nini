"""执行计划数据模型。

用于 PlannerAgent 生成的结构化分析计划。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class PlanStatus(str, Enum):
    """计划状态。"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    REQUIRES_REVISION = "requires_revision"


class PlanAction(BaseModel):
    """计划中的单个动作。"""

    action_type: str = Field(description="动作类型，如 statistical_analysis、visualization 等")
    skill: str = Field(description="要调用的技能名称")
    parameters: dict[str, Any] = Field(default_factory=dict, description="技能参数")
    description: str = Field(default="", description="动作描述")
    depends_on: list[str] = Field(default_factory=list, description="依赖的动作 ID")


class PlanPhase(BaseModel):
    """计划中的一个阶段。"""

    phase_type: str = Field(
        description="阶段类型，如 data_check、statistical_test、visualization 等"
    )
    description: str = Field(description="阶段描述")
    actions: list[PlanAction] = Field(default_factory=list, description="该阶段的动作列表")
    status: PlanStatus = Field(default=PlanStatus.PENDING, description="阶段状态")
    order: int = Field(default=0, description="执行顺序")


class ExecutionPlan(BaseModel):
    """分析执行计划。

    由 PlannerAgent 生成，包含完整的分析路径。
    """

    # 基本信息
    user_intent: str = Field(min_length=1, description="用户意图分析")
    phases: list[PlanPhase] = Field(min_length=1, description="分析阶段列表")

    # 状态跟踪
    status: PlanStatus = Field(default=PlanStatus.PENDING, description="计划状态")
    current_phase_index: int = Field(default=0, description="当前执行到的阶段索引")

    # 元数据
    plan_id: str = Field(
        default_factory=lambda: f"plan_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
        description="计划唯一标识",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="创建时间"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="更新时间"
    )

    # 验证结果
    validation_errors: list[str] = Field(default_factory=list, description="验证错误列表")
    suggestions: list[str] = Field(default_factory=list, description="改进建议")

    def model_post_init(self, __context: Any) -> None:
        """初始化后验证。"""
        super().model_post_init(__context)
        # 更新阶段顺序
        for idx, phase in enumerate(self.phases):
            phase.order = idx

    def get_current_phase(self) -> PlanPhase | None:
        """获取当前执行阶段。"""
        if 0 <= self.current_phase_index < len(self.phases):
            return self.phases[self.current_phase_index]
        return None

    def advance_to_next_phase(self) -> bool:
        """推进到下一阶段。返回是否成功。"""
        if self.current_phase_index < len(self.phases) - 1:
            self.current_phase_index += 1
            self.updated_at = datetime.now(timezone.utc)
            return True
        return False

    def mark_completed(self) -> None:
        """标记计划为完成。"""
        self.status = PlanStatus.COMPLETED
        self.updated_at = datetime.now(timezone.utc)

    def mark_failed(self, error: str) -> None:
        """标记计划为失败。"""
        self.status = PlanStatus.FAILED
        self.validation_errors.append(error)
        self.updated_at = datetime.now(timezone.utc)

    def add_suggestion(self, suggestion: str) -> None:
        """添加改进建议。"""
        if suggestion not in self.suggestions:
            self.suggestions.append(suggestion)
            self.updated_at = datetime.now(timezone.utc)


# 预定义的阶段类型
class PhaseType(str, Enum):
    """标准阶段类型。"""

    DATA_LOADING = "data_loading"
    DATA_CHECK = "data_check"
    ASSUMPTION_TEST = "assumption_test"
    STATISTICAL_TEST = "statistical_test"
    EFFECT_SIZE = "effect_size"
    VISUALIZATION = "visualization"
    REPORT = "report"
    POST_HOC = "post_hoc"


# 预定义的动作类型
class ActionType(str, Enum):
    """标准动作类型。"""

    LOAD_DATA = "load_data"
    SUMMARY = "summary"
    NORMALITY_TEST = "normality_test"
    VARIANCE_TEST = "variance_test"
    STATISTICAL_ANALYSIS = "statistical_analysis"
    EFFECT_SIZE_CALCULATION = "effect_size_calculation"
    CREATE_CHART = "create_chart"
    GENERATE_REPORT = "generate_report"
    POST_HOC_TEST = "post_hoc_test"
