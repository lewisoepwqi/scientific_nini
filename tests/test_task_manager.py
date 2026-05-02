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
    tm = _make_manager(
        [
            {"id": 1, "title": "A", "depends_on": []},
            {"id": 2, "title": "B", "depends_on": [1]},
            {"id": 3, "title": "C", "depends_on": [1, 2]},
        ]
    )
    assert tm.tasks[0].depends_on == []
    assert tm.tasks[1].depends_on == [1]
    assert tm.tasks[2].depends_on == [1, 2]


def test_init_tasks_missing_depends_on():
    """未传 depends_on 时默认为空列表。"""
    tm = _make_manager([{"id": 1, "title": "A"}])
    assert tm.tasks[0].depends_on == []


def test_to_analysis_plan_dict_exposes_depends_on():
    """to_analysis_plan_dict 应在 steps 中暴露 depends_on（10.3 前端依赖关系展示）。"""
    tm = _make_manager(
        [
            {"id": 1, "title": "A", "depends_on": []},
            {"id": 2, "title": "B", "depends_on": [1]},
        ]
    )
    plan_dict = tm.to_analysis_plan_dict()
    assert plan_dict["steps"][0]["depends_on"] == []
    assert plan_dict["steps"][1]["depends_on"] == [1]


def test_init_tasks_reads_execution_metadata():
    """init_tasks 应保留执行器、输入输出引用和交接契约。"""
    tm = _make_manager(
        [
            {
                "id": 1,
                "title": "清洗数据",
                "executor": "subagent",
                "owner": "data_cleaner",
                "input_refs": ["dataset:raw.v1"],
                "output_refs": ["dataset:cleaned.v1"],
                "handoff_contract": {"required_columns": ["age", "sbp"]},
                "tool_profile": "cleaning_execution",
                "failure_policy": "stop_pipeline",
                "acceptance_checks": ["缺失率已下降"],
            }
        ]
    )
    task = tm.tasks[0]
    assert task.executor == "subagent"
    assert task.owner == "data_cleaner"
    assert task.input_refs == ["dataset:raw.v1"]
    assert task.output_refs == ["dataset:cleaned.v1"]
    assert task.handoff_contract == {"required_columns": ["age", "sbp"]}
    assert task.tool_profile == "cleaning_execution"
    assert task.failure_policy == "stop_pipeline"
    assert task.acceptance_checks == ["缺失率已下降"]
    plan_dict = tm.to_analysis_plan_dict()
    assert plan_dict["steps"][0]["handoff_contract"] == {"required_columns": ["age", "sbp"]}
    assert plan_dict["steps"][0]["failure_policy"] == "stop_pipeline"
    assert plan_dict["steps"][0]["acceptance_checks"] == ["缺失率已下降"]


# ---- group_into_waves 拓扑排序 ----


def test_group_into_waves_no_deps():
    """无依赖时所有 pending 任务应在同一 wave。"""
    tm = _make_manager(
        [
            {"id": 1, "title": "A"},
            {"id": 2, "title": "B"},
            {"id": 3, "title": "C"},
        ]
    )
    waves = tm.group_into_waves()
    assert len(waves) == 1
    ids_in_wave = {t.id for t in waves[0]}
    assert ids_in_wave == {1, 2, 3}


def test_group_into_waves_chain():
    """链式依赖应分为多个 wave，每个 wave 只有一个任务。"""
    tm = _make_manager(
        [
            {"id": 1, "title": "A"},
            {"id": 2, "title": "B", "depends_on": [1]},
            {"id": 3, "title": "C", "depends_on": [2]},
        ]
    )
    waves = tm.group_into_waves()
    assert len(waves) == 3
    assert waves[0][0].id == 1
    assert waves[1][0].id == 2
    assert waves[2][0].id == 3


def test_group_into_waves_diamond():
    """菱形依赖：1 -> 2, 1 -> 3, {2,3} -> 4"""
    tm = _make_manager(
        [
            {"id": 1, "title": "A"},
            {"id": 2, "title": "B", "depends_on": [1]},
            {"id": 3, "title": "C", "depends_on": [1]},
            {"id": 4, "title": "D", "depends_on": [2, 3]},
        ]
    )
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


def test_group_into_waves_splits_write_conflicts():
    """同一拓扑层中存在共享输出时，应拆成多个 wave。"""
    tm = _make_manager(
        [
            {"id": 1, "title": "清洗 A", "output_refs": ["dataset:cleaned.v1"]},
            {"id": 2, "title": "清洗 B", "output_refs": ["dataset:cleaned.v1"]},
        ]
    )
    waves = tm.group_into_waves()
    assert len(waves) == 2
    assert [waves[0][0].id, waves[1][0].id] == [1, 2]


def test_group_into_waves_splits_read_after_write_conflicts():
    """同层任务若一个写入另一个读取的引用，也应拆分 wave。"""
    tm = _make_manager(
        [
            {"id": 1, "title": "清洗", "output_refs": ["dataset:cleaned.v1"]},
            {"id": 2, "title": "统计", "input_refs": ["dataset:cleaned.v1"]},
        ]
    )
    waves = tm.group_into_waves()
    assert len(waves) == 2
    assert waves[0][0].id == 1
    assert waves[1][0].id == 2


def test_group_into_waves_reuses_later_subwave_for_newly_unlocked_tasks():
    """前一子 wave 解锁的新任务，应能进入后续无冲突子 wave。"""
    tm = _make_manager(
        [
            {"id": 1, "title": "A", "output_refs": ["dataset:cleaned.v1"]},
            {"id": 2, "title": "B", "input_refs": ["dataset:cleaned.v1"]},
            {"id": 3, "title": "C", "depends_on": [1], "input_refs": ["dataset:cleaned.v1"]},
        ]
    )
    waves = tm.group_into_waves()
    assert len(waves) == 2
    assert [task.id for task in waves[0]] == [1]
    assert {task.id for task in waves[1]} == {2, 3}


def test_group_into_waves_skips_completed():
    """非 pending 任务不参与 wave 分组。"""
    tm = _make_manager(
        [
            {"id": 1, "title": "A", "status": "completed"},
            {"id": 2, "title": "B", "depends_on": [1]},
        ]
    )
    waves = tm.group_into_waves()
    # 任务 1 已完成，任务 2 的依赖不在 pending 中，应单独在 wave 0
    assert len(waves) == 1
    assert waves[0][0].id == 2


def test_get_dispatch_context_prefers_current_in_progress_task():
    """存在进行中任务时，dispatch context 应锁定当前任务并禁止 pending wave 派发。"""
    tm = _make_manager(
        [
            {"id": 1, "title": "读取数据", "status": "completed", "tool_hint": "dataset_catalog"},
            {
                "id": 2,
                "title": "清洗数据",
                "status": "in_progress",
                "tool_hint": "dataset_transform",
            },
            {"id": 3, "title": "统计分析", "status": "pending", "depends_on": [2]},
        ]
    )

    context = tm.get_dispatch_context()

    assert context.current_in_progress_task_id == 2
    assert context.allow_direct_execution is True
    assert context.allow_current_task_subdispatch is True
    assert context.allow_pending_wave_dispatch is False
    assert context.recommended_tools == ["dataset_transform"]


def test_get_dispatch_context_returns_pending_wave_when_no_in_progress():
    """无进行中任务时，应暴露首个可启动 pending wave。"""
    tm = _make_manager(
        [
            {"id": 1, "title": "读取数据", "status": "completed", "tool_hint": "dataset_catalog"},
            {
                "id": 2,
                "title": "清洗数据",
                "status": "pending",
                "depends_on": [1],
                "tool_hint": "dataset_transform",
            },
            {"id": 3, "title": "统计分析", "status": "pending", "depends_on": [2]},
        ]
    )

    context = tm.get_dispatch_context()

    assert context.current_in_progress_task_id is None
    assert context.current_pending_wave_task_ids == [2]
    assert context.allow_pending_wave_dispatch is True
    assert context.allow_current_task_subdispatch is False
    assert context.recommended_tools == ["dataset_transform"]


def test_normalize_init_task_payload_adds_linear_dependencies_for_high_confidence_pipeline():
    """高置信线性流水线应自动补齐前序 depends_on。"""
    result = TaskManager.normalize_init_task_payload(
        [
            {"id": 1, "title": "读取数据", "status": "pending", "tool_hint": "dataset_catalog"},
            {"id": 2, "title": "预处理数据", "status": "pending", "tool_hint": "dataset_transform"},
            {"id": 3, "title": "统计分析", "status": "pending", "tool_hint": "stat_test"},
            {"id": 4, "title": "绘制柱状图", "status": "pending", "tool_hint": "chart_session"},
        ]
    )

    assert [task["depends_on"] for task in result.tasks] == [[], [1], [2], [3]]
    assert [item["task_id"] for item in result.normalized_dependencies] == [2, 3, 4]
    assert result.normalization_warnings == []


def test_normalize_init_task_payload_warns_on_ambiguous_parallel_like_pipeline():
    """疑似线性但不满足高置信规则时只返回 warning，不静默改写依赖。"""
    result = TaskManager.normalize_init_task_payload(
        [
            {"id": 1, "title": "读取数据", "status": "pending", "tool_hint": "dataset_catalog"},
            {"id": 2, "title": "清洗 A", "status": "pending", "tool_hint": "dataset_transform"},
            {"id": 3, "title": "清洗 B", "status": "pending", "tool_hint": "data_cleaner"},
        ]
    )

    assert [task["depends_on"] for task in result.tasks] == [[], [], []]
    assert result.normalized_dependencies == []
    assert result.normalization_warnings[0]["code"] == "LINEAR_PIPELINE_RISK"


# ---- update_tasks 幂等性检测（no_op_ids） ----


def test_update_tasks_detects_no_op_when_status_unchanged():
    """状态未变化时应返回 no_op_ids。"""
    tm = _make_manager(
        [
            {"id": 1, "title": "数据清洗", "status": "in_progress"},
            {"id": 2, "title": "统计分析", "status": "pending"},
        ]
    )
    result = tm.update_tasks([{"id": 1, "status": "in_progress"}])
    assert result.no_op_ids == [1]
    assert result.manager.tasks[0].status == "in_progress"


def test_update_tasks_no_no_op_when_status_actually_changes():
    """状态实际变化时 no_op_ids 应为空。"""
    tm = _make_manager(
        [
            {"id": 1, "title": "数据清洗", "status": "in_progress"},
            {"id": 2, "title": "统计分析", "status": "pending"},
        ]
    )
    result = tm.update_tasks([{"id": 2, "status": "in_progress"}])
    assert result.no_op_ids == []
    assert result.auto_completed_ids == []
    assert result.manager.tasks[0].status == "in_progress"
    assert result.manager.tasks[1].status == "in_progress"


def test_update_tasks_mixed_no_op_and_real_change():
    """混合场景：部分任务无操作，部分实际变化。"""
    tm = _make_manager(
        [
            {"id": 1, "title": "数据清洗", "status": "completed"},
            {"id": 2, "title": "统计分析", "status": "in_progress"},
        ]
    )
    result = tm.update_tasks(
        [
            {"id": 1, "status": "completed"},  # 无操作
            {"id": 2, "status": "completed"},  # 实际变化
        ]
    )
    assert result.no_op_ids == [1]
    assert result.manager.tasks[1].status == "completed"


def test_update_tasks_preserves_depends_on_when_status_changes():
    """状态更新时不应丢失依赖字段。"""
    tm = _make_manager(
        [
            {"id": 1, "title": "A"},
            {"id": 2, "title": "B", "depends_on": [1], "status": "pending"},
        ]
    )
    result = tm.update_tasks([{"id": 2, "status": "in_progress"}])
    assert result.manager.tasks[1].depends_on == [1]


def test_update_tasks_preserves_extended_metadata():
    """状态更新时不应丢失新增的任务协作元数据。"""
    tm = _make_manager(
        [
            {
                "id": 1,
                "title": "统计分析",
                "status": "pending",
                "executor": "subagent",
                "owner": "statistician",
                "input_refs": ["dataset:cleaned.v1"],
                "output_refs": ["artifact:stats.v1"],
                "tool_profile": "analysis_execution",
            }
        ]
    )
    result = tm.update_tasks([{"id": 1, "status": "in_progress"}])
    task = result.manager.tasks[0]
    assert task.executor == "subagent"
    assert task.owner == "statistician"
    assert task.input_refs == ["dataset:cleaned.v1"]
    assert task.output_refs == ["artifact:stats.v1"]
    assert task.tool_profile == "analysis_execution"
