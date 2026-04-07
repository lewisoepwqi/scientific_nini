"""dispatch_agents 工具 —— 将任务分发给多个 Specialist Agent 并行执行后融合结果。

继承 tools/base.py:Tool，通过 TaskRouter → SubAgentSpawner → ResultFusionEngine 流水线执行。
该工具不暴露给子 Agent（防止递归派发），仅主 Agent 可调用。
"""

from __future__ import annotations

import logging
from typing import Any

from nini.agent.dag_executor import DagExecutor, DagTask
from nini.agent.session import session_manager
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
            "tasks=[{\"task\":\"清洗\",\"id\":\"t1\"},{\"task\":\"统计\",\"id\":\"t2\",\"depends_on\":[\"t1\"]}]。"
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
                    "description": (
                        "任务列表：字符串或带 id/depends_on 的对象，支持混合格式"
                    ),
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
                dag_tasks, session, context=context, turn_id=turn_id
            )
        else:
            # C1 路径：并行/串行分叉（保持现有行为）
            task_texts = [t.task for t in dag_tasks]
            task_pairs, should_run_parallel = await _build_task_pairs(
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
                        "拆分为更明确的独立子任务，或检查 AgentRegistry 中是否存在可用 Agent。"
                    ),
                    minimal_example=(
                        '{"tasks":["清洗缺失值","执行独立样本 t 检验"],'
                        '"context":"研究问题为干预组与对照组比较"}'
                    ),
                )

            if should_run_parallel:
                sub_results = await self._spawner.spawn_batch(
                    task_pairs,
                    session,
                    parent_turn_id=turn_id,
                )
            else:
                sub_results = []
                for agent_id, task_text in task_pairs:
                    result = await self._spawner.spawn(
                        agent_id,
                        task_text,
                        session,
                        parent_turn_id=turn_id,
                    )
                    sub_results.append(result)
                    if session is not None:
                        for key, value in result.artifacts.items():
                            session.artifacts[f"{result.agent_id}.{key}"] = value
                        for key, value in result.documents.items():
                            session.documents[f"{result.agent_id}.{key}"] = value

            routed_agents = [agent_id for agent_id, _ in task_pairs]
            dag_error = None

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
        success_count = sum(1 for item in subtask_results if item["success"])
        stopped_count = sum(1 for item in subtask_results if item["stopped"])
        failure_count = len(subtask_results) - success_count - stopped_count
        partial_failure = failure_count > 0 and success_count > 0
        dispatch_run_id = self._build_dispatch_run_id(turn_id=turn_id, tool_call_id=tool_call_id)

        self._record_dispatch_run_events(
            session=session,
            dispatch_run_id=dispatch_run_id,
            turn_id=turn_id,
            routed_agents=routed_agents,
            context=context,
            subtasks=subtask_results,
            fusion_result=fusion_result,
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
        }
        if dag_error:
            metadata["dag_error"] = dag_error

        return ToolResult(
            success=True,
            message=fusion_result.content,
            metadata=metadata,
        )

    async def _execute_dag(
        self,
        dag_tasks: list[DagTask],
        session: Any,
        *,
        context: str,
        turn_id: str | None,
    ) -> tuple[list[Any], list[str], str | None]:
        """DAG 路径：路由任务、拓扑排序分 wave、逐 wave 执行。

        Returns:
            (sub_results, routed_agent_ids, dag_error_code_or_None)
        """
        # 为每个 DagTask 路由 agent_id
        routed_dag_tasks = await _route_dag_tasks(
            dag_tasks,
            task_router=self._task_router,
            agent_registry=self._agent_registry,
            context=context,
        )

        executor = DagExecutor()
        waves = executor.build_waves(routed_dag_tasks)

        # 检测循环依赖降级（build_waves 将每任务单独 wave 时表示降级）
        dag_error: str | None = None
        total_in_waves = sum(len(w) for w in waves)
        if total_in_waves == len(dag_tasks) and all(len(w) == 1 for w in waves) and len(dag_tasks) > 1:
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
        )

        routed_agents = [t.agent_id for t in routed_dag_tasks]
        return sub_results, routed_agents, dag_error

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
                    "success_count": sum(1 for item in subtasks if item["success"]),
                    "failure_count": sum(1 for item in subtasks if item["status"] == "error"),
                    "stopped_count": sum(1 for item in subtasks if item["status"] == "stopped"),
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
) -> list[DagTask]:
    """为每个 DagTask 路由 agent_id，返回更新后的 DagTask 列表。

    无法路由时使用 agent_registry 第一个可用 Agent 作为兜底。
    """
    if agent_registry is None:
        return dag_tasks

    available_agents = agent_registry.list_agents()
    if not available_agents:
        return dag_tasks

    available_agent_ids = {agent.agent_id for agent in available_agents}
    default_agent_id = available_agents[0].agent_id

    routed: list[DagTask] = []
    for t in dag_tasks:
        task_text = f"{t.task}\n背景：{context}" if context else t.task

        routed_pairs, _ = await _route_task_pairs(
            t.task,
            task_router=task_router,
            available_agent_ids=available_agent_ids,
            context=context,
        )

        if routed_pairs:
            # 取第一个路由结果的 agent_id 和 task_text
            agent_id, routed_task = routed_pairs[0]
        else:
            agent_id = default_agent_id
            routed_task = task_text

        routed.append(
            DagTask(
                task=routed_task,
                id=t.id,
                depends_on=t.depends_on,
                agent_id=agent_id,
            )
        )
    return routed


async def _build_task_pairs(
    tasks: list[str],
    *,
    task_router: Any,
    agent_registry: Any,
    context: str = "",
) -> tuple[list[tuple[str, str]], bool]:
    """为任务列表构造 (agent_id, task_description) 元组，并返回是否可并行标志。

    parallel 策略：所有路由决策均明确标注 parallel=True 时才返回 True；
    任意一个任务走了默认兜底（无法路由）则视为串行不确定，返回 False。

    若 AgentRegistry 不可用或无已注册 Agent，返回 ([], False)。
    """
    if agent_registry is None:
        return [], False

    available_agents = agent_registry.list_agents()
    if not available_agents:
        return [], False

    available_agent_ids = {agent.agent_id for agent in available_agents}
    default_agent_id = available_agents[0].agent_id
    pairs: list[tuple[str, str]] = []
    parallel_flags: list[bool] = []

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
        # 默认兜底：无法路由，串行安全优先
        task_text = f"{task}\n背景：{context}" if context else task
        pairs.append((default_agent_id, task_text))
        parallel_flags.append(False)

    overall_parallel = bool(parallel_flags) and all(parallel_flags)
    return pairs, overall_parallel


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
