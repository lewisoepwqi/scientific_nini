"""子 Agent 动态派生器。

提供 SubAgentResult 数据类和 SubAgentSpawner 类，
支持单次派生、指数退避重试和批量并行执行。
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SubAgentResult:
    """子 Agent 执行结果。"""

    agent_id: str
    success: bool
    summary: str = ""
    detailed_output: str = ""
    artifacts: dict[str, Any] = field(default_factory=dict)
    documents: dict[str, Any] = field(default_factory=dict)
    token_usage: dict[str, Any] = field(default_factory=dict)
    execution_time_ms: int = 0


class SubAgentSpawner:
    """子 Agent 动态派生器。

    负责创建子会话、构造受限工具集、执行子 Agent ReAct 循环，
    支持超时控制、重试和批量并行执行。
    """

    def __init__(self, registry: Any, tool_registry: Any) -> None:
        """初始化派生器。

        Args:
            registry: AgentRegistry 实例，用于查询 Agent 定义
            tool_registry: ToolRegistry 实例，用于构造受限工具子集
        """
        self._registry = registry
        self._tool_registry = tool_registry

    async def spawn(
        self,
        agent_id: str,
        task: str,
        session: Any,
        timeout_seconds: int = 300,
        *,
        attempt: int = 1,
        retry_count: int = 0,
    ) -> SubAgentResult:
        """派生并执行单个子 Agent。

        Args:
            agent_id: Agent 定义 ID
            task: 分配给子 Agent 的任务描述
            session: 父会话（用于共享数据集和推送事件）
            timeout_seconds: 超时秒数

        Returns:
            SubAgentResult：执行结果
        """
        agent_def = self._registry.get(agent_id)
        if agent_def is None:
            logger.warning("SubAgentSpawner.spawn: 未知 agent_id '%s'", agent_id)
            return SubAgentResult(
                agent_id=agent_id,
                success=False,
                summary=f"未找到 Agent 定义: {agent_id}",
            )

        # 推送 agent_start 事件
        await self._push_event(
            session,
            "agent_start",
            {
                "event_type": "agent_start",
                "agent_id": agent_id,
                "agent_name": agent_def.name,
                "task": task,
                "attempt": attempt,
                "retry_count": retry_count,
            },
        )

        start_time = time.monotonic()
        # 根据 paradigm 字段路由到对应执行路径
        paradigm = getattr(agent_def, "paradigm", "react")
        if paradigm == "hypothesis_driven":
            _execute_coro = self._spawn_hypothesis_driven(agent_def, task, session)
        else:
            _execute_coro = self._execute_agent(agent_def, task, session)
        try:
            result = await asyncio.wait_for(
                _execute_coro,
                timeout=float(timeout_seconds),
            )
        except asyncio.TimeoutError:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            error_msg = f"Agent '{agent_id}' 执行超时（{timeout_seconds}s）"
            logger.warning(error_msg)
            await self._push_event(
                session,
                "agent_error",
                {
                    "event_type": "agent_error",
                    "agent_id": agent_id,
                    "agent_name": agent_def.name,
                    "error": error_msg,
                    "execution_time_ms": elapsed_ms,
                    "attempt": attempt,
                    "retry_count": retry_count,
                },
            )
            return SubAgentResult(
                agent_id=agent_id,
                success=False,
                summary="执行超时",
                execution_time_ms=elapsed_ms,
            )
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            error_msg = f"Agent '{agent_id}' 执行异常: {exc}"
            logger.exception(error_msg)
            await self._push_event(
                session,
                "agent_error",
                {
                    "event_type": "agent_error",
                    "agent_id": agent_id,
                    "agent_name": agent_def.name,
                    "error": str(exc),
                    "execution_time_ms": elapsed_ms,
                    "attempt": attempt,
                    "retry_count": retry_count,
                },
            )
            return SubAgentResult(
                agent_id=agent_id,
                success=False,
                summary=error_msg,
                execution_time_ms=elapsed_ms,
            )

        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        result.execution_time_ms = elapsed_ms

        if result.success:
            await self._push_event(
                session,
                "agent_complete",
                {
                    "event_type": "agent_complete",
                    "agent_id": agent_id,
                    "agent_name": agent_def.name,
                    "summary": result.summary,
                    "execution_time_ms": elapsed_ms,
                    "attempt": attempt,
                    "retry_count": retry_count,
                },
            )
        else:
            await self._push_event(
                session,
                "agent_error",
                {
                    "event_type": "agent_error",
                    "agent_id": agent_id,
                    "agent_name": agent_def.name,
                    "error": result.summary or "执行失败",
                    "execution_time_ms": elapsed_ms,
                    "attempt": attempt,
                    "retry_count": retry_count,
                },
            )

        return result

    async def spawn_with_retry(
        self,
        agent_id: str,
        task: str,
        session: Any,
        max_retries: int = 3,
    ) -> SubAgentResult:
        """派生子 Agent，失败时指数退避重试。

        Args:
            agent_id: Agent 定义 ID
            task: 任务描述
            session: 父会话
            max_retries: 最大重试次数（含首次执行）

        Returns:
            最终执行结果（首次成功或达到上限后的失败结果）
        """
        agent_def = self._registry.get(agent_id)
        timeout = agent_def.timeout_seconds if agent_def else 300

        last_result: SubAgentResult | None = None
        for attempt in range(max_retries):
            result = await self.spawn(
                agent_id,
                task,
                session,
                timeout_seconds=timeout,
                attempt=attempt + 1,
                retry_count=attempt,
            )
            if result.success:
                return result
            last_result = result
            if attempt < max_retries - 1:
                wait_secs = 2**attempt
                logger.info(
                    "Agent '%s' 第 %d 次执行失败，%ds 后重试",
                    agent_id,
                    attempt + 1,
                    wait_secs,
                )
                await asyncio.sleep(wait_secs)

        return last_result or SubAgentResult(
            agent_id=agent_id, success=False, summary="重试次数耗尽"
        )

    async def spawn_batch(
        self,
        tasks: list[tuple[str, str]],
        session: Any,
        max_concurrency: int = 4,
    ) -> list[SubAgentResult]:
        """批量并行执行子 Agent。

        Args:
            tasks: (agent_id, task_description) 元组列表
            session: 父会话
            max_concurrency: 最大并发数（asyncio.Semaphore 控制）

        Returns:
            与输入顺序一致的 SubAgentResult 列表
        """
        if not tasks:
            return []

        semaphore = asyncio.Semaphore(max_concurrency)

        async def run_with_semaphore(agent_id: str, task: str) -> SubAgentResult:
            async with semaphore:
                return await self.spawn(agent_id, task, session)

        results = await asyncio.gather(
            *(run_with_semaphore(agent_id, task) for agent_id, task in tasks),
            return_exceptions=False,
        )

        # 串行将子 Agent 产物回写到父会话
        for result in results:
            if isinstance(result, SubAgentResult):
                session.artifacts.update(result.artifacts)
                session.documents.update(result.documents)

        return list(results)

    async def _execute_agent(
        self,
        agent_def: Any,
        task: str,
        parent_session: Any,
    ) -> SubAgentResult:
        """执行子 Agent ReAct 循环。

        Args:
            agent_def: AgentDefinition 实例
            task: 任务描述
            parent_session: 父会话

        Returns:
            SubAgentResult
        """
        from nini.agent.runner import AgentRunner
        from nini.agent.sub_session import SubSession

        # 构造子会话，共享父会话数据集和事件回调
        sub_session = SubSession(
            parent_session_id=parent_session.id,
            datasets=parent_session.datasets,
            artifacts={},
            documents={},
            event_callback=parent_session.event_callback,
        )

        # 构造受限工具子集
        subset_registry = self._tool_registry.create_subset(agent_def.allowed_tools)

        # 实例化 AgentRunner，注入受限工具集
        runner = AgentRunner(tool_registry=subset_registry)

        # 执行 ReAct 循环，收集输出
        output_parts: list[str] = []
        async for event in runner.run(sub_session, task):
            from nini.agent.events import EventType

            if event.type == EventType.TEXT and event.data:
                text = event.data if isinstance(event.data, str) else str(event.data)
                output_parts.append(text)

        detailed_output = "".join(output_parts)
        summary = (
            detailed_output[:500] if detailed_output else f"Agent {agent_def.agent_id} 执行完成"
        )

        return SubAgentResult(
            agent_id=agent_def.agent_id,
            success=True,
            summary=summary,
            detailed_output=detailed_output,
            artifacts=dict(sub_session.artifacts),
            documents=dict(sub_session.documents),
        )

    async def _spawn_hypothesis_driven(
        self,
        agent_def: Any,
        task: str,
        parent_session: Any,
    ) -> SubAgentResult:
        """执行 Hypothesis-Driven 推理循环。

        创建 SubSession，初始化 HypothesisContext，外层 Python 循环调用
        AgentRunner 单轮 ReAct，直到 HypothesisContext.should_conclude() 为 True。

        Args:
            agent_def: AgentDefinition（paradigm == "hypothesis_driven"）
            task: 任务描述
            parent_session: 父会话

        Returns:
            SubAgentResult，detailed_output 包含完整假设链
        """
        from nini.agent.runner import AgentRunner
        from nini.agent.sub_session import SubSession
        from nini.agent.hypothesis_context import HypothesisContext, Hypothesis
        from nini.agent import event_builders as eb

        # 推送范式切换事件
        callback = getattr(parent_session, "event_callback", None)
        await self._push_event(
            parent_session,
            "paradigm_switched",
            eb.build_paradigm_switched_event(agent_def.agent_id, "hypothesis_driven").data,
        )

        # 创建子会话
        sub_session = SubSession(
            parent_session_id=parent_session.id,
            datasets=parent_session.datasets,
            artifacts={},
            documents={},
            event_callback=parent_session.event_callback,
        )

        # 初始化假设上下文，存入子会话 artifacts
        hypothesis_context = HypothesisContext()
        sub_session.artifacts["_hypothesis_context"] = hypothesis_context

        # 构造受限工具子集
        subset_registry = self._tool_registry.create_subset(agent_def.allowed_tools)
        runner = AgentRunner(tool_registry=subset_registry)

        all_output_parts: list[str] = []

        while not hypothesis_context.should_conclude():
            # 构建带假设链提示的任务消息
            if hypothesis_context.hypotheses:
                hyp_summary = "\n".join(
                    f"- [{h.status}] {h.content} (置信度: {h.confidence:.2f})"
                    for h in hypothesis_context.hypotheses
                )
                round_task = (
                    f"{task}\n\n当前假设列表：\n{hyp_summary}\n\n"
                    "请根据现有假设收集证据或提出新假设，给出本轮分析结论。"
                )
            else:
                round_task = f"{task}\n\n请提出 2-3 个初始假设并说明检验方法。"

            # 执行单轮 ReAct
            output_parts: list[str] = []
            async for event in runner.run(sub_session, round_task):
                from nini.agent.events import EventType

                if event.type == EventType.TEXT and event.data:
                    text = event.data if isinstance(event.data, str) else str(event.data)
                    output_parts.append(text)

            round_output = "".join(output_parts)
            all_output_parts.append(round_output)

            # 首轮生成假设事件（如尚未生成）
            if not hypothesis_context.hypotheses:
                hypothesis_context.hypotheses.append(
                    Hypothesis(id="h1", content=round_output[:200] if round_output else task)
                )
                await self._push_event(
                    parent_session,
                    "hypothesis_generated",
                    eb.build_hypothesis_generated_event(
                        agent_def.agent_id,
                        [
                            {"id": h.id, "content": h.content, "confidence": h.confidence}
                            for h in hypothesis_context.hypotheses
                        ],
                    ).data,
                )
            else:
                # 后续轮次：推送证据收集事件（简化：将本轮输出视为支持证据）
                if round_output and hypothesis_context.hypotheses:
                    h = hypothesis_context.hypotheses[0]
                    hypothesis_context.update_confidence(h.id, "for")
                    h.evidence_for.append(round_output[:200])
                    await self._push_event(
                        parent_session,
                        "evidence_collected",
                        eb.build_evidence_collected_event(
                            agent_def.agent_id, h.id, "for", round_output[:200]
                        ).data,
                    )

            hypothesis_context.iteration_count += 1

        # 推送最终假设状态事件
        for h in hypothesis_context.hypotheses:
            if h.confidence >= 0.65:
                h.status = "validated"
                await self._push_event(
                    parent_session,
                    "hypothesis_validated",
                    eb.build_hypothesis_validated_event(
                        agent_def.agent_id, h.id, h.confidence
                    ).data,
                )
            elif h.confidence <= 0.30:
                h.status = "refuted"
                await self._push_event(
                    parent_session,
                    "hypothesis_refuted",
                    eb.build_hypothesis_refuted_event(agent_def.agent_id, h.id, "置信度过低").data,
                )

        detailed_output = "\n".join(all_output_parts)
        summary = (
            detailed_output[:500] if detailed_output else f"Agent {agent_def.agent_id} 完成假设推理"
        )

        return SubAgentResult(
            agent_id=agent_def.agent_id,
            success=True,
            summary=summary,
            detailed_output=detailed_output,
            artifacts={k: v for k, v in sub_session.artifacts.items() if not k.startswith("_")},
            documents=dict(sub_session.documents),
        )

    async def _push_event(
        self,
        session: Any,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        """通过父会话 event_callback 推送事件。

        若 event_callback 为 None 则静默跳过。
        """
        callback = getattr(session, "event_callback", None)
        if callback is None:
            return
        try:
            from nini.agent.events import AgentEvent, EventType

            event_type_enum = EventType(event_type)
            event = AgentEvent(type=event_type_enum, data=payload)
            if asyncio.iscoroutinefunction(callback):
                await callback(event)
            else:
                callback(event)
        except Exception as exc:
            logger.warning("推送事件 '%s' 失败: %s", event_type, exc)
