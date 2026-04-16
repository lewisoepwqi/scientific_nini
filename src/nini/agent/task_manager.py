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

_HIGH_CONFIDENCE_PIPELINE_RANKS: dict[str, int] = {
    "dataset_catalog": 10,
    "dataset_transform": 20,
    "data_cleaner": 20,
    "stat_test": 30,
    "stat_model": 30,
    "chart_session": 40,
    "export_chart": 40,
    "report_session": 50,
    "export_document": 50,
    "export_report": 50,
}
_HIGH_CONFIDENCE_TITLE_RULES: tuple[tuple[int, tuple[str, ...]], ...] = (
    (10, ("读取", "加载", "检查数据", "概览", "审查数据", "查看数据", "profile")),
    (20, ("预处理", "清洗", "整理", "标准化", "转换", "特征工程")),
    (30, ("聚合", "统计", "分析", "建模", "检验", "相关", "回归")),
    (40, ("绘图", "图表", "柱状图", "可视化", "画图")),
    (50, ("报告", "总结", "复盘", "汇总", "导出")),
)


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


@dataclass(frozen=True)
class TaskInitNormalizationResult:
    """任务初始化归一化结果。"""

    tasks: list[dict[str, Any]]
    normalized_task_ids: list[int] = field(default_factory=list)
    normalized_dependencies: list[dict[str, Any]] = field(default_factory=list)
    normalization_warnings: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class DispatchContext:
    """调度上下文。"""

    current_in_progress_task: TaskItem | None = None
    current_pending_wave: list[TaskItem] = field(default_factory=list)
    allow_direct_execution: bool = False
    allow_current_task_subdispatch: bool = False
    allow_pending_wave_dispatch: bool = False
    recommended_tools: list[str] = field(default_factory=list)
    recommended_action: str | None = None

    @property
    def current_in_progress_task_id(self) -> int | None:
        task = self.current_in_progress_task
        return task.id if task is not None else None

    @property
    def current_pending_wave_task_ids(self) -> list[int]:
        return [task.id for task in self.current_pending_wave]

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_in_progress_task_id": self.current_in_progress_task_id,
            "current_pending_wave_task_ids": self.current_pending_wave_task_ids,
            "allow_direct_execution": self.allow_direct_execution,
            "allow_current_task_subdispatch": self.allow_current_task_subdispatch,
            "allow_pending_wave_dispatch": self.allow_pending_wave_dispatch,
            "recommended_tools": list(self.recommended_tools),
            "recommended_action": self.recommended_action,
        }


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

    @classmethod
    def _infer_pipeline_rank(cls, task: dict[str, Any]) -> int | None:
        tool_hint = str(task.get("tool_hint", "") or "").strip().lower()
        if tool_hint in _HIGH_CONFIDENCE_PIPELINE_RANKS:
            return _HIGH_CONFIDENCE_PIPELINE_RANKS[tool_hint]

        title = str(task.get("title", "") or "").strip().lower()
        if not title:
            return None
        for rank, keywords in _HIGH_CONFIDENCE_TITLE_RULES:
            if any(keyword in title for keyword in keywords):
                return rank
        return None

    @classmethod
    def normalize_init_task_payload(
        cls,
        raw_tasks: list[dict[str, Any]],
    ) -> TaskInitNormalizationResult:
        """归一化 init 任务输入，仅对高置信线性流水线补齐依赖。"""
        normalized_tasks: list[dict[str, Any]] = []
        normalized_task_ids: list[int] = []
        normalized_dependencies: list[dict[str, Any]] = []
        normalization_warnings: list[dict[str, Any]] = []

        for index, task in enumerate(raw_tasks, start=1):
            normalized = dict(task)
            task_id = int(normalized.get("id", index))
            raw_status = str(normalized.get("status", "pending")).strip()
            if raw_status != "pending":
                normalized_task_ids.append(task_id)
            normalized["id"] = task_id
            normalized["status"] = "pending"
            raw_depends = normalized.get("depends_on", [])
            if isinstance(raw_depends, list):
                normalized["depends_on"] = [
                    int(dep) for dep in raw_depends if str(dep).strip().isdigit()
                ]
            else:
                normalized["depends_on"] = []
            normalized_tasks.append(normalized)

        if len(normalized_tasks) < 2:
            return TaskInitNormalizationResult(
                tasks=normalized_tasks,
                normalized_task_ids=normalized_task_ids,
                normalized_dependencies=normalized_dependencies,
                normalization_warnings=normalization_warnings,
            )

        ranks = [cls._infer_pipeline_rank(task) for task in normalized_tasks]
        recognized = all(rank is not None for rank in ranks)
        if recognized and all(ranks[i] < ranks[i + 1] for i in range(len(ranks) - 1)):
            for index, task in enumerate(normalized_tasks[1:], start=1):
                prev_id = int(normalized_tasks[index - 1]["id"])
                current_depends = [
                    int(dep)
                    for dep in task.get("depends_on", [])
                    if str(dep).strip().isdigit() and int(dep) < int(task["id"])
                ]
                next_depends = sorted(set(current_depends) | {prev_id})
                if next_depends != current_depends:
                    task["depends_on"] = next_depends
                    normalized_dependencies.append(
                        {
                            "task_id": int(task["id"]),
                            "depends_on": next_depends,
                            "reason": "high_confidence_linear_pipeline",
                        }
                    )
            return TaskInitNormalizationResult(
                tasks=normalized_tasks,
                normalized_task_ids=normalized_task_ids,
                normalized_dependencies=normalized_dependencies,
                normalization_warnings=normalization_warnings,
            )

        if recognized and all(ranks[i] <= ranks[i + 1] for i in range(len(ranks) - 1)):
            task_ids = [int(task["id"]) for task in normalized_tasks]
            normalization_warnings.append(
                {
                    "code": "LINEAR_PIPELINE_RISK",
                    "message": (
                        "检测到疑似线性分析流水线，但当前任务顺序存在并列阶段或依赖歧义，"
                        "系统未自动改写 depends_on。"
                    ),
                    "task_ids": task_ids,
                }
            )

        return TaskInitNormalizationResult(
            tasks=normalized_tasks,
            normalized_task_ids=normalized_task_ids,
            normalized_dependencies=normalized_dependencies,
            normalization_warnings=normalization_warnings,
        )

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

    def current_pending_wave(self) -> list[TaskItem]:
        """返回当前可执行的首个 pending wave。"""
        waves = self.group_into_waves()
        if not waves:
            return []
        return list(waves[0])

    def get_dispatch_context(self) -> DispatchContext:
        """返回当前运行时调度上下文。"""
        current = self.current_in_progress()
        pending_wave = self.current_pending_wave()
        recommended_tools: list[str] = []
        recommended_action: str | None = None

        if current is not None:
            if current.tool_hint:
                recommended_tools.append(str(current.tool_hint))
            recommended_action = "direct_execution"
            return DispatchContext(
                current_in_progress_task=current,
                current_pending_wave=pending_wave,
                allow_direct_execution=True,
                allow_current_task_subdispatch=True,
                allow_pending_wave_dispatch=False,
                recommended_tools=recommended_tools,
                recommended_action=recommended_action,
            )

        if pending_wave:
            first = pending_wave[0]
            if first.tool_hint:
                recommended_tools.append(str(first.tool_hint))
            recommended_action = "start_pending_wave"

        return DispatchContext(
            current_in_progress_task=None,
            current_pending_wave=pending_wave,
            allow_direct_execution=not bool(pending_wave),
            allow_current_task_subdispatch=False,
            allow_pending_wave_dispatch=bool(pending_wave),
            recommended_tools=recommended_tools,
            recommended_action=recommended_action,
        )

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
