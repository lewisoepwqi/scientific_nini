"""WebSocket 事件构造器测试。

验证使用 Pydantic 模型构造的事件数据符合契约。
"""

from __future__ import annotations

import pytest

from nini.agent.event_builders import (
    build_agent_complete_event,
    build_agent_error_event,
    build_agent_start_event,
    build_analysis_plan_event,
    build_blocked_event,
    build_completion_check_event,
    build_done_event,
    build_error_event,
    build_model_fallback_event,
    build_plan_progress_event,
    build_plan_step_update_event,
    build_run_context_event,
    build_session_event,
    build_task_attempt_event,
    build_text_event,
    build_token_usage_event,
    build_tool_call_event,
    build_tool_result_event,
    build_workspace_update_event,
)
from nini.agent.events import EventType


class TestAnalysisPlanEventBuilder:
    """ANALYSIS_PLAN 事件构造器测试。"""

    def test_build_with_all_fields(self):
        """使用完整字段构造分析计划事件。"""
        steps = [
            {
                "id": 1,
                "title": "步骤1",
                "tool_hint": "t_test",
                "status": "completed",
                "action_id": "task_1",
                "raw_status": "completed",
                "depends_on": [],
                "executor": "subagent",
                "owner": "data_cleaner",
                "input_refs": ["dataset:raw.v1"],
                "output_refs": ["dataset:cleaned.v1"],
                "handoff_contract": {"required_columns": ["age"]},
                "tool_profile": "cleaning_execution",
                "failure_policy": "stop_pipeline",
                "acceptance_checks": ["缺失率已下降"],
            },
            {
                "id": 2,
                "title": "步骤2",
                "status": "blocked",
                "action_id": "task_2",
            },
        ]

        event = build_analysis_plan_event(steps, raw_text="分析计划", turn_id="turn_1", seq=1)

        assert event.type == EventType.ANALYSIS_PLAN
        assert event.data["raw_text"] == "分析计划"
        assert len(event.data["steps"]) == 2
        # 验证 action_id 被正确传递
        assert event.data["steps"][0]["action_id"] == "task_1"
        assert event.data["steps"][1]["action_id"] == "task_2"
        # 验证 raw_status 被正确传递
        assert event.data["steps"][0]["raw_status"] == "completed"
        assert event.data["steps"][0]["executor"] == "subagent"
        assert event.data["steps"][0]["handoff_contract"] == {"required_columns": ["age"]}
        assert event.data["steps"][1]["status"] == "blocked"
        # 验证 turn_id 和 seq
        assert event.turn_id == "turn_1"
        assert event.metadata["seq"] == 1

    def test_build_with_minimal_fields(self):
        """使用最少字段构造分析计划事件。"""
        steps = [{"id": 1, "title": "步骤1"}]

        event = build_analysis_plan_event(steps)

        assert event.type == EventType.ANALYSIS_PLAN
        step = event.data["steps"][0]
        # 验证默认值
        assert step["status"] == "pending"
        assert step["action_id"] is None
        assert step["raw_status"] is None
        assert step["depends_on"] == []
        assert step["input_refs"] == []
        assert step["acceptance_checks"] == []
        # 验证 turn_id 与 metadata 默认值
        assert event.turn_id is None
        assert event.metadata == {}


class TestPlanStepUpdateEventBuilder:
    """PLAN_STEP_UPDATE 事件构造器测试。"""

    def test_build_with_error(self):
        """构造包含错误的步骤更新事件。"""
        event = build_plan_step_update_event(
            step_id=1,
            status="failed",
            error="参数无效",
        )

        assert event.type == EventType.PLAN_STEP_UPDATE
        assert event.data["id"] == 1
        assert event.data["status"] == "failed"
        assert event.data["error"] == "参数无效"


class TestPlanProgressEventBuilder:
    """PLAN_PROGRESS 事件构造器测试。"""

    def test_build_progress(self):
        """构造计划进度事件。"""
        steps = [
            {"id": 1, "title": "步骤1", "status": "completed"},
            {
                "id": 2,
                "title": "步骤2",
                "status": "blocked",
                "executor": "subagent",
                "input_refs": ["dataset:cleaned.v1"],
                "failure_policy": "retryable",
            },
        ]

        event = build_plan_progress_event(
            steps=steps,
            current_step_index=2,
            total_steps=2,
            step_title="步骤2",
            step_status="blocked",
            next_hint="下一步操作",
            block_reason="等待用户补充字段映射",
        )

        assert event.type == EventType.PLAN_PROGRESS
        assert event.data["current_step_index"] == 2
        assert event.data["next_hint"] == "下一步操作"
        assert event.data["block_reason"] == "等待用户补充字段映射"
        assert event.data["steps"][1]["status"] == "blocked"
        assert event.data["steps"][1]["executor"] == "subagent"


class TestTaskAttemptEventBuilder:
    """TASK_ATTEMPT 事件构造器测试。"""

    def test_build_retrying(self):
        """构造重试中的任务尝试事件。"""
        event = build_task_attempt_event(
            action_id="task_1",
            step_id=1,
            tool_name="run_code",
            attempt=2,
            max_attempts=3,
            status="retrying",
            note="正在重试",
            error="上次失败的原因",
            turn_id="turn_1",
            seq=5,
        )

        assert event.type == EventType.TASK_ATTEMPT
        assert event.data["action_id"] == "task_1"
        assert event.data["attempt"] == 2
        assert event.data["status"] == "retrying"
        assert event.turn_id == "turn_1"
        assert event.metadata["seq"] == 5


class TestHarnessEventBuilders:
    """Harness 相关事件构造器测试。"""

    def test_build_run_context_event(self):
        event = build_run_context_event(
            turn_id="turn_ctx",
            datasets=[{"name": "demo.csv", "rows": 10, "columns": 3}],
            artifacts=[{"name": "report.md", "artifact_type": "report"}],
            tool_hints=["dataset_catalog"],
            constraints=["结束前检查失败工具"],
        )

        assert event.type == EventType.RUN_CONTEXT
        assert event.turn_id == "turn_ctx"
        assert event.data["datasets"][0]["name"] == "demo.csv"
        assert event.data["artifacts"][0]["artifact_type"] == "report"

    def test_build_completion_check_event(self):
        event = build_completion_check_event(
            turn_id="turn_check",
            passed=False,
            attempt=1,
            items=[{"key": "artifact_generated", "label": "承诺产物已生成", "passed": False}],
            missing_actions=["承诺产物已生成"],
        )

        assert event.type == EventType.COMPLETION_CHECK
        assert event.data["passed"] is False
        assert event.data["items"][0]["key"] == "artifact_generated"
        assert event.data["missing_actions"] == ["承诺产物已生成"]

    def test_build_blocked_event(self):
        event = build_blocked_event(
            turn_id="turn_blocked",
            reason_code="tool_loop",
            message="工具连续失败",
            suggested_action="调整参数后重试",
        )

        assert event.type == EventType.BLOCKED
        assert event.turn_id == "turn_blocked"
        assert event.data["reason_code"] == "tool_loop"


class TestAgentEventBuilders:
    """Agent 生命周期事件构造器测试。"""

    def test_build_agent_start_event(self):
        """构造 Agent 启动事件。"""
        event = build_agent_start_event(
            agent_id="agent-stat",
            agent_name="统计分析专家",
            task="执行正态性检验",
            attempt=2,
            retry_count=1,
            turn_id="turn_agent",
        )

        assert event.type == EventType.AGENT_START
        assert event.turn_id == "turn_agent"
        assert event.data["agent_id"] == "agent-stat"
        assert event.data["attempt"] == 2
        assert event.data["retry_count"] == 1

    def test_build_agent_complete_event(self):
        """构造 Agent 完成事件。"""
        event = build_agent_complete_event(
            agent_id="agent-stat",
            agent_name="统计分析专家",
            summary="分析完成",
            execution_time_ms=1280,
            attempt=2,
            retry_count=1,
            turn_id="turn_agent",
        )

        assert event.type == EventType.AGENT_COMPLETE
        assert event.data["summary"] == "分析完成"
        assert event.data["execution_time_ms"] == 1280
        assert event.data["attempt"] == 2
        assert event.data["retry_count"] == 1

    def test_build_agent_error_event(self):
        """构造 Agent 失败事件。"""
        event = build_agent_error_event(
            agent_id="agent-stat",
            agent_name="统计分析专家",
            error="执行超时",
            execution_time_ms=300000,
            attempt=3,
            retry_count=2,
            turn_id="turn_agent",
        )

        assert event.type == EventType.AGENT_ERROR
        assert event.data["error"] == "执行超时"
        assert event.data["execution_time_ms"] == 300000
        assert event.data["attempt"] == 3
        assert event.data["retry_count"] == 2


class TestTokenUsageEventBuilder:
    """TOKEN_USAGE 事件构造器测试。"""

    def test_build_with_cost(self):
        """构造包含成本的 token 使用事件。"""
        event = build_token_usage_event(
            input_tokens=1000,
            output_tokens=500,
            model="gpt-4o",
            cost_usd=0.015,
        )

        assert event.type == EventType.TOKEN_USAGE
        assert event.data["input_tokens"] == 1000
        assert event.data["output_tokens"] == 500
        assert event.data["cost_usd"] == 0.015

    def test_build_without_cost(self):
        """构造不包含成本的 token 使用事件（兜底价格）。"""
        event = build_token_usage_event(
            input_tokens=1000,
            output_tokens=500,
            model="unknown-model",
        )

        assert event.type == EventType.TOKEN_USAGE
        assert event.data["cost_usd"] is None


class TestModelFallbackEventBuilder:
    """MODEL_FALLBACK 事件构造器测试。"""

    def test_build_model_fallback(self):
        event = build_model_fallback_event(
            purpose="chat",
            attempt=2,
            from_provider_id="zhipu",
            from_provider_name="智谱 AI (GLM)",
            from_model="glm-5",
            to_provider_id="deepseek",
            to_provider_name="DeepSeek",
            to_model="deepseek-coder",
            reason="quota exceeded",
            fallback_chain=[
                {"attempt": 1, "provider_id": "zhipu", "status": "failed"},
                {"attempt": 2, "provider_id": "deepseek", "status": "success"},
            ],
            turn_id="turn_x",
        )

        assert event.type == EventType.MODEL_FALLBACK
        assert event.turn_id == "turn_x"
        assert event.data["to_model"] == "deepseek-coder"
        assert event.data["from_model"] == "glm-5"
        assert len(event.data["fallback_chain"]) == 2


class TestToolEventBuilders:
    """工具事件构造器测试。"""

    def test_build_tool_call(self):
        """构造工具调用事件。"""
        event = build_tool_call_event(
            tool_call_id="call_123",
            name="run_code",
            arguments={"code": "print(1)"},
        )

        assert event.type == EventType.TOOL_CALL
        assert event.tool_call_id == "call_123"
        assert event.tool_name == "run_code"
        assert event.data["arguments"]["code"] == "print(1)"

    def test_build_tool_result_success(self):
        """构造工具结果成功事件。"""
        event = build_tool_result_event(
            tool_call_id="call_123",
            name="run_code",
            status="success",
            message="执行成功",
            data={"output": "1"},
        )

        assert event.type == EventType.TOOL_RESULT
        assert event.data["status"] == "success"
        assert event.data["data"]["output"] == "1"

    def test_build_tool_result_error(self):
        """构造工具结果失败事件。"""
        event = build_tool_result_event(
            tool_call_id="call_123",
            name="run_code",
            status="error",
            message="执行失败",
        )

        assert event.type == EventType.TOOL_RESULT
        assert event.data["status"] == "error"
        assert event.data["data"] is None


class TestCommonEventBuilders:
    """通用事件构造器测试。"""

    def test_build_text(self):
        """构造文本事件。"""
        event = build_text_event(content="你好")

        assert event.type == EventType.TEXT
        assert event.data["content"] == "你好"

    def test_build_error(self):
        """构造错误事件。"""
        event = build_error_event(message="出错了", code="ERR_001")

        assert event.type == EventType.ERROR
        assert event.data["message"] == "出错了"
        assert event.data["code"] == "ERR_001"

    def test_build_done(self):
        """构造完成事件。"""
        event = build_done_event(reason="completed")

        assert event.type == EventType.DONE
        assert event.data["reason"] == "completed"

    def test_build_session(self):
        """构造会话事件。"""
        event = build_session_event(session_id="abc123")

        assert event.type == EventType.SESSION
        assert event.data["session_id"] == "abc123"

    def test_build_workspace_update(self):
        """构造工作区更新事件。"""
        event = build_workspace_update_event(
            action="add",
            file_id="file_1",
            task_id="task_demo",
            attempt_id="task_demo:workflow:1",
        )

        assert event.type == EventType.WORKSPACE_UPDATE
        assert event.data["action"] == "add"
        assert event.data["file_id"] == "file_1"
        assert event.data["task_id"] == "task_demo"
        assert event.data["attempt_id"] == "task_demo:workflow:1"

    def test_build_budget_warning(self):
        """构造预算告警事件。"""
        from nini.agent.event_builders import build_budget_warning_event

        event = build_budget_warning_event(
            task_id="task_demo",
            metric="tokens",
            threshold=1000,
            current_value=1200,
            warning_level="warning",
            message="预算超阈值",
            recipe_id="literature_review",
        )

        assert event.type == EventType.BUDGET_WARNING
        assert event.data["task_id"] == "task_demo"
        assert event.data["metric"] == "tokens"
        assert event.data["recipe_id"] == "literature_review"


class TestEventValidation:
    """事件数据验证测试。"""

    def test_action_id_field_always_present(self):
        """验证 action_id 字段始终存在于序列化数据中。"""
        steps = [{"id": 1, "title": "步骤1"}]  # 不提供 action_id

        event = build_analysis_plan_event(steps)

        step_data = event.data["steps"][0]
        # 即使 action_id 为 None，也应该存在
        assert "action_id" in step_data
        assert step_data["action_id"] is None
