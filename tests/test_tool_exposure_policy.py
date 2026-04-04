"""工具暴露策略测试。"""

from __future__ import annotations

from nini.agent.session import Session
from nini.agent.tool_exposure_policy import compute_tool_exposure_policy, resolve_surface_stage


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
