"""任务管理器 —— 支持 LLM 自驱动任务生命周期。

LLM 通过 task_state 工具声明并更新任务列表（内部由 TaskWriteTool 处理），TaskManager 管理其状态机。
immutable 风格：所有变更操作返回新对象，不修改原对象。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

TaskStatus = Literal["pending", "in_progress", "completed", "failed", "blocked", "skipped"]
TaskExecutor = Literal["main_agent", "subagent", "local_tool"]
TaskFailurePolicy = Literal["stop_pipeline", "allow_partial", "retryable"]


@dataclass(frozen=True)
class TaskItem:
    """单个分析任务。"""

    id: int  # 1-based，与前端 plan_step_id 对齐
    title: str
    status: TaskStatus = "pending"
    tool_hint: str | None = None
    action_id: str | None = None  # 格式 "task_{id}"，用于 TASK_ATTEMPT 事件关联
    depends_on: list[int] = field(default_factory=list)  # 依赖的任务 id 列表，用于 wave 并行调度
    executor: TaskExecutor | None = None
    owner: str | None = None
    input_refs: list[str] = field(default_factory=list)
    output_refs: list[str] = field(default_factory=list)
    handoff_contract: dict[str, Any] | None = None
    tool_profile: str | None = None
    failure_policy: TaskFailurePolicy | None = None
    acceptance_checks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "tool_hint": self.tool_hint,
            "action_id": self.action_id,
            "depends_on": self.depends_on,
            "executor": self.executor,
            "owner": self.owner,
            "input_refs": list(self.input_refs),
            "output_refs": list(self.output_refs),
            "handoff_contract": self.handoff_contract,
            "tool_profile": self.tool_profile,
            "failure_policy": self.failure_policy,
            "acceptance_checks": list(self.acceptance_checks),
        }


@dataclass(frozen=True)
class UpdateResult:
    """update_tasks 的返回结果。"""

    manager: "TaskManager"
    auto_completed_ids: list[int] = field(default_factory=list)
    no_op_ids: list[int] = field(default_factory=list)


@dataclass
class TaskManager:
    """管理会话内的任务列表。

    使用 immutable 风格：init_tasks/update_tasks 返回新的 TaskManager 实例。
    原实例保持不变，调用方用返回值替换 session.task_manager。
    """

    tasks: list[TaskItem] = field(default_factory=list)
    initialized: bool = False

    @staticmethod
    def _normalize_ref_list(raw_refs: Any) -> list[str]:
        if not isinstance(raw_refs, list):
            return []
        refs: list[str] = []
        for item in raw_refs:
            ref = str(item or "").strip()
            if ref and ref not in refs:
                refs.append(ref)
        return refs

    def init_tasks(self, raw_tasks: list[dict[str, Any]]) -> "TaskManager":
        """用完整任务列表初始化，返回新的 TaskManager。"""
        items: list[TaskItem] = []
        for t in raw_tasks:
            task_id = int(t.get("id", len(items) + 1))
            raw_depends = t.get("depends_on", [])
            depends_on = (
                [int(d) for d in raw_depends if str(d).isdigit()]
                if isinstance(raw_depends, list)
                else []
            )
            items.append(
                TaskItem(
                    id=task_id,
                    title=str(t.get("title", f"任务 {task_id}")),
                    status=t.get("status", "pending"),
                    tool_hint=t.get("tool_hint") or None,
                    action_id=f"task_{task_id}",
                    depends_on=depends_on,
                    executor=t.get("executor") or None,
                    owner=t.get("owner") or None,
                    input_refs=self._normalize_ref_list(t.get("input_refs")),
                    output_refs=self._normalize_ref_list(t.get("output_refs")),
                    handoff_contract=(
                        dict(t.get("handoff_contract"))
                        if isinstance(t.get("handoff_contract"), dict)
                        else None
                    ),
                    tool_profile=t.get("tool_profile") or None,
                    failure_policy=t.get("failure_policy") or None,
                    acceptance_checks=self._normalize_ref_list(t.get("acceptance_checks")),
                )
            )
        return TaskManager(tasks=items, initialized=True)

    @staticmethod
    def _tasks_conflict(left: TaskItem, right: TaskItem) -> bool:
        """判断两个任务是否存在读写冲突，冲突任务不能落入同一 wave。"""
        left_inputs = set(left.input_refs)
        left_outputs = set(left.output_refs)
        right_inputs = set(right.input_refs)
        right_outputs = set(right.output_refs)
        if not left_outputs and not right_outputs:
            return False
        if left_outputs & right_outputs:
            return True
        if left_outputs & right_inputs:
            return True
        if right_outputs & left_inputs:
            return True
        return False

    def _take_conflict_free_wave(
        self, ready: list[TaskItem]
    ) -> tuple[list[TaskItem], list[TaskItem]]:
        """从 ready 中贪心取出一个无冲突 wave，并返回剩余任务。"""
        if not ready:
            return [], []
        selected: list[TaskItem] = []
        deferred: list[TaskItem] = []
        for task in sorted(ready, key=lambda item: item.id):
            if any(self._tasks_conflict(task, existing) for existing in selected):
                deferred.append(task)
                continue
            selected.append(task)
        return selected, deferred

    def group_into_waves(self) -> list[list[TaskItem]]:
        """拓扑排序将任务分组为并行 wave。

        同一 wave 内的任务互不依赖，可通过 asyncio.gather() 并行触发。
        只考虑 pending 状态的任务，已完成/跳过/失败的任务不参与分组。

        Returns:
            有序的 wave 列表，每个 wave 是可并行执行的任务列表。
            若存在循环依赖则退化为顺序执行（每个任务单独一个 wave）。
        """
        pending = [t for t in self.tasks if t.status == "pending"]
        id_to_task = {t.id: t for t in pending}

        # 拓扑排序（Kahn 算法）
        in_degree = {t.id: 0 for t in pending}
        for t in pending:
            for dep in t.depends_on:
                if dep in id_to_task:
                    in_degree[t.id] += 1

        waves: list[list[TaskItem]] = []
        ready = [t for t in pending if in_degree[t.id] == 0]

        while ready:
            wave, deferred = self._take_conflict_free_wave(ready)
            if not wave:
                break
            waves.append(wave)
            next_ready = list(deferred)
            for task in wave:
                # 找出依赖当前 task 的后继
                for other in pending:
                    if task.id in other.depends_on:
                        in_degree[other.id] -= 1
                        if (
                            in_degree[other.id] == 0
                            and other not in next_ready
                            and other not in wave
                        ):
                            next_ready.append(other)
            ready = next_ready

        # 检测循环依赖：若有 pending 任务未被分组，退化为顺序执行
        grouped_ids = {t.id for wave in waves for t in wave}
        remaining = [t for t in pending if t.id not in grouped_ids]
        if remaining:
            for t in remaining:
                waves.append([t])

        return waves

    def update_tasks(self, raw_updates: list[dict[str, Any]]) -> "UpdateResult":
        """按 id 更新部分任务状态，返回 UpdateResult。"""
        update_map: dict[int, dict[str, Any]] = {int(t["id"]): t for t in raw_updates if "id" in t}

        auto_completed_ids: list[int] = []
        no_op_ids: list[int] = []
        new_tasks: list[TaskItem] = []
        for task in self.tasks:
            if task.id in update_map:
                upd = update_map[task.id]
                new_status = upd.get("status", task.status)
                # 检测状态未实际变化的无操作调用（用于打破 LLM 循环）
                if new_status == task.status:
                    no_op_ids.append(task.id)
                new_tasks.append(
                    TaskItem(
                        id=task.id,
                        title=str(upd.get("title", task.title)),
                        status=new_status,
                        tool_hint=upd.get("tool_hint", task.tool_hint),
                        action_id=task.action_id,
                        depends_on=list(task.depends_on),
                        executor=upd.get("executor", task.executor),
                        owner=upd.get("owner", task.owner),
                        input_refs=self._normalize_ref_list(upd.get("input_refs", task.input_refs)),
                        output_refs=self._normalize_ref_list(
                            upd.get("output_refs", task.output_refs)
                        ),
                        handoff_contract=(
                            dict(upd["handoff_contract"])
                            if isinstance(upd.get("handoff_contract"), dict)
                            else task.handoff_contract
                        ),
                        tool_profile=upd.get("tool_profile", task.tool_profile),
                        failure_policy=upd.get("failure_policy", task.failure_policy),
                        acceptance_checks=self._normalize_ref_list(
                            upd.get("acceptance_checks", task.acceptance_checks)
                        ),
                    )
                )
            else:
                new_tasks.append(task)
        new_manager = TaskManager(tasks=new_tasks, initialized=self.initialized)
        return UpdateResult(
            manager=new_manager,
            auto_completed_ids=auto_completed_ids,
            no_op_ids=no_op_ids,
        )

    def all_completed(self) -> bool:
        """所有任务均已到达终态（completed/failed/skipped）。"""
        terminal = {"completed", "failed", "skipped"}
        return bool(self.tasks) and all(t.status in terminal for t in self.tasks)

    def has_tasks(self) -> bool:
        """是否已声明了任务。"""
        return self.initialized and bool(self.tasks)

    def current_in_progress(self) -> TaskItem | None:
        """返回当前第一个 in_progress 状态的任务（用于 TASK_ATTEMPT 事件的 action_id 关联）。"""
        for t in self.tasks:
            if t.status == "in_progress":
                return t
        return None

    def to_analysis_plan_dict(self) -> dict[str, Any]:
        """转换为前端 ANALYSIS_PLAN 事件的 data 格式（兼容 store.ts 现有处理逻辑）。"""
        return {
            "steps": [
                {
                    "id": t.id,
                    "title": t.title,
                    "tool_hint": t.tool_hint,
                    "status": t.status,
                    "action_id": t.action_id,
                    "depends_on": t.depends_on,
                    "executor": t.executor,
                    "owner": t.owner,
                    "input_refs": list(t.input_refs),
                    "output_refs": list(t.output_refs),
                    "handoff_contract": t.handoff_contract,
                    "tool_profile": t.tool_profile,
                    "failure_policy": t.failure_policy,
                    "acceptance_checks": list(t.acceptance_checks),
                }
                for t in self.tasks
            ],
            "raw_text": "",
        }

    def pending_count(self) -> int:
        """尚未开始的任务数（仅 pending 状态）。"""
        return sum(1 for t in self.tasks if t.status == "pending")

    def remaining_count(self) -> int:
        """还未完成的任务数（pending + in_progress）。"""
        return sum(1 for t in self.tasks if t.status in ("pending", "in_progress"))
