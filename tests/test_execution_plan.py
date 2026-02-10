"""测试 ExecutionPlan 数据模型。

TDD 方式：先写测试，再写实现。
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError


class TestExecutionPlan:
    """测试 ExecutionPlan 数据模型。"""

    def test_execution_plan_basic_structure(self):
        """测试 ExecutionPlan 基本结构。"""
        # 导入将在实现完成后正常工作
        from nini.models.execution_plan import ExecutionPlan, PlanPhase, PlanAction

        # 创建基本计划
        plan = ExecutionPlan(
            user_intent="分析两组数据的差异",
            phases=[
                PlanPhase(
                    phase_type="data_check",
                    description="检查数据质量",
                    actions=[
                        PlanAction(
                            action_type="check_missing",
                            skill="data_summary",
                            parameters={"dataset_name": "test_data"},
                        )
                    ],
                )
            ],
        )

        assert plan.user_intent == "分析两组数据的差异"
        assert len(plan.phases) == 1
        assert plan.phases[0].phase_type == "data_check"

    def test_execution_plan_validation(self):
        """测试 ExecutionPlan 验证规则。"""
        from nini.models.execution_plan import ExecutionPlan, PlanPhase

        # 测试空 phases 列表应该失败
        with pytest.raises(ValidationError):
            ExecutionPlan(
                user_intent="测试意图",
                phases=[],
            )

        # 测试缺少 user_intent 应该失败
        with pytest.raises(ValidationError):
            ExecutionPlan(
                user_intent="",
                phases=[
                    PlanPhase(
                        phase_type="data_check",
                        description="检查",
                        actions=[],
                    )
                ],
            )

    def test_execution_plan_serialization(self):
        """测试 ExecutionPlan 序列化与反序列化。"""
        from nini.models.execution_plan import ExecutionPlan, PlanPhase, PlanAction

        plan = ExecutionPlan(
            user_intent="比较两组均值",
            phases=[
                PlanPhase(
                    phase_type="statistical_test",
                    description="执行 t 检验",
                    actions=[
                        PlanAction(
                            action_type="statistical_analysis",
                            skill="t_test",
                            parameters={
                                "dataset_name": "data",
                                "value_column": "value",
                                "group_column": "group",
                            },
                        )
                    ],
                )
            ],
        )

        # 测试 model_dump
        plan_dict = plan.model_dump()
        assert plan_dict["user_intent"] == "比较两组均值"
        assert len(plan_dict["phases"]) == 1

        # 测试 model_dump_json
        plan_json = plan.model_dump_json()
        assert isinstance(plan_json, str)

        # 测试反序列化
        restored = ExecutionPlan.model_validate_json(plan_json)
        assert restored.user_intent == plan.user_intent
        assert len(restored.phases) == len(plan.phases)

    def test_execution_plan_status_tracking(self):
        """测试执行计划状态跟踪。"""
        from nini.models.execution_plan import ExecutionPlan, PlanStatus, PlanPhase

        plan = ExecutionPlan(
            user_intent="测试",
            phases=[
                PlanPhase(
                    phase_type="data_check",
                    description="检查",
                    actions=[],
                )
            ],
        )

        # 初始状态
        assert plan.status == PlanStatus.PENDING

        # 更新状态
        plan.status = PlanStatus.IN_PROGRESS
        assert plan.status == PlanStatus.IN_PROGRESS

        plan.status = PlanStatus.COMPLETED
        assert plan.status == PlanStatus.COMPLETED

        plan.status = PlanStatus.FAILED
        assert plan.status == PlanStatus.FAILED

    def test_execution_plan_metadata(self):
        """测试元数据记录。"""
        from nini.models.execution_plan import ExecutionPlan, PlanPhase

        created_at = datetime.now(timezone.utc)

        plan = ExecutionPlan(
            user_intent="测试",
            phases=[
                PlanPhase(
                    phase_type="data_check",
                    description="检查",
                    actions=[],
                )
            ],
            created_at=created_at,
        )

        assert plan.created_at == created_at
        assert isinstance(plan.updated_at, datetime)

    def test_plan_phase_actions_validation(self):
        """测试阶段和动作验证。"""
        from nini.models.execution_plan import PlanPhase, PlanAction

        # 测试有效动作
        action = PlanAction(
            action_type="statistical_analysis",
            skill="t_test",
            parameters={"dataset": "data"},
        )
        assert action.action_type == "statistical_analysis"

        # 测试空 actions 的 phase
        phase = PlanPhase(
            phase_type="data_check",
            description="检查数据",
            actions=[],
        )
        assert len(phase.actions) == 0

    def test_execution_plan_from_llm_output(self):
        """测试从 LLM 输出构建执行计划。"""
        from nini.models.execution_plan import ExecutionPlan

        # 模拟 LLM 输出的 JSON
        llm_output = {
            "user_intent": "分析两组差异",
            "phases": [
                {
                    "phase_type": "data_check",
                    "description": "检查数据质量",
                    "actions": [
                        {
                            "action_type": "summary",
                            "skill": "data_summary",
                            "parameters": {"dataset_name": "data"},
                        }
                    ],
                }
            ],
        }

        plan = ExecutionPlan.model_validate(llm_output)
        assert plan.user_intent == "分析两组差异"
        assert len(plan.phases) == 1


class TestPlannerAgent:
    """测试 PlannerAgent 类。"""

    @pytest.mark.asyncio
    async def test_planner_creates_valid_plan(self):
        """测试规划 Agent 生成有效计划。"""
        from nini.agent.planner import PlannerAgent
        from nini.agent.session import Session

        session = Session()
        planner = PlannerAgent()

        user_message = "帮我分析对照组和处理组的血压数据有没有显著差异"

        plan = await planner.create_plan(session, user_message)

        assert plan is not None
        assert plan.user_intent != ""
        assert len(plan.phases) > 0

    @pytest.mark.asyncio
    async def test_planner_handles_missing_data(self):
        """测试规划 Agent 处理缺失数据的情况。"""
        from nini.agent.planner import PlannerAgent
        from nini.agent.session import Session

        session = Session()
        planner = PlannerAgent()

        # 没有数据集的会话
        user_message = "分析数据差异"

        plan = await planner.create_plan(session, user_message)

        # 计划应该包含数据加载阶段
        assert any(p.phase_type == "data_loading" for p in plan.phases)

    @pytest.mark.asyncio
    async def test_planner_validates_existing_plan(self):
        """测试规划 Agent 验证现有计划。"""
        from nini.agent.planner import PlannerAgent
        from nini.agent.session import Session
        from nini.models.execution_plan import ExecutionPlan, PlanPhase

        session = Session()
        planner = PlannerAgent()

        # 创建一个可能需要修正的计划
        plan = ExecutionPlan(
            user_intent="测试",
            phases=[
                PlanPhase(
                    phase_type="invalid_phase",
                    description="无效阶段",
                    actions=[],
                )
            ],
        )

        validation_result = await planner.validate_plan(session, plan)

        assert "is_valid" in validation_result
        assert "suggestions" in validation_result
