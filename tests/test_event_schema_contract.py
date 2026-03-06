"""WebSocket 事件数据契约验证测试。

确保后端发送的事件数据格式与前端的期望一致。
防止前后端字段不匹配导致的功能异常。
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from nini.models.event_schemas import (
    AnalysisPlanEventData,
    AnalysisPlanStep,
    PlanProgressEventData,
    PlanStepUpdateEventData,
    TaskAttemptEventData,
    TokenUsageEventData,
    ToolCallEventData,
    ToolResultEventData,
    ErrorEventData,
    DoneEventData,
    SessionEventData,
)


class TestAnalysisPlanEventContract:
    """ANALYSIS_PLAN 事件数据契约测试。"""

    def test_analysis_plan_with_all_fields(self) -> None:
        """完整的分析计划事件应包含所有必要字段。"""
        data = {
            "steps": [
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
                    "tool_hint": None,
                    "status": "in_progress",
                    "action_id": "task_2",
                    "raw_status": "in_progress",
                },
            ],
            "raw_text": "分析计划",
        }

        event_data = AnalysisPlanEventData.model_validate(data)

        assert len(event_data.steps) == 2
        assert event_data.steps[0].id == 1
        assert event_data.steps[0].action_id == "task_1"
        assert event_data.steps[0].raw_status == "completed"
        assert event_data.steps[1].status == "in_progress"

    def test_analysis_plan_step_defaults(self) -> None:
        """分析步骤应提供合理的默认值。"""
        data = {
            "steps": [
                {"id": 1, "title": "步骤1"},
            ],
            "raw_text": "",
        }

        event_data = AnalysisPlanEventData.model_validate(data)

        step = event_data.steps[0]
        assert step.status == "pending"
        assert step.tool_hint is None
        assert step.action_id is None
        assert step.raw_status is None

    def test_analysis_plan_step_to_dict(self) -> None:
        """步骤转换为字典时应包含所有字段。"""
        step = AnalysisPlanStep(
            id=1,
            title="测试步骤",
            tool_hint="t_test",
            status="in_progress",
            action_id="task_1",
            raw_status="in_progress",
        )

        result = step.model_dump()

        assert result["id"] == 1
        assert result["title"] == "测试步骤"
        assert result["tool_hint"] == "t_test"
        assert result["status"] == "in_progress"
        assert result["action_id"] == "task_1"
        assert result["raw_status"] == "in_progress"


class TestPlanStepUpdateEventContract:
    """PLAN_STEP_UPDATE 事件数据契约测试。"""

    def test_step_update_with_error(self) -> None:
        """步骤更新事件应支持错误信息。"""
        data = {
            "id": 1,
            "status": "failed",
            "error": "参数无效",
        }

        event_data = PlanStepUpdateEventData.model_validate(data)

        assert event_data.id == 1
        assert event_data.status == "failed"
        assert event_data.error == "参数无效"

    def test_step_update_without_error(self) -> None:
        """步骤更新事件错误信息可为空。"""
        data = {"id": 2, "status": "completed"}

        event_data = PlanStepUpdateEventData.model_validate(data)

        assert event_data.id == 2
        assert event_data.status == "completed"
        assert event_data.error is None


class TestPlanProgressEventContract:
    """PLAN_PROGRESS 事件数据契约测试。"""

    def test_plan_progress_with_all_fields(self) -> None:
        """完整的计划进度事件应包含所有字段。"""
        data = {
            "steps": [
                {"id": 1, "title": "步骤1", "status": "completed"},
                {"id": 2, "title": "步骤2", "status": "in_progress"},
            ],
            "current_step_index": 2,
            "total_steps": 2,
            "step_title": "步骤2",
            "step_status": "in_progress",
            "next_hint": "下一步",
            "block_reason": None,
        }

        event_data = PlanProgressEventData.model_validate(data)

        assert event_data.current_step_index == 2
        assert event_data.total_steps == 2
        assert event_data.step_title == "步骤2"
        assert event_data.next_hint == "下一步"
        assert event_data.block_reason is None


class TestTaskAttemptEventContract:
    """TASK_ATTEMPT 事件数据契约测试。"""

    def test_task_attempt_retrying(self) -> None:
        """任务重试事件应包含重试信息。"""
        data = {
            "action_id": "task_1",
            "step_id": 1,
            "tool_name": "run_code",
            "attempt": 2,
            "max_attempts": 3,
            "status": "retrying",
            "note": "正在重试",
            "error": "上次失败",
        }

        event_data = TaskAttemptEventData.model_validate(data)

        assert event_data.action_id == "task_1"
        assert event_data.step_id == 1
        assert event_data.attempt == 2
        assert event_data.max_attempts == 3
        assert event_data.status == "retrying"


class TestTokenUsageEventContract:
    """TOKEN_USAGE 事件数据契约测试。"""

    def test_token_usage_with_cost(self) -> None:
        """Token 使用事件应包含成本信息。"""
        data = {
            "input_tokens": 1000,
            "output_tokens": 500,
            "model": "gpt-4o",
            "cost_usd": 0.015,
        }

        event_data = TokenUsageEventData.model_validate(data)

        assert event_data.input_tokens == 1000
        assert event_data.output_tokens == 500
        assert event_data.model == "gpt-4o"
        assert event_data.cost_usd == 0.015

    def test_token_usage_without_cost(self) -> None:
        """Token 使用事件成本可为空（兜底价格）。"""
        data = {
            "input_tokens": 1000,
            "output_tokens": 500,
            "model": "unknown-model",
        }

        event_data = TokenUsageEventData.model_validate(data)

        assert event_data.cost_usd is None


class TestToolEventContract:
    """工具调用相关事件数据契约测试。"""

    def test_tool_call_event(self) -> None:
        """工具调用事件应包含参数。"""
        data = {
            "id": "call_123",
            "name": "run_code",
            "arguments": {"code": "print(1)"},
        }

        event_data = ToolCallEventData.model_validate(data)

        assert event_data.id == "call_123"
        assert event_data.name == "run_code"
        assert event_data.arguments["code"] == "print(1)"

    def test_tool_result_success(self) -> None:
        """工具结果成功事件。"""
        data = {
            "id": "call_123",
            "name": "run_code",
            "status": "success",
            "message": "执行成功",
            "data": {"output": "1"},
        }

        event_data = ToolResultEventData.model_validate(data)

        assert event_data.status == "success"
        assert event_data.message == "执行成功"
        assert event_data.data is not None

    def test_tool_result_error(self) -> None:
        """工具结果失败事件。"""
        data = {
            "id": "call_123",
            "name": "run_code",
            "status": "error",
            "message": "执行失败",
        }

        event_data = ToolResultEventData.model_validate(data)

        assert event_data.status == "error"
        assert event_data.data is None


class TestCommonEventContract:
    """通用事件数据契约测试。"""

    def test_error_event(self) -> None:
        """错误事件应包含消息和代码。"""
        data = {"message": "出错了", "code": "ERR_001"}

        event_data = ErrorEventData.model_validate(data)

        assert event_data.message == "出错了"
        assert event_data.code == "ERR_001"

    def test_done_event(self) -> None:
        """完成事件应包含原因。"""
        data = {"reason": "completed"}

        event_data = DoneEventData.model_validate(data)

        assert event_data.reason == "completed"

    def test_session_event(self) -> None:
        """会话事件应包含会话 ID。"""
        data = {"session_id": "abc123"}

        event_data = SessionEventData.model_validate(data)

        assert event_data.session_id == "abc123"


class TestEventSerialization:
    """事件序列化契约测试。"""

    def test_analysis_plan_json_serialization(self) -> None:
        """分析计划事件应能正确序列化为 JSON。"""
        event_data = AnalysisPlanEventData(
            steps=[
                AnalysisPlanStep(
                    id=1,
                    title="步骤1",
                    tool_hint=None,
                    status="pending",
                    action_id="task_1",
                    raw_status=None,
                ),
                AnalysisPlanStep(
                    id=2,
                    title="步骤2",
                    tool_hint=None,
                    status="in_progress",
                    action_id=None,
                    raw_status=None,
                ),
            ],
            raw_text="测试",
        )

        # 模拟后端发送给前端的 JSON
        json_str = json.dumps(event_data.model_dump())
        parsed = json.loads(json_str)

        # 验证前端能正确解析
        assert parsed["steps"][0]["id"] == 1
        assert parsed["steps"][0]["action_id"] == "task_1"
        assert parsed["steps"][1]["status"] == "in_progress"

    def test_action_id_field_presence(self) -> None:
        """验证 action_id 字段在序列化中始终存在（即使为 null）。"""
        event_data = AnalysisPlanEventData(
            steps=[
                AnalysisPlanStep(
                    id=1,
                    title="步骤1",
                    tool_hint=None,
                    status="pending",
                    action_id=None,
                    raw_status=None,
                )
            ],
            raw_text="",
        )

        result = event_data.model_dump()

        # 即使 action_id 为 None，也应该在结果中（前端需要这个字段）
        assert "action_id" in result["steps"][0]
