"""dispatch_agents 工具 —— 将任务分发给多个 Specialist Agent 并行执行后融合结果。

继承 tools/base.py:Tool，通过 TaskRouter → SubAgentSpawner → ResultFusionEngine 流水线执行。
该工具不暴露给子 Agent（防止递归派发），仅主 Agent 可调用。
"""

from __future__ import annotations

import logging
from typing import Any

from nini.agent.dag_executor import DagExecutor, DagTask
from nini.agent.session import session_manager
from nini.agent.spawner import BatchPreflightPlan, SubAgentResult
from nini.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)


class DispatchAgentsTool(Tool):
    """多 Agent 并行派发工具。

    接受任务描述列表，通过路由器映射到 Specialist Agent，
    并行执行后融合结果，返回整合摘要。
    """

    def __init__(
        self,
        agent_registry: Any = None,
        spawner: Any = None,
        fusion_engine: Any = None,
        task_router: Any = None,
    ) -> None:
        """初始化工具，通过构造函数注入依赖。

        Args:
            agent_registry: AgentRegistry 实例
            spawner: SubAgentSpawner 实例
            fusion_engine: ResultFusionEngine 实例
            task_router: TaskRouter 实例
        """
        self._agent_registry = agent_registry
        self._spawner = spawner
        self._fusion_engine = fusion_engine
        self._task_router = task_router

    @property
    def name(self) -> str:
        return "dispatch_agents"

    @property
    def description(self) -> str:
        return (
            "将复杂任务分解并分发给多个专业 Agent 并行/DAG 执行，融合结果后返回整合摘要。"
            "tasks 支持两种格式：字符串（并行执行）或对象（可声明 id 和 depends_on 建立 DAG 依赖）。"
            "存在 depends_on 时自动按拓扑排序分 wave 执行；否则按路由决策并行或串行。"
            "最小示例：tasks=['清洗数据','绘图'] 或 "
            'tasks=[{"task":"清洗","id":"t1"},{"task":"统计","id":"t2","depends_on":["t1"]}]。'
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "tasks": {
                    "type": "array",
                    "items": {
                        "oneOf": [
                            {"type": "string"},
                            {
                                "type": "object",
                                "properties": {
                                    "task": {"type": "string", "description": "任务描述文本"},
                                    "id": {"type": "string", "description": "任务唯一标识符"},
                                    "depends_on": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "依赖的任务 id 列表",
                                    },
                                },
                                "required": ["task"],
                                "additionalProperties": False,
                            },
                        ]
                    },
                    "description": ("任务列表：字符串或带 id/depends_on 的对象，支持混合格式"),
                },
                "context": {
                    "type": "string",
                    "description": "背景信息（可选），帮助 Agent 更好理解任务上下文",
                },
            },
            "required": ["tasks"],
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
        tasks: list[str | dict[str, Any]] | None = None,
        context: str = "",
        turn_id: str | None = None,
        tool_call_id: str | None = None,
        **_kwargs: Any,
    ) -> ToolResult:
        """执行多 Agent 并行/DAG 派发。

        Args:
            session: 当前会话
            tasks: 任务列表，支持字符串或带 id/depends_on 的对象，可混合使用
            context: 背景信息（可选）

        Returns:
            ToolResult，message 字段包含融合后的结果文本
        """
        # 依赖检查
        if self._spawner is None or self._fusion_engine is None:
            logger.error(
                "DispatchAgentsTool.execute: 依赖未正确注入（spawner 或 fusion_engine 为 None）"
            )
            return self._input_error(
                message="dispatch_agents 未正确初始化，当前无法执行并行派发。",
                error_code="DISPATCH_AGENTS_NOT_INITIALIZED",
                expected_fields=["tasks"],
                recovery_hint="检查 spawner 与 fusion_engine 是否已注入后重试。",
                minimal_example='{"tasks":["清洗数据","绘制图表"],"context":"数据集为 demo"}',
            )

        raw_tasks: list[str | dict[str, Any]] = tasks or []
        dispatch_run_id = self._build_dispatch_run_id(turn_id=turn_id, tool_call_id=tool_call_id)

        # 空任务快速返回
        if not raw_tasks:
            return ToolResult(
                success=True,
                message="",
                metadata={
                    "task_count": 0,
                    "routed_agents": [],
                    "recovery_hint": "如需并行派发，请在 tasks 中提供至少一个可独立执行的子任务。",
                },
            )

        # 解析原始任务列表，统一转换为 DagTask 对象
        dag_tasks = _parse_dag_tasks(raw_tasks)

        # 路径分叉：是否有任意任务声明了 depends_on
        has_dependencies = any(t.depends_on for t in dag_tasks)

        if has_dependencies:
            # DAG 路径：拓扑排序分 wave 执行
            sub_results, routed_agents, dag_error = await self._execute_dag(
                dag_tasks,
                session,
                context=context,
                turn_id=turn_id,
                dispatch_run_id=dispatch_run_id,
            )
        else:
            # C1 路径：并行/串行分叉（保持现有行为）
            task_texts = [t.task for t in dag_tasks]
            task_pairs, should_run_parallel, unmatched_tasks = await _build_task_pairs(
                task_texts,
                task_router=self._task_router,
                agent_registry=self._agent_registry,
                context=context,
            )

            if not task_pairs:
                return self._input_error(
                    message="dispatch_agents 无法为当前任务找到可用的 Agent。",
                    error_code="DISPATCH_AGENTS_NO_MATCHED_AGENTS",
                    expected_fields=["tasks"],
                    recovery_hint=(
                        "当前任务无法路由到子 Agent。请直接使用 run_code(dataset_name='...') "
                        "在当前 Agent 内执行代码完成分析，或用 dataset_catalog(operation='profile') "
                        "先确认数据集名称。禁止用 workspace_session(read) 读取数据集文件。"
                    ),
                    minimal_example=(
                        '{"tasks":["清洗缺失值","执行独立样本 t 检验"],'
                        '"context":"研究问题为干预组与对照组比较"}'
                    ),
                )

            if should_run_parallel:
                preflight_plan = await self._spawner.preflight_batch(
                    task_pairs,
                    session,
                    parent_turn_id=turn_id,
                    emit_agent_errors=False,
                )
                preflight_summary = self._build_dispatch_preflight_summary(
                    task_pairs=task_pairs,
                    preflight_plan=preflight_plan,
                    unmatched_tasks=unmatched_tasks,
                )
                self._record_dispatch_preflight_event(
                    session=session,
                    dispatch_run_id=dispatch_run_id,
                    turn_id=turn_id,
                    routed_agents=[agent_id for agent_id, _ in task_pairs],
                    payload=preflight_summary,
                )
                await self._push_dispatch_preflight_event(
                    session=session,
                    turn_id=turn_id,
                    dispatch_run_id=dispatch_run_id,
                    payload=preflight_summary,
                )
                sub_results = await self._spawner.spawn_batch(
                    task_pairs,
                    session,
                    parent_turn_id=turn_id,
                    preflight_plan=preflight_plan,
                )
            else:
                preflight_plan = await self._spawner.preflight_batch(
                    task_pairs,
                    session,
                    parent_turn_id=turn_id,
                    emit_agent_errors=False,
                )
                preflight_summary = self._build_dispatch_preflight_summary(
                    task_pairs=task_pairs,
                    preflight_plan=preflight_plan,
                    unmatched_tasks=unmatched_tasks,
                )
                self._record_dispatch_preflight_event(
                    session=session,
                    dispatch_run_id=dispatch_run_id,
                    turn_id=turn_id,
                    routed_agents=[agent_id for agent_id, _ in task_pairs],
                    payload=preflight_summary,
                )
                await self._push_dispatch_preflight_event(
                    session=session,
                    turn_id=turn_id,
                    dispatch_run_id=dispatch_run_id,
                    payload=preflight_summary,
                )
                sub_results = []
                materialized_failures = {
                    index: result
                    for index, result in enumerate(preflight_plan.ordered_results, start=1)
                    if result is not None
                }
                for task_index, (agent_id, task_text) in enumerate(task_pairs, start=1):
                    if task_index in materialized_failures:
                        result = materialized_failures[task_index]
                        await self._spawner._emit_preflight_failure_event(
                            parent_session=session,
                            result=result,
                            parent_turn_id=turn_id,
                            attempt=1,
                            retry_count=0,
                            subtask_index=task_index,
                        )
                        self._spawner._attach_snapshot(session, result, attempt=1)
                        sub_results.append(result)
                        continue
                    result = await self._spawner.spawn(
                        agent_id,
                        task_text,
                        session,
                        parent_turn_id=turn_id,
                        subtask_index=task_index,
                        skip_preflight=True,
                    )
                    sub_results.append(result)
                    if session is not None:
                        for key, value in result.artifacts.items():
                            session.artifacts[f"{result.agent_id}.{key}"] = value
                        for key, value in result.documents.items():
                            session.documents[f"{result.agent_id}.{key}"] = value

            sub_results.extend(
                _build_routing_failure_results(
                    unmatched_tasks,
                    session=session,
                )
            )
            routed_agents = [agent_id for agent_id, _ in task_pairs]
            dag_error = "routing_failed" if unmatched_tasks else None

        # 融合结果
        fusion_result = await self._fusion_engine.fuse(sub_results)
        subtask_results = [
            self._serialize_sub_result(
                result,
                routed_task=getattr(result, "task", ""),
                fallback_agent_id=result.agent_id,
            )
            for result in sub_results
        ]
        failure_summary = self._summarize_subtasks(subtask_results)
        success_count = failure_summary["success_count"]
        stopped_count = failure_summary["stopped_count"]
        failure_count = failure_summary["failure_count"]
        partial_failure = failure_count > 0 and success_count > 0
        dispatch_success = success_count > 0 or (failure_count == 0 and stopped_count == 0)
        self._record_dispatch_run_events(
            session=session,
            dispatch_run_id=dispatch_run_id,
            turn_id=turn_id,
            routed_agents=routed_agents,
            context=context,
            subtasks=subtask_results,
            fusion_result=fusion_result,
            failure_summary=failure_summary,
        )
        await self._push_dispatch_workflow_event(
            session=session,
            turn_id=turn_id,
            dispatch_run_id=dispatch_run_id,
            phase="fused",
            payload={
                "task_count": len(raw_tasks),
                "success_count": success_count,
                "failure_count": failure_count,
                "stopped_count": stopped_count,
                "subtasks": subtask_results,
                "preflight_failure_count": failure_summary["preflight_failure_count"],
                "routing_failure_count": failure_summary["routing_failure_count"],
                "execution_failure_count": failure_summary["execution_failure_count"],
                "preflight_failures": failure_summary["preflight_failures"],
                "routing_failures": failure_summary["routing_failures"],
                "execution_failures": failure_summary["execution_failures"],
                "routed_agents": routed_agents,
            },
        )

        metadata: dict[str, Any] = {
            "task_count": len(raw_tasks),
            "routed_agents": routed_agents,
            "fusion_strategy": fusion_result.strategy,
            "sources": fusion_result.sources,
            "conflicts": fusion_result.conflicts,
            "dispatch_run_id": dispatch_run_id,
            "success_count": success_count,
            "failure_count": failure_count,
            "stopped_count": stopped_count,
            "partial_failure": partial_failure,
            "subtasks": subtask_results,
            "preflight_failure_count": failure_summary["preflight_failure_count"],
            "routing_failure_count": failure_summary["routing_failure_count"],
            "execution_failure_count": failure_summary["execution_failure_count"],
            "preflight_failures": failure_summary["preflight_failures"],
            "routing_failures": failure_summary["routing_failures"],
            "execution_failures": failure_summary["execution_failures"],
        }
        if dag_error:
            metadata["dag_error"] = dag_error

        # 全部子任务均为 preflight 失败（模型额度/配置不可用）时，附加降级指引
        all_preflight_failed = (
            failure_count > 0
            and success_count == 0
            and stopped_count == 0
            and failure_summary["preflight_failure_count"] == failure_count
        )
        if all_preflight_failed:
            # 提取 preflight 失败原因（取第一条）
            first_pf_error = ""
            pf_failures = failure_summary.get("preflight_failures", [])
            if pf_failures and isinstance(pf_failures[0], dict):
                first_pf_error = str(pf_failures[0].get("error", ""))
            fallback_hint = (
                f"以下子任务因模型额度或配置不可执行：\n"
                + "\n".join(
                    f"[{r.get('task', '')[:120]}\n背景：{context}]"
                    for r in pf_failures
                )
                + (f"\n{first_pf_error}" if first_pf_error else "")
                + "\n\n【降级建议】dispatch_agents 无法继续。"
                "请直接使用 run_code(dataset_name='...') 在当前 Agent 内执行任务，"
                "或使用 dataset_catalog(operation='profile') 确认数据集名称后再执行分析。"
                "禁止尝试 workspace_session(read) 读取数据集文件。"
            )
            metadata["fallback_hint"] = fallback_hint
            metadata["all_preflight_failed"] = True
            return ToolResult(
                success=False,
                message=fallback_hint,
                metadata=metadata,
            )

        return ToolResult(
            success=dispatch_success,
            message=self._build_dispatch_message(fusion_result, subtask_results, failure_summary),
            metadata=metadata,
        )

    async def _execute_dag(
        self,
        dag_tasks: list[DagTask],
        session: Any,
        *,
        context: str,
        turn_id: str | None,
        dispatch_run_id: str,
    ) -> tuple[list[Any], list[str], str | None]:
        """DAG 路径：路由任务、拓扑排序分 wave、逐 wave 执行。

        Returns:
            (sub_results, routed_agent_ids, dag_error_code_or_None)
        """
        # 为每个 DagTask 路由 agent_id
        routed_dag_tasks, unmatched_tasks = await _route_dag_tasks(
            dag_tasks,
            task_router=self._task_router,
            agent_registry=self._agent_registry,
            context=context,
        )
        if unmatched_tasks:
            return (
                _build_routing_failure_results(unmatched_tasks, session=session),
                [t.agent_id for t in routed_dag_tasks if t.agent_id],
                "routing_failed",
            )

        executor = DagExecutor()
        waves = executor.build_waves(routed_dag_tasks)

        # 检测循环依赖降级（build_waves 将每任务单独 wave 时表示降级）
        dag_error: str | None = None
        total_in_waves = sum(len(w) for w in waves)
        if (
            total_in_waves == len(dag_tasks)
            and all(len(w) == 1 for w in waves)
            and len(dag_tasks) > 1
        ):
            # 可能是循环依赖降级，也可能是正常链式依赖；只有当所有任务都有依赖时才标注
            all_have_deps = all(t.depends_on for t in dag_tasks)
            if all_have_deps:
                dag_error = "circular_dependency"

        sub_results = await executor.execute(
            waves,
            session,
            spawner=self._spawner,
            router=self._task_router,
            turn_id=turn_id,
            preflight_reporter=self._make_dag_preflight_reporter(
                session=session,
                turn_id=turn_id,
                dispatch_run_id=dispatch_run_id,
                waves=waves,
            ),
        )

        routed_agents = [t.agent_id for t in routed_dag_tasks]
        return sub_results, routed_agents, dag_error

    def _build_dispatch_preflight_summary(
        self,
        *,
        task_pairs: list[tuple[str, str]],
        preflight_plan: BatchPreflightPlan,
        unmatched_tasks: list[str],
    ) -> dict[str, Any]:
        """构造 dispatch 级预检摘要。"""
        preflight_failures = [
            {
                "agent_id": result.agent_id,
                "agent_name": result.agent_name,
                "task": result.task,
                "error": result.error or result.summary,
            }
            for result in preflight_plan.failed_results
        ]
        return {
            "task_count": len(task_pairs) + len(unmatched_tasks),
            "routed_task_count": len(task_pairs),
            "runnable_count": preflight_plan.runnable_count,
            "preflight_failure_count": preflight_plan.failure_count,
            "routing_failure_count": len(unmatched_tasks),
            "preflight_failures": preflight_failures,
        }

    def _input_error(
        self,
        *,
        message: str,
        error_code: str,
        expected_fields: list[str],
        recovery_hint: str,
        minimal_example: str,
    ) -> ToolResult:
        """返回统一结构化输入错误。"""
        return self.build_input_error(
            message=message,
            payload={
                "error_code": error_code,
                "expected_fields": expected_fields,
                "recovery_hint": recovery_hint,
                "minimal_example": minimal_example,
            },
        )

    def _serialize_sub_result(
        self,
        result: Any,
        *,
        routed_task: str,
        fallback_agent_id: str,
    ) -> dict[str, Any]:
        """将子 Agent 结果归一化为结构化字典。"""
        agent_id = str(getattr(result, "agent_id", "") or fallback_agent_id)
        stopped = bool(getattr(result, "stopped", False))
        success = bool(getattr(result, "success", False))
        error = str(getattr(result, "error", "") or "").strip()
        summary = str(getattr(result, "summary", "") or "").strip()
        artifact_keys = sorted(getattr(result, "artifacts", {}).keys())
        document_keys = sorted(getattr(result, "documents", {}).keys())
        status = "stopped" if stopped else ("success" if success else "error")
        return {
            "agent_id": agent_id,
            "agent_name": str(getattr(result, "agent_name", "") or agent_id),
            "task": str(getattr(result, "task", "") or routed_task),
            "status": status,
            "success": success,
            "stopped": stopped,
            "stop_reason": str(getattr(result, "stop_reason", "") or ""),
            "summary": summary,
            "error": error or (summary if not success else ""),
            "execution_time_ms": int(getattr(result, "execution_time_ms", 0) or 0),
            "run_id": str(getattr(result, "run_id", "") or ""),
            "turn_id": str(getattr(result, "turn_id", "") or ""),
            "parent_session_id": str(getattr(result, "parent_session_id", "") or ""),
            "child_session_id": str(getattr(result, "child_session_id", "") or ""),
            "resource_session_id": str(getattr(result, "resource_session_id", "") or ""),
            "artifact_names": artifact_keys,
            "document_names": document_keys,
            "artifact_count": len(artifact_keys),
            "document_count": len(document_keys),
        }

    def _build_dispatch_message(
        self,
        fusion_result: Any,
        subtasks: list[dict[str, Any]],
        failure_summary: dict[str, Any],
    ) -> str:
        """为 dispatch_agents 生成可操作的返回消息。"""
        fused_content = str(getattr(fusion_result, "content", "") or "").strip()
        if fused_content and failure_summary["success_count"] > 0:
            return fused_content

        preflight_lines = [
            f"[{item['task']}] {item['error'] or item['summary']}"
            for item in subtasks
            if item["status"] == "error" and item["stop_reason"] == "preflight_failed"
        ]
        if preflight_lines and failure_summary["success_count"] == 0:
            return "以下子任务因模型额度或配置不可执行：\n" + "\n".join(preflight_lines)

        routing_lines = [
            f"[{item['task']}] {item['error'] or item['summary']}"
            for item in subtasks
            if item["status"] == "error" and item["stop_reason"] == "routing_failed"
        ]
        execution_lines = [
            f"[{item['task']}] {item['error'] or item['summary']}"
            for item in subtasks
            if item["status"] == "error"
            and item["stop_reason"] not in {"preflight_failed", "routing_failed"}
        ]

        sections: list[str] = []
        if preflight_lines:
            sections.append("模型额度或配置不可执行：\n" + "\n".join(preflight_lines))
        if routing_lines:
            sections.append("路由失败：\n" + "\n".join(routing_lines))
        if execution_lines:
            sections.append("执行失败：\n" + "\n".join(execution_lines))
        if sections:
            msg = "\n\n".join(sections)
            if execution_lines:
                msg += (
                    "\n\n【重要】子任务执行失败属于逻辑错误，"
                    "重复调用 dispatch_agents 无法解决此类问题。"
                    "请直接使用 run_code(dataset_name='...') 或 dataset_catalog "
                    "在当前 Agent 内完成任务。"
                )
            return msg

        stopped_lines = [
            f"[{item['task']}] {item['stop_reason'] or '已停止'}"
            for item in subtasks
            if item["status"] == "stopped"
        ]
        if stopped_lines:
            return "子任务已停止：\n" + "\n".join(stopped_lines)
        return fused_content

    async def _push_dispatch_preflight_event(
        self,
        *,
        session: Any,
        turn_id: str | None,
        dispatch_run_id: str,
        payload: dict[str, Any],
    ) -> None:
        """通过会话事件回调推送 dispatch 预检摘要。"""
        await self._push_dispatch_workflow_event(
            session=session,
            turn_id=turn_id,
            dispatch_run_id=dispatch_run_id,
            phase="preflight",
            payload=payload,
        )

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
                data={
                    "scope": "dispatch_agents",
                    "phase": phase,
                    **payload,
                },
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

    def _make_dag_preflight_reporter(
        self,
        *,
        session: Any,
        turn_id: str | None,
        dispatch_run_id: str,
        waves: list[list[DagTask]],
    ):
        """构造 DAG wave 级预检摘要上报器。"""

        total_waves = len(waves)
        wave_index = 0

        async def _report(payload: dict[str, Any]) -> None:
            nonlocal wave_index
            wave_index += 1
            wave_payload = {
                **payload,
                "wave_index": wave_index,
                "wave_count": total_waves,
            }
            self._record_dispatch_preflight_event(
                session=session,
                dispatch_run_id=dispatch_run_id,
                turn_id=turn_id,
                routed_agents=[],
                payload=wave_payload,
            )
            await self._push_dispatch_preflight_event(
                session=session,
                turn_id=turn_id,
                dispatch_run_id=dispatch_run_id,
                payload=wave_payload,
            )

        return _report

    def _summarize_subtasks(self, subtasks: list[dict[str, Any]]) -> dict[str, Any]:
        """汇总 dispatch 子任务结果，显式区分预检、路由与执行失败。"""
        success_count = sum(1 for item in subtasks if item["success"])
        stopped_count = sum(1 for item in subtasks if item["status"] == "stopped")
        preflight_failures = self._collect_failure_details(
            subtasks,
            stop_reasons={"preflight_failed"},
        )
        routing_failures = self._collect_failure_details(
            subtasks,
            stop_reasons={"routing_failed"},
        )
        execution_failures = self._collect_failure_details(
            subtasks,
            exclude_stop_reasons={"preflight_failed", "routing_failed"},
        )
        preflight_failure_count = len(preflight_failures)
        routing_failure_count = len(routing_failures)
        execution_failure_count = len(execution_failures)
        failure_count = preflight_failure_count + routing_failure_count + execution_failure_count
        return {
            "success_count": success_count,
            "stopped_count": stopped_count,
            "failure_count": failure_count,
            "preflight_failure_count": preflight_failure_count,
            "routing_failure_count": routing_failure_count,
            "execution_failure_count": execution_failure_count,
            "preflight_failures": preflight_failures,
            "routing_failures": routing_failures,
            "execution_failures": execution_failures,
        }

    def _collect_failure_details(
        self,
        subtasks: list[dict[str, Any]],
        *,
        stop_reasons: set[str] | None = None,
        exclude_stop_reasons: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        """按 stop_reason 收集结构化失败明细。"""
        details: list[dict[str, Any]] = []
        for item in subtasks:
            if item["status"] != "error":
                continue
            stop_reason = str(item.get("stop_reason") or "").strip()
            if stop_reasons is not None and stop_reason not in stop_reasons:
                continue
            if exclude_stop_reasons is not None and stop_reason in exclude_stop_reasons:
                continue
            details.append(
                {
                    "agent_id": item.get("agent_id"),
                    "task": item.get("task"),
                    "error": item.get("error") or item.get("summary"),
                }
            )
        return details

    def _build_dispatch_run_id(
        self,
        *,
        turn_id: str | None,
        tool_call_id: str | None,
    ) -> str:
        """构造父级 dispatch 运行 ID。"""
        normalized_tool_call = str(tool_call_id or "").strip()
        if normalized_tool_call:
            return f"dispatch:{normalized_tool_call}"
        normalized_turn = str(turn_id or "").strip() or "unknown"
        return f"dispatch:{normalized_turn}"

    def _record_dispatch_run_events(
        self,
        *,
        session: Any,
        dispatch_run_id: str,
        turn_id: str | None,
        routed_agents: list[str],
        context: str,
        subtasks: list[dict[str, Any]],
        fusion_result: Any,
        failure_summary: dict[str, Any],
    ) -> None:
        """将 dispatch 结果写入父会话运行事件文件，便于事后排障。"""
        session_id = str(getattr(session, "id", "") or "").strip()
        if not session_id:
            return

        normalized_turn_id = str(turn_id or "").strip() or None
        parent_run_id = f"root:{normalized_turn_id}" if normalized_turn_id else None

        for item in subtasks:
            run_id = str(item.get("run_id") or "").strip()
            if not run_id:
                continue
            session_manager.append_agent_run_event(
                session_id,
                {
                    "type": "subagent_result",
                    "data": item,
                    "turn_id": normalized_turn_id,
                    "metadata": {
                        "run_scope": "subagent",
                        "run_id": run_id,
                        "parent_run_id": dispatch_run_id,
                        "agent_id": item.get("agent_id"),
                        "agent_name": item.get("agent_name"),
                        "attempt": 1,
                        "phase": item.get("status"),
                        "turn_id": normalized_turn_id,
                    },
                },
            )

        session_manager.append_agent_run_event(
            session_id,
            {
                "type": "dispatch_agents_result",
                "data": {
                    "task_count": len(subtasks),
                    "routed_agents": routed_agents,
                    "context": context,
                    "fusion_strategy": getattr(fusion_result, "strategy", "concatenate"),
                    "sources": list(getattr(fusion_result, "sources", []) or []),
                    "conflicts": list(getattr(fusion_result, "conflicts", []) or []),
                    "subtasks": subtasks,
                    "success_count": failure_summary["success_count"],
                    "failure_count": failure_summary["failure_count"],
                    "stopped_count": failure_summary["stopped_count"],
                    "preflight_failure_count": failure_summary["preflight_failure_count"],
                    "routing_failure_count": failure_summary["routing_failure_count"],
                    "execution_failure_count": failure_summary["execution_failure_count"],
                    "preflight_failures": failure_summary["preflight_failures"],
                    "routing_failures": failure_summary["routing_failures"],
                    "execution_failures": failure_summary["execution_failures"],
                },
                "turn_id": normalized_turn_id,
                "metadata": {
                    "run_scope": "dispatch",
                    "run_id": dispatch_run_id,
                    "parent_run_id": parent_run_id,
                    "agent_id": "dispatch_agents",
                    "agent_name": "dispatch_agents",
                    "attempt": 1,
                    "phase": "fused",
                    "turn_id": normalized_turn_id,
                },
            },
        )

    def _record_dispatch_preflight_event(
        self,
        *,
        session: Any,
        dispatch_run_id: str,
        turn_id: str | None,
        routed_agents: list[str],
        payload: dict[str, Any],
    ) -> None:
        """将 dispatch 预检摘要写入运行事件。"""
        session_id = str(getattr(session, "id", "") or "").strip()
        if not session_id:
            return

        normalized_turn_id = str(turn_id or "").strip() or None
        parent_run_id = f"root:{normalized_turn_id}" if normalized_turn_id else None
        session_manager.append_agent_run_event(
            session_id,
            {
                "type": "dispatch_agents_preflight",
                "data": {
                    **payload,
                    "routed_agents": routed_agents,
                },
                "turn_id": normalized_turn_id,
                "metadata": {
                    "run_scope": "dispatch",
                    "run_id": dispatch_run_id,
                    "parent_run_id": parent_run_id,
                    "agent_id": "dispatch_agents",
                    "agent_name": "dispatch_agents",
                    "attempt": 1,
                    "phase": "preflight",
                    "turn_id": normalized_turn_id,
                },
            },
        )


def _parse_dag_tasks(raw_tasks: list[str | dict[str, Any]]) -> list[DagTask]:
    """将原始任务列表（字符串/字典混合）解析为 DagTask 列表。

    字符串元素：自动分配 id（t1、t2…），depends_on=[]。
    字典元素：使用声明的 id 和 depends_on（id 缺失时自动分配）。
    """
    dag_tasks: list[DagTask] = []
    for idx, raw in enumerate(raw_tasks):
        auto_id = f"t{idx + 1}"
        if isinstance(raw, str):
            dag_tasks.append(DagTask(task=raw, id=auto_id, depends_on=[]))
        else:
            task_text = str(raw.get("task", ""))
            task_id = str(raw.get("id", auto_id)) or auto_id
            depends_on = [str(d) for d in raw.get("depends_on", [])]
            dag_tasks.append(DagTask(task=task_text, id=task_id, depends_on=depends_on))
    return dag_tasks


async def _route_dag_tasks(
    dag_tasks: list[DagTask],
    *,
    task_router: Any,
    agent_registry: Any,
    context: str,
) -> tuple[list[DagTask], list[str]]:
    """为每个 DagTask 路由 agent_id，返回更新后的 DagTask 列表。

    无法路由时使用 agent_registry 第一个可用 Agent 作为兜底。
    """
    if agent_registry is None:
        return dag_tasks

    available_agents = agent_registry.list_agents()
    if not available_agents:
        return dag_tasks

    available_agent_ids = {agent.agent_id for agent in available_agents}
    sole_agent_id = available_agents[0].agent_id if len(available_agents) == 1 else ""

    routed: list[DagTask] = []
    unmatched_tasks: list[str] = []
    for t in dag_tasks:
        task_text = f"{t.task}\n背景：{context}" if context else t.task

        routed_pairs, _ = await _route_task_pairs(
            t.task,
            task_router=task_router,
            available_agent_ids=available_agent_ids,
            context=context,
        )

        if not routed_pairs and sole_agent_id:
            routed_pairs = [(sole_agent_id, task_text)]

        if not routed_pairs:
            unmatched_tasks.append(task_text)
            continue

        # 取第一个路由结果的 agent_id 和 task_text
        agent_id, routed_task = routed_pairs[0]

        routed.append(
            DagTask(
                task=routed_task,
                id=t.id,
                depends_on=t.depends_on,
                agent_id=agent_id,
            )
        )
    return routed, unmatched_tasks


async def _build_task_pairs(
    tasks: list[str],
    *,
    task_router: Any,
    agent_registry: Any,
    context: str = "",
) -> tuple[list[tuple[str, str]], bool, list[str]]:
    """为任务列表构造 (agent_id, task_description) 元组，并返回是否可并行标志。

    parallel 策略：所有路由决策均明确标注 parallel=True 时才返回 True；
    任意一个任务走了默认兜底（无法路由）则视为串行不确定，返回 False。

    若 AgentRegistry 不可用或无已注册 Agent，返回 ([], False)。
    """
    if agent_registry is None:
        return [], False, list(tasks)

    available_agents = agent_registry.list_agents()
    if not available_agents:
        return [], False, list(tasks)

    available_agent_ids = {agent.agent_id for agent in available_agents}
    sole_agent_id = available_agents[0].agent_id if len(available_agents) == 1 else ""
    pairs: list[tuple[str, str]] = []
    parallel_flags: list[bool] = []
    unmatched_tasks: list[str] = []

    for task in tasks:
        routed_pairs, task_parallel = await _route_task_pairs(
            task,
            task_router=task_router,
            available_agent_ids=available_agent_ids,
            context=context,
        )
        if routed_pairs:
            pairs.extend(routed_pairs)
            parallel_flags.append(task_parallel)
            continue
        if sole_agent_id:
            task_text = f"{task}\n背景：{context}" if context else task
            pairs.append((sole_agent_id, task_text))
            parallel_flags.append(False)
            continue
        unmatched_tasks.append(f"{task}\n背景：{context}" if context else task)

    overall_parallel = bool(parallel_flags) and all(parallel_flags)
    return pairs, overall_parallel, unmatched_tasks


async def _route_task_pairs(
    task: str,
    *,
    task_router: Any,
    available_agent_ids: set[str],
    context: str,
) -> tuple[list[tuple[str, str]], bool]:
    """通过 TaskRouter 生成合法的 (agent_id, task) 对，并返回路由决策的 parallel 标志。"""
    if task_router is None:
        return [], False

    decision = await task_router.route(
        task,
        context={"background": context} if context else None,
    )
    if not getattr(decision, "agent_ids", None):
        return [], False

    routed_pairs: list[tuple[str, str]] = []
    for index, agent_id in enumerate(decision.agent_ids):
        if agent_id not in available_agent_ids:
            continue
        routed_task = task
        if index < len(decision.tasks):
            candidate = decision.tasks[index]
            if candidate:
                routed_task = candidate
        task_text = f"{routed_task}\n背景：{context}" if context else routed_task
        routed_pairs.append((agent_id, task_text))
    return routed_pairs, bool(getattr(decision, "parallel", False))


def _build_routing_failure_results(
    tasks: list[str],
    *,
    session: Any,
) -> list[SubAgentResult]:
    """为未匹配任务生成显式失败结果，避免危险兜底路由。"""
    parent_session_id = str(getattr(session, "id", "") or "")
    resource_session_id = (
        session.get_resource_session_id()
        if session is not None and hasattr(session, "get_resource_session_id")
        else parent_session_id
    )
    return [
        SubAgentResult(
            agent_id="routing_guard",
            agent_name="routing_guard",
            success=False,
            task=task,
            summary="未找到与该任务兼容的 specialist agent",
            error="未找到与该任务兼容的 specialist agent",
            stop_reason="routing_failed",
            parent_session_id=parent_session_id,
            resource_session_id=resource_session_id,
        )
        for task in tasks
    ]
