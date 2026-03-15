"""dispatch_agents 工具 —— 将任务分发给多个 Specialist Agent 并行执行后融合结果。

继承 tools/base.py:Skill，通过 TaskRouter → SubAgentSpawner → ResultFusionEngine 流水线执行。
该工具不暴露给子 Agent（防止递归派发），仅主 Agent 可调用。
"""

from __future__ import annotations

import logging
from typing import Any

from nini.tools.base import Skill, SkillResult

logger = logging.getLogger(__name__)


class DispatchAgentsTool(Skill):
    """多 Agent 并行派发工具。

    接受任务描述列表，通过路由器映射到 Specialist Agent，
    并行执行后融合结果，返回整合摘要。
    """

    def __init__(
        self,
        agent_registry: Any = None,
        spawner: Any = None,
        fusion_engine: Any = None,
    ) -> None:
        """初始化工具，通过构造函数注入依赖。

        Args:
            agent_registry: AgentRegistry 实例
            spawner: SubAgentSpawner 实例
            fusion_engine: ResultFusionEngine 实例
        """
        self._agent_registry = agent_registry
        self._spawner = spawner
        self._fusion_engine = fusion_engine

    @property
    def name(self) -> str:
        return "dispatch_agents"

    @property
    def description(self) -> str:
        return (
            "将复杂任务分解并分发给多个专业 Agent 并行执行，融合结果后返回整合摘要。"
            "适用于需要多领域协作的任务（如同时进行数据清洗、统计分析、作图）。"
            "参数 tasks 为任务描述列表，context 为可选背景信息。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
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
    ) -> SkillResult:
        """执行多 Agent 并行派发。

        Args:
            session: 当前会话
            tasks: 任务描述列表
            context: 背景信息（可选）

        Returns:
            SkillResult，message 字段包含融合后的结果文本
        """
        # 依赖检查
        if self._spawner is None or self._fusion_engine is None:
            logger.error("DispatchAgentsTool.execute: 依赖未正确注入（spawner 或 fusion_engine 为 None）")
            return SkillResult(
                success=False,
                message="dispatch_agents 未正确初始化",
            )

        tasks = tasks or []

        # 空任务快速返回
        if not tasks:
            return SkillResult(success=True, message="")

        # 为每个任务构造 (agent_id, task) 元组
        # 使用 AgentRegistry 中存在的第一个 agent 作为默认（若无路由信息）
        # 实际路由由 Orchestrator 钩子 _handle_dispatch_agents 在调用前已完成
        # 这里直接通过 spawner.spawn_batch 使用传入的路由结果
        # （Orchestrator 钩子会将路由后的 agent_id-task 对传入，此处为直接调用路径）
        task_pairs = _build_task_pairs(tasks, self._agent_registry, context)

        if not task_pairs:
            return SkillResult(
                success=False,
                message="dispatch_agents: 无法为任务找到匹配的 Agent",
            )

        # 并行派发
        sub_results = await self._spawner.spawn_batch(task_pairs, session)

        # 融合结果
        fusion_result = await self._fusion_engine.fuse(sub_results)

        return SkillResult(
            success=True,
            message=fusion_result.content,
            metadata={
                "fusion_strategy": fusion_result.strategy,
                "sources": fusion_result.sources,
                "conflicts": fusion_result.conflicts,
            },
        )


def _build_task_pairs(
    tasks: list[str],
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

    # 简单启发：对每个任务选取第一个可用 Agent（Orchestrator 钩子中会做真正路由）
    # 此处为 execute() 直接调用路径（不经过 Orchestrator 钩子）的默认行为
    pairs: list[tuple[str, str]] = []
    for task in tasks:
        # 使用第一个可用 Agent 作为默认
        agent_id = available_agents[0].agent_id
        task_text = f"{task}\n背景：{context}" if context else task
        pairs.append((agent_id, task_text))

    return pairs
