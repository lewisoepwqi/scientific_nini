"""Runner turn 结束自动完成 last in_progress 任务测试。"""

from __future__ import annotations

import pytest

from nini.agent.runner import AgentRunner
from nini.agent.session import Session
from nini.agent.task_manager import TaskItem, TaskManager


@pytest.mark.asyncio
async def test_turn_end_auto_completes_pending_task() -> None:
    """turn 结束时，若 session.pending_auto_complete_task_id 有值且任务仍 in_progress，应置 completed。"""
    session = Session()
    session.task_manager = TaskManager(
        tasks=[TaskItem(id=1, title="汇总", status="in_progress", action_id="task_1")],
        initialized=True,
    )
    session.pending_auto_complete_task_id = 1

    runner = AgentRunner()
    # 直接调用 Task 2 新增的内部收尾函数
    runner._finalize_turn(session, turn_id="test-turn")

    target = next(t for t in session.task_manager.tasks if t.id == 1)
    assert target.status == "completed"
    # 标记应被清除避免重复触发
    assert session.pending_auto_complete_task_id is None


@pytest.mark.asyncio
async def test_turn_end_skips_if_task_already_completed() -> None:
    """若目标任务已非 in_progress（被模型手动改过），auto-complete 应幂等跳过。"""
    session = Session()
    session.task_manager = TaskManager(
        tasks=[TaskItem(id=1, title="汇总", status="completed", action_id="task_1")],
        initialized=True,
    )
    session.pending_auto_complete_task_id = 1

    runner = AgentRunner()
    runner._finalize_turn(session, turn_id="test-turn")

    target = next(t for t in session.task_manager.tasks if t.id == 1)
    assert target.status == "completed"
    # 即使未实际修改，也应清除标记避免下轮误触发
    assert session.pending_auto_complete_task_id is None


@pytest.mark.asyncio
async def test_turn_end_skips_if_no_pending_flag() -> None:
    """未设置 pending_auto_complete_task_id 时不应改动任务列表。"""
    session = Session()
    session.task_manager = TaskManager(
        tasks=[TaskItem(id=1, title="汇总", status="in_progress", action_id="task_1")],
        initialized=True,
    )
    session.pending_auto_complete_task_id = None

    runner = AgentRunner()
    runner._finalize_turn(session, turn_id="test-turn")

    target = next(t for t in session.task_manager.tasks if t.id == 1)
    assert target.status == "in_progress"
    assert session.pending_auto_complete_task_id is None
