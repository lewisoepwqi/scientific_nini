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


def test_profile_stage_with_analysis_pending_includes_analysis_tools() -> None:
    """当前 profile 任务 in_progress 但下一任务是 analysis 时，分析工具应可见。

    复现场景：task2(dataset_transform) in_progress, task3(stat_test) pending。
    LLM 完成了 dataset_transform 但忘记标记 task2 为 completed，
    下一轮 stat_test/code_session 全部不可见。
    """
    session = Session()
    session.task_manager = session.task_manager.init_tasks(
        [
            {
                "id": 1,
                "title": "检查数据质量",
                "status": "completed",
                "tool_hint": "dataset_catalog",
            },
            {
                "id": 2,
                "title": "数据预处理",
                "status": "in_progress",
                "tool_hint": "dataset_transform",
            },
            {"id": 3, "title": "相关性分析", "status": "pending", "tool_hint": "stat_test"},
            {"id": 4, "title": "绘制热图", "status": "pending", "tool_hint": "chart_session"},
        ]
    )
    registry = _FakeRegistry(
        [
            "task_state",
            "dataset_catalog",
            "dataset_transform",
            "stat_test",
            "code_session",
            "chart_session",
        ]
    )

    policy = compute_tool_exposure_policy(
        session=session,
        tool_registry=registry,
        user_message="继续分析",
    )

    # stage 仍是 profile（因为 task2 in_progress）
    assert policy["stage"] == "profile"
    # 但 analysis 工具也应可见（look-ahead 机制）
    assert "stat_test" in policy["visible_tools"]
    assert "code_session" in policy["visible_tools"]
    # 应有 look-ahead 警告
    assert any("look-ahead" in w or "下一" in w for w in policy["policy_warnings"])


def test_stage_transition_hint_informs_llm_about_hidden_tools() -> None:
    """当 analysis 阶段隐藏了导出工具时，transition_hint 应告知 LLM 解锁方式。"""
    session = Session()
    session.task_manager = session.task_manager.init_tasks(
        [
            {
                "id": 1,
                "title": "数据预处理",
                "status": "completed",
                "tool_hint": "dataset_transform",
            },
            {"id": 2, "title": "相关性分析", "status": "in_progress", "tool_hint": "stat_test"},
            {"id": 3, "title": "导出报告", "status": "pending", "tool_hint": "export_document"},
        ]
    )
    registry = _FakeRegistry(
        ["task_state", "stat_test", "code_session", "export_chart", "export_document"]
    )

    policy = compute_tool_exposure_policy(
        session=session,
        tool_registry=registry,
        user_message="继续分析",
    )

    assert "stage_transition_hint" in policy
    hint = policy["stage_transition_hint"]
    assert hint is not None
    # 被隐藏的导出工具应出现在提示中
    assert "export_chart" in hint
    # 提示应引导 LLM 调用 task_state
    assert "task_state" in hint
