"""工具暴露策略测试。"""

from __future__ import annotations

from nini.agent.session import Session
from nini.agent.tool_exposure_policy import (
    _collect_task_tool_hints,
    compute_tool_exposure_policy,
    is_execution_tool,
    resolve_surface_stage,
    tool_satisfies_tool_hint,
)


class _FakeRegistry:
    def __init__(self, tools: list[str]) -> None:
        self._tools = tools

    def list_tools(self) -> list[str]:
        return list(self._tools)


def test_resolve_surface_stage_uses_task_tool_hints_for_analysis() -> None:
    session = Session()
    session.task_manager = session.task_manager.init_tasks(
        [
            {
                "id": 1,
                "title": "明确问题",
                "status": "in_progress",
                "tool_hint": "ask_user_question",
            },
            {"id": 2, "title": "估算样本量", "status": "pending", "tool_hint": "sample_size"},
        ]
    )

    stage = resolve_surface_stage(session, user_message="请帮我设计实验方案")

    assert stage == "analysis"


def test_compute_tool_exposure_policy_keeps_analysis_tools_for_recipe_hints() -> None:
    session = Session()
    session.task_manager = session.task_manager.init_tasks(
        [
            {
                "id": 1,
                "title": "明确问题",
                "status": "in_progress",
                "tool_hint": "ask_user_question",
            },
            {"id": 2, "title": "估算样本量", "status": "pending", "tool_hint": "sample_size"},
        ]
    )
    registry = _FakeRegistry(["task_state", "ask_user_question", "sample_size", "stat_test"])

    policy = compute_tool_exposure_policy(
        session=session,
        tool_registry=registry,
        user_message="请帮我设计一个实验计划",
    )

    assert policy["stage"] == "analysis"
    assert "sample_size" in policy["visible_tools"]
    assert "stat_test" in policy["visible_tools"]


def test_collect_task_tool_hints_splits_slash_separated() -> None:
    """tool_hint 中的 '/' 分隔候选工具应被拆分为独立 hint。"""
    session = Session()
    session.task_manager = session.task_manager.init_tasks(
        [
            {
                "id": 1,
                "title": "正态性检验",
                "status": "pending",
                "tool_hint": "stat_test/code_session",
            },
        ]
    )
    hints = _collect_task_tool_hints(session)
    assert "stat_test" in hints
    assert "code_session" in hints
    assert "stat_test/code_session" not in hints


def test_resolve_surface_stage_detects_analysis_with_slash_hint() -> None:
    """当 tool_hint 包含 '/' 分隔的分析工具时，阶段应为 analysis。"""
    session = Session()
    session.task_manager = session.task_manager.init_tasks(
        [
            {"id": 1, "title": "数据准备", "status": "completed", "tool_hint": "dataset_transform"},
            {
                "id": 2,
                "title": "统计检验",
                "status": "in_progress",
                "tool_hint": "stat_test/code_session",
            },
        ]
    )
    stage = resolve_surface_stage(session)
    assert stage == "analysis"


def test_collect_task_tool_hints_empty_hint() -> None:
    """空 tool_hint 不应产生 hint。"""
    session = Session()
    session.task_manager = session.task_manager.init_tasks(
        [
            {"id": 1, "title": "步骤1", "status": "pending", "tool_hint": ""},
            {"id": 2, "title": "步骤2", "status": "pending"},
        ]
    )
    hints = _collect_task_tool_hints(session)
    assert hints == []


def test_collect_task_tool_hints_none_session() -> None:
    """session 为 None 时应返回空列表。"""
    assert _collect_task_tool_hints(None) == []


def test_compute_tool_exposure_policy_with_user_message_export() -> None:
    """当 user_message 包含导出关键词时，策略阶段应为 export。"""
    session = Session()
    registry = _FakeRegistry(["task_state", "export_chart", "stat_test"])
    policy = compute_tool_exposure_policy(
        session=session,
        tool_registry=registry,
        user_message="导出图表",
    )
    assert policy["stage"] == "export"
    assert "export_chart" in policy["visible_tools"]
    assert "stat_test" not in policy["visible_tools"]


def test_future_visualization_step_does_not_pollute_active_analysis_stage() -> None:
    """未来热图步骤不能把当前正态性检验轮次提前切到 visualization/export。"""
    session = Session()
    session.task_manager = session.task_manager.init_tasks(
        [
            {
                "id": 1,
                "title": "检查数据质量",
                "status": "completed",
                "tool_hint": "dataset_catalog",
            },
            {"id": 2, "title": "正态性检验", "status": "in_progress", "tool_hint": "code_session"},
            {"id": 3, "title": "相关性分析", "status": "pending", "tool_hint": "stat_test"},
            {"id": 4, "title": "绘制热图", "status": "pending", "tool_hint": "chart_session"},
        ]
    )

    registry = _FakeRegistry(
        [
            "task_state",
            "dataset_catalog",
            "code_session",
            "stat_test",
            "chart_session",
            "generate_widget",
        ]
    )
    policy = compute_tool_exposure_policy(
        session=session,
        tool_registry=registry,
        user_message="开始分析",
    )

    assert policy["stage"] == "analysis"
    assert policy["stage_reason"] == "active_task"
    assert policy["active_task_title"] == "正态性检验"
    assert "code_session" in policy["visible_tools"]
    assert "stat_test" in policy["visible_tools"]
    assert "generate_widget" not in policy["visible_tools"]


def test_visualization_stage_keeps_chart_and_execution_tools() -> None:
    """真正进入画图阶段时，应同时保留 chart_session 与 code_session。"""
    session = Session()
    session.task_manager = session.task_manager.init_tasks(
        [
            {"id": 1, "title": "绘制热图", "status": "in_progress", "tool_hint": "chart_session"},
        ]
    )
    registry = _FakeRegistry(["task_state", "chart_session", "code_session", "generate_widget"])

    policy = compute_tool_exposure_policy(
        session=session,
        tool_registry=registry,
        user_message="开始分析",
    )

    assert policy["stage"] == "visualization"
    assert "chart_session" in policy["visible_tools"]
    assert "code_session" in policy["visible_tools"]
    assert "generate_widget" not in policy["visible_tools"]


def test_tool_satisfies_tool_hint_rejects_presentation_for_execution_hint() -> None:
    """展示工具不能替代执行型 task hint。"""
    assert tool_satisfies_tool_hint("code_session", "stat_test/code_session") is True
    assert tool_satisfies_tool_hint("generate_widget", "code_session") is False
    assert is_execution_tool("code_session") is True
