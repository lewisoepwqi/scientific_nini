"""task_write 最后任务分支消息与自动完成标记测试。"""

from __future__ import annotations

import pytest

from nini.agent.session import Session
from nini.tools.task_write import TaskWriteTool


@pytest.mark.asyncio
async def test_last_remaining_task_message_forbids_task_state_call() -> None:
    """最后一个任务（pending==0 且仅该任务 in_progress）的消息不能要求再调 task_state。"""
    session = Session()
    tool = TaskWriteTool()

    # 初始化 2 个任务
    await tool.execute(
        session,
        mode="init",
        tasks=[
            {"id": 1, "title": "加载数据", "status": "pending"},
            {"id": 2, "title": "汇总结论", "status": "pending"},
        ],
    )

    # 把 1 → completed，2 → in_progress（此时 pending==0，只剩 2 在 in_progress）
    result = await tool.execute(
        session,
        mode="update",
        tasks=[
            {"id": 1, "status": "completed"},
            {"id": 2, "status": "in_progress"},
        ],
    )

    assert result.success, result.message
    msg = result.message
    # 绝对不能要求再次调用 task_state
    assert "将本任务标记为 completed 再输出" not in msg, msg
    assert "标记为 completed" not in msg or "不要再调用" in msg, msg
    # 必须显式告诉模型"直接输出总结"
    assert "直接输出" in msg or "直接给出" in msg, msg
    # 必须显式禁止再调 task_state
    assert "不要再调用 task_state" in msg or "无需再调用 task_state" in msg, msg


@pytest.mark.asyncio
async def test_last_remaining_task_marks_session_for_auto_complete() -> None:
    """最后一个任务进入 in_progress 时，session 应记录其 id，用于 turn 结束自动关闭。"""
    session = Session()
    tool = TaskWriteTool()

    await tool.execute(
        session,
        mode="init",
        tasks=[
            {"id": 1, "title": "加载数据", "status": "pending"},
            {"id": 2, "title": "汇总结论", "status": "pending"},
        ],
    )

    await tool.execute(
        session,
        mode="update",
        tasks=[
            {"id": 1, "status": "completed"},
            {"id": 2, "status": "in_progress"},
        ],
    )

    assert session.pending_auto_complete_task_id == 2


@pytest.mark.asyncio
async def test_non_last_task_does_not_mark_auto_complete() -> None:
    """非最后任务 in_progress 不应设置 auto_complete 标记。"""
    session = Session()
    tool = TaskWriteTool()

    await tool.execute(
        session,
        mode="init",
        tasks=[
            {"id": 1, "title": "加载数据", "status": "pending"},
            {"id": 2, "title": "分析", "status": "pending"},
            {"id": 3, "title": "汇总", "status": "pending"},
        ],
    )

    # 只让任务 1 进入 in_progress，任务 2、3 还是 pending
    await tool.execute(
        session,
        mode="update",
        tasks=[{"id": 1, "status": "in_progress"}],
    )

    assert session.pending_auto_complete_task_id is None
