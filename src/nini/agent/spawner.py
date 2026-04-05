"""子 Agent 动态派生器。

提供 SubAgentResult 数据类和 SubAgentSpawner 类，
支持单次派生、指数退避重试和批量并行执行。
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from dataclasses import dataclass, field
from typing import Any, cast

logger = logging.getLogger(__name__)


@dataclass
class SubAgentResult:
    """子 Agent 执行结果。"""

    agent_id: str
    success: bool
    agent_name: str = ""
    task: str = ""
    summary: str = ""
    detailed_output: str = ""
    artifacts: dict[str, Any] = field(default_factory=dict)
    documents: dict[str, Any] = field(default_factory=dict)
    token_usage: dict[str, Any] = field(default_factory=dict)
    execution_time_ms: int = 0
    stopped: bool = False
    stop_reason: str = ""
    error: str = ""
    run_id: str = ""
    turn_id: str = ""
    parent_session_id: str = ""
    child_session_id: str = ""
    resource_session_id: str = ""


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

    async def _invoke_execute_impl(self, impl: Any, *args: Any, **kwargs: Any) -> Any:
        """兼容旧测试桩的执行签名。"""
        try:
            return await impl(*args, **kwargs)
        except TypeError as exc:
            error_text = str(exc)
            if "unexpected keyword argument" not in error_text:
                raise

        try:
            signature = inspect.signature(impl)
        except (TypeError, ValueError):
            return await impl(*args)

        accepted_kwargs = {
            key: value for key, value in kwargs.items() if key in signature.parameters
        }
        if accepted_kwargs:
            return await impl(*args, **accepted_kwargs)
        return await impl(*args)

    async def spawn(
        self,
        agent_id: str,
        task: str,
        session: Any,
        timeout_seconds: int = 300,
        *,
        attempt: int = 1,
        retry_count: int = 0,
        parent_turn_id: str | None = None,
        stop_event: asyncio.Event | None = None,
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
                task=task,
                summary=f"未找到 Agent 定义: {agent_id}",
                error=f"未找到 Agent 定义: {agent_id}",
            )

        run_id = self._build_run_id(parent_turn_id, agent_id, attempt)
        run_metadata = self._build_run_metadata(
            parent_turn_id=parent_turn_id,
            agent_id=agent_id,
            agent_name=agent_def.name,
            attempt=attempt,
            run_id=run_id,
        )

        subagent_stop_events = getattr(session, "subagent_stop_events", None)
        if not isinstance(subagent_stop_events, dict):
            subagent_stop_events = {}
            setattr(session, "subagent_stop_events", subagent_stop_events)
        child_stop_event = stop_event or asyncio.Event()
        subagent_stop_events[run_id] = child_stop_event
        parent_stop_event = getattr(session, "runtime_stop_event", None)
        stop_relay_task: asyncio.Task[None] | None = None
        if isinstance(parent_stop_event, asyncio.Event):
            if parent_stop_event.is_set():
                child_stop_event.set()
            else:
                stop_relay_task = asyncio.create_task(
                    self._relay_parent_stop_event(
                        parent_stop_event=parent_stop_event,
                        child_stop_event=child_stop_event,
                    )
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
            turn_id=parent_turn_id,
            metadata=run_metadata,
        )
        await self._emit_progress(
            session,
            agent_id=agent_id,
            agent_name=agent_def.name,
            attempt=attempt,
            retry_count=retry_count,
            phase="starting",
            message="子 Agent 已启动，正在准备执行。",
            progress_hint=task[:120] if task else None,
            turn_id=parent_turn_id,
            metadata=run_metadata,
        )

        try:
            start_time = time.monotonic()
            # 根据 paradigm 字段路由到对应执行路径
            paradigm = getattr(agent_def, "paradigm", "react")
            if paradigm == "hypothesis_driven":
                _execute_coro = self._invoke_execute_impl(
                    self._spawn_hypothesis_driven,
                    agent_def,
                    task,
                    session,
                    parent_turn_id=parent_turn_id,
                    attempt=attempt,
                    retry_count=retry_count,
                    run_id=run_id,
                    stop_event=child_stop_event,
                )
            else:
                _execute_coro = self._invoke_execute_impl(
                    self._execute_agent,
                    agent_def,
                    task,
                    session,
                    parent_turn_id=parent_turn_id,
                    attempt=attempt,
                    retry_count=retry_count,
                    run_id=run_id,
                    stop_event=child_stop_event,
                )
            try:
                result = await asyncio.wait_for(
                    _execute_coro,
                    timeout=float(timeout_seconds),
                )
                if not isinstance(result, SubAgentResult):
                    raise TypeError("子 Agent 返回值不是 SubAgentResult")
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
                    turn_id=parent_turn_id,
                    metadata=run_metadata,
                )
                return SubAgentResult(
                    agent_id=agent_id,
                    success=False,
                    agent_name=agent_def.name,
                    task=task,
                    summary="执行超时",
                    execution_time_ms=elapsed_ms,
                    error=error_msg,
                    run_id=run_id,
                    turn_id=parent_turn_id or "",
                    parent_session_id=str(getattr(session, "id", "") or ""),
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
                    turn_id=parent_turn_id,
                    metadata=run_metadata,
                )
                return SubAgentResult(
                    agent_id=agent_id,
                    success=False,
                    agent_name=agent_def.name,
                    task=task,
                    summary=error_msg,
                    execution_time_ms=elapsed_ms,
                    error=str(exc),
                    run_id=run_id,
                    turn_id=parent_turn_id or "",
                    parent_session_id=str(getattr(session, "id", "") or ""),
                )

            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            result.execution_time_ms = elapsed_ms
            self._finalize_result(
                result,
                agent_def=agent_def,
                task=task,
                parent_session=session,
                parent_turn_id=parent_turn_id,
                run_id=run_id,
            )

            if result.stopped:
                await self._push_event(
                    session,
                    "agent_stopped",
                    {
                        "event_type": "agent_stopped",
                        "agent_id": agent_id,
                        "agent_name": agent_def.name,
                        "reason": result.stop_reason or "用户终止",
                        "execution_time_ms": elapsed_ms,
                        "attempt": attempt,
                        "retry_count": retry_count,
                    },
                    turn_id=parent_turn_id,
                    metadata=run_metadata,
                )
            elif result.success:
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
                    turn_id=parent_turn_id,
                    metadata=run_metadata,
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
                    turn_id=parent_turn_id,
                    metadata=run_metadata,
                )
            return result
        finally:
            if stop_relay_task is not None:
                stop_relay_task.cancel()
            subagent_stop_events.pop(run_id, None)

    async def spawn_with_retry(
        self,
        agent_id: str,
        task: str,
        session: Any,
        max_retries: int = 3,
        *,
        parent_turn_id: str | None = None,
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
                parent_turn_id=parent_turn_id,
            )
            if result.success or result.stopped:
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
        *,
        parent_turn_id: str | None = None,
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
                return await self.spawn(
                    agent_id,
                    task,
                    session,
                    parent_turn_id=parent_turn_id,
                )

        raw_results = await asyncio.gather(
            *(run_with_semaphore(agent_id, task) for agent_id, task in tasks),
            return_exceptions=False,
        )
        results = cast(list[SubAgentResult], raw_results)

        # 串行将子 Agent 产物回写到父会话
        for result in results:
            session.artifacts.update(result.artifacts)
            session.documents.update(result.documents)

        return list(results)

    async def _execute_agent(
        self,
        agent_def: Any,
        task: str,
        parent_session: Any,
        *,
        parent_turn_id: str | None = None,
        attempt: int = 1,
        retry_count: int = 0,
        run_id: str | None = None,
        stop_event: asyncio.Event | None = None,
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
        from nini.logging_config import bind_log_context, reset_log_context

        effective_stop_event = stop_event or asyncio.Event()
        effective_run_id = run_id or self._build_run_id(parent_turn_id, agent_def.agent_id, attempt)

        # 构造子会话，共享父会话数据集和事件回调
        sub_session = SubSession(
            parent_session_id=parent_session.id,
            datasets=parent_session.datasets,
            artifacts={},
            documents={},
            event_callback=self._make_subagent_event_callback(
                parent_session=parent_session,
                agent_def=agent_def,
                parent_turn_id=parent_turn_id,
                attempt=attempt,
                retry_count=retry_count,
                run_id=effective_run_id,
            ),
        )

        # 构造受限工具子集
        subset_registry = self._tool_registry.create_subset(agent_def.allowed_tools)

        # 实例化 AgentRunner，注入受限工具集
        runner = AgentRunner(tool_registry=subset_registry)

        # 执行 ReAct 循环，收集输出
        output_parts: list[str] = []
        log_token = bind_log_context(session_id=sub_session.id)
        try:
            logger.info(
                "启动子 Agent: agent=%s parent_session=%s child_session=%s",
                agent_def.agent_id,
                parent_session.id,
                sub_session.id,
            )
            async for event in self._iterate_runner_events(
                runner,
                sub_session,
                task,
                effective_stop_event,
            ):
                from nini.agent.events import EventType

                await self._relay_child_event(
                    parent_session=parent_session,
                    agent_def=agent_def,
                    event=event,
                    parent_turn_id=parent_turn_id,
                    attempt=attempt,
                    retry_count=retry_count,
                    run_id=effective_run_id,
                )
                if event.type == EventType.TEXT and event.data:
                    text = event.data if isinstance(event.data, str) else str(event.data)
                    output_parts.append(text)
        finally:
            reset_log_context(log_token)

        if effective_stop_event.is_set():
            return SubAgentResult(
                agent_id=agent_def.agent_id,
                success=False,
                summary="用户已终止该子 Agent",
                execution_time_ms=0,
                stopped=True,
                stop_reason="用户已终止该子 Agent",
                artifacts=dict(sub_session.artifacts),
                documents=dict(sub_session.documents),
            )

        detailed_output = "".join(output_parts)
        summary = (
            detailed_output[:500] if detailed_output else f"Agent {agent_def.agent_id} 执行完成"
        )

        return SubAgentResult(
            agent_id=agent_def.agent_id,
            success=True,
            agent_name=agent_def.name,
            task=task,
            summary=summary,
            detailed_output=detailed_output,
            artifacts=dict(sub_session.artifacts),
            documents=dict(sub_session.documents),
            run_id=effective_run_id,
            turn_id=parent_turn_id or "",
            parent_session_id=str(getattr(parent_session, "id", "") or ""),
            child_session_id=sub_session.id,
            resource_session_id=sub_session.get_resource_session_id(),
        )

    async def _spawn_hypothesis_driven(
        self,
        agent_def: Any,
        task: str,
        parent_session: Any,
        *,
        parent_turn_id: str | None = None,
        attempt: int = 1,
        retry_count: int = 0,
        run_id: str | None = None,
        stop_event: asyncio.Event | None = None,
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
        from nini.logging_config import bind_log_context, reset_log_context

        effective_stop_event = stop_event or asyncio.Event()
        effective_run_id = run_id or self._build_run_id(parent_turn_id, agent_def.agent_id, attempt)

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
            event_callback=self._make_subagent_event_callback(
                parent_session=parent_session,
                agent_def=agent_def,
                parent_turn_id=parent_turn_id,
                attempt=attempt,
                retry_count=retry_count,
                run_id=effective_run_id,
            ),
        )

        # 初始化假设上下文，存入子会话 artifacts
        hypothesis_context = HypothesisContext()
        sub_session.artifacts["_hypothesis_context"] = hypothesis_context

        # 构造受限工具子集
        subset_registry = self._tool_registry.create_subset(agent_def.allowed_tools)
        runner = AgentRunner(tool_registry=subset_registry)

        all_output_parts: list[str] = []

        log_token = bind_log_context(session_id=sub_session.id)
        try:
            logger.info(
                "启动子 Agent: agent=%s parent_session=%s child_session=%s paradigm=hypothesis_driven",
                agent_def.agent_id,
                parent_session.id,
                sub_session.id,
            )
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
                async for event in self._iterate_runner_events(
                    runner,
                    sub_session,
                    round_task,
                    effective_stop_event,
                ):
                    from nini.agent.events import EventType

                    await self._relay_child_event(
                        parent_session=parent_session,
                        agent_def=agent_def,
                        event=event,
                        parent_turn_id=parent_turn_id,
                        attempt=attempt,
                        retry_count=retry_count,
                        run_id=effective_run_id,
                    )
                    if event.type == EventType.TEXT and event.data:
                        text = event.data if isinstance(event.data, str) else str(event.data)
                        output_parts.append(text)

                round_output = "".join(output_parts)
                all_output_parts.append(round_output)
                if effective_stop_event.is_set():
                    break

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
        finally:
            reset_log_context(log_token)

        if effective_stop_event.is_set():
            return SubAgentResult(
                agent_id=agent_def.agent_id,
                success=False,
                summary="用户已终止该子 Agent",
                execution_time_ms=0,
                stopped=True,
                stop_reason="用户已终止该子 Agent",
                artifacts={k: v for k, v in sub_session.artifacts.items() if not k.startswith("_")},
                documents=dict(sub_session.documents),
            )

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
            agent_name=agent_def.name,
            task=task,
            summary=summary,
            detailed_output=detailed_output,
            artifacts={k: v for k, v in sub_session.artifacts.items() if not k.startswith("_")},
            documents=dict(sub_session.documents),
            run_id=effective_run_id,
            turn_id=parent_turn_id or "",
            parent_session_id=str(getattr(parent_session, "id", "") or ""),
            child_session_id=sub_session.id,
            resource_session_id=sub_session.get_resource_session_id(),
        )

    def _finalize_result(
        self,
        result: SubAgentResult,
        *,
        agent_def: Any,
        task: str,
        parent_session: Any,
        parent_turn_id: str | None,
        run_id: str,
    ) -> None:
        """补齐子 Agent 结果中的结构化上下文字段。"""
        from nini.agent.session import resolve_session_resource_id

        if not result.agent_id:
            result.agent_id = agent_def.agent_id
        if not result.agent_name:
            result.agent_name = agent_def.name
        if not result.task:
            result.task = task
        if not result.run_id:
            result.run_id = run_id
        if not result.turn_id:
            result.turn_id = parent_turn_id or ""
        if not result.parent_session_id:
            result.parent_session_id = str(getattr(parent_session, "id", "") or "")
        if not result.resource_session_id:
            result.resource_session_id = resolve_session_resource_id(parent_session)
        if not result.error and not result.success:
            result.error = result.summary or "执行失败"

    @staticmethod
    def _build_run_id(parent_turn_id: str | None, agent_id: str, attempt: int) -> str:
        turn_id = str(parent_turn_id or "unknown").strip() or "unknown"
        return f"agent:{turn_id}:{agent_id}:{attempt}"

    def _build_run_metadata(
        self,
        *,
        parent_turn_id: str | None,
        agent_id: str,
        agent_name: str,
        attempt: int,
        run_id: str,
    ) -> dict[str, Any]:
        turn_id = str(parent_turn_id or "").strip() or None
        return {
            "run_scope": "subagent",
            "run_id": run_id,
            "parent_run_id": f"root:{turn_id}" if turn_id else None,
            "agent_id": agent_id,
            "agent_name": agent_name,
            "attempt": attempt,
            "phase": None,
            "turn_id": turn_id,
        }

    async def _emit_progress(
        self,
        session: Any,
        *,
        agent_id: str,
        agent_name: str,
        attempt: int,
        retry_count: int,
        phase: str,
        message: str,
        progress_hint: str | None,
        turn_id: str | None,
        metadata: dict[str, Any],
    ) -> None:
        next_metadata = dict(metadata)
        next_metadata["phase"] = phase
        await self._push_event(
            session,
            "agent_progress",
            {
                "event_type": "agent_progress",
                "agent_id": agent_id,
                "agent_name": agent_name,
                "phase": phase,
                "message": message,
                "progress_hint": progress_hint,
                "attempt": attempt,
                "retry_count": retry_count,
            },
            turn_id=turn_id,
            metadata=next_metadata,
        )

    def _make_subagent_event_callback(
        self,
        *,
        parent_session: Any,
        agent_def: Any,
        parent_turn_id: str | None,
        attempt: int,
        retry_count: int,
        run_id: str,
    ):
        async def _callback(event: Any) -> None:
            await self._relay_child_event(
                parent_session=parent_session,
                agent_def=agent_def,
                event=event,
                parent_turn_id=parent_turn_id,
                attempt=attempt,
                retry_count=retry_count,
                run_id=run_id,
            )

        return _callback

    async def _relay_child_event(
        self,
        *,
        parent_session: Any,
        agent_def: Any,
        event: Any,
        parent_turn_id: str | None,
        attempt: int,
        retry_count: int,
        run_id: str,
    ) -> None:
        from nini.agent.events import EventType

        if event.type in {
            EventType.AGENT_START,
            EventType.AGENT_PROGRESS,
            EventType.AGENT_COMPLETE,
            EventType.AGENT_ERROR,
            EventType.AGENT_STOPPED,
        }:
            return

        next_metadata = self._build_run_metadata(
            parent_turn_id=parent_turn_id,
            agent_id=agent_def.agent_id,
            agent_name=agent_def.name,
            attempt=attempt,
            run_id=run_id,
        )
        if isinstance(getattr(event, "metadata", None), dict):
            next_metadata.update(event.metadata)
        await self._push_event(
            parent_session,
            event.type.value,
            event.data,
            tool_call_id=getattr(event, "tool_call_id", None),
            tool_name=getattr(event, "tool_name", None),
            turn_id=parent_turn_id or getattr(event, "turn_id", None),
            metadata=next_metadata,
        )
        progress = self._derive_progress_payload(event)
        if progress is not None:
            await self._emit_progress(
                parent_session,
                agent_id=agent_def.agent_id,
                agent_name=agent_def.name,
                attempt=attempt,
                retry_count=retry_count,
                phase=progress["phase"],
                message=progress["message"],
                progress_hint=progress.get("progress_hint"),
                turn_id=parent_turn_id,
                metadata=next_metadata,
            )

    def _derive_progress_payload(self, event: Any) -> dict[str, Any] | None:
        from nini.agent.events import EventType

        if event.type == EventType.REASONING:
            return {
                "phase": "thinking",
                "message": "正在推理与规划下一步操作。",
                "progress_hint": None,
            }
        if event.type == EventType.TOOL_CALL:
            tool_name = str(getattr(event, "tool_name", "") or "工具")
            return {
                "phase": "tool_call",
                "message": f"正在调用 {tool_name}。",
                "progress_hint": None,
            }
        if event.type == EventType.TOOL_RESULT:
            return {
                "phase": "tool_result",
                "message": "工具执行已返回结果。",
                "progress_hint": None,
            }
        if event.type == EventType.TEXT:
            raw = event.data
            if isinstance(raw, dict):
                content = str(raw.get("content") or "").strip()
            else:
                content = str(raw or "").strip()
            if not content:
                return None
            return {
                "phase": "responding",
                "message": content[:120],
                "progress_hint": None,
            }
        if event.type in {EventType.CHART, EventType.DATA, EventType.ARTIFACT, EventType.IMAGE}:
            return {
                "phase": event.type.value,
                "message": "已生成阶段性产物。",
                "progress_hint": None,
            }
        return None

    async def _iterate_runner_events(
        self,
        runner: Any,
        session: Any,
        task: str,
        stop_event: asyncio.Event,
    ):
        """兼容旧测试桩的 AgentRunner.run 签名。"""
        try:
            event_iter = runner.run(session, task, stop_event=stop_event)
        except TypeError as exc:
            if "unexpected keyword argument 'stop_event'" not in str(exc):
                raise
            event_iter = runner.run(session, task)
        async for event in event_iter:
            yield event

    async def _relay_parent_stop_event(
        self,
        *,
        parent_stop_event: asyncio.Event,
        child_stop_event: asyncio.Event,
    ) -> None:
        """父会话停止时，向子 Agent 广播同一停止信号。"""
        try:
            await parent_stop_event.wait()
            child_stop_event.set()
        except asyncio.CancelledError:
            raise

    async def _push_event(
        self,
        session: Any,
        event_type: str,
        payload: dict[str, Any],
        *,
        tool_call_id: str | None = None,
        tool_name: str | None = None,
        turn_id: str | None = None,
        metadata: dict[str, Any] | None = None,
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
            event = AgentEvent(
                type=event_type_enum,
                data=payload,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                turn_id=turn_id,
                metadata=metadata or {},
            )
            if asyncio.iscoroutinefunction(callback):
                await callback(event)
            else:
                callback(event)
        except Exception as exc:
            logger.warning("推送事件 '%s' 失败: %s", event_type, exc)
