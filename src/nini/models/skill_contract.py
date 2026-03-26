"""Skill 执行契约数据模型。

定义 SkillContract、SkillStep 及相关 Pydantic 模型，
为运行时提供结构化的步骤 DAG、trust_ceiling 约束和 review_gate 支持。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from nini.models.risk import TrustLevel

# 信任等级排序（数值越大等级越高）
_TRUST_ORDER: dict[TrustLevel, int] = {
    TrustLevel.T1: 1,
    TrustLevel.T2: 2,
    TrustLevel.T3: 3,
}


class SkillStep(BaseModel):
    """Skill 契约中的单个执行步骤。"""

    id: str = Field(..., description="步骤标识，如 'load_data'")
    name: str = Field(..., description="步骤显示名称")
    description: str = Field(..., description="步骤说明")
    tool_hint: str | None = Field(None, description="推荐使用的工具")
    depends_on: list[str] = Field(default_factory=list, description="前置步骤 ID 列表")
    trust_level: TrustLevel = Field(TrustLevel.T1, description="步骤信任等级")
    review_gate: bool = Field(False, description="是否需要人工复核")
    retry_policy: Literal["retry", "skip", "abort"] = Field(
        "skip", description="失败策略：retry / skip / abort"
    )


class SkillContract(BaseModel):
    """Skill 执行契约根模型。

    描述完整工作流的步骤 DAG、信任上限和输入输出 schema。
    """

    version: str = Field("1", description="契约版本")
    trust_ceiling: TrustLevel = Field(TrustLevel.T1, description="整体信任上限")
    steps: list[SkillStep] = Field(..., description="步骤列表")
    input_schema: dict[str, Any] = Field(default_factory=dict, description="输入参数 schema")
    output_schema: dict[str, Any] = Field(default_factory=dict, description="输出参数 schema")
    evidence_required: bool = Field(False, description="是否要求证据溯源")

    @model_validator(mode="after")
    def _validate_depends_on_references(self) -> "SkillContract":
        """验证 depends_on 中的所有步骤 ID 都存在于 steps 列表中。"""
        known_ids = {step.id for step in self.steps}
        for step in self.steps:
            for dep_id in step.depends_on:
                if dep_id not in known_ids:
                    raise ValueError(
                        f"步骤 '{step.id}' 的 depends_on 引用了不存在的步骤 ID '{dep_id}'"
                    )
        return self

    @model_validator(mode="after")
    def _validate_no_circular_dependencies(self) -> "SkillContract":
        """检测步骤间是否存在循环依赖（使用 DFS 拓扑排序）。"""
        adj: dict[str, list[str]] = {step.id: list(step.depends_on) for step in self.steps}
        # 0=未访问 1=访问中 2=已完成
        state: dict[str, int] = {step.id: 0 for step in self.steps}

        def _dfs(node: str) -> None:
            if state[node] == 1:
                raise ValueError(f"步骤依赖中存在循环依赖，涉及步骤 '{node}'")
            if state[node] == 2:
                return
            state[node] = 1
            for dep in adj[node]:
                _dfs(dep)
            state[node] = 2

        for step in self.steps:
            if state[step.id] == 0:
                _dfs(step.id)
        return self

    @model_validator(mode="after")
    def _validate_trust_ceiling(self) -> "SkillContract":
        """验证所有步骤的 trust_level 不超过 trust_ceiling。"""
        ceiling_order = _TRUST_ORDER[self.trust_ceiling]
        for step in self.steps:
            if _TRUST_ORDER[step.trust_level] > ceiling_order:
                raise ValueError(
                    f"步骤 '{step.id}' 的 trust_level '{step.trust_level.value}' "
                    f"超过了 contract 的 trust_ceiling '{self.trust_ceiling.value}'"
                )
        return self


class StepExecutionRecord(BaseModel):
    """单个步骤的执行记录。"""

    step_id: str = Field(..., description="步骤 ID")
    status: Literal["completed", "failed", "skipped"] = Field(..., description="执行结果")
    duration_ms: int | None = Field(None, description="耗时（毫秒）")
    error_message: str | None = Field(None, description="失败时的错误信息")


class ContractResult(BaseModel):
    """契约执行结果汇总。"""

    status: Literal["completed", "partial", "failed"] = Field(..., description="整体执行状态")
    step_records: list[StepExecutionRecord] = Field(
        default_factory=list, description="每个步骤的执行记录"
    )
    total_ms: int | None = Field(None, description="总耗时（毫秒）")
    error_message: str | None = Field(None, description="整体失败时的错误信息")
