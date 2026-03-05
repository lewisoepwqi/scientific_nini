"""WebSocket 事件构造器测试。

验证使用 Pydantic 模型构造的事件数据符合契约。
"""

from __future__ import annotations

import pytest

from nini.agent.event_builders import (
    build_analysis_plan_event,
    build_plan_step_update_event,
    build_plan_progress_event,
    build_task_attempt_event,
    build_token_usage_event,
    build_tool_call_event,
    build_tool_result_event,
    build_text_event,
    build_error_event,
    build_done_event,
    build_session_event,
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
            },
            {
                "id": 2,
                "title": "步骤2",
                "status": "in_progress",
                "action_id": "task_2",
            },
        ]

        event = build_analysis_plan_event(
            steps, raw_text="分析计划", turn_id="turn_1", seq=1
        )

        assert event.type == EventType.ANALYSIS_PLAN
        assert event.data["raw_text"] == "分析计划"
        assert len(event.data["steps"]) == 2
        # 验证 action_id 被正确传递
        assert event.data["steps"][0]["action_id"] == "task_1"
        assert event.data["steps"][1]["action_id"] == "task_2"
        # 验证 raw_status 被正确传递
        assert event.data["steps"][0]["raw_status"] == "completed"
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
        # 验证 turn_id 和 metadata 为 None
        assert event.turn_id is None
        assert event.metadata is None


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
            {"id": 2, "title": "步骤2", "status": "in_progress"},
        ]

        event = build_plan_progress_event(
            steps=steps,
            current_step_index=2,
            total_steps=2,
            step_title="步骤2",
            step_status="in_progress",
            next_hint="下一步操作",
        )

        assert event.type == EventType.PLAN_PROGRESS
        assert event.data["current_step_index"] == 2
        assert event.data["next_hint"] == "下一步操作"
        assert event.data["block_reason"] is None


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
        )

        assert event.type == EventType.WORKSPACE_UPDATE
        assert event.data["action"] == "add"
        assert event.data["file_id"] == "file_1"


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
