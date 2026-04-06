"""统一 TODO 模块测试。"""

from __future__ import annotations

import pytest

from nini.todo import InvalidTaskTransitionError, TaskConflictError, TaskStatus, TodoService


def test_todo_service_crud_and_event_log(tmp_path) -> None:
    """创建、更新、删除任务应落盘并写入事件。"""
    service = TodoService(base_dir=tmp_path)

    created = service.create_task("sess_a", title="整理数据", actor_id="tester")
    assert created.status == TaskStatus.PENDING

    updated = service.update_task(
        "sess_a",
        created.task_id,
        title="整理试验数据",
        metadata={"source": "unit-test"},
    )
    assert updated.title == "整理试验数据"
    assert updated.metadata["source"] == "unit-test"

    listed = service.list_tasks("sess_a")
    assert [task.task_id for task in listed] == [created.task_id]

    deleted = service.delete_task("sess_a", created.task_id, actor_id="tester")
    assert deleted.task_id == created.task_id
    assert service.list_tasks("sess_a") == []

    events = service.list_events("sess_a")
    assert [event.event_type for event in events] == ["created", "updated", "deleted"]


def test_claim_start_complete_release_flow(tmp_path) -> None:
    """任务应支持 claim、start、release、re-claim、complete。"""
    service = TodoService(base_dir=tmp_path)
    task = service.create_task("sess_b", title="执行统计检验")

    claimed = service.claim_task("sess_b", task.task_id, agent_id="agent.alpha")
    assert claimed.status == TaskStatus.ASSIGNED
    assert claimed.assignee_id == "agent.alpha"

    running = service.start_task("sess_b", task.task_id, agent_id="agent.alpha")
    assert running.status == TaskStatus.IN_PROGRESS
    assert running.started_at is not None

    released = service.release_task("sess_b", task.task_id, agent_id="agent.alpha")
    assert released.status == TaskStatus.PENDING
    assert released.assignee_id is None

    reclaimed = service.claim_task("sess_b", task.task_id, agent_id="agent.beta")
    done = service.start_task("sess_b", reclaimed.task_id, agent_id="agent.beta")
    done = service.complete_task("sess_b", done.task_id, agent_id="agent.beta")
    assert done.status == TaskStatus.DONE
    assert done.finished_at is not None


def test_claim_next_task_respects_dependencies(tmp_path) -> None:
    """claim_next_task 只应返回依赖已完成的任务。"""
    service = TodoService(base_dir=tmp_path)
    first = service.create_task("sess_c", title="收集数据")
    second = service.create_task(
        "sess_c",
        title="建模分析",
        dependency_ids=[first.task_id],
    )

    claimed_first = service.claim_next_task("sess_c", agent_id="agent.alpha")
    assert claimed_first is not None
    assert claimed_first.task_id == first.task_id

    service.start_task("sess_c", first.task_id, agent_id="agent.alpha")
    service.complete_task("sess_c", first.task_id, agent_id="agent.alpha")

    claimed_second = service.claim_next_task("sess_c", agent_id="agent.beta")
    assert claimed_second is not None
    assert claimed_second.task_id == second.task_id


def test_invalid_transition_and_delete_conflict(tmp_path) -> None:
    """非法状态迁移与执行中删除应失败。"""
    service = TodoService(base_dir=tmp_path)
    task = service.create_task("sess_d", title="导出图表")

    with pytest.raises(InvalidTaskTransitionError):
        service.complete_task("sess_d", task.task_id)

    claimed = service.claim_task("sess_d", task.task_id, agent_id="agent.alpha")
    service.start_task("sess_d", claimed.task_id, agent_id="agent.alpha")

    with pytest.raises(TaskConflictError):
        service.delete_task("sess_d", task.task_id)
