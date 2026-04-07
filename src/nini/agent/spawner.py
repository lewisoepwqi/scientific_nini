"""子 Agent 动态派生器。

提供 SubAgentResult 数据类和 SubAgentSpawner 类，
支持单次派生、指数退避重试和批量并行执行。
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

logger = logging.getLogger(__name__)

# model_preference → ModelResolver purpose 映射表
# 子 Agent 的 model_preference 声明按此表翻译为 resolver.chat() 的 purpose 参数
# 注意：ModelResolver 中 "planning"/"verification" 等内部用途仍由 runner 自主决策
_MODEL_PREFERENCE_TO_PURPOSE: dict[str | None, str] = {
    "haiku": "fast",
    "sonnet": "analysis",
    "opus": "deep_reasoning",
    None: "analysis",  # 未声明时与父 Agent 默认保持一致
}


class _FixedPurposeResolver:
    """包装 ModelResolver，将子 Agent 的所有 chat 调用的 purpose 固定为指定值。

    子 Agent 的 model_preference 通过此包装器影响模型选择，
    父 Agent 的 resolver 及其 API key/base_url 配置完全保留。
    """

    def __init__(self, base: Any, purpose: str) -> None:
        self._base = base
        self._purpose = purpose

    async def chat(
        self,
        messages: Any,
        tools: Any = None,
        *,
        purpose: str = "default",
        **kwargs: Any,
    ):
        """代理 chat 调用，强制使用固定 purpose。"""
        async for chunk in self._base.chat(messages, tools, purpose=self._purpose, **kwargs):
            yield chunk

    async def preflight(self, *, purpose: str = "default"):
        """代理预检调用，强制使用固定 purpose。"""
        return await self._base.preflight(purpose=self._purpose)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._base, name)


# OpenTelemetry 集成（可选依赖，缺失时降级为无操作）
try:
    from opentelemetry import trace as _otel_trace

    _tracer = _otel_trace.get_tracer("nini.agent.spawner")
    _OTEL_AVAILABLE = True
except ImportError:
    _tracer = None  # type: ignore[assignment]
    _OTEL_AVAILABLE = False


def _start_span(name: str, attributes: dict[str, Any] | None = None):
    """启动 OTel span，若 OTel 不可用则返回无操作上下文管理器。"""
    if _OTEL_AVAILABLE and _tracer is not None:
        span = _tracer.start_as_current_span(name)
        if attributes:
            import contextlib

            @contextlib.contextmanager
            def _span_ctx():
                with span as s:
                    for k, v in attributes.items():
                        try:
                            s.set_attribute(k, str(v))
                        except Exception:
                            pass
                    yield s

            return _span_ctx()
        return span
    import contextlib

    @contextlib.contextmanager
    def _noop():
        yield None

    return _noop()


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


@dataclass
class BatchPreflightPlan:
    """批量子任务的预检计划。"""

    ordered_results: list[SubAgentResult | None]
    executable_tasks: list[tuple[int, str, str]]

    @property
    def failed_results(self) -> list[SubAgentResult]:
        return [result for result in self.ordered_results if result is not None]

    @property
    def runnable_count(self) -> int:
        return len(self.executable_tasks)

    @property
    def failure_count(self) -> int:
        return len(self.failed_results)


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
        # 断路器：记录各 agent_id 的连续失败次数（跨 spawn_with_retry 调用有效）
        self._circuit_breaker_failures: dict[str, int] = {}

    @staticmethod
    def _build_subagent_task(task: str, *, allow_task_planning: bool) -> str:
        """为子 Agent 注入执行边界，避免其在窄任务上重新规划整条流程。"""
        if allow_task_planning:
            return task
        guardrail = (
            "执行约束：这是主 Agent 分配给你的单个窄子任务。\n"
            "只执行当前任务所需的分析，不要重新拆分全局任务，不要创建新的任务板，"
            "不要调用 task_state 或 task_write。\n\n"
        )
        return guardrail + task

    @staticmethod
    def _extract_child_failure_message(event: Any) -> str | None:
        """从子 Agent 事件中提取失败信号。"""
        from nini.agent.events import EventType

        if event.type == EventType.ERROR:
            data = getattr(event, "data", None)
            if isinstance(data, dict):
                return (
                    str(data.get("message") or data.get("error") or "").strip()
                    or "子 Agent 执行失败"
                )
            return str(data or "").strip() or "子 Agent 执行失败"

        if event.type == EventType.TOOL_RESULT:
            data = getattr(event, "data", None)
            if isinstance(data, dict) and str(data.get("status") or "").strip() == "error":
                return str(data.get("message") or "工具执行失败").strip()
        return None

    @staticmethod
    def _collect_session_level_failures(session: Any) -> list[str]:
        """从子会话消息中补采集失败信号，兜底 runner 未显式抛错的场景。"""
        failures: list[str] = []
        for message in getattr(session, "messages", []):
            if not isinstance(message, dict):
                continue
            if (
                message.get("role") == "tool"
                and str(message.get("status") or "").strip() == "error"
            ):
                content = str(message.get("content") or "").strip()
                if content:
                    failures.append(content)
            elif (
                message.get("role") == "assistant"
                and str(message.get("event_type") or "").strip() == "error"
            ):
                content = str(message.get("content") or "").strip()
                if content:
                    failures.append(content)
        return failures

    def _record_child_audit_event(
        self,
        *,
        child_session: Any,
        event: Any,
        agent_def: Any,
        run_id: str,
        parent_turn_id: str | None,
        attempt: int,
        subtask_index: int | None,
    ) -> None:
        """将子 Agent 原始事件写入子会话审计日志。"""
        if (
            child_session is None
            or not getattr(child_session, "supports_persistent_state", lambda: False)()
        ):
            return
        try:
            from nini.agent.session import session_manager

            session_manager.append_agent_run_event(
                child_session.id,
                {
                    "type": getattr(event.type, "value", str(event.type)),
                    "data": getattr(event, "data", None),
                    "tool_call_id": getattr(event, "tool_call_id", None),
                    "tool_name": getattr(event, "tool_name", None),
                    "turn_id": parent_turn_id or getattr(event, "turn_id", None),
                    "metadata": {
                        "run_scope": "subagent",
                        "run_id": run_id,
                        "agent_id": agent_def.agent_id,
                        "agent_name": agent_def.name,
                        "attempt": attempt,
                        "subtask_index": subtask_index,
                        "phase": getattr(event.type, "value", str(event.type)),
                    },
                },
            )
        except Exception as exc:
            logger.debug("写入子会话审计事件失败（非致命）: %s", exc)

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
        subtask_index: int | None = None,
        skip_preflight: bool = False,
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
        with _start_span(
            "sub_agent.spawn",
            {"agent.id": agent_id, "agent.attempt": attempt, "task.preview": task[:100]},
        ):
            return await self._spawn_impl(
                agent_id=agent_id,
                task=task,
                session=session,
                timeout_seconds=timeout_seconds,
                attempt=attempt,
                retry_count=retry_count,
                parent_turn_id=parent_turn_id,
                stop_event=stop_event,
                subtask_index=subtask_index,
                skip_preflight=skip_preflight,
            )

    async def _preflight_agent_execution(
        self,
        agent_def: Any,
        task: str,
        *,
        parent_session: Any,
        parent_turn_id: str | None,
        attempt: int,
        retry_count: int,
        run_id: str,
        subtask_index: int | None,
        emit_agent_error: bool = True,
        attach_snapshot: bool = True,
    ) -> SubAgentResult | None:
        """在真正启动子 Agent 前检查模型可执行性。"""
        from nini.agent.model_resolver import model_resolver as _default_resolver

        model_pref = getattr(agent_def, "model_preference", None)
        sub_purpose = _MODEL_PREFERENCE_TO_PURPOSE.get(model_pref, "analysis")
        preflight = await _default_resolver.preflight(purpose=sub_purpose)
        if preflight.available:
            return None

        preflight_reason = preflight.reason or "模型预检失败"
        result = SubAgentResult(
            agent_id=agent_def.agent_id,
            success=False,
            agent_name=agent_def.name,
            task=task,
            summary=preflight_reason,
            execution_time_ms=0,
            error=preflight_reason,
            stop_reason="preflight_failed",
            run_id=run_id,
            turn_id=parent_turn_id or "",
            parent_session_id=str(getattr(parent_session, "id", "") or ""),
        )
        self._finalize_result(
            result,
            agent_def=agent_def,
            task=task,
            parent_session=parent_session,
            parent_turn_id=parent_turn_id,
            run_id=run_id,
        )
        if emit_agent_error:
            await self._emit_preflight_failure_event(
                parent_session=parent_session,
                result=result,
                parent_turn_id=parent_turn_id,
                attempt=attempt,
                retry_count=retry_count,
                subtask_index=subtask_index,
            )
        if attach_snapshot:
            self._attach_snapshot(parent_session, result, attempt=attempt)
        return result

    async def _emit_preflight_failure_event(
        self,
        *,
        parent_session: Any,
        result: SubAgentResult,
        parent_turn_id: str | None,
        attempt: int,
        retry_count: int,
        subtask_index: int | None,
    ) -> None:
        """将预检失败显式推送为子 Agent 错误事件。"""
        await self._push_event(
            parent_session,
            "agent_error",
            {
                "event_type": "agent_error",
                "agent_id": result.agent_id,
                "agent_name": result.agent_name,
                "error": result.error or result.summary,
                "execution_time_ms": 0,
                "attempt": attempt,
                "retry_count": retry_count,
            },
            turn_id=parent_turn_id,
            metadata=self._build_run_metadata(
                parent_turn_id=parent_turn_id,
                agent_id=result.agent_id,
                agent_name=result.agent_name or result.agent_id,
                attempt=attempt,
                run_id=result.run_id,
                subtask_index=subtask_index,
            ),
        )

    async def preflight_batch(
        self,
        tasks: list[tuple[str, str]],
        session: Any,
        *,
        parent_turn_id: str | None = None,
        emit_agent_errors: bool = False,
    ) -> BatchPreflightPlan:
        """批量预检子任务，返回可执行计划。"""
        ordered_results: list[SubAgentResult | None] = [None] * len(tasks)
        executable_tasks: list[tuple[int, str, str]] = []

        for task_index, (agent_id, task) in enumerate(tasks, start=1):
            agent_def = self._registry.get(agent_id)
            if agent_def is None:
                executable_tasks.append((task_index, agent_id, task))
                continue

            run_id = self._build_run_id(parent_turn_id, agent_id, 1, task_index)
            preflight_result = await self._preflight_agent_execution(
                agent_def,
                task,
                parent_session=session,
                parent_turn_id=parent_turn_id,
                attempt=1,
                retry_count=0,
                run_id=run_id,
                subtask_index=task_index,
                emit_agent_error=emit_agent_errors,
                attach_snapshot=emit_agent_errors,
            )
            if preflight_result is not None:
                ordered_results[task_index - 1] = preflight_result
            else:
                executable_tasks.append((task_index, agent_id, task))

        return BatchPreflightPlan(
            ordered_results=ordered_results,
            executable_tasks=executable_tasks,
        )

    async def _spawn_impl(
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
        subtask_index: int | None = None,
        skip_preflight: bool = False,
    ) -> SubAgentResult:
        """spawn 的实际实现（由 spawn() 包装 OTel span 后调用）。"""
        agent_def = self._registry.get(agent_id)
        if agent_def is None:
            logger.warning("SubAgentSpawner.spawn: 未知 agent_id '%s'", agent_id)
            return SubAgentResult(
                agent_id=agent_id,
                success=False,
                task=task,
                summary=f"未找到 Agent 定义: {agent_id}",
                error=f"未找到 Agent 定义: {agent_id}",
                stop_reason="missing_agent",
            )

        run_id = self._build_run_id(parent_turn_id, agent_id, attempt, subtask_index)
        run_metadata = self._build_run_metadata(
            parent_turn_id=parent_turn_id,
            agent_id=agent_id,
            agent_name=agent_def.name,
            attempt=attempt,
            run_id=run_id,
            subtask_index=subtask_index,
        )

        if not skip_preflight:
            preflight_result = await self._preflight_agent_execution(
                agent_def,
                task,
                parent_session=session,
                parent_turn_id=parent_turn_id,
                attempt=attempt,
                retry_count=retry_count,
                run_id=run_id,
                subtask_index=subtask_index,
            )
            if preflight_result is not None:
                return preflight_result

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
                    subtask_index=subtask_index,
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
                    subtask_index=subtask_index,
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
                    stop_reason="timeout",
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
                    stop_reason="error",
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
            # 生成执行快照并挂载到父会话（供调试和回放使用）
            self._attach_snapshot(session, result, attempt=attempt)
            return result
        finally:
            if stop_relay_task is not None:
                stop_relay_task.cancel()
            subagent_stop_events.pop(run_id, None)

    # 不可重试的永久失败类型：这些情况下重试无意义
    _PERMANENT_STOP_REASONS: frozenset[str] = frozenset(
        {
            "missing_agent",  # agent_id 不存在，重试也不会出现
            "permission_denied",  # 权限拒绝，配置问题
            "config_error",  # 配置错误
            "preflight_failed",  # 模型额度/配置预检失败，短期内重试无意义
        }
    )

    # 断路器：同一 agent_id 在本次 spawner 实例中连续失败次数阈值
    _CIRCUIT_BREAKER_THRESHOLD: int = 3

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

        对 _PERMANENT_STOP_REASONS 中的失败类型立即返回，不重试。
        瞬时失败（timeout、error）才走指数退避重试。

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

        # 断路器检查：连续失败次数超阈值则立即拒绝
        current_failures = self._circuit_breaker_failures.get(agent_id, 0)
        if current_failures >= self._CIRCUIT_BREAKER_THRESHOLD:
            logger.warning(
                "Agent '%s' 断路器已触发（连续失败 %d 次），跳过本次执行",
                agent_id,
                current_failures,
            )
            return SubAgentResult(
                agent_id=agent_id,
                success=False,
                task=task,
                summary=f"Agent '{agent_id}' 断路器已触发，连续失败 {current_failures} 次",
                stop_reason="circuit_breaker_open",
                error=f"断路器触发（阈值={self._CIRCUIT_BREAKER_THRESHOLD}）",
            )

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
                # 成功：重置断路器计数
                self._circuit_breaker_failures.pop(agent_id, None)
                return result
            # 永久失败：不重试，更新断路器
            if result.stop_reason in self._PERMANENT_STOP_REASONS:
                logger.warning(
                    "Agent '%s' 遇到永久失败（stop_reason=%s），跳过重试",
                    agent_id,
                    result.stop_reason,
                )
                self._circuit_breaker_failures[agent_id] = current_failures + 1
                return result
            last_result = result
            if attempt < max_retries - 1:
                wait_secs = 2**attempt
                logger.info(
                    "Agent '%s' 第 %d 次执行失败（stop_reason=%s），%ds 后重试",
                    agent_id,
                    attempt + 1,
                    result.stop_reason or "unknown",
                    wait_secs,
                )
                await asyncio.sleep(wait_secs)

        # 所有重试耗尽，更新断路器
        self._circuit_breaker_failures[agent_id] = (
            self._circuit_breaker_failures.get(agent_id, 0) + 1
        )
        return last_result or SubAgentResult(
            agent_id=agent_id, success=False, summary="重试次数耗尽", stop_reason="max_retries"
        )

    async def spawn_batch(
        self,
        tasks: list[tuple[str, str]],
        session: Any,
        max_concurrency: int = 4,
        *,
        parent_turn_id: str | None = None,
        preflight_plan: BatchPreflightPlan | None = None,
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

        plan = preflight_plan or await self.preflight_batch(
            tasks,
            session,
            parent_turn_id=parent_turn_id,
            emit_agent_errors=preflight_plan is None,
        )
        ordered_results: list[SubAgentResult | None] = list(plan.ordered_results)
        executable_tasks = list(plan.executable_tasks)

        if preflight_plan is not None:
            for task_index, result in enumerate(ordered_results, start=1):
                if result is None:
                    continue
                await self._emit_preflight_failure_event(
                    parent_session=session,
                    result=result,
                    parent_turn_id=parent_turn_id,
                    attempt=1,
                    retry_count=0,
                    subtask_index=task_index,
                )
                self._attach_snapshot(session, result, attempt=1)

        semaphore = asyncio.Semaphore(max_concurrency)

        async def run_with_semaphore(
            agent_id: str,
            task: str,
            task_index: int,
        ) -> SubAgentResult:
            async with semaphore:
                return await self.spawn(
                    agent_id,
                    task,
                    session,
                    parent_turn_id=parent_turn_id,
                    subtask_index=task_index,
                    skip_preflight=True,
                )

        if executable_tasks:
            raw_results = await asyncio.gather(
                *(
                    run_with_semaphore(agent_id, task, task_index)
                    for task_index, agent_id, task in executable_tasks
                ),
                return_exceptions=False,
            )
            for (task_index, _, _), result in zip(executable_tasks, raw_results, strict=False):
                ordered_results[task_index - 1] = result

        if any(result is None for result in ordered_results):
            raise RuntimeError("spawn_batch 未能为所有子任务生成结果")
        results = cast(list[SubAgentResult], ordered_results)

        # 串行将子 Agent 产物回写到父会话，使用命名空间键 {agent_id}.{key} 防止多 Agent 同名覆盖
        for result in results:
            agent_id = result.agent_id
            for key, value in result.artifacts.items():
                namespaced = f"{agent_id}.{key}"
                if namespaced in session.artifacts:
                    logger.warning("spawn_batch: artifact 命名空间键冲突 '%s'，已覆盖", namespaced)
                session.artifacts[namespaced] = value
            for key, value in result.documents.items():
                namespaced = f"{agent_id}.{key}"
                if namespaced in session.documents:
                    logger.warning("spawn_batch: document 命名空间键冲突 '%s'，已覆盖", namespaced)
                session.documents[namespaced] = value

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
        subtask_index: int | None = None,
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
        effective_run_id = run_id or self._build_run_id(
            parent_turn_id,
            agent_def.agent_id,
            attempt,
            subtask_index,
        )

        # 构造子会话：datasets 浅拷贝以隔离键的增删（防止子 Agent 污染父会话的 datasets 键集）
        current_depth = getattr(parent_session, "spawn_depth", 0)
        sub_session = SubSession(
            parent_session_id=parent_session.id,
            datasets=dict(parent_session.datasets),
            artifacts={},
            documents={},
            persist_runtime_state=True,
            event_callback=self._make_subagent_event_callback(
                parent_session=parent_session,
                agent_def=agent_def,
                parent_turn_id=parent_turn_id,
                attempt=attempt,
                retry_count=retry_count,
                run_id=effective_run_id,
                subtask_index=subtask_index,
            ),
        )
        # 将派生深度写入子会话，使嵌套链路可感知（硬限制 ≤ 2）
        try:
            sub_session.spawn_depth = min(current_depth + 1, 2)
        except (AttributeError, TypeError):
            pass

        # 创建沙箱目录，将子会话的 workspace_root 指向沙箱（隔离并行子 Agent 的写入）
        from nini.config import settings as _settings

        parent_session_id_str = str(getattr(parent_session, "id", "") or "")
        parent_workspace = _settings.sessions_dir / parent_session_id_str / "workspace"
        sandbox_dir = parent_workspace / "sandbox_tmp" / effective_run_id
        try:
            sandbox_dir.mkdir(parents=True, exist_ok=True)
            sub_session.workspace_root = sandbox_dir
        except OSError:
            logger.warning(
                "_execute_agent: 创建沙箱目录失败 %s，使用默认 workspace",
                sandbox_dir,
            )

        # 构造受限工具子集，深度控制 dispatch_agents 暴露
        from nini.agent.tool_exposure_policy import ToolExposurePolicy

        max_depth = getattr(agent_def, "max_spawn_depth", 0)
        allow_task_planning = bool(getattr(agent_def, "allow_subtask_planning", False))
        policy = ToolExposurePolicy.from_agent_def(agent_def)
        if not allow_task_planning:
            policy = ToolExposurePolicy(
                allowed_tools=policy.allowed_tools,
                deny_names=policy.deny_names | frozenset({"task_state", "task_write"}),
                deny_prefixes=policy.deny_prefixes,
            )
        if current_depth < max_depth:
            # 允许子 Agent 派发（移除 dispatch_agents 的黑名单屏蔽）
            policy = ToolExposurePolicy(
                allowed_tools=policy.allowed_tools,
                deny_names=policy.deny_names - {"dispatch_agents"},
                deny_prefixes=policy.deny_prefixes,
            )
        subset_registry = policy.apply(self._tool_registry)

        # 根据 model_preference 选择子 Agent 的 purpose，构造限定 purpose 的 resolver 包装
        from nini.agent.model_resolver import model_resolver as _default_resolver

        model_pref = getattr(agent_def, "model_preference", None)
        sub_purpose = _MODEL_PREFERENCE_TO_PURPOSE.get(model_pref, "analysis")
        sub_resolver = _FixedPurposeResolver(_default_resolver, sub_purpose)

        # 实例化 AgentRunner，注入受限工具集和 purpose 限定的 resolver
        runner = AgentRunner(resolver=sub_resolver, tool_registry=subset_registry)

        # 执行 ReAct 循环，收集输出
        output_parts: list[str] = []
        child_failures: list[str] = []
        effective_task = self._build_subagent_task(
            task,
            allow_task_planning=allow_task_planning,
        )
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
                effective_task,
                effective_stop_event,
            ):
                self._record_child_audit_event(
                    child_session=sub_session,
                    event=event,
                    agent_def=agent_def,
                    run_id=effective_run_id,
                    parent_turn_id=parent_turn_id,
                    attempt=attempt,
                    subtask_index=subtask_index,
                )
                from nini.agent.events import EventType

                await self._relay_child_event(
                    parent_session=parent_session,
                    agent_def=agent_def,
                    event=event,
                    parent_turn_id=parent_turn_id,
                    attempt=attempt,
                    retry_count=retry_count,
                    run_id=effective_run_id,
                    subtask_index=subtask_index,
                )
                failure_message = self._extract_child_failure_message(event)
                if failure_message:
                    child_failures.append(failure_message)
                if event.type == EventType.TEXT and event.data:
                    text = event.data if isinstance(event.data, str) else str(event.data)
                    output_parts.append(text)
        finally:
            reset_log_context(log_token)

        child_failures.extend(self._collect_session_level_failures(sub_session))
        child_failures = list(dict.fromkeys(msg for msg in child_failures if msg))
        success = not effective_stop_event.is_set() and not child_failures
        detailed_output = "".join(output_parts)
        summary: str
        if effective_stop_event.is_set():
            summary = "用户已终止该子 Agent"
        elif child_failures:
            summary = child_failures[0]
        else:
            summary = (
                detailed_output[:500] if detailed_output else f"Agent {agent_def.agent_id} 执行完成"
            )

        # 将沙箱产物移入主 workspace（成功 → artifacts/{agent_id}/，失败 → sandbox_tmp/.failed/{run_id}/）
        await self._archive_sandbox(
            sandbox_dir=sandbox_dir,
            parent_workspace=parent_workspace,
            agent_id=agent_def.agent_id,
            run_id=effective_run_id,
            success=success,
            artifacts=sub_session.artifacts,
        )

        if effective_stop_event.is_set():
            return SubAgentResult(
                agent_id=agent_def.agent_id,
                success=False,
                summary=summary,
                execution_time_ms=0,
                stopped=True,
                stop_reason="用户已终止该子 Agent",
                artifacts=dict(sub_session.artifacts),
                documents=dict(sub_session.documents),
            )

        return SubAgentResult(
            agent_id=agent_def.agent_id,
            success=success,
            agent_name=agent_def.name,
            task=task,
            summary=summary,
            detailed_output=detailed_output,
            artifacts=dict(sub_session.artifacts),
            documents=dict(sub_session.documents),
            error=summary if not success else "",
            stop_reason="" if success else "child_execution_failed",
            run_id=effective_run_id,
            turn_id=parent_turn_id or "",
            parent_session_id=str(getattr(parent_session, "id", "") or ""),
            child_session_id=sub_session.id,
            resource_session_id=sub_session.get_resource_session_id(),
        )

    async def _archive_sandbox(
        self,
        *,
        sandbox_dir: Path,
        parent_workspace: Path,
        agent_id: str,
        run_id: str,
        success: bool,
        artifacts: dict[str, Any],
    ) -> None:
        """将沙箱产物归档到主 workspace。

        成功时移动到 workspace/artifacts/{agent_id}/，失败时移动到
        workspace/sandbox_tmp/.failed/{run_id}/。同时更新 artifacts 中
        ArtifactRef.path 为相对于 workspace 的最终路径。

        Args:
            sandbox_dir: 沙箱目录（workspace/sandbox_tmp/{run_id}/）
            parent_workspace: 父会话 workspace 根目录
            agent_id: 子 Agent ID
            run_id: 本次执行 run_id
            success: 执行是否成功
            artifacts: 子会话 artifacts 字典（原地更新 ArtifactRef.path）
        """
        from nini.agent.artifact_ref import ArtifactRef

        if not isinstance(sandbox_dir, Path) or not sandbox_dir.exists():
            return

        # 沙箱为空（无文件写入）时跳过，避免移动空目录
        has_files = any(sandbox_dir.rglob("*"))
        if not has_files:
            try:
                sandbox_dir.rmdir()
            except OSError:
                pass
            return

        if success:
            dest = parent_workspace / "artifacts" / agent_id
        else:
            dest = parent_workspace / "sandbox_tmp" / ".failed" / run_id

        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(sandbox_dir), str(dest))
            logger.info(
                "_archive_sandbox: 沙箱产物已归档 %s → %s",
                sandbox_dir,
                dest,
            )
        except OSError as exc:
            logger.error(
                "_archive_sandbox: 移动沙箱目录失败 %s → %s: %s，产物仍在沙箱路径",
                sandbox_dir,
                dest,
                exc,
            )
            return

        # 更新 artifacts 中 ArtifactRef 的 path 为相对于 workspace 的最终路径
        if success:
            rel_prefix = Path("artifacts") / agent_id
        else:
            rel_prefix = Path("sandbox_tmp") / ".failed" / run_id

        for key, ref in artifacts.items():
            if isinstance(ref, ArtifactRef):
                filename = Path(ref.path).name
                ref.path = (rel_prefix / filename).as_posix()
                ref.agent_id = agent_id

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
        subtask_index: int | None = None,
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
        effective_run_id = run_id or self._build_run_id(
            parent_turn_id,
            agent_def.agent_id,
            attempt,
            subtask_index,
        )

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
            persist_runtime_state=True,
            event_callback=self._make_subagent_event_callback(
                parent_session=parent_session,
                agent_def=agent_def,
                parent_turn_id=parent_turn_id,
                attempt=attempt,
                retry_count=retry_count,
                run_id=effective_run_id,
                subtask_index=subtask_index,
            ),
        )

        # 初始化假设上下文，存入子会话 artifacts
        hypothesis_context = HypothesisContext()
        sub_session.artifacts["_hypothesis_context"] = hypothesis_context

        # 构造受限工具子集（ToolExposurePolicy 自动排除 dispatch_agents 防递归）
        from nini.agent.tool_exposure_policy import ToolExposurePolicy

        subset_registry = ToolExposurePolicy.from_agent_def(agent_def).apply(self._tool_registry)
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
                        subtask_index=subtask_index,
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
        if result.success and not result.stop_reason:
            result.stop_reason = "completed"
        if not result.error and not result.success:
            result.error = result.summary or "执行失败"

    @staticmethod
    def _attach_snapshot(session: Any, result: Any, *, attempt: int) -> None:
        """生成执行快照并追加到父会话的 sub_agent_snapshots 列表。

        sub_agent_snapshots 由 Session.__init__ 预创建，无需懒初始化。
        """
        try:
            from nini.agent.snapshot import SubAgentRunSnapshot

            snapshot = SubAgentRunSnapshot.from_result(result, attempt=attempt)
            snapshots = getattr(session, "sub_agent_snapshots", None)
            if isinstance(snapshots, list):
                snapshots.append(snapshot)
        except Exception as exc:
            logger.debug("生成子 Agent 快照失败（非致命）: %s", exc)

    @staticmethod
    def _build_run_id(
        parent_turn_id: str | None,
        agent_id: str,
        attempt: int,
        subtask_index: int | None = None,
    ) -> str:
        turn_id = str(parent_turn_id or "unknown").strip() or "unknown"
        subtask_key = (
            f"task{subtask_index}"
            if isinstance(subtask_index, int) and subtask_index > 0
            else "direct"
        )
        return f"agent:{turn_id}:{agent_id}:{subtask_key}:{attempt}"

    def _build_run_metadata(
        self,
        *,
        parent_turn_id: str | None,
        agent_id: str,
        agent_name: str,
        attempt: int,
        run_id: str,
        subtask_index: int | None,
    ) -> dict[str, Any]:
        turn_id = str(parent_turn_id or "").strip() or None
        return {
            "run_scope": "subagent",
            "run_id": run_id,
            "parent_run_id": f"root:{turn_id}" if turn_id else None,
            "agent_id": agent_id,
            "agent_name": agent_name,
            "attempt": attempt,
            "subtask_index": subtask_index,
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
        subtask_index: int | None,
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
                subtask_index=subtask_index,
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
        subtask_index: int | None,
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
            subtask_index=subtask_index,
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
            return None
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
            return None
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
