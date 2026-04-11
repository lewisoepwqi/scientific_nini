"""工具暴露策略测试。"""

from __future__ import annotations

from nini.agent.session import Session
from nini.agent.tool_exposure_policy import (
    _collect_task_tool_hints,
    compute_tool_exposure_policy,
    resolve_surface_stage,
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


def test_collect_task_tool_hints_extracts_tool_names_from_free_text() -> None:
    session = Session()
    session.task_manager = session.task_manager.init_tasks(
        [
            {
                "id": 1,
                "title": "时间变量衍生",
                "status": "in_progress",
                "tool_hint": "dataset_transform derive_column",
            },
            {
                "id": 2,
                "title": "异常值检测",
                "status": "pending",
                "tool_hint": "code_session + dataset_transform",
            },
        ]
    )
    hints = _collect_task_tool_hints(session)
    assert hints == ["dataset_transform", "code_session"]


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


def test_compute_tool_exposure_policy_does_not_let_future_export_hint_pollute_current_step() -> None:
    session = Session()
    session.task_manager = session.task_manager.init_tasks(
        [
            {
                "id": 1,
                "title": "时间变量衍生",
                "status": "in_progress",
                "tool_hint": "dataset_transform derive_column",
            },
            {
                "id": 2,
                "title": "结果可视化",
                "status": "pending",
                "tool_hint": "chart_session",
            },
        ]
    )
    registry = _FakeRegistry(
        ["task_state", "dataset_transform", "chart_session", "code_session", "workspace_session"]
    )
    policy = compute_tool_exposure_policy(
        session=session,
        tool_registry=registry,
        user_message="继续做时间变量衍生",
    )
    assert policy["stage"] == "profile"
    assert "dataset_transform" in policy["visible_tools"]
    assert "code_session" in policy["visible_tools"]
    assert "workspace_session" not in policy["visible_tools"]
