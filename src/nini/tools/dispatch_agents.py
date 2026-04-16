"""dispatch_agents 工具 —— 将任务并行分发给多个 Specialist Agent 后拼接原始结果。

继承 tools/base.py:Tool，主 Agent 直接声明 agent_id，通过 SubAgentSpawner 并行执行，
各子 Agent 原始输出拼接后返回，主 Agent 自行综合。
该工具不暴露给子 Agent（防止递归派发），仅主 Agent 可调用。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from nini.agent.session import session_manager
from nini.agent.spawner import SubAgentResult
from nini.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)


def _build_legacy_agent_item_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "agent_id": {
                "type": "string",
                "description": "目标 Agent 的 ID，必须是可用列表中的合法值",
            },
            "task": {
                "type": "string",
                "description": "分配给该 Agent 的具体任务描述",
            },
        },
        "required": ["agent_id", "task"],
        "additionalProperties": False,
    }


def _build_dispatch_task_item_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "integer",
                "description": "任务 ID，应与 task_state/task_write 中的任务 ID 对齐",
            },
            "parent_task_id": {
                "type": "integer",
                "description": "当前进行中主任务 ID，用于当前任务内部子派发",
            },
            "agent_id": {
                "type": "string",
                "description": "目标 Agent 的 ID，必须是可派发 specialist",
            },
            "task": {
                "type": "string",
                "description": "分配给该 Agent 的具体任务描述",
            },
            "depends_on": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "任务的前置依赖，用于校验该任务是否已进入当前可执行 wave",
            },
            "input_refs": {
                "type": "array",
                "items": {"type": "string"},
                "description": "任务输入引用列表",
            },
            "output_refs": {
                "type": "array",
                "items": {"type": "string"},
                "description": "任务输出引用列表",
            },
            "expected_output": {
                "type": "object",
                "description": "期望结构化输出契约",
            },
            "tool_profile": {
                "type": "string",
                "description": "建议子 Agent 使用的工具档位",
            },
        },
        "required": ["agent_id", "task"],
        "oneOf": [{"required": ["task_id"]}, {"required": ["parent_task_id"]}],
        "additionalProperties": False,
    }


class DispatchAgentsTool(Tool):
    """多 Agent 并行派发工具。

    主 Agent 直接声明 agent_id 和任务描述，工具并行执行后拼接各子 Agent 原始输出返回。
    """

    def __init__(
        self,
        agent_registry: Any = None,
        spawner: Any = None,
    ) -> None:
        self._agent_registry = agent_registry
        self._spawner = spawner

    @property
    def name(self) -> str:
        return "dispatch_agents"

    @property
    def description(self) -> str:
        return (
            "将同一 wave 中相互独立的任务并行分发给多个专业 Agent 执行。"
            "只适用于当前可执行 wave 内、无共享写目标、无上下游读写冲突的任务。"
            "推荐传 tasks=[{task_id, agent_id, task, input_refs, output_refs}]；"
            "当前进行中任务的内部子派发使用 tasks=[{parent_task_id, agent_id, task}]；"
            "旧格式 agents=[{agent_id, task}] 仅在无歧义任务上下文时兼容。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "agents": {
                    "type": "array",
                    "items": _build_legacy_agent_item_schema(),
                    "description": "兼容旧格式的并行 Agent 任务列表",
                },
                "wave_id": {
                    "type": "string",
                    "description": "（可选）当前并行波次 ID，用于审计和前端展示",
                },
                "tasks": {
                    "type": "array",
                    "items": _build_dispatch_task_item_schema(),
                    "description": "结构化并行任务列表。仅允许同一 wave 的独立任务。",
                },
            },
            "anyOf": [{"required": ["agents"]}, {"required": ["tasks"]}],
        }

    @property
    def category(self) -> str:
        return "utility"

    @property
    def expose_to_llm(self) -> bool:
        # 通过 Orchestrator 路径暴露，不走普通工具白名单
        return False

    async def execute(
        self,
        session: Any,
        *,
        agents: list[dict[str, Any]] | None = None,
        tasks: list[dict[str, Any]] | None = None,
        wave_id: str | None = None,
        turn_id: str | None = None,
        tool_call_id: str | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        del kwargs  # 吸收框架可能传入的额外参数
        """执行多 Agent 并行派发。

        Args:
            session: 当前会话
            agents: 兼容旧格式的 Agent 任务列表，每项含 agent_id 和 task
            tasks: 结构化任务列表
            turn_id: 父会话 turn ID

        Returns:
            ToolResult，message 字段包含各子 Agent 原始输出拼接文本
        """
        if self._spawner is None:
            return ToolResult(
                success=False,
                message="dispatch_agents 未正确初始化，spawner 未注入。",
                metadata={"error_code": "DISPATCH_AGENTS_NOT_INITIALIZED"},
            )

        task_specs = self._normalize_task_specs(tasks=tasks, agents=agents)
        dispatch_run_id = self._build_dispatch_run_id(turn_id=turn_id, tool_call_id=tool_call_id)
        dispatch_context = self._get_dispatch_context(session)

        # 空任务列表：agents 和 tasks 均为空，视为参数错误
        if not task_specs:
            return ToolResult(
                success=False,
                message=(
                    "dispatch_agents 未收到任何任务：agents 和 tasks 均为空或未提供。\n"
                    "请使用 tasks=[{task_id, agent_id, task}] 格式指定至少一个任务。"
                ),
                metadata={
                    "error_code": "DISPATCH_AGENTS_NO_TASKS",
                    "agent_count": 0,
                    "wave_id": wave_id,
                },
            )

        if self._legacy_agents_require_structured_tasks(dispatch_context=dispatch_context, tasks=tasks):
            payload = self._build_context_error_payload(
                error_code="DISPATCH_TASK_CONTEXT_REQUIRED",
                message=(
                    "当前会话存在会影响派发语义的任务上下文。"
                    "请改用结构化 tasks=[{task_id,...}] 或 tasks=[{parent_task_id,...}]，"
                    "不要继续使用 agents=[...]."
                ),
                dispatch_context=dispatch_context,
                recovery_action="migrate_to_structured_tasks",
                recommended_dispatch_shape="tasks=[{task_id, agent_id, task}]",
                tool_misuse_category="legacy_agents_context_ambiguous",
            )
            return ToolResult(
                success=False,
                message=payload["message"],
                data=payload,
                metadata=payload,
            )

        # 校验所有 agent_id 合法性
        invalid_ids = self._validate_agent_ids(task_specs)
        if invalid_ids:
            available = self._list_available_agent_ids()
            payload = self._build_context_error_payload(
                error_code="INVALID_AGENT_IDS",
                message=(
                    f"以下 agent_id 不存在：{', '.join(invalid_ids)}。\n"
                    f"可用 agent_id：{', '.join(available)}"
                ),
                dispatch_context=dispatch_context,
                recovery_action="use_registered_agent_ids",
                recommended_dispatch_shape="tasks=[{task_id, agent_id, task}]",
                tool_misuse_category="invalid_agent_id",
                invalid_ids=invalid_ids,
                available_ids=available,
            )
            return ToolResult(
                success=False,
                message=payload["message"],
                data=payload,
                metadata=payload,
            )

        validation_error = self._validate_parallel_task_specs(
            session,
            task_specs,
            dispatch_context=dispatch_context,
            enforce_current_wave=isinstance(tasks, list) and bool(tasks),
        )
        if validation_error is not None:
            return ToolResult(
                success=False,
                message=validation_error["message"],
                data={**validation_error, "wave_id": wave_id},
                metadata={**validation_error, "wave_id": wave_id},
            )

        # 构造 (agent_id, task) 对
        task_pairs = [
            (str(item["agent_id"]), self._build_structured_task_prompt(item)) for item in task_specs
        ]

        # 推送 dispatch 开始事件
        await self._push_dispatch_workflow_event(
            session=session,
            turn_id=turn_id,
            dispatch_run_id=dispatch_run_id,
            phase="started",
            payload={"agent_count": len(task_pairs), "wave_id": wave_id},
        )

        # 并行执行
        sub_results: list[SubAgentResult] = await self._spawner.spawn_batch(
            task_pairs,
            session,
            parent_turn_id=turn_id,
        )

        # 拼接原始输出
        subtasks_payload = self._build_subtask_payload(task_specs, sub_results)
        message = self._build_result_message(sub_results, task_specs)

        # 统计
        success_count = sum(1 for r in sub_results if r.success)
        failure_count = sum(
            1 for r in sub_results if not r.success and not getattr(r, "stopped", False)
        )
        stopped_count = sum(1 for r in sub_results if getattr(r, "stopped", False))
        dispatch_success = success_count > 0 or (failure_count == 0 and stopped_count == 0)
        dispatch_mode = self._resolve_dispatch_mode(task_specs)
        parent_task_id = next(
            (int(item["parent_task_id"]) for item in task_specs if item.get("parent_task_id") is not None),
            None,
        )

        # 记录运行事件
        self._record_dispatch_run_events(
            session=session,
            dispatch_run_id=dispatch_run_id,
            turn_id=turn_id,
            sub_results=sub_results,
            task_specs=task_specs,
            wave_id=wave_id,
        )

        await self._push_dispatch_workflow_event(
            session=session,
            turn_id=turn_id,
            dispatch_run_id=dispatch_run_id,
            phase="completed",
            payload={
                "agent_count": len(task_pairs),
                "success_count": success_count,
                "failure_count": failure_count,
                "stopped_count": stopped_count,
                "wave_id": wave_id,
                "subtasks": subtasks_payload,
            },
        )

        return ToolResult(
            success=dispatch_success,
            message=message,
            metadata={
                "agent_count": len(task_pairs),
                "success_count": success_count,
                "failure_count": failure_count,
                "stopped_count": stopped_count,
                "dispatch_run_id": dispatch_run_id,
                "wave_id": wave_id,
                "dispatch_mode": dispatch_mode,
                "current_in_progress_task_id": (
                    dispatch_context.current_in_progress_task_id if dispatch_context else None
                ),
                "current_pending_wave_task_ids": (
                    dispatch_context.current_pending_wave_task_ids if dispatch_context else []
                ),
                "parent_task_id": parent_task_id,
                "subtasks": subtasks_payload,
            },
            data={
                "dispatch_mode": dispatch_mode,
                "current_in_progress_task_id": (
                    dispatch_context.current_in_progress_task_id if dispatch_context else None
                ),
                "current_pending_wave_task_ids": (
                    dispatch_context.current_pending_wave_task_ids if dispatch_context else []
                ),
                "parent_task_id": parent_task_id,
                "subtasks": subtasks_payload,
            },
        )

    def _normalize_task_specs(
        self,
        *,
        tasks: list[dict[str, Any]] | None,
        agents: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        raw_specs = (
            tasks
            if isinstance(tasks, list) and tasks
            else agents if isinstance(agents, list) else []
        )
        normalized: list[dict[str, Any]] = []
        using_legacy_agents = not (isinstance(tasks, list) and tasks)
        for index, item in enumerate(raw_specs, start=1):
            if not isinstance(item, dict):
                continue
            try:
                task_id = int(item.get("task_id", index))
            except (TypeError, ValueError):
                task_id = index
            raw_parent_task_id = item.get("parent_task_id")
            parent_task_id: int | None = None
            if str(raw_parent_task_id or "").strip().isdigit():
                parent_task_id = int(raw_parent_task_id)
            normalized.append(
                {
                    "task_id": task_id if parent_task_id is None else None,
                    "parent_task_id": parent_task_id,
                    "agent_id": str(item.get("agent_id", "")).strip(),
                    "task": str(item.get("task", "")).strip(),
                    "depends_on": (
                        [
                            int(dep)
                            for dep in item.get("depends_on", [])
                            if str(dep).strip().isdigit()
                        ]
                        if isinstance(item.get("depends_on"), list)
                        else []
                    ),
                    "input_refs": self._normalize_ref_list(item.get("input_refs")),
                    "output_refs": self._normalize_ref_list(item.get("output_refs")),
                    "expected_output": (
                        dict(item.get("expected_output"))
                        if isinstance(item.get("expected_output"), dict)
                        else None
                    ),
                    "tool_profile": str(item.get("tool_profile", "")).strip() or None,
                    "legacy_shape": using_legacy_agents,
                }
            )
        return normalized

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

    def _validate_agent_ids(self, task_specs: list[dict[str, Any]]) -> list[str]:
        """返回不存在于 AgentRegistry 的非法 agent_id 列表。"""
        if self._agent_registry is None:
            return []
        if hasattr(self._agent_registry, "list_dispatchable_agents"):
            available = {
                a.agent_id for a in (self._agent_registry.list_dispatchable_agents() or [])
            }
        else:
            available = {a.agent_id for a in (self._agent_registry.list_agents() or [])}
        if not available:
            return []
        return [item["agent_id"] for item in task_specs if item.get("agent_id") not in available]

    def _list_available_agent_ids(self) -> list[str]:
        """返回当前已注册的所有 agent_id 列表。"""
        if self._agent_registry is None:
            return []
        if hasattr(self._agent_registry, "list_dispatchable_agents"):
            agents = self._agent_registry.list_dispatchable_agents() or []
        else:
            agents = self._agent_registry.list_agents() or []
        return [a.agent_id for a in agents]

    @staticmethod
    def _get_dispatch_context(session: Any) -> Any | None:
        """返回当前 session 的 dispatch context；无任务图时返回 None。"""
        manager = getattr(session, "task_manager", None)
        if manager is None or not hasattr(manager, "get_dispatch_context"):
            return None
        return manager.get_dispatch_context()

    @staticmethod
    def _resolve_dispatch_mode(task_specs: list[dict[str, Any]]) -> str:
        if not task_specs:
            return "unknown"
        modes = {
            "current_task_subdispatch" if item.get("parent_task_id") is not None else "pending_wave"
            for item in task_specs
        }
        if len(modes) == 1:
            return next(iter(modes))
        return "mixed"

    @staticmethod
    def _legacy_agents_require_structured_tasks(
        *,
        dispatch_context: Any | None,
        tasks: list[dict[str, Any]] | None,
    ) -> bool:
        if isinstance(tasks, list) and tasks:
            return False
        if dispatch_context is None:
            return False
        return bool(
            dispatch_context.current_in_progress_task_id
            or dispatch_context.current_pending_wave_task_ids
        )

    @staticmethod
    def _build_context_error_payload(
        *,
        error_code: str,
        message: str,
        dispatch_context: Any | None,
        recovery_action: str,
        recommended_dispatch_shape: str | None = None,
        recommended_tools: list[str] | None = None,
        tool_misuse_category: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "error_code": error_code,
            "message": message,
            "dispatch_mode": (
                "current_task_locked"
                if dispatch_context is not None and dispatch_context.current_in_progress_task_id
                else "pending_wave"
            ),
            "current_in_progress_task_id": (
                dispatch_context.current_in_progress_task_id if dispatch_context else None
            ),
            "current_pending_wave_task_ids": (
                dispatch_context.current_pending_wave_task_ids if dispatch_context else []
            ),
            "current_wave_task_ids": (
                dispatch_context.current_pending_wave_task_ids if dispatch_context else []
            ),
            "recovery_action": recovery_action,
            "recommended_tools": list(recommended_tools or (dispatch_context.recommended_tools if dispatch_context else [])),
            "recommended_dispatch_shape": recommended_dispatch_shape,
            "tool_misuse_category": tool_misuse_category,
        }
        recovery_hint_parts: list[str] = []
        if payload["recommended_tools"]:
            recovery_hint_parts.append(
                f"优先改用当前 Agent 内的工具：{', '.join(payload['recommended_tools'])}"
            )
        if recommended_dispatch_shape:
            recovery_hint_parts.append(f"如需继续派发，请改用 {recommended_dispatch_shape}")
        if not recovery_hint_parts:
            recovery_hint_parts.append("请按当前任务上下文改用直接执行或正确的结构化派发参数。")
        payload["recovery_hint"] = "；".join(recovery_hint_parts)
        payload.update(extra)
        return payload

    def _validate_parallel_task_specs(
        self,
        session: Any,
        task_specs: list[dict[str, Any]],
        *,
        dispatch_context: Any | None,
        enforce_current_wave: bool,
    ) -> dict[str, Any] | None:
        """拒绝跨 wave 或存在读写冲突的任务，确保 dispatch 仅做当前 wave 并行。"""
        seen_task_ids: set[int] = set()
        current_wave_ids = (
            set(dispatch_context.current_pending_wave_task_ids)
            if dispatch_context is not None
            else set()
        )
        dispatch_mode = self._resolve_dispatch_mode(task_specs)
        if dispatch_mode == "mixed":
            return self._build_context_error_payload(
                error_code="MIXED_DISPATCH_MODES",
                message="同一批 dispatch_agents 任务不能混用 task_id 与 parent_task_id。",
                dispatch_context=dispatch_context,
                recovery_action="split_dispatch_modes",
                recommended_dispatch_shape="分别提交 pending wave 派发和当前任务内部子派发",
                tool_misuse_category="mixed_dispatch_modes",
            )
        for item in task_specs:
            task_id = item.get("task_id")
            parent_task_id = item.get("parent_task_id")
            unique_key = (
                f"parent:{parent_task_id}"
                if parent_task_id is not None
                else f"task:{int(task_id or 0)}"
            )
            if unique_key in seen_task_ids:
                return {
                    **self._build_context_error_payload(
                        error_code="DUPLICATE_TASK_IDS",
                        message=(
                            f"dispatch_agents 收到重复任务目标 {unique_key}，请先在任务图中去重。"
                        ),
                        dispatch_context=dispatch_context,
                        recovery_action="deduplicate_dispatch_targets",
                        tool_misuse_category="duplicate_dispatch_target",
                    ),
                    "task_id": task_id,
                    "parent_task_id": parent_task_id,
                }
            seen_task_ids.add(unique_key)
            if parent_task_id is not None:
                current_task_id = (
                    dispatch_context.current_in_progress_task_id if dispatch_context else None
                )
                if current_task_id is None or parent_task_id != current_task_id:
                    return {
                        **self._build_context_error_payload(
                            error_code="DISPATCH_CONTEXT_MISMATCH",
                            message=(
                                "当前没有与 parent_task_id 匹配的进行中主任务。"
                                "请先在主 Agent 内直接执行当前任务，或确认 parent_task_id 指向当前 in_progress 任务。"
                            ),
                            dispatch_context=dispatch_context,
                            recovery_action="use_current_in_progress_parent",
                            recommended_dispatch_shape="tasks=[{parent_task_id, agent_id, task}]",
                            tool_misuse_category="parent_task_context_mismatch",
                        ),
                        "parent_task_id": parent_task_id,
                    }
                continue

            normalized_task_id = int(task_id or 0)
            if dispatch_context is not None and dispatch_context.current_in_progress_task_id:
                if normalized_task_id == dispatch_context.current_in_progress_task_id:
                    return {
                        **self._build_context_error_payload(
                            error_code="DISPATCH_CONTEXT_MISMATCH",
                            message=(
                                f"任务{normalized_task_id} 当前处于 in_progress。"
                                "该任务应在主 Agent 内直接执行，或改用 parent_task_id 发起当前任务内部子派发。"
                            ),
                            dispatch_context=dispatch_context,
                            recovery_action="run_direct_tool_or_use_parent_task_id",
                            recommended_dispatch_shape=(
                                f'tasks=[{{"parent_task_id": {normalized_task_id}, "agent_id": "...", "task": "..."}}]'
                            ),
                            tool_misuse_category="in_progress_task_dispatched_as_wave_item",
                        ),
                        "task_id": normalized_task_id,
                    }
            if enforce_current_wave and current_wave_ids and normalized_task_id not in current_wave_ids:
                return {
                    **self._build_context_error_payload(
                        error_code="TASK_NOT_IN_CURRENT_WAVE",
                        message=(
                            f"任务{normalized_task_id} 不在当前可执行 wave 中。"
                            "请先完成当前波次的上游任务，再调度后续任务。"
                        ),
                        dispatch_context=dispatch_context,
                        recovery_action="wait_for_current_wave_completion",
                        recommended_dispatch_shape="tasks=[{task_id, agent_id, task}]",
                        tool_misuse_category="task_outside_current_pending_wave",
                    ),
                    "task_id": normalized_task_id,
                }

        for index, left in enumerate(task_specs):
            left_outputs = set(left.get("output_refs") or [])
            left_inputs = set(left.get("input_refs") or [])
            for right in task_specs[index + 1 :]:
                right_outputs = set(right.get("output_refs") or [])
                right_inputs = set(right.get("input_refs") or [])
                conflict_refs = (
                    (left_outputs & right_outputs)
                    | (left_outputs & right_inputs)
                    | (right_outputs & left_inputs)
                )
                if conflict_refs:
                    return {
                        **self._build_context_error_payload(
                            error_code="PARALLEL_TASK_CONFLICT",
                            message=(
                                f"任务{left.get('task_id') or left.get('parent_task_id')} 与任务"
                                f"{right.get('task_id') or right.get('parent_task_id')} 存在读写冲突："
                                f"{', '.join(sorted(conflict_refs))}。"
                                "这类任务必须拆成串行波次，由主 Agent 先执行上游任务。"
                            ),
                            dispatch_context=dispatch_context,
                            recovery_action="serialize_conflicting_tasks",
                            tool_misuse_category="parallel_read_write_conflict",
                        ),
                        "conflict_task_ids": [left["task_id"], right["task_id"]],
                        "conflict_refs": sorted(conflict_refs),
                    }
        return None

    def _build_result_message(
        self,
        sub_results: list[SubAgentResult],
        task_specs: list[dict[str, Any]],
    ) -> str:
        """将各子 Agent 结果拼接为带标签的文本，供主 Agent 综合。"""
        if not sub_results:
            return ""

        n = len(sub_results)
        sections: list[str] = [f"以下是 {n} 个子 Agent 的执行结果：\n"]

        for result, task_spec in zip(sub_results, task_specs):
            agent_id = result.agent_id or task_spec.get("agent_id", "")
            task = task_spec.get("task", getattr(result, "task", ""))
            header = f"[任务{task_spec.get('task_id')}][{agent_id}] {task}"

            if result.success:
                body = (result.summary or "（无输出）").strip()
            else:
                error = (getattr(result, "error", "") or result.summary or "未知错误").strip()
                body = f"执行失败: {error}"

            sections.append(f"{header}\n{body}")

        return "\n\n".join(sections)

    def _build_structured_task_prompt(self, task_spec: dict[str, Any]) -> str:
        """把结构化任务包展开成稳定的子 Agent 输入，避免自由发挥。"""
        lines = [
            "这是主 Agent 下发的结构化子任务，请严格按输入执行，不要改写任务边界。",
            (
                f"task_id: {task_spec['task_id']}"
                if task_spec.get("task_id") is not None
                else f"parent_task_id: {task_spec['parent_task_id']}"
            ),
            f"goal: {task_spec['task']}",
        ]
        if task_spec.get("input_refs"):
            lines.append(f"input_refs: {json.dumps(task_spec['input_refs'], ensure_ascii=False)}")
        if task_spec.get("output_refs"):
            lines.append(f"output_refs: {json.dumps(task_spec['output_refs'], ensure_ascii=False)}")
        if task_spec.get("tool_profile"):
            lines.append(f"tool_profile: {task_spec['tool_profile']}")
        if task_spec.get("expected_output") is not None:
            lines.append(
                f"expected_output: {json.dumps(task_spec['expected_output'], ensure_ascii=False)}"
            )
        lines.append("若缺少必需输入，请直接报告失败原因，不要自行规划新任务。")
        return "\n".join(lines)

    def _build_subtask_payload(
        self,
        task_specs: list[dict[str, Any]],
        sub_results: list[SubAgentResult],
    ) -> list[dict[str, Any]]:
        payload: list[dict[str, Any]] = []
        for spec, result in zip(task_specs, sub_results):
            status = "success"
            if getattr(result, "stopped", False):
                status = "stopped"
            elif not result.success:
                status = "error"
            payload.append(
                {
                    "task_id": spec.get("task_id"),
                    "parent_task_id": spec.get("parent_task_id"),
                    "agent_id": result.agent_id or spec.get("agent_id"),
                    "agent_name": result.agent_name or None,
                    "task": spec.get("task"),
                    "status": status,
                    "stop_reason": getattr(result, "stop_reason", "") or None,
                    "summary": (result.summary or "").strip() or None,
                    "error": (result.error or "").strip() or None,
                    "execution_time_ms": getattr(result, "execution_time_ms", 0) or None,
                    "artifact_count": len(getattr(result, "artifacts", {}) or {}),
                    "document_count": len(getattr(result, "documents", {}) or {}),
                    "input_refs": list(spec.get("input_refs") or []),
                    "output_refs": list(spec.get("output_refs") or []),
                    "expected_output": spec.get("expected_output"),
                }
            )
        return payload

    def _build_dispatch_run_id(
        self,
        *,
        turn_id: str | None,
        tool_call_id: str | None,
    ) -> str:
        """构造派发运行 ID。"""
        normalized_tool_call = str(tool_call_id or "").strip()
        if normalized_tool_call:
            return f"dispatch:{normalized_tool_call}"
        normalized_turn = str(turn_id or "").strip() or "unknown"
        return f"dispatch:{normalized_turn}"

    async def _push_dispatch_workflow_event(
        self,
        *,
        session: Any,
        turn_id: str | None,
        dispatch_run_id: str,
        phase: str,
        payload: dict[str, Any],
    ) -> None:
        """通过会话事件回调推送 dispatch 工作流事件。"""
        callback = getattr(session, "event_callback", None)
        if callback is None:
            return
        try:
            from nini.agent.events import AgentEvent, EventType

            event = AgentEvent(
                type=EventType.WORKFLOW_STATUS,
                data={"scope": "dispatch_agents", "phase": phase, **payload},
                turn_id=turn_id,
                metadata={
                    "run_scope": "dispatch",
                    "run_id": dispatch_run_id,
                    "agent_id": "dispatch_agents",
                    "agent_name": "dispatch_agents",
                    "attempt": 1,
                    "phase": phase,
                    "turn_id": turn_id,
                },
            )
            if callable(callback):
                maybe_coro = callback(event)
                if hasattr(maybe_coro, "__await__"):
                    await maybe_coro
        except Exception as exc:
            logger.warning("推送 dispatch 工作流事件失败: %s", exc)

    def _record_dispatch_run_events(
        self,
        *,
        session: Any,
        dispatch_run_id: str,
        turn_id: str | None,
        sub_results: list[SubAgentResult],
        task_specs: list[dict[str, Any]],
        wave_id: str | None,
    ) -> None:
        """将 dispatch 结果写入父会话运行事件文件，便于事后排障。"""
        session_id = str(getattr(session, "id", "") or "").strip()
        if not session_id:
            return

        normalized_turn_id = str(turn_id or "").strip() or None
        parent_run_id = f"root:{normalized_turn_id}" if normalized_turn_id else None

        for result, task_spec in zip(sub_results, task_specs):
            run_id = str(getattr(result, "run_id", "") or "").strip()
            if not run_id:
                continue
            session_manager.append_agent_run_event(
                session_id,
                {
                    "type": "subagent_result",
                    "data": {
                        "task_id": task_spec.get("task_id"),
                        "agent_id": result.agent_id,
                        "task": task_spec.get("task", getattr(result, "task", "")),
                        "success": result.success,
                        "summary": result.summary,
                        "error": getattr(result, "error", ""),
                        "run_id": run_id,
                        "output_refs": list(task_spec.get("output_refs") or []),
                    },
                    "turn_id": normalized_turn_id,
                    "metadata": {
                        "run_scope": "subagent",
                        "run_id": run_id,
                        "parent_run_id": dispatch_run_id,
                        "agent_id": result.agent_id,
                        "attempt": 1,
                        "turn_id": normalized_turn_id,
                    },
                },
            )

        success_count = sum(1 for r in sub_results if r.success)
        failure_count = len(sub_results) - success_count
        session_manager.append_agent_run_event(
            session_id,
            {
                "type": "dispatch_agents_result",
                "data": {
                    "agent_count": len(sub_results),
                    "success_count": success_count,
                    "failure_count": failure_count,
                    "agents": [item.get("agent_id") for item in task_specs],
                    "wave_id": wave_id,
                    "subtasks": self._build_subtask_payload(task_specs, sub_results),
                },
                "turn_id": normalized_turn_id,
                "metadata": {
                    "run_scope": "dispatch",
                    "run_id": dispatch_run_id,
                    "parent_run_id": parent_run_id,
                    "agent_id": "dispatch_agents",
                    "attempt": 1,
                    "phase": "completed",
                    "turn_id": normalized_turn_id,
                },
            },
        )
