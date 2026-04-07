"""DAG 执行引擎 —— 基于拓扑排序的 wave 并行执行器。

将带依赖声明的任务列表通过 Kahn 算法分组为执行 wave，
同一 wave 内并行执行，wave 间串行并将前序结果摘要注入下一 wave。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from nini.agent.task_manager import TaskManager

logger = logging.getLogger(__name__)


@dataclass
class DagTask:
    """DAG 任务节点。"""

    task: str  # 任务描述文本
    id: str  # 唯一标识符（字符串形式）
    depends_on: list[str] = field(default_factory=list)  # 依赖的任务 id 列表
    agent_id: str = ""  # 路由后对应的 agent_id


class DagExecutor:
    """DAG 拓扑波次执行引擎（纯计算类，无状态）。

    不持有任何实例状态——每次调用 build_waves / execute 均从参数构建逻辑。
    可在 execute() 内直接实例化，无需依赖注入。
    """

    def build_waves(self, tasks: list[DagTask]) -> list[list[DagTask]]:
        """将 DagTask 列表拓扑排序为执行 wave。

        同一 wave 内的任务互不依赖，可并行执行；wave 间按依赖顺序串行推进。

        若检测到循环依赖，记录 ERROR 并将所有任务降级为单一串行波次（每个任务独占一个 wave）。

        Args:
            tasks: 带依赖声明的任务列表

        Returns:
            有序 wave 列表；循环依赖时每个任务单独一个 wave。
        """
        if not tasks:
            return []

        # 将 DagTask 转换为 TaskManager 识别的整数 id 映射
        # 使用字符串 id → 整数 id 的映射表（Kahn 算法基于整数 id）
        str_id_to_int: dict[str, int] = {t.id: idx + 1 for idx, t in enumerate(tasks)}
        int_to_dag_task: dict[int, DagTask] = {str_id_to_int[t.id]: t for t in tasks}

        raw_tasks: list[dict[str, Any]] = []
        for t in tasks:
            int_id = str_id_to_int[t.id]
            # 只保留在任务列表中存在的依赖（过滤无效引用）
            valid_deps = [str_id_to_int[dep] for dep in t.depends_on if dep in str_id_to_int]
            if len(valid_deps) < len(t.depends_on):
                invalid = [dep for dep in t.depends_on if dep not in str_id_to_int]
                logger.warning(
                    "DagExecutor.build_waves: 任务 '%s' 引用了不存在的依赖 %s，已忽略",
                    t.id,
                    invalid,
                )
            raw_tasks.append({"id": int_id, "title": t.task, "depends_on": valid_deps})

        manager = TaskManager().init_tasks(raw_tasks)
        int_waves = manager.group_into_waves()

        # 检测循环依赖：group_into_waves 返回的 wave 总任务数应等于输入任务数
        total_in_waves = sum(len(w) for w in int_waves)
        if total_in_waves < len(tasks):
            # 计算未被分组的任务 id
            grouped_int_ids = {t.id for wave in int_waves for t in wave}
            remaining_ids = [
                dag_task.id
                for int_id, dag_task in int_to_dag_task.items()
                if int_id not in grouped_int_ids
            ]
            logger.error(
                "DagExecutor.build_waves: 检测到循环依赖，涉及任务 %s，降级为串行执行",
                remaining_ids,
            )
            # 降级：每个任务单独一个 wave，保持原始顺序
            return [[t] for t in tasks]

        # 将整数 TaskItem wave 映射回 DagTask wave
        dag_waves: list[list[DagTask]] = []
        for wave in int_waves:
            dag_wave = [int_to_dag_task[item.id] for item in wave]
            dag_waves.append(dag_wave)

        return dag_waves

    async def execute(
        self,
        waves: list[list[DagTask]],
        session: Any,
        spawner: Any,
        router: Any,
        turn_id: str | None = None,
        preflight_reporter: Any = None,
    ) -> list[Any]:
        """按 wave 顺序执行所有任务，wave 间注入前序摘要。

        Args:
            waves: build_waves() 返回的 wave 列表
            session: 父会话
            spawner: SubAgentSpawner 实例
            _router: TaskRouter 实例（为未来条件路由扩展预留，当前未使用）
            turn_id: 父会话 turn ID，透传给 spawn_batch

        Returns:
            所有子 Agent 的结果列表（按 wave 顺序，wave 内按 spawn_batch 返回顺序）
        """
        del router  # 为未来条件路由扩展预留，当前未使用
        all_results: list[Any] = []
        prev_wave_results: list[Any] = []

        for wave in waves:
            # 将前序摘要注入当前 wave 的任务描述
            injected_wave = _inject_context(wave, prev_wave_results)

            # 构造 (agent_id, task_text) 对
            task_pairs = [(t.agent_id, t.task) for t in injected_wave]

            preflight_plan = None
            if hasattr(spawner, "preflight_batch"):
                preflight_plan = await spawner.preflight_batch(
                    task_pairs,
                    session,
                    parent_turn_id=turn_id,
                    emit_agent_errors=False,
                )
                if preflight_reporter is not None:
                    payload = {
                        "task_count": len(task_pairs),
                        "routed_task_count": len(task_pairs),
                        "runnable_count": preflight_plan.runnable_count,
                        "preflight_failure_count": preflight_plan.failure_count,
                        "routing_failure_count": 0,
                        "preflight_failures": [
                            {
                                "agent_id": result.agent_id,
                                "agent_name": result.agent_name,
                                "task": result.task,
                                "error": result.error or result.summary,
                            }
                            for result in preflight_plan.failed_results
                        ],
                    }
                    maybe_coro = preflight_reporter(payload)
                    if hasattr(maybe_coro, "__await__"):
                        await maybe_coro

            # 并行执行当前 wave
            wave_results = await spawner.spawn_batch(
                task_pairs,
                session,
                parent_turn_id=turn_id,
                preflight_plan=preflight_plan,
            )
            all_results.extend(wave_results)
            prev_wave_results = list(wave_results)

        return all_results


def _inject_context(
    wave_tasks: list[DagTask],
    completed_results: list[Any],
) -> list[DagTask]:
    """将前序 wave 成功任务的摘要注入当前 wave 的任务描述前缀。

    每条摘要截断为 200 字符，防止上下文膨胀。
    """
    context_lines = [
        f"[{r.agent_id}] {(r.summary or '')[:200]}"
        for r in completed_results
        if getattr(r, "success", False) and getattr(r, "summary", "")
    ]
    if not context_lines:
        return wave_tasks

    context_prefix = "前序 Agent 结果摘要：\n" + "\n".join(context_lines) + "\n\n"
    return [
        DagTask(
            task=context_prefix + t.task,
            id=t.id,
            depends_on=t.depends_on,
            agent_id=t.agent_id,
        )
        for t in wave_tasks
    ]
