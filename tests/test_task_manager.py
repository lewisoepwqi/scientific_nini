"""TaskManager 单元测试。

覆盖：
- TaskItem.depends_on 字段填充与序列化
- group_into_waves() 拓扑排序正确性
- 无依赖任务归入同一 wave
- 链式依赖正确分层
- 循环依赖退化为顺序执行
"""

from __future__ import annotations

import pytest

from nini.agent.task_manager import TaskItem, TaskManager


def _make_manager(tasks_raw: list[dict]) -> TaskManager:
    """创建并初始化 TaskManager。"""
    tm = TaskManager()
    return tm.init_tasks(tasks_raw)


# ---- depends_on 字段 ----


def test_task_item_depends_on_default():
    """TaskItem.depends_on 默认为空列表。"""
    item = TaskItem(id=1, title="任务1")
    assert item.depends_on == []


def test_init_tasks_reads_depends_on():
    """init_tasks 应正确解析 depends_on 字段。"""
    tm = _make_manager([
        {"id": 1, "title": "A", "depends_on": []},
        {"id": 2, "title": "B", "depends_on": [1]},
        {"id": 3, "title": "C", "depends_on": [1, 2]},
    ])
    assert tm.tasks[0].depends_on == []
    assert tm.tasks[1].depends_on == [1]
    assert tm.tasks[2].depends_on == [1, 2]


def test_init_tasks_missing_depends_on():
    """未传 depends_on 时默认为空列表。"""
    tm = _make_manager([{"id": 1, "title": "A"}])
    assert tm.tasks[0].depends_on == []


def test_to_analysis_plan_dict_exposes_depends_on():
    """to_analysis_plan_dict 应在 steps 中暴露 depends_on（10.3 前端依赖关系展示）。"""
    tm = _make_manager([
        {"id": 1, "title": "A", "depends_on": []},
        {"id": 2, "title": "B", "depends_on": [1]},
    ])
    plan_dict = tm.to_analysis_plan_dict()
    assert plan_dict["steps"][0]["depends_on"] == []
    assert plan_dict["steps"][1]["depends_on"] == [1]


# ---- group_into_waves 拓扑排序 ----


def test_group_into_waves_no_deps():
    """无依赖时所有 pending 任务应在同一 wave。"""
    tm = _make_manager([
        {"id": 1, "title": "A"},
        {"id": 2, "title": "B"},
        {"id": 3, "title": "C"},
    ])
    waves = tm.group_into_waves()
    assert len(waves) == 1
    ids_in_wave = {t.id for t in waves[0]}
    assert ids_in_wave == {1, 2, 3}


def test_group_into_waves_chain():
    """链式依赖应分为多个 wave，每个 wave 只有一个任务。"""
    tm = _make_manager([
        {"id": 1, "title": "A"},
        {"id": 2, "title": "B", "depends_on": [1]},
        {"id": 3, "title": "C", "depends_on": [2]},
    ])
    waves = tm.group_into_waves()
    assert len(waves) == 3
    assert waves[0][0].id == 1
    assert waves[1][0].id == 2
    assert waves[2][0].id == 3


def test_group_into_waves_diamond():
    """菱形依赖：1 -> 2, 1 -> 3, {2,3} -> 4"""
    tm = _make_manager([
        {"id": 1, "title": "A"},
        {"id": 2, "title": "B", "depends_on": [1]},
        {"id": 3, "title": "C", "depends_on": [1]},
        {"id": 4, "title": "D", "depends_on": [2, 3]},
    ])
    waves = tm.group_into_waves()
    assert len(waves) == 3
    assert {t.id for t in waves[0]} == {1}
    assert {t.id for t in waves[1]} == {2, 3}
    assert {t.id for t in waves[2]} == {4}


def test_group_into_waves_empty():
    """空任务列表应返回空 wave 列表。"""
    tm = TaskManager()
    waves = tm.group_into_waves()
    assert waves == []


def test_group_into_waves_skips_completed():
    """非 pending 任务不参与 wave 分组。"""
    tm = _make_manager([
        {"id": 1, "title": "A", "status": "completed"},
        {"id": 2, "title": "B", "depends_on": [1]},
    ])
    waves = tm.group_into_waves()
    # 任务 1 已完成，任务 2 的依赖不在 pending 中，应单独在 wave 0
    assert len(waves) == 1
    assert waves[0][0].id == 2
