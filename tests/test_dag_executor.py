"""测试 DagExecutor —— 拓扑排序、wave 分组、循环依赖回退、摘要注入。"""

from __future__ import annotations

from typing import Any

import pytest

from nini.agent.dag_executor import DagExecutor, DagTask, _inject_context
from nini.agent.spawner import BatchPreflightPlan, SubAgentResult

# ─── 辅助 ──────────────────────────────────────────────────────────────────────


def _task(
    tid: str,
    task: str = "",
    depends_on: list[str] | None = None,
    agent_id: str = "",
) -> DagTask:
    return DagTask(
        task=task or tid,
        id=tid,
        depends_on=depends_on or [],
        agent_id=agent_id or tid,
    )


def _result(agent_id: str, summary: str = "", success: bool = True) -> SubAgentResult:
    return SubAgentResult(agent_id=agent_id, success=success, summary=summary)


class _MockSpawner:
    """记录 spawn_batch 调用顺序的 mock。"""

    def __init__(self, results_per_wave: list[list[SubAgentResult]] | None = None) -> None:
        self.call_args: list[list[tuple[str, str]]] = []
        self._results_per_wave = results_per_wave or []
        self._call_index = 0

    async def spawn_batch(
        self,
        tasks: list[tuple[str, str]],
        _session: Any,
        **_kwargs: Any,
    ) -> list[SubAgentResult]:
        self.call_args.append(list(tasks))
        if self._call_index < len(self._results_per_wave):
            results = self._results_per_wave[self._call_index]
        else:
            results = [_result(agent_id) for agent_id, _ in tasks]
        self._call_index += 1
        return results

    async def preflight_batch(
        self,
        tasks: list[tuple[str, str]],
        _session: Any,
        **_kwargs: Any,
    ) -> BatchPreflightPlan:
        return BatchPreflightPlan(
            ordered_results=[None] * len(tasks),
            executable_tasks=[
                (index, agent_id, task) for index, (agent_id, task) in enumerate(tasks, start=1)
            ],
        )


# ─── build_waves ───────────────────────────────────────────────────────────────


def test_build_waves_no_dependency():
    """无依赖任务全部放入同一 wave。"""
    executor = DagExecutor()
    tasks = [_task("A"), _task("B"), _task("C")]
    waves = executor.build_waves(tasks)
    assert len(waves) == 1
    wave_ids = {t.id for t in waves[0]}
    assert wave_ids == {"A", "B", "C"}


def test_build_waves_chain():
    """链式依赖产生 3 个波次：A → B → C。"""
    executor = DagExecutor()
    tasks = [
        _task("A"),
        _task("B", depends_on=["A"]),
        _task("C", depends_on=["B"]),
    ]
    waves = executor.build_waves(tasks)
    assert len(waves) == 3
    assert [t.id for t in waves[0]] == ["A"]
    assert [t.id for t in waves[1]] == ["B"]
    assert [t.id for t in waves[2]] == ["C"]


def test_build_waves_fanout():
    """扇出：A → B, A → C，B 和 C 同一 wave 并行。"""
    executor = DagExecutor()
    tasks = [
        _task("A"),
        _task("B", depends_on=["A"]),
        _task("C", depends_on=["A"]),
    ]
    waves = executor.build_waves(tasks)
    assert len(waves) == 2
    assert [t.id for t in waves[0]] == ["A"]
    assert {t.id for t in waves[1]} == {"B", "C"}


def test_build_waves_fanin():
    """扇入：B → C, A → C，C 在第三 wave。"""
    executor = DagExecutor()
    tasks = [
        _task("A"),
        _task("B"),
        _task("C", depends_on=["A", "B"]),
    ]
    waves = executor.build_waves(tasks)
    assert len(waves) == 2
    assert {t.id for t in waves[0]} == {"A", "B"}
    assert {t.id for t in waves[1]} == {"C"}


def test_build_waves_diamond():
    """菱形拓扑：A → B, A → C, B+C → D。"""
    executor = DagExecutor()
    tasks = [
        _task("A"),
        _task("B", depends_on=["A"]),
        _task("C", depends_on=["A"]),
        _task("D", depends_on=["B", "C"]),
    ]
    waves = executor.build_waves(tasks)
    assert len(waves) == 3
    assert {t.id for t in waves[0]} == {"A"}
    assert {t.id for t in waves[1]} == {"B", "C"}
    assert {t.id for t in waves[2]} == {"D"}


def test_build_waves_circular_dependency_fallback():
    """循环依赖时：记录 ERROR 并降级为每任务一个 wave（串行）。"""
    executor = DagExecutor()
    tasks = [
        _task("A", depends_on=["B"]),
        _task("B", depends_on=["A"]),
    ]
    waves = executor.build_waves(tasks)
    # 降级：每个任务单独一个 wave
    assert len(waves) == len(tasks)
    all_ids = [wave[0].id for wave in waves]
    assert set(all_ids) == {"A", "B"}


def test_build_waves_empty():
    """空任务列表返回空 wave 列表。"""
    executor = DagExecutor()
    assert executor.build_waves([]) == []


def test_build_waves_invalid_depends_on_ignored(caplog):
    """引用不存在的依赖 id 时记录 WARNING 并忽略该依赖（任务仍被执行）。"""
    import logging

    executor = DagExecutor()
    tasks = [_task("A", depends_on=["X_NONEXISTENT"])]
    with caplog.at_level(logging.WARNING, logger="nini.agent.dag_executor"):
        waves = executor.build_waves(tasks)
    assert len(waves) == 1
    assert waves[0][0].id == "A"
    assert "X_NONEXISTENT" in caplog.text


# ─── _inject_context ───────────────────────────────────────────────────────────


def test_inject_context_empty_results():
    """无前序结果时任务描述不变。"""
    tasks = [_task("A", task="原始任务")]
    injected = _inject_context(tasks, [])
    assert injected[0].task == "原始任务"


def test_inject_context_success_result():
    """成功任务的摘要注入为前缀。"""
    tasks = [_task("B", task="统计分析")]
    results = [_result("agent_a", summary="清洗完成，删除 3 行异常值")]
    injected = _inject_context(tasks, results)
    assert "前序 Agent 结果摘要：" in injected[0].task
    assert "[agent_a] 清洗完成，删除 3 行异常值" in injected[0].task
    assert "统计分析" in injected[0].task


def test_inject_context_failed_result_not_injected():
    """失败任务的摘要不注入。"""
    tasks = [_task("B", task="分析")]
    results = [_result("agent_a", summary="失败摘要", success=False)]
    injected = _inject_context(tasks, results)
    assert injected[0].task == "分析"


def test_inject_context_summary_truncated():
    """摘要截断为 200 字符。"""
    long_summary = "X" * 300
    tasks = [_task("B", task="任务")]
    results = [_result("agent_a", summary=long_summary)]
    injected = _inject_context(tasks, results)
    # 注入的摘要部分长度不超过 200
    assert "X" * 201 not in injected[0].task
    assert "X" * 200 in injected[0].task


# ─── execute ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_single_wave():
    """单 wave 执行：spawn_batch 调用一次，返回结果。"""
    executor = DagExecutor()
    tasks = [_task("A", agent_id="data_cleaner"), _task("B", agent_id="statistician")]
    waves = [[tasks[0], tasks[1]]]  # 手动构造单 wave
    spawner = _MockSpawner()
    results = await executor.execute(waves, session=None, spawner=spawner, router=None)
    assert len(spawner.call_args) == 1
    assert len(results) == 2


@pytest.mark.asyncio
async def test_execute_chain_injects_summary():
    """链式依赖：wave1 结果摘要注入 wave2 任务描述。"""
    executor = DagExecutor()
    wave1 = [_task("A", task="清洗数据", agent_id="cleaner")]
    wave2 = [_task("B", task="统计分析", depends_on=["A"], agent_id="statistician")]

    wave1_results = [_result("cleaner", summary="清洗完成，删除 3 行")]
    spawner = _MockSpawner(results_per_wave=[wave1_results, [_result("statistician")]])

    await executor.execute([wave1, wave2], session=None, spawner=spawner, router=None)

    assert len(spawner.call_args) == 2
    # wave2 任务描述应包含 wave1 的摘要
    wave2_task_text = spawner.call_args[1][0][1]
    assert "清洗完成，删除 3 行" in wave2_task_text


@pytest.mark.asyncio
async def test_execute_no_injection_for_failed_wave():
    """wave1 全部失败时，wave2 任务描述不含摘要前缀。"""
    executor = DagExecutor()
    wave1 = [_task("A", task="清洗数据", agent_id="cleaner")]
    wave2 = [_task("B", task="分析", depends_on=["A"], agent_id="statistician")]

    wave1_results = [_result("cleaner", summary="失败摘要", success=False)]
    spawner = _MockSpawner(results_per_wave=[wave1_results, [_result("statistician")]])

    await executor.execute([wave1, wave2], session=None, spawner=spawner, router=None)

    wave2_task_text = spawner.call_args[1][0][1]
    assert "前序 Agent 结果摘要" not in wave2_task_text


@pytest.mark.asyncio
async def test_execute_empty_waves():
    """空 wave 列表返回空结果。"""
    executor = DagExecutor()
    spawner = _MockSpawner()
    results = await executor.execute([], session=None, spawner=spawner, router=None)
    assert results == []
    assert spawner.call_args == []


@pytest.mark.asyncio
async def test_execute_reports_wave_preflight_summary():
    """DAG wave 执行前应上报每一波的预检摘要。"""
    executor = DagExecutor()
    wave1 = [_task("A", task="清洗数据", agent_id="cleaner")]
    wave2 = [_task("B", task="统计分析", depends_on=["A"], agent_id="statistician")]
    spawner = _MockSpawner()
    reported: list[dict[str, Any]] = []

    await executor.execute(
        [wave1, wave2],
        session=None,
        spawner=spawner,
        router=None,
        preflight_reporter=lambda payload: reported.append(payload),
    )

    assert len(reported) == 2
    assert reported[0]["task_count"] == 1
    assert reported[0]["runnable_count"] == 1
