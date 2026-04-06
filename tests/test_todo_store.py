"""TODO 核心模块测试。"""

from __future__ import annotations

import json

import pytest

from nini.todo import (
    InvalidTaskTransitionError,
    TaskConflictError,
    TaskDependencyError,
    TaskDispatcher,
    TaskStatus,
    TaskStore,
)


def test_task_store_crud_and_json_persistence(tmp_path) -> None:
    """任务应支持基础 CRUD 与 JSON 落盘。"""
    store_path = tmp_path / "todo.json"
    store = TaskStore(storage_path=store_path)

    created = store.create_task(title="准备数据", description="读取并检查数据集")
    assert created.status == TaskStatus.PENDING

    updated = store.update_task(created.task_id, description="先检查缺失值")
    assert updated.description == "先检查缺失值"

    reloaded = TaskStore(storage_path=store_path)
    loaded = reloaded.get_task(created.task_id)
    assert loaded.description == "先检查缺失值"

    deleted = reloaded.delete_task(created.task_id, actor_id="admin")
    assert deleted.task_id == created.task_id

    snapshot = json.loads(store_path.read_text(encoding="utf-8"))
    assert snapshot["tasks"] == []
    assert any(event["event_type"] == "deleted" for event in snapshot["events"])


def test_dispatcher_claim_release_and_complete() -> None:
    """调度器应支持认领、释放、重新认领与完成。"""
    dispatcher = TaskDispatcher(TaskStore())
    task = dispatcher.create_task(title="执行统计检验")

    claimed = dispatcher.assign_task(task.task_id, "agent-a")
    assert claimed.status == TaskStatus.ASSIGNED
    assert claimed.assigned_agent_id == "agent-a"

    with pytest.raises(TaskConflictError):
        dispatcher.assign_task(task.task_id, "agent-b")

    released = dispatcher.release_task(task.task_id, "agent-a", reason="等待依赖结果")
    assert released.status == TaskStatus.PENDING
    assert released.assigned_agent_id is None

    dispatcher.assign_task(task.task_id, "agent-b")
    running = dispatcher.mark_in_progress(task.task_id, "agent-b")
    assert running.status == TaskStatus.IN_PROGRESS

    done = dispatcher.mark_done(task.task_id, "agent-b")
    assert done.status == TaskStatus.DONE


def test_ready_queue_respects_dependencies() -> None:
    """只有依赖满足的任务才能进入 ready queue。"""
    dispatcher = TaskDispatcher(TaskStore())
    first = dispatcher.create_task(title="清洗数据")
    second = dispatcher.create_task(
        title="生成图表",
        dependency_ids=[first.task_id],
    )

    ready_before = dispatcher.list_ready_tasks()
    assert [task.task_id for task in ready_before] == [first.task_id]

    dispatcher.assign_task(first.task_id, "agent-a")
    dispatcher.mark_in_progress(first.task_id, "agent-a")
    dispatcher.mark_done(first.task_id, "agent-a")

    ready_after = dispatcher.list_ready_tasks()
    assert [task.task_id for task in ready_after] == [second.task_id]


def test_invalid_transition_and_missing_dependency_raise() -> None:
    """非法迁移与缺失依赖应失败。"""
    store = TaskStore()
    task = store.create_task(title="撰写结论")

    with pytest.raises(InvalidTaskTransitionError):
        store.start_task(task.task_id, agent_id="agent-a")

    with pytest.raises(TaskDependencyError):
        store.create_task(title="二级任务", dependency_ids=["missing-task"])
