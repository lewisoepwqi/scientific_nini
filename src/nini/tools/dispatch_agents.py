"""dispatch_agents 工具 —— 将任务分发给多个 Specialist Agent 并行执行后融合结果。

继承 tools/base.py:Tool，通过 TaskRouter → SubAgentSpawner → ResultFusionEngine 流水线执行。
该工具不暴露给子 Agent（防止递归派发），仅主 Agent 可调用。
"""

from __future__ import annotations

import logging
from typing import Any

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
            "将复杂任务分解并分发给多个专业 Agent 并行执行，融合结果后返回整合摘要。"
            "适用于需要多领域协作的任务（如同时进行数据清洗、统计分析、作图）。"
            "tasks 中每个元素都应是可独立并行的子任务，避免互相依赖。"
            "参数 tasks 为任务描述列表，context 为可选背景信息。"
            "最小示例：tasks=['清洗异常值','绘制分组箱线图']，context='数据集为 blood_pressure_cleaned'。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "tasks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "需要并行处理的任务描述列表，每个元素为一个独立子任务",
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
        tasks: list[str] | None = None,
        context: str = "",
        **kwargs: Any,
    ) -> ToolResult:
        """执行多 Agent 并行派发。

        Args:
            session: 当前会话
            tasks: 任务描述列表
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

        tasks = tasks or []

        # 空任务快速返回
        if not tasks:
            return ToolResult(
                success=True,
                message="",
                metadata={
                    "task_count": 0,
                    "routed_agents": [],
                    "recovery_hint": "如需并行派发，请在 tasks 中提供至少一个可独立执行的子任务。",
                },
            )

        # 为每个任务构造 (agent_id, task) 元组。
        # 直接调用 execute() 时，这里也会进行真实路由，而不是退化到固定 agent。
        task_pairs = await _build_task_pairs(
            tasks,
            task_router=self._task_router,
            agent_registry=self._agent_registry,
            context=context,
        )

        if not task_pairs:
            return self._input_error(
                message="dispatch_agents 无法为当前任务找到可用的 Agent。",
                error_code="DISPATCH_AGENTS_NO_MATCHED_AGENTS",
                expected_fields=["tasks"],
                recovery_hint="拆分为更明确的独立子任务，或检查 AgentRegistry 中是否存在可用 Agent。",
                minimal_example='{"tasks":["清洗缺失值","执行独立样本 t 检验"],"context":"研究问题为干预组与对照组比较"}',
            )

        # 并行派发
        sub_results = await self._spawner.spawn_batch(task_pairs, session)

        # 融合结果
        fusion_result = await self._fusion_engine.fuse(sub_results)
        routed_agents = [agent_id for agent_id, _ in task_pairs]

        return ToolResult(
            success=True,
            message=fusion_result.content,
            metadata={
                "task_count": len(tasks),
                "routed_agents": routed_agents,
                "fusion_strategy": fusion_result.strategy,
                "sources": fusion_result.sources,
                "conflicts": fusion_result.conflicts,
            },
        )

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


async def _build_task_pairs(
    tasks: list[str],
    *,
    task_router: Any,
    agent_registry: Any,
    context: str = "",
) -> list[tuple[str, str]]:
    """为任务列表构造 (agent_id, task_description) 元组。

    若 AgentRegistry 不可用或无已注册 Agent，返回空列表。
    """
    if agent_registry is None:
        return []

    available_agents = agent_registry.list_agents()
    if not available_agents:
        return []

    available_agent_ids = {agent.agent_id for agent in available_agents}
    default_agent_id = available_agents[0].agent_id
    pairs: list[tuple[str, str]] = []
    for task in tasks:
        routed_pairs = await _route_task_pairs(
            task,
            task_router=task_router,
            available_agent_ids=available_agent_ids,
            context=context,
        )
        if routed_pairs:
            pairs.extend(routed_pairs)
            continue
        task_text = f"{task}\n背景：{context}" if context else task
        pairs.append((default_agent_id, task_text))

    return pairs


async def _route_task_pairs(
    task: str,
    *,
    task_router: Any,
    available_agent_ids: set[str],
    context: str,
) -> list[tuple[str, str]]:
    """通过 TaskRouter 生成合法的 (agent_id, task) 对。"""
    if task_router is None:
        return []

    decision = await task_router.route(
        task,
        context={"background": context} if context else None,
    )
    if not getattr(decision, "agent_ids", None):
        return []

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
    return routed_pairs
