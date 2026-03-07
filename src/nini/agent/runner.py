"""Agent ReAct 主循环。

接收用户消息 → 构建上下文 → 调用 LLM → 执行工具 → 循环。
所有事件通过 callback 推送到调用方（WebSocket / CLI）。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncGenerator, Awaitable, Callable

from nini.agent.model_resolver import (
    LLMChunk,
    ModelResolver,
    model_resolver,
)
from nini.agent.prompt_policy import AGENTS_MD_MAX_CHARS
from nini.agent.providers import ReasoningStreamParser
from nini.agent.session import Session
from nini.config import settings
from nini.knowledge.loader import KnowledgeLoader
from nini.intent import default_intent_analyzer, optimized_intent_analyzer
from nini.intent.service import SLASH_SKILL_WITH_ARGS_RE
from nini.memory.compression import (
    compress_session_history_with_llm,
)
from nini.memory.research_profile import (
    DEFAULT_RESEARCH_PROFILE_ID,
    get_research_profile_manager,
)
from nini.memory.storage import ArtifactStorage
from nini.utils.token_counter import count_messages_tokens, get_tracker
from nini.utils.chart_payload import normalize_chart_payload
from nini.workspace import WorkspaceManager

# 导入事件模块
from nini.agent.events import EventType, AgentEvent, create_reasoning_event
from nini.agent.plan_parser import AnalysisPlan, AnalysisStep, parse_analysis_plan

# 导入类型安全的事件构造器（逐步迁移中）
from nini.agent import event_builders as eb
from nini.agent.task_manager import TaskManager
from nini.capabilities import create_default_capabilities

# 导入组件模块
from nini.agent.components import (
    ContextBuilder,
    maybe_auto_compress,
    force_auto_compress,
    compress_session_context,
    sliding_window_trim,
    ReasoningChainTracker,
    detect_reasoning_type,
    detect_key_decisions,
    calculate_confidence_score,
    execute_tool,
    parse_tool_arguments,
    serialize_tool_result_for_memory,
    compact_tool_content,
    sanitize_for_system_context,
    get_last_user_message,
    replace_arguments,
)

logger = logging.getLogger(__name__)

# 兼容别名：测试通过下划线前缀名称访问此函数
_replace_arguments = replace_arguments


def _get_intent_analyzer():
    """获取配置的意图分析器。

    根据 settings.intent_strategy 返回对应的分析器：
    - optimized_rules: 优化版规则分析器（默认，本地优先）
    - rules: 原始规则分析器
    """
    strategy = getattr(settings, "intent_strategy", "optimized_rules")

    if strategy == "optimized_rules":
        return optimized_intent_analyzer
    return default_intent_analyzer


_CONTEXT_LIMIT_ERROR_PATTERNS = (
    "maximum context length",
    "context length",
    "context window",
    "too many tokens",
    "token limit",
    "prompt is too long",
    "exceeds the context",
    "input is too long",
    "超出上下文",
    "上下文长度",
    "超过最大 token",
    "超过最大token",
)

_SLASH_SKILL_WITH_ARGS_RE = SLASH_SKILL_WITH_ARGS_RE


_RESEARCH_PROFILE_ANALYSIS_TOOLS = {
    "t_test",
    "anova",
    "correlation",
    "regression",
    "mann_whitney",
    "kruskal_wallis",
    "wilcoxon",
    "chi_square",
    "fisher_exact",
}

_FILE_NAME_CONFIRMATION_RE = re.compile(
    r"(文件名|命名).{0,24}(确认使用|是否使用|是否采用|希望修改|可以修改)",
)
_FILE_NAME_CANDIDATE_RE = re.compile(
    r"`([^`\n]+\.[A-Za-z0-9]{1,16})`|[“\"]([^\"\n]+\.[A-Za-z0-9]{1,16})[”\"]"
)


def _tool_result_message(result: Any, *, is_error: bool) -> str:
    """从工具返回值中提取可展示消息。"""
    if isinstance(result, dict):
        if is_error:
            error_message = result.get("error")
            if isinstance(error_message, str) and error_message.strip():
                return error_message
        message = result.get("message")
        if isinstance(message, str) and message.strip():
            return message
    return "工具执行失败" if is_error else "工具执行完成"


def _enrich_chart_payload_from_artifacts(
    chart_data: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    """为实时 chart 事件补齐下载地址与名称。

    前端实时消息优先消费 WebSocket 的 chart 事件；若该事件只包含 metadata，
    会误判为无图表数据。这里优先复用工具返回的 chart artifact，将
    `.plotly.json` 的 download_url 合并回 chart payload。
    """
    enriched = dict(chart_data)
    artifacts = result.get("artifacts")
    if not isinstance(artifacts, list):
        return enriched

    selected_artifact: dict[str, Any] | None = None
    for item in artifacts:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        artifact_type = str(item.get("type", "")).strip().lower()
        if name.lower().endswith(".plotly.json"):
            selected_artifact = item
            break
        if artifact_type == "chart" and selected_artifact is None:
            selected_artifact = item

    if selected_artifact is None:
        return enriched

    artifact_url = str(selected_artifact.get("download_url", "")).strip()
    artifact_name = str(selected_artifact.get("name", "")).strip()

    if artifact_url:
        enriched.setdefault("url", artifact_url)
        enriched.setdefault("download_url", artifact_url)
    if artifact_name:
        enriched.setdefault("name", artifact_name)

    return enriched


# ---- Agent Runner ----


class AgentRunner:
    """ReAct 循环执行器。"""

    _AGENTS_MD_MAX_CHARS = AGENTS_MD_MAX_CHARS
    _agents_md_cache: str | None = None  # None means not yet scanned
    _agents_md_scanned: bool = False

    # 静态方法别名：测试通过类属性访问这些工具函数
    _serialize_tool_result_for_memory = staticmethod(serialize_tool_result_for_memory)
    _sanitize_for_system_context = staticmethod(sanitize_for_system_context)

    def __init__(
        self,
        resolver: Any | None = None,
        skill_registry: Any = None,
        knowledge_loader: Any | None = None,
        ask_user_question_handler: (
            Callable[[Session, str, dict[str, Any]], Awaitable[dict[str, str]]] | None
        ) = None,
    ):
        self._resolver = resolver or model_resolver
        self._skill_registry = skill_registry
        self._knowledge_loader = knowledge_loader or KnowledgeLoader(settings.knowledge_dir)
        self._context_builder = ContextBuilder(
            knowledge_loader=self._knowledge_loader,
            skill_registry=skill_registry,
        )
        self._ask_user_question_handler = ask_user_question_handler

    async def run(
        self,
        session: Session,
        user_message: str,
        *,
        append_user_message: bool = True,
        stop_event: asyncio.Event | None = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        """执行一轮 Agent 交互，产出事件流。

        流程：
        1. 将用户消息加入会话
        2. 构建 LLM 调用 messages（系统 prompt + 历史 + 数据摘要）
        3. 调用 LLM 获取响应
        4. 如果有 tool_calls → 执行工具 → 将结果反馈 → 重复
           （当 agent_max_iterations > 0 时最多该次数；<=0 不限制）
        5. 如果是纯文本 → 输出并结束
        """
        turn_id = uuid.uuid4().hex[:12]
        if append_user_message:
            session.add_message("user", user_message, turn_id=turn_id)

        # ---- 试用模式前置检查 ----
        from nini.config_manager import activate_trial, get_active_provider_id, get_trial_status

        active_provider = await get_active_provider_id()
        if not active_provider:
            trial_status = await get_trial_status()
            if trial_status["expired"]:
                # 试用已到期且无自有密钥 → 推送阻断事件后立即返回
                yield AgentEvent(
                    type=EventType.TRIAL_EXPIRED,
                    data={"message": "试用已结束，请配置自己的 API 密钥继续使用"},
                )
                return
            if not trial_status["activated"]:
                # 首次发消息激活试用
                await activate_trial()
                yield AgentEvent(
                    type=EventType.TRIAL_ACTIVATED,
                    data={
                        "fast_calls_remaining": trial_status.get("fast_calls_remaining"),
                        "deep_calls_remaining": trial_status.get("deep_calls_remaining"),
                    },
                )

        max_iter = settings.agent_max_iterations
        should_stop = stop_event.is_set if stop_event else (lambda: False)
        report_markdown_for_turn: str | None = None
        active_plan: AnalysisPlan | None = None
        next_step_idx: int = 0
        plan_event_seq: int = 0
        iteration = 0
        # Initialize reasoning chain tracker for this turn
        reasoning_tracker = ReasoningChainTracker()
        # 消息序列号，用于生成 message_id (格式: {turn_id}-{sequence})
        message_seq: int = 0
        # 当前消息ID，用于关联同一消息的多个流式片段
        current_message_id: str | None = None
        reasoning_tracker = ReasoningChainTracker()
        # 同一轮内的工具失败链路：用于重复错误熔断
        tool_failure_chains: dict[str, dict[str, Any]] = {}
        breaker_threshold = max(1, int(settings.tool_circuit_breaker_threshold))
        allowed_tool_whitelist, allowed_tool_sources = self._resolve_allowed_tool_recommendations(
            user_message
        )

        async for intent_event in self._maybe_handle_intent_clarification(
            session,
            user_message,
            turn_id=turn_id,
        ):
            yield intent_event

        def _build_tool_args_signature(name: str, raw_arguments: str) -> str:
            parsed = parse_tool_arguments(raw_arguments)
            if parsed:
                normalized = json.dumps(parsed, ensure_ascii=False, sort_keys=True, default=str)
            else:
                normalized = str(raw_arguments).strip()
            return f"{name}::{normalized}"

        def _to_plan_status(raw_status: str) -> str:
            """将历史计划状态映射为前端统一状态。"""
            mapping = {
                "pending": "not_started",
                "in_progress": "in_progress",
                "completed": "done",
                "error": "failed",
                "not_started": "not_started",
                "done": "done",
                "failed": "failed",
                "skipped": "skipped",
                "blocked": "blocked",
            }
            return mapping.get(raw_status, "not_started")

        def _build_plan_progress_payload(
            *,
            current_idx: int,
            step_status: str,
            next_hint: str | None = None,
            block_reason: str | None = None,
        ) -> dict[str, Any]:
            """构建 plan_progress 标准载荷。"""
            if active_plan is None or not active_plan.steps:
                return {
                    "current_step_index": 0,
                    "total_steps": 0,
                    "step_title": "",
                    "step_status": "not_started",
                    "next_hint": next_hint,
                }

            safe_idx = max(0, min(current_idx, len(active_plan.steps) - 1))
            current_step = active_plan.steps[safe_idx]
            total_steps = len(active_plan.steps)
            resolved_status = _to_plan_status(step_status)

            auto_next_hint = next_hint
            if auto_next_hint is None:
                next_idx = safe_idx + 1
                if resolved_status in {"failed", "blocked"}:
                    auto_next_hint = "可尝试重试当前步骤或补充输入后继续。"
                elif resolved_status == "done" and next_idx < total_steps:
                    auto_next_hint = f"下一步：{active_plan.steps[next_idx].title}"
                elif resolved_status == "done" and next_idx >= total_steps:
                    auto_next_hint = "全部步骤已完成。"
                elif resolved_status == "in_progress":
                    auto_next_hint = (
                        f"完成后将进入：{active_plan.steps[next_idx].title}"
                        if next_idx < total_steps
                        else "当前为最后一步，完成后将结束流程。"
                    )
                else:
                    auto_next_hint = f"下一步：{current_step.title}"

            payload: dict[str, Any] = {
                "current_step_index": safe_idx + 1,
                "total_steps": total_steps,
                "step_title": current_step.title,
                "step_status": resolved_status,
                "next_hint": auto_next_hint,
            }
            if block_reason:
                payload["block_reason"] = block_reason
            return payload

        def _new_plan_progress_event(
            *,
            current_idx: int,
            step_status: str,
            next_hint: str | None = None,
            block_reason: str | None = None,
        ) -> AgentEvent:
            """创建带序号的计划进度事件，便于前端乱序保护。"""
            nonlocal plan_event_seq
            plan_event_seq += 1
            payload = _build_plan_progress_payload(
                current_idx=current_idx,
                step_status=step_status,
                next_hint=next_hint,
                block_reason=block_reason,
            )
            return eb.build_plan_progress_event(
                steps=payload.get("steps", []),
                current_step_index=payload.get("current_step_index", 1),
                total_steps=payload.get("total_steps", 1),
                step_title=payload.get("step_title", ""),
                step_status=payload.get("step_status", "not_started"),
                next_hint=payload.get("next_hint"),
                block_reason=payload.get("block_reason"),
                turn_id=turn_id,
                seq=plan_event_seq,
            )

        def _new_analysis_plan_event(plan_data: dict[str, Any]) -> AgentEvent:
            """创建带序号的分析计划事件，确保前端按同一时钟域处理。"""
            nonlocal plan_event_seq
            plan_event_seq += 1
            return eb.build_analysis_plan_event(
                steps=plan_data.get("steps", []),
                raw_text=plan_data.get("raw_text", ""),
                turn_id=turn_id,
                seq=plan_event_seq,
            )

        def _new_plan_step_update_event(step_data: dict[str, Any]) -> AgentEvent:
            """创建带序号的任务步骤更新事件，避免被前端乱序保护丢弃。"""
            nonlocal plan_event_seq
            plan_event_seq += 1
            return eb.build_plan_step_update_event(
                step_id=step_data.get("id", 0),
                status=step_data.get("status", ""),
                error=step_data.get("error"),
                turn_id=turn_id,
                seq=plan_event_seq,
            )

        def _new_task_attempt_event(
            *,
            step_id: int | None,
            action_id: str | None,
            tool_name: str,
            attempt: int,
            max_attempts: int,
            status: str,
            error: str | None = None,
            note: str | None = None,
        ) -> AgentEvent:
            """创建任务尝试事件（attempt 级别），用于前端展示重试轨迹。"""
            nonlocal plan_event_seq
            plan_event_seq += 1
            return eb.build_task_attempt_event(
                action_id=action_id,
                step_id=step_id,
                tool_name=tool_name,
                attempt=attempt,
                max_attempts=max_attempts,
                status=status,
                error=error,
                note=note,
                turn_id=turn_id,
                seq=plan_event_seq,
            )

        # 自动上下文压缩检查
        compress_event = await self._maybe_auto_compress(session)
        if compress_event is not None:
            yield compress_event

        while max_iter <= 0 or iteration < max_iter:
            if should_stop():
                yield eb.build_done_event(turn_id=turn_id)
                return

            # 通知前端新迭代开始（用于重置流式文本累积）
            yield eb.build_iteration_start_event(
                iteration=iteration,
                turn_id=turn_id,
            )
            # 重置当前消息ID，新迭代生成新的消息ID
            current_message_id = None

            # 构建消息与检索可观测事件
            messages, retrieval_event = await self._build_messages_and_retrieval(session)
            if iteration == 0 and retrieval_event is not None:
                yield eb.build_retrieval_event(
                    query=retrieval_event.get("query", ""),
                    results=retrieval_event.get("results", []),
                    turn_id=turn_id,
                )
            # 基于完整上下文再次检查 token（含系统提示、知识注入与压缩摘要）
            compress_event = await self._maybe_auto_compress(
                session,
                current_tokens=count_messages_tokens(messages),
            )
            if compress_event is not None:
                yield compress_event
                messages, _ = await self._build_messages_and_retrieval(session)

            # 获取工具定义
            tools = self._get_tool_definitions()

            # 调用 LLM（流式）；若遇到上下文超限错误，自动压缩后重试一次
            full_text = ""
            full_reasoning = ""
            raw_full_text = ""
            tool_calls: list[dict[str, Any]] = []
            usage: dict[str, int] = {}
            retried_after_compress = False
            effective_model_info: dict[str, Any] | None = None
            fallback_chain: list[dict[str, Any]] = []
            fallback_event_sent = False
            # 流式 reasoning 追踪
            current_reasoning_id: str | None = None
            streamed_reasoning_buffer = ""

            while True:
                full_text = ""
                full_reasoning = ""
                raw_full_text = ""
                tool_calls = []
                usage = {}
                current_reasoning_id = None
                streamed_reasoning_buffer = ""
                try:
                    async for chunk in self._resolver.chat(
                        messages,
                        tools or None,
                        purpose="chat",
                    ):
                        if should_stop():
                            yield eb.build_done_event(turn_id=turn_id)
                            return

                        chunk_reasoning = getattr(chunk, "reasoning", "")
                        if chunk_reasoning:
                            stripped = ReasoningStreamParser.strip_reasoning_markers(
                                str(chunk_reasoning)
                            )
                            full_reasoning += stripped
                            # 流式推送 reasoning（如果启用）
                            if settings.enable_reasoning and stripped:
                                if current_reasoning_id is None:
                                    current_reasoning_id = str(uuid.uuid4())
                                streamed_reasoning_buffer += stripped
                                yield eb.build_reasoning_event(
                                    content=stripped,
                                    reasoning_id=current_reasoning_id,
                                    reasoning_live=True,
                                    turn_id=turn_id,
                                )

                        chunk_raw_text = getattr(chunk, "raw_text", "")
                        if chunk_raw_text:
                            raw_full_text += chunk_raw_text

                        # 流式推送文本
                        if chunk.text:
                            display_text = ReasoningStreamParser.strip_reasoning_markers(
                                str(chunk.text)
                            )
                            if display_text:
                                full_text += display_text
                                if not chunk_raw_text:
                                    raw_full_text += chunk.text
                                # 生成消息ID（首次发送时）
                                if current_message_id is None:
                                    current_message_id = f"{turn_id}-{message_seq}"
                                    message_seq += 1
                                yield eb.build_text_event(
                                    content=display_text,
                                    turn_id=turn_id,
                                    metadata={
                                        "message_id": current_message_id,
                                        "operation": "append",
                                    },
                                )

                        if chunk.tool_calls:
                            tool_calls.extend(chunk.tool_calls)

                        if chunk.usage:
                            usage = chunk.usage

                        chunk_provider_id = str(getattr(chunk, "provider_id", "") or "").strip()
                        if chunk_provider_id:
                            effective_model_info = {
                                "provider_id": chunk_provider_id,
                                "provider_name": str(
                                    getattr(chunk, "provider_name", "") or chunk_provider_id
                                ).strip(),
                                "model": str(getattr(chunk, "model", "") or "").strip()
                                or "unknown",
                                "attempt": int(getattr(chunk, "attempt", 1) or 1),
                            }
                            raw_chain = getattr(chunk, "fallback_chain", [])
                            if isinstance(raw_chain, list):
                                fallback_chain = [
                                    item for item in raw_chain if isinstance(item, dict)
                                ]

                        if (
                            not fallback_event_sent
                            and bool(getattr(chunk, "fallback_applied", False))
                            and effective_model_info is not None
                        ):
                            from_provider_id = (
                                str(getattr(chunk, "fallback_from_provider_id", "") or "").strip()
                                or None
                            )
                            from_model = (
                                str(getattr(chunk, "fallback_from_model", "") or "").strip() or None
                            )
                            reason = (
                                str(getattr(chunk, "fallback_reason", "") or "").strip() or None
                            )
                            from_provider_name: str | None = None
                            for item in fallback_chain:
                                if str(item.get("provider_id", "")).strip() != (
                                    from_provider_id or ""
                                ):
                                    continue
                                from_provider_name = (
                                    str(item.get("provider_name", "")).strip() or None
                                )
                                break

                            yield eb.build_model_fallback_event(
                                purpose="chat",
                                attempt=int(effective_model_info.get("attempt", 1) or 1),
                                from_provider_id=from_provider_id,
                                from_provider_name=from_provider_name,
                                from_model=from_model,
                                to_provider_id=str(effective_model_info.get("provider_id", "")),
                                to_provider_name=str(effective_model_info.get("provider_name", "")),
                                to_model=str(effective_model_info.get("model", "")),
                                reason=reason,
                                fallback_chain=fallback_chain,
                                turn_id=turn_id,
                            )
                            fallback_event_sent = True
                except asyncio.CancelledError:
                    logger.info("Agent 运行被取消: session=%s", session.id)
                    raise
                except Exception as e:
                    # 仅在无输出且尚未重试时触发自动压缩重试，避免重复流式片段。
                    if (
                        not retried_after_compress
                        and not full_text
                        and not full_reasoning
                        and not raw_full_text
                        and not tool_calls
                        and self._is_context_limit_error(e)
                    ):
                        forced_event = await self._force_auto_compress(
                            session,
                            current_tokens=count_messages_tokens(messages),
                        )
                        if forced_event is not None:
                            retried_after_compress = True
                            yield forced_event
                            messages, _ = await self._build_messages_and_retrieval(session)
                            continue
                    logger.error("LLM 调用失败: %s", e)
                    yield eb.build_error_event(message=str(e), turn_id=turn_id)
                    return
                break

            if full_reasoning.strip() and settings.enable_reasoning:
                # Detect enhanced reasoning metadata
                reasoning_type = detect_reasoning_type(full_reasoning)
                key_decisions = detect_key_decisions(full_reasoning)
                confidence_score = calculate_confidence_score(full_reasoning)

                # Track in reasoning chain
                reasoning_node = reasoning_tracker.add_reasoning(
                    content=full_reasoning.strip(),
                    reasoning_type=reasoning_type,
                    key_decisions=key_decisions,
                    confidence_score=confidence_score,
                )

                # 发送最终 reasoning 事件（标记为完成）
                # 如果有流式 reasoning，使用相同的 reasoning_id 以便前端合并
                final_reasoning_id = current_reasoning_id or reasoning_node.get("id")
                # 先保存到 session 持久化
                session.add_reasoning(
                    content=full_reasoning.strip(),
                    reasoning_type=reasoning_type,
                    key_decisions=key_decisions,
                    confidence_score=confidence_score,
                    reasoning_id=final_reasoning_id,
                    parent_id=reasoning_node.get("parent_id"),
                    turn_id=turn_id,
                )
                yield eb.build_reasoning_event(
                    content=full_reasoning.strip(),
                    reasoning_id=final_reasoning_id,
                    reasoning_live=False,
                    turn_id=turn_id,
                    reasoning_type=reasoning_type,
                    key_decisions=key_decisions,
                    confidence_score=confidence_score,
                    parent_id=reasoning_node.get("parent_id"),
                )

            # 记录 token 消耗
            if usage and settings.enable_cost_tracking:
                model_info = effective_model_info or self._resolver.get_active_model_info(
                    purpose="chat"
                )
                tracker = get_tracker(session.id)
                rec = tracker.record(
                    model=model_info.get("model", "unknown"),
                    input_tokens=usage.get("input_tokens", 0),
                    output_tokens=usage.get("output_tokens", 0),
                )
                # 推送 token 使用事件到前端
                yield eb.build_token_usage_event(
                    input_tokens=rec.input_tokens,
                    output_tokens=rec.output_tokens,
                    model=rec.model,
                    cost_usd=rec.cost_usd,
                    turn_id=turn_id,
                    total_tokens=rec.input_tokens + rec.output_tokens,
                    session_total_tokens=tracker.total_tokens,
                    session_total_cost=tracker.total_cost_usd,
                )

            if should_stop():
                yield eb.build_done_event(turn_id=turn_id)
                return

            # 如果没有 tool_calls → 纯文本回复，结束循环
            if not tool_calls:
                final_text = full_text or raw_full_text
                confirmation_payload = self._build_confirmation_question_payload(final_text)
                if confirmation_payload and self._ask_user_question_handler is not None:
                    tool_call_id = f"confirm-ask-{uuid.uuid4().hex[:8]}"
                    arguments = json.dumps(confirmation_payload, ensure_ascii=False)
                    session.add_tool_call(
                        tool_call_id,
                        "ask_user_question",
                        arguments,
                        turn_id=turn_id,
                        message_id=f"tool-call-{tool_call_id}",
                    )
                    yield eb.build_tool_call_event(
                        tool_call_id=tool_call_id,
                        name="ask_user_question",
                        arguments={"name": "ask_user_question", "arguments": arguments},
                        turn_id=turn_id,
                        metadata={"source": "confirmation_fallback"},
                    )
                    yield eb.build_ask_user_question_event(
                        questions=confirmation_payload.get("questions", []),
                        turn_id=turn_id,
                        tool_call_id=tool_call_id,
                        tool_name="ask_user_question",
                        source="confirmation_fallback",
                    )

                    try:
                        raw_answers = await self._ask_user_question_handler(
                            session,
                            tool_call_id,
                            confirmation_payload,
                        )
                        normalized_answers = self._normalize_ask_user_question_answers(raw_answers)
                        result = {
                            "success": True,
                            "message": "已收到用户回答。",
                            "data": {
                                "questions": confirmation_payload["questions"],
                                "answers": normalized_answers,
                            },
                        }
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        logger.warning(
                            "确认型 ask_user_question 等待用户回答失败: session=%s err=%s",
                            session.id,
                            exc,
                        )
                        result = {
                            "success": False,
                            "message": f"等待用户回答失败: {exc}",
                        }

                    has_error = bool(
                        isinstance(result, dict)
                        and (result.get("error") or result.get("success") is False)
                    )
                    result_str = serialize_tool_result_for_memory(result)
                    session.add_tool_result(
                        tool_call_id,
                        result_str,
                        tool_name="ask_user_question",
                        status="error" if has_error else "success",
                        intent="confirmation_fallback",
                        turn_id=turn_id,
                        message_id=f"tool-result-{tool_call_id}",
                    )
                    yield eb.build_tool_result_event(
                        tool_call_id=tool_call_id,
                        name="ask_user_question",
                        status="error" if has_error else "success",
                        message=_tool_result_message(result, is_error=has_error),
                        data={"result": result},
                        turn_id=turn_id,
                        metadata={"source": "confirmation_fallback"},
                    )
                    iteration += 1
                    continue

                final_message_id = current_message_id or f"{turn_id}-{message_seq}"
                if current_message_id is None:
                    message_seq += 1
                final_message_extra: dict[str, Any] = {}
                if effective_model_info:
                    final_message_extra["effective_model"] = effective_model_info
                if fallback_chain:
                    final_message_extra["fallback_chain"] = fallback_chain
                session.add_message(
                    "assistant",
                    final_text,
                    turn_id=turn_id,
                    message_id=final_message_id,
                    operation="complete",
                    **final_message_extra,
                )
                yield eb.build_done_event(turn_id=turn_id)

                # 会话结束后异步沉淀分析记忆为跨会话长期记忆
                try:
                    from nini.memory.long_term_memory import consolidate_session_memories

                    asyncio.create_task(consolidate_session_memories(session.id))
                except Exception:
                    pass

                return

            # 有 tool_calls → 记录并执行
            # 第一次迭代中，LLM 同时输出文本和 tool_calls：
            # 这段文本是面向用户的解释，应作为正常文本发送给前端
            if iteration == 0 and full_text and full_text.strip():
                assistant_text = full_text.strip()
                # 仅当 LLM 未使用 task_write/task_state 初始化任务（task_manager 未初始化）时
                # 才回退到文本解析模式（parse_analysis_plan 的 fallback 路径）
                # 同时检查即将到来的 tool_calls 是否包含 task_write/task_state，避免重复发送 analysis_plan
                has_task_write_in_calls = any(
                    tc.get("function", {}).get("name") in ("task_write", "task_state")
                    for tc in tool_calls
                )
                if not session.task_manager.initialized and not has_task_write_in_calls:
                    parsed_plan = parse_analysis_plan(assistant_text)
                    if active_plan is None and parsed_plan is not None:
                        active_plan = parsed_plan
                        next_step_idx = 0
                    if active_plan is not None:
                        logger.debug(
                            "[分析计划] 从文本解析发送 analysis_plan，步骤数: %d",
                            len(active_plan.steps),
                        )
                        yield _new_analysis_plan_event(active_plan.to_dict())
                        yield _new_plan_progress_event(
                            current_idx=0,
                            step_status="pending",
                            next_hint=(
                                f"下一步：{active_plan.steps[0].title}"
                                if active_plan.steps
                                else None
                            ),
                        )

                # 说明文本通常已经在上面的流式 chunk 中发送过。
                # 如果这里再次补发且分配新的 message_id，前端会把同一语义渲染成第二个气泡。
                # 仅当上游没有产生任何 text chunk（极少数非标准流实现）时，才补发一次。
                if current_message_id is None:
                    plan_message_id = f"{turn_id}-{message_seq}"
                    message_seq += 1
                    current_message_id = plan_message_id
                    yield eb.build_text_event(
                        content=assistant_text,
                        turn_id=turn_id,
                        metadata={
                            "message_id": plan_message_id,
                            "operation": "append",
                        },
                    )

            # 先把 assistant 带 tool_calls 的消息加入会话
            assistant_tool_msg: dict[str, Any] = {
                "role": "assistant",
                "content": raw_full_text or full_text or None,
                "event_type": "tool_call",
                "operation": "complete",
                "turn_id": turn_id,
                "tool_calls": tool_calls,
            }
            if effective_model_info:
                assistant_tool_msg["effective_model"] = effective_model_info
            if fallback_chain:
                assistant_tool_msg["fallback_chain"] = fallback_chain
            if current_message_id and assistant_tool_msg["content"]:
                assistant_tool_msg["message_id"] = current_message_id
            session.messages.append(assistant_tool_msg)
            session.conversation_memory.append(assistant_tool_msg)

            for tc in tool_calls:
                if should_stop():
                    yield eb.build_done_event(turn_id=turn_id)
                    return

                tc_id = tc["id"]
                func_name = tc["function"]["name"]
                func_args = tc["function"]["arguments"]
                tool_args_signature = _build_tool_args_signature(func_name, func_args)
                tool_call_metadata: dict[str, Any] = {}
                if func_name in {"run_code", "run_r_code"}:
                    try:
                        parsed_args = json.loads(func_args)
                        if isinstance(parsed_args, dict):
                            intent = str(
                                parsed_args.get("intent") or parsed_args.get("label") or ""
                            ).strip()
                            if intent:
                                tool_call_metadata["intent"] = intent
                    except Exception:
                        pass

                # 从 task_manager 获取当前 in_progress 任务（用于 TASK_ATTEMPT 事件关联）
                # task_write/task_state 本身不计入任务执行轨迹
                matched_step_id: int | None = None
                matched_action_id: str | None = None
                if (
                    func_name not in ("task_write", "task_state")
                    and session.task_manager.has_tasks()
                ):
                    in_progress_task = session.task_manager.current_in_progress()
                    if in_progress_task:
                        matched_action_id = in_progress_task.action_id
                        matched_step_id = in_progress_task.id
                elif func_name not in ("task_write", "task_state") and active_plan is not None:
                    # 兼容 fallback 模式：未使用 task_write 时，最小化推进计划状态。
                    while (
                        next_step_idx < len(active_plan.steps)
                        and active_plan.steps[next_step_idx].status != "pending"
                    ):
                        next_step_idx += 1

                    if next_step_idx < len(active_plan.steps):
                        fallback_step = active_plan.steps[next_step_idx]
                        fallback_action_id = f"fallback_{fallback_step.id}"
                        fallback_step.status = "in_progress"
                        matched_step_id = fallback_step.id
                        matched_action_id = fallback_action_id
                        yield _new_plan_step_update_event(
                            {
                                **fallback_step.to_dict(),
                                "action_id": fallback_action_id,
                            }
                        )
                        yield _new_plan_progress_event(
                            current_idx=next_step_idx,
                            step_status="in_progress",
                        )
                        next_step_idx += 1
                # 确保非 task_write/task_state 工具始终有 action_id（用于关联重试轨迹）
                if matched_action_id is None and func_name not in ("task_write", "task_state"):
                    matched_action_id = tc_id
                # 重试策略：由 LLM 自行决定是否重试，不自动重试
                max_retries = 0

                # 构建 tool_call 元数据
                _tc_metadata: dict[str, Any] = dict(tool_call_metadata)
                if matched_action_id:
                    _tc_metadata["action_id"] = matched_action_id
                    if max_retries > 0:
                        _tc_metadata["retry_policy"] = {
                            "max_retries": max_retries,
                            "retry_count": 0,
                        }
                yield eb.build_tool_call_event(
                    tool_call_id=tc_id,
                    name=func_name,
                    arguments=func_args,
                    turn_id=turn_id,
                    metadata=_tc_metadata or None,
                )

                # Markdown Skill 的 allowed_tools 仅作推荐提示，不做硬阻断。
                if allowed_tool_whitelist is not None and func_name not in allowed_tool_whitelist:
                    allowed_sorted = ", ".join(sorted(allowed_tool_whitelist))
                    source_text = (
                        ", ".join(allowed_tool_sources) if allowed_tool_sources else "当前技能"
                    )
                    logger.info(
                        "工具 '%s' 不在技能推荐工具集合内（来源技能: %s；推荐工具: %s），继续执行。",
                        func_name,
                        source_text,
                        allowed_sorted,
                    )

                # ── task_write/task_state 特殊处理 ────────────────────────────────
                # task_write 由 LLM 调用来声明/更新任务列表，不走正常执行流程
                # task_state 是 task_write 的代理，也支持 init/update/get/current 操作
                if func_name in ("task_write", "task_state"):
                    result = await self._execute_tool(session, func_name, func_args)
                    has_error = bool(
                        isinstance(result, dict)
                        and (result.get("error") or result.get("success") is False)
                    )
                    if not has_error:
                        try:
                            tw_args = json.loads(func_args)
                            # task_write 使用 mode，task_state 使用 operation
                            tw_mode = tw_args.get("mode") or tw_args.get("operation", "init")
                            if tw_mode == "init":
                                plan_dict = session.task_manager.to_analysis_plan_dict()
                                logger.debug(
                                    "[分析计划] 从 %s 发送 analysis_plan，步骤数: %d",
                                    func_name,
                                    len(plan_dict.get("steps", [])),
                                )
                                yield _new_analysis_plan_event(plan_dict)
                                yield _new_plan_progress_event(
                                    current_idx=0,
                                    step_status="pending",
                                    next_hint=(
                                        session.task_manager.tasks[0].title
                                        if session.task_manager.tasks
                                        else None
                                    ),
                                )
                            else:  # update
                                # 收集需要发送事件的任务 ID：包括显式更新的和自动完成的
                                updated_ids = {
                                    int(u["id"]) for u in tw_args.get("tasks", []) if "id" in u
                                }
                                auto_completed: set[int] = set()
                                if isinstance(result, dict):
                                    result_data = result.get("data", {})
                                    if isinstance(result_data, dict):
                                        auto_completed = set(
                                            result_data.get("auto_completed_ids", [])
                                        )
                                all_event_ids = updated_ids | auto_completed
                                for t in session.task_manager.tasks:
                                    if t.id in all_event_ids:
                                        yield _new_plan_step_update_event(
                                            {
                                                "id": t.id,
                                                "title": t.title,
                                                "tool_hint": t.tool_hint,
                                                "status": t.status,
                                                "action_id": t.action_id,
                                            }
                                        )
                        except Exception as exc:
                            logger.debug("%s 事件发射失败: %s", func_name, exc)

                    result_str = serialize_tool_result_for_memory(result)
                    session.add_tool_result(
                        tc_id,
                        result_str,
                        tool_name=func_name,
                        status="success" if not has_error else "error",
                        turn_id=turn_id,
                        message_id=f"tool-result-{tc_id}",
                    )
                    yield eb.build_tool_result_event(
                        tool_call_id=tc_id,
                        name=func_name,
                        status="success" if not has_error else "error",
                        message=_tool_result_message(result, is_error=has_error),
                        data={"result": result},
                        turn_id=turn_id,
                    )
                    continue  # 跳过正常执行流程
                # ── task_write/task_state 特殊处理结束 ────────────────────────────

                # ── ask_user_question 特殊处理 ─────────────────────────────────
                # ask_user_question 会暂停当前回合，等待用户完成回答后继续。
                if func_name == "ask_user_question":
                    try:
                        parsed_payload = json.loads(func_args)
                    except json.JSONDecodeError:
                        parsed_payload = None

                    questions, question_error = self._normalize_ask_user_question_questions(
                        parsed_payload
                    )
                    if question_error:
                        result = {"success": False, "message": question_error}
                    elif self._ask_user_question_handler is None:
                        result = {
                            "success": False,
                            "message": "当前通道不支持 ask_user_question 交互。",
                        }
                    else:
                        assert questions is not None
                        yield eb.build_ask_user_question_event(
                            questions=questions,
                            turn_id=turn_id,
                            tool_call_id=tc_id,
                            tool_name=func_name,
                        )
                        try:
                            raw_answers = await self._ask_user_question_handler(
                                session,
                                tc_id,
                                {"questions": questions},
                            )
                            normalized_answers = self._normalize_ask_user_question_answers(
                                raw_answers
                            )
                            result = {
                                "success": True,
                                "message": "已收到用户回答。",
                                "data": {
                                    "questions": questions,
                                    "answers": normalized_answers,
                                },
                            }
                        except asyncio.CancelledError:
                            raise
                        except Exception as exc:
                            logger.warning(
                                "ask_user_question 等待用户回答失败: session=%s tc_id=%s err=%s",
                                session.id,
                                tc_id,
                                exc,
                            )
                            result = {
                                "success": False,
                                "message": f"等待用户回答失败: {exc}",
                            }

                    has_error = bool(
                        isinstance(result, dict)
                        and (result.get("error") or result.get("success") is False)
                    )
                    status = "error" if has_error else "success"
                    result_str = serialize_tool_result_for_memory(result)
                    session.add_tool_result(
                        tc_id,
                        result_str,
                        tool_name=func_name,
                        status=status,
                        turn_id=turn_id,
                        message_id=f"tool-result-{tc_id}",
                    )
                    yield eb.build_tool_result_event(
                        tool_call_id=tc_id,
                        name=func_name,
                        status=status,
                        message=_tool_result_message(result, is_error=has_error),
                        data={"result": result},
                        turn_id=turn_id,
                    )
                    continue
                # ── ask_user_question 特殊处理结束 ─────────────────────────────

                # 智能体生成的代码自动沉淀为工作空间产物
                code_artifact = self._persist_code_source(
                    session=session,
                    func_name=func_name,
                    func_args=func_args,
                )
                if code_artifact:
                    session.add_assistant_event(
                        "artifact",
                        "代码已保存到工作空间",
                        turn_id=turn_id,
                        artifacts=[code_artifact],
                    )
                    yield eb.build_artifact_event(
                        artifact_id=code_artifact.get("id", ""),
                        artifact_type=code_artifact.get("type", ""),
                        name=code_artifact.get("name", ""),
                        url=code_artifact.get("url"),
                        mime_type=code_artifact.get("mime_type"),
                        turn_id=turn_id,
                        tool_call_id=tc_id,
                        tool_name=func_name,
                    )

                if func_name == "code_session":
                    parsed_func_args = parse_tool_arguments(func_args)
                    operation = str(parsed_func_args.get("operation", "")).strip().lower()
                    if operation in {"patch_script", "create_script"}:
                        # 脚本内容发生变更后，清空 code_session 的失败链路，避免误触熔断。
                        for signature in list(tool_failure_chains.keys()):
                            if signature.startswith("code_session::"):
                                tool_failure_chains.pop(signature, None)

                chain_state = tool_failure_chains.get(tool_args_signature)
                if (
                    isinstance(chain_state, dict)
                    and int(chain_state.get("count", 0)) >= breaker_threshold
                ):
                    last_error_code = str(chain_state.get("error_code") or "TOOL_EXECUTION_ERROR")
                    recovery_hint = str(
                        chain_state.get("recovery_hint")
                        or "请调整参数后重试，避免重复发送相同失败调用。"
                    ).strip()
                    result = {
                        "success": False,
                        "message": (
                            f"检测到相同工具调用已连续失败 {int(chain_state.get('count', 0))} 次，"
                            "已触发熔断并阻止本次重复调用。"
                        ),
                        "error_code": "TOOL_CALL_CIRCUIT_BREAKER",
                        "data": {
                            "last_error_code": last_error_code,
                            "recovery_hint": recovery_hint,
                        },
                        "metadata": {
                            "breaker_triggered": True,
                            "breaker_threshold": breaker_threshold,
                            "repeat_failure_count": int(chain_state.get("count", 0)),
                            "last_error_code": last_error_code,
                            "recovery_hint": recovery_hint,
                            "action_id": matched_action_id,
                            "retry_count": 0,
                            "max_retries": max_retries,
                        },
                    }
                    has_error = True
                    status = "error"
                    result_str = serialize_tool_result_for_memory(result)
                    session.add_tool_result(
                        tc_id,
                        result_str,
                        tool_name=func_name,
                        status=status,
                        intent=tool_call_metadata.get("intent"),
                        turn_id=turn_id,
                        message_id=f"tool-result-{tc_id}",
                    )
                    raw_result_metadata = (
                        result.get("metadata") if isinstance(result, dict) else None
                    )
                    event_metadata = (
                        raw_result_metadata if isinstance(raw_result_metadata, dict) else None
                    )
                    yield eb.build_tool_result_event(
                        tool_call_id=tc_id,
                        name=func_name,
                        status=status,
                        message=str(result.get("message", "工具执行失败")),
                        data={"result": result},
                        turn_id=turn_id,
                        metadata=event_metadata,
                    )
                    continue

                # 执行工具（max_retries 已在 TOOL_CALL 事件发出前计算）
                retry_attempt = 0
                max_attempts = max_retries + 1
                while True:
                    attempt_no = retry_attempt + 1
                    yield _new_task_attempt_event(
                        step_id=matched_step_id,
                        action_id=matched_action_id,
                        tool_name=func_name,
                        attempt=attempt_no,
                        max_attempts=max_attempts,
                        status="in_progress",
                        note=f"第 {attempt_no}/{max_attempts} 次尝试执行 {func_name}",
                    )

                    # 执行工具
                    result = await self._execute_tool(session, func_name, func_args)

                    # 检查是否发生了统计降级 fallback
                    if isinstance(result, dict) and result.get("fallback"):
                        fallback_event = create_reasoning_event(
                            step="statistical_fallback",
                            thought=f"由于{result.get('fallback_reason', '前提条件不满足')}，自动降级为非参数检验",
                            rationale=f"原始方法 '{result.get('original_skill')}' 被降级为 '{result.get('fallback_skill')}'",
                            confidence=0.9,
                            original_skill=result.get("original_skill"),
                            fallback_skill=result.get("fallback_skill"),
                            reason=result.get("fallback_reason"),
                        )
                        yield fallback_event

                    has_error = bool(
                        isinstance(result, dict)
                        and (result.get("error") or result.get("success") is False)
                    )

                    error_reason: str | None = None
                    error_code: str | None = None
                    if has_error and isinstance(result, dict):
                        reason_text = result.get("error") or result.get("message")
                        if isinstance(reason_text, str) and reason_text.strip():
                            error_reason = reason_text.strip()
                        raw_error_code = result.get("error_code")
                        if isinstance(raw_error_code, str) and raw_error_code.strip():
                            error_code = raw_error_code.strip()
                        else:
                            raw_meta = result.get("metadata")
                            if isinstance(raw_meta, dict):
                                meta_error_code = raw_meta.get("error_code")
                                if isinstance(meta_error_code, str) and meta_error_code.strip():
                                    error_code = meta_error_code.strip()
                    if has_error and not error_code:
                        error_code = "TOOL_EXECUTION_ERROR"

                    if not has_error:
                        tool_failure_chains.pop(tool_args_signature, None)
                        yield _new_task_attempt_event(
                            step_id=matched_step_id,
                            action_id=matched_action_id,
                            tool_name=func_name,
                            attempt=attempt_no,
                            max_attempts=max_attempts,
                            status="success",
                            note=f"第 {attempt_no}/{max_attempts} 次尝试成功",
                        )
                        break

                    existing_chain = tool_failure_chains.get(tool_args_signature)
                    if isinstance(existing_chain, dict) and str(
                        existing_chain.get("error_code", "")
                    ) == str(error_code):
                        existing_chain["count"] = int(existing_chain.get("count", 0)) + 1
                        existing_chain["message"] = error_reason or existing_chain.get(
                            "message", ""
                        )
                    else:
                        next_recovery_hint: str | None = None
                        if isinstance(result, dict):
                            raw_hint = result.get("recovery_hint")
                            if isinstance(raw_hint, str) and raw_hint.strip():
                                next_recovery_hint = raw_hint.strip()
                            else:
                                data_obj = result.get("data")
                                if isinstance(data_obj, dict):
                                    data_hint = data_obj.get("recovery_hint")
                                    if isinstance(data_hint, str) and data_hint.strip():
                                        next_recovery_hint = data_hint.strip()
                        tool_failure_chains[tool_args_signature] = {
                            "count": 1,
                            "error_code": error_code,
                            "message": error_reason or "",
                            "recovery_hint": next_recovery_hint,
                        }

                    if retry_attempt >= max_retries:
                        yield _new_task_attempt_event(
                            step_id=matched_step_id,
                            action_id=matched_action_id,
                            tool_name=func_name,
                            attempt=attempt_no,
                            max_attempts=max_attempts,
                            status="failed",
                            error=error_reason,
                            note=f"第 {attempt_no}/{max_attempts} 次尝试失败，已达到最大尝试次数",
                        )
                        break

                    yield _new_task_attempt_event(
                        step_id=matched_step_id,
                        action_id=matched_action_id,
                        tool_name=func_name,
                        attempt=attempt_no,
                        max_attempts=max_attempts,
                        status="retrying",
                        error=error_reason,
                        note=f"第 {attempt_no}/{max_attempts} 次尝试失败，准备重试",
                    )

                    retry_attempt += 1
                    logger.warning(
                        "工具执行失败，触发自动重试: session=%s tool=%s action_id=%s attempt=%d/%d",
                        session.id,
                        func_name,
                        matched_action_id,
                        retry_attempt,
                        max_retries,
                    )

                # 判断执行状态
                has_error = bool(
                    isinstance(result, dict)
                    and (result.get("error") or result.get("success") is False)
                )
                status = "error" if has_error else "success"

                if (
                    func_name not in ("task_write", "task_state")
                    and not session.task_manager.initialized
                    and active_plan is not None
                    and matched_step_id is not None
                ):
                    for fallback_idx, fallback_step in enumerate(active_plan.steps):
                        if fallback_step.id != matched_step_id:
                            continue
                        fallback_step.status = "error" if has_error else "completed"
                        yield _new_plan_step_update_event(
                            {
                                **fallback_step.to_dict(),
                                "action_id": matched_action_id,
                            }
                        )
                        yield _new_plan_progress_event(
                            current_idx=fallback_idx,
                            step_status=fallback_step.status,
                        )
                        break

                if func_name == "generate_report" and not has_error and isinstance(result, dict):
                    data_obj = result.get("data")
                    if isinstance(data_obj, dict):
                        report_md = data_obj.get("report_markdown")
                        if isinstance(report_md, str) and report_md.strip():
                            report_markdown_for_turn = report_md

                raw_metadata: Any = result.get("metadata") if isinstance(result, dict) else None
                result_metadata: dict[str, Any] = (
                    raw_metadata if isinstance(raw_metadata, dict) else {}
                )
                top_level_error_code = (
                    result.get("error_code") if isinstance(result, dict) else None
                )
                if (
                    isinstance(top_level_error_code, str)
                    and top_level_error_code.strip()
                    and "error_code" not in result_metadata
                ):
                    result_metadata["error_code"] = top_level_error_code.strip()
                execution_id = result_metadata.get("execution_id")
                if not isinstance(execution_id, str):
                    execution_id = None

                # 推送工具结果
                result_str = serialize_tool_result_for_memory(result)

                # 必须先将工具结果加入会话，保证消息历史完整
                # 即使后续发送事件失败（如 WebSocket 断开），消息顺序也正确
                session.add_tool_result(
                    tc_id,
                    result_str,
                    tool_name=func_name,
                    status=status,
                    intent=tool_call_metadata.get("intent"),
                    execution_id=execution_id,
                    turn_id=turn_id,
                    message_id=f"tool-result-{tc_id}",
                )
                if not has_error:
                    self._record_research_profile_activity(
                        session=session,
                        tool_name=func_name,
                        arguments=func_args,
                    )

                if matched_action_id:
                    result_metadata = {
                        **result_metadata,
                        "action_id": matched_action_id,
                        "retry_count": retry_attempt,
                        "max_retries": max_retries,
                    }

                try:
                    yield eb.build_tool_result_event(
                        tool_call_id=tc_id,
                        name=func_name,
                        status=status,
                        message=_tool_result_message(result, is_error=has_error),
                        data={"result": result},
                        turn_id=turn_id,
                        metadata=result_metadata if isinstance(result_metadata, dict) else None,
                    )
                    # 检查是否有图表数据
                    if isinstance(result, dict) and result.get("has_chart"):
                        raw_chart_data = result.get("chart_data")
                        normalized_chart_data = normalize_chart_payload(raw_chart_data)
                        chart_data_candidate = (
                            normalized_chart_data if normalized_chart_data else raw_chart_data
                        )
                        chart_data: dict[str, Any] = (
                            chart_data_candidate if isinstance(chart_data_candidate, dict) else {}
                        )
                        chart_data = _enrich_chart_payload_from_artifacts(chart_data, result)
                        session.add_assistant_event(
                            "chart",
                            "图表已生成",
                            turn_id=turn_id,
                            chart_data=chart_data,
                        )
                        chart_event_extra = {
                            key: value
                            for key, value in chart_data.items()
                            if key not in {"chart_id", "name", "url", "chart_type"}
                        }
                        yield eb.build_chart_event(
                            chart_id=chart_data.get("id", ""),
                            name=chart_data.get("name", ""),
                            url=chart_data.get("url", ""),
                            chart_type=chart_data.get("chart_type"),
                            turn_id=turn_id,
                            **chart_event_extra,
                        )
                    if isinstance(result, dict) and result.get("has_dataframe"):
                        raw_data_preview = result.get("dataframe_preview")
                        data_preview: dict[str, Any] = (
                            raw_data_preview if isinstance(raw_data_preview, dict) else {}
                        )
                        session.add_assistant_event(
                            "data",
                            "数据预览如下",
                            turn_id=turn_id,
                            data_preview=data_preview,
                        )
                        # 传递完整的数据预览内容，供前端 DataViewer 组件渲染
                        yield eb.build_data_event(
                            data_id=data_preview.get("id", ""),
                            name=data_preview.get("name", ""),
                            url=data_preview.get("url", ""),
                            row_count=data_preview.get("total_rows"),
                            column_count=len(data_preview.get("columns", [])),
                            data=data_preview.get("data", []),
                            columns=data_preview.get("columns", []),
                            total_rows=data_preview.get("total_rows"),
                            preview_rows=data_preview.get("preview_rows"),
                            preview_strategy=data_preview.get("preview_strategy"),
                            turn_id=turn_id,
                        )

                    # 检查是否有产物（可下载文件）
                    if isinstance(result, dict) and result.get("artifacts"):
                        artifacts_raw = result.get("artifacts")
                        if isinstance(artifacts_raw, list):
                            for artifact in artifacts_raw:
                                session.add_assistant_event(
                                    "artifact",
                                    "产物已生成",
                                    turn_id=turn_id,
                                    artifacts=[artifact],
                                )
                                yield eb.build_artifact_event(
                                    artifact_id=artifact.get("id", ""),
                                    artifact_type=artifact.get("type", ""),
                                    name=artifact.get("name", ""),
                                    url=artifact.get("url"),
                                    mime_type=artifact.get("mime_type"),
                                    turn_id=turn_id,
                                    tool_call_id=tc_id,
                                    tool_name=func_name,
                                )
                    if isinstance(result, dict) and result.get("images"):
                        images_raw = result.get("images")
                        images: list[str]
                        if isinstance(images_raw, list):
                            images = [str(url) for url in images_raw if isinstance(url, str)]
                        elif isinstance(images_raw, str):
                            images = [images_raw]
                        else:
                            images = []
                        if images:
                            session.add_assistant_event(
                                "image",
                                "图片已生成",
                                turn_id=turn_id,
                                images=images,
                            )
                            # 为每张图片发送单独的 IMAGE 事件
                            for img_url in images:
                                yield eb.build_image_event(
                                    image_id=img_url.split("/")[-1].split(".")[0],
                                    name=img_url.split("/")[-1],
                                    url=img_url,
                                    turn_id=turn_id,
                                )
                except Exception:
                    # 发送事件失败（如客户端断开），但消息已保存
                    # 继续处理下一个 tool_call
                    pass

            # generate_report 已返回完整报告时，直接将同一内容作为最终回复。
            # 这样可确保页面展示与保存文件完全一致，避免模型二次改写造成偏差。
            if report_markdown_for_turn:
                # 如果有当前消息ID，使用 replace 操作替换之前的内容
                # 否则创建新的消息ID
                report_message_id = current_message_id or f"{turn_id}-{message_seq}"
                if current_message_id is None:
                    message_seq += 1
                report_message_extra: dict[str, Any] = {}
                if effective_model_info:
                    report_message_extra["effective_model"] = effective_model_info
                if fallback_chain:
                    report_message_extra["fallback_chain"] = fallback_chain
                session.add_message(
                    "assistant",
                    report_markdown_for_turn,
                    turn_id=turn_id,
                    message_id=report_message_id,
                    operation="replace",
                    **report_message_extra,
                )
                yield eb.build_text_event(
                    content=report_markdown_for_turn,
                    turn_id=turn_id,
                    metadata={
                        "message_id": report_message_id,
                        "operation": "replace",  # 使用 replace 替换流式预览
                    },
                )
                # 发送 complete 操作标记消息结束
                yield eb.build_text_event(
                    content="",
                    turn_id=turn_id,
                    metadata={
                        "message_id": report_message_id,
                        "operation": "complete",
                    },
                )
                yield eb.build_done_event(turn_id=turn_id)
                return
            iteration += 1

        if max_iter > 0:
            # 达到最大迭代次数（仅在启用上限时触发）
            yield eb.build_error_event(
                message=f"达到最大迭代次数 ({max_iter})，已停止执行。",
                turn_id=turn_id,
            )

    async def _build_messages(self, session: Session) -> list[dict[str, Any]]:
        """构建发送给 LLM 的消息列表。"""
        messages, _ = await self._build_messages_and_retrieval(session)
        return messages

    async def _build_messages_and_retrieval(
        self,
        session: Session,
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        """通过 canonical context builder 构建发送给 LLM 的消息列表。"""
        return await self._context_builder.build_messages_and_retrieval(session)

    def _build_explicit_skill_context(self, user_message: str) -> str:
        """兼容旧测试入口，委托给 canonical context builder。"""
        return self._context_builder.build_explicit_skill_context(user_message)

    def _build_intent_runtime_context(self, user_message: str) -> str:
        """兼容旧测试入口，委托给 canonical context builder。"""
        return self._context_builder.build_intent_runtime_context(user_message)

    async def _maybe_handle_intent_clarification(
        self,
        session: Session,
        user_message: str,
        *,
        turn_id: str,
    ) -> AsyncGenerator[AgentEvent, None]:
        """在首轮 LLM 调用前按需发起意图澄清。"""
        if not user_message or self._ask_user_question_handler is None:
            return

        capability_catalog = [cap.to_dict() for cap in create_default_capabilities()]
        analysis = _get_intent_analyzer().analyze(user_message, capabilities=capability_catalog)
        if not analysis.clarification_needed or not analysis.clarification_question:
            return

        questions = self._build_intent_clarification_questions(analysis)
        if not questions:
            return

        tool_call_id = f"intent-ask-{uuid.uuid4().hex[:8]}"
        payload = {"questions": questions}
        arguments = json.dumps(payload, ensure_ascii=False)
        session.add_tool_call(
            tool_call_id,
            "ask_user_question",
            arguments,
            turn_id=turn_id,
            message_id=f"tool-call-{tool_call_id}",
        )
        yield eb.build_tool_call_event(
            tool_call_id=tool_call_id,
            name="ask_user_question",
            arguments={"name": "ask_user_question", "arguments": arguments},
            turn_id=turn_id,
            metadata={"source": "intent_clarification"},
        )
        yield eb.build_ask_user_question_event(
            questions=questions,
            turn_id=turn_id,
            tool_call_id=tool_call_id,
            tool_name="ask_user_question",
            source="intent_clarification",
        )

        try:
            raw_answers = await self._ask_user_question_handler(
                session,
                tool_call_id,
                payload,
            )
            normalized_answers = self._normalize_ask_user_question_answers(raw_answers)
            result = {
                "success": True,
                "message": "已收到用户回答。",
                "data": {
                    "questions": questions,
                    "answers": normalized_answers,
                },
            }
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("intent 澄清等待用户回答失败: session=%s err=%s", session.id, exc)
            result = {
                "success": False,
                "message": f"等待用户回答失败: {exc}",
            }

        has_error = bool(
            isinstance(result, dict) and (result.get("error") or result.get("success") is False)
        )
        result_str = serialize_tool_result_for_memory(result)
        session.add_tool_result(
            tool_call_id,
            result_str,
            tool_name="ask_user_question",
            status="error" if has_error else "success",
            intent="intent_clarification",
            turn_id=turn_id,
            message_id=f"tool-result-{tool_call_id}",
        )
        yield eb.build_tool_result_event(
            tool_call_id=tool_call_id,
            name="ask_user_question",
            status="error" if has_error else "success",
            message=_tool_result_message(result, is_error=has_error),
            data={"result": result},
            turn_id=turn_id,
            metadata={"source": "intent_clarification"},
        )

    @staticmethod
    def _build_intent_clarification_questions(analysis: Any) -> list[dict[str, Any]]:
        """根据意图分析生成澄清问题。"""
        options = list(getattr(analysis, "clarification_options", []) or [])
        if len(options) < 2:
            candidates = list(getattr(analysis, "capability_candidates", []) or [])
            for candidate in candidates[:3]:
                payload = getattr(candidate, "payload", {}) or {}
                display_name = str(payload.get("display_name", "")).strip() or getattr(
                    candidate, "name", ""
                )
                description = str(payload.get("description", "")).strip() or getattr(
                    candidate, "reason", ""
                )
                if not display_name or not description:
                    continue
                options.append(
                    {
                        "label": display_name,
                        "description": description,
                    }
                )

        if len(options) < 2:
            options = []

        if len(options) < 2:
            for cap in create_default_capabilities()[:3]:
                if any(option["label"] == cap.display_name for option in options):
                    continue
                options.append(
                    {
                        "label": cap.display_name,
                        "description": cap.description,
                    }
                )
                if len(options) >= 2:
                    break

        if len(options) < 2:
            return []

        return [
            {
                "question": analysis.clarification_question,
                "header": "分析目标",
                "options": options[:3],
                "multiSelect": False,
            }
        ]

    def _match_skills_by_context(self, user_message: str) -> list[dict[str, Any]]:
        """兼容旧测试入口，委托给 canonical context builder。"""
        return self._context_builder._match_skills_by_context(user_message)

    @staticmethod
    def _build_confirmation_question_payload(text: str) -> dict[str, Any] | None:
        """将高确定性确认型文本兜底转换为 ask_user_question。"""
        normalized = str(text or "").strip()
        if not normalized:
            return None
        if not _FILE_NAME_CONFIRMATION_RE.search(normalized):
            return None

        filename = None
        match = _FILE_NAME_CANDIDATE_RE.search(normalized)
        if match:
            filename = next((group for group in match.groups() if group), None)

        if filename:
            question = f"建议文件名为 {filename}。是否使用这个文件名？"
            use_description = f"继续使用 {filename} 并继续后续操作"
        else:
            question = "当前步骤需要确认文件名。是否使用当前建议文件名？"
            use_description = "继续使用当前建议文件名并继续后续操作"

        return {
            "questions": [
                {
                    "question": question,
                    "header": "文件名",
                    "options": [
                        {
                            "label": "使用建议文件名",
                            "description": use_description,
                        },
                        {
                            "label": "修改文件名",
                            "description": "输入你希望使用的新文件名后继续",
                        },
                    ],
                    "multiSelect": False,
                    "allowTextInput": True,
                }
            ]
        }

    def _build_skill_runtime_resources_note(self, skill_name: str) -> str:
        """兼容旧测试入口，委托给 canonical context builder。"""
        return self._context_builder._build_skill_runtime_resources_note(skill_name)

    def _select_active_markdown_skills(self, user_message: str) -> list[dict[str, Any]]:
        """选择本轮激活的 Markdown Skills（显式 slash 优先，缺失时走自动匹配）。"""
        if not user_message or self._skill_registry is None:
            return []
        if not hasattr(self._skill_registry, "list_markdown_skills"):
            return []

        markdown_items = self._skill_registry.list_markdown_skills()
        if not isinstance(markdown_items, list):
            return []
        return default_intent_analyzer.select_active_skills(
            user_message,
            markdown_items,
            explicit_limit=self._context_builder.inline_skill_max_count,
            auto_limit=self._context_builder.auto_skill_max_count,
        )

    def _resolve_allowed_tool_recommendations(
        self,
        user_message: str,
    ) -> tuple[set[str] | None, list[str]]:
        """根据激活的 Markdown Skills 解析 allowed_tools 推荐集合。"""
        items = self._select_active_markdown_skills(user_message)
        return default_intent_analyzer.collect_allowed_tools(items)

    @classmethod
    def _discover_agents_md(cls) -> str:
        """兼容旧测试入口，委托给 canonical context builder。"""
        ContextBuilder._agents_md_scanned = cls._agents_md_scanned
        ContextBuilder._agents_md_cache = cls._agents_md_cache
        result = ContextBuilder._discover_agents_md()
        cls._agents_md_scanned = ContextBuilder._agents_md_scanned
        cls._agents_md_cache = ContextBuilder._agents_md_cache
        return result

    def _get_tool_definitions(self) -> list[dict[str, Any]]:
        """获取所有已注册技能的工具定义。"""
        tools: list[dict[str, Any]] = []
        if self._skill_registry is not None:
            raw = self._skill_registry.get_tool_definitions()
            if isinstance(raw, list):
                tools = [item for item in raw if isinstance(item, dict)]

        # 内建用户问答工具：允许模型暂停并向用户发起澄清问题。
        has_ask_user_question = any(
            isinstance(item, dict)
            and isinstance(item.get("function"), dict)
            and item["function"].get("name") == "ask_user_question"
            for item in tools
        )
        if not has_ask_user_question:
            tools.append(self._ask_user_question_tool_definition())
        return tools

    @staticmethod
    def _ask_user_question_tool_definition() -> dict[str, Any]:
        """ask_user_question 工具定义（Claude Code 兼容风格）。"""
        return {
            "type": "function",
            "function": {
                "name": "ask_user_question",
                "description": ("向用户发起 1-4 个澄清问题，等待用户完成回答后继续任务。"),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "questions": {
                            "type": "array",
                            "description": "问题列表（每次 1-4 题）",
                            "minItems": 1,
                            "maxItems": 4,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "question": {"type": "string"},
                                    "header": {"type": "string"},
                                    "options": {
                                        "type": "array",
                                        "minItems": 2,
                                        "maxItems": 4,
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "label": {"type": "string"},
                                                "description": {"type": "string"},
                                            },
                                            "required": ["label", "description"],
                                        },
                                    },
                                    "multiSelect": {"type": "boolean"},
                                    "allowTextInput": {"type": "boolean"},
                                },
                                "required": ["question", "options"],
                            },
                        }
                    },
                    "required": ["questions"],
                },
            },
        }

    @staticmethod
    def _normalize_ask_user_question_questions(
        payload: Any,
    ) -> tuple[list[dict[str, Any]] | None, str | None]:
        """校验并标准化 ask_user_question 的问题列表。"""
        if not isinstance(payload, dict):
            return None, "ask_user_question 参数必须是对象。"

        raw_questions = payload.get("questions")
        if not isinstance(raw_questions, list):
            return None, "ask_user_question 参数缺少 questions 数组。"
        if len(raw_questions) < 1 or len(raw_questions) > 4:
            return None, "ask_user_question 每次调用必须包含 1-4 个问题。"

        normalized_questions: list[dict[str, Any]] = []
        for q_idx, raw_question in enumerate(raw_questions, start=1):
            if not isinstance(raw_question, dict):
                return None, f"第 {q_idx} 个问题格式错误，必须是对象。"

            question = str(raw_question.get("question") or "").strip()
            if not question:
                return None, f"第 {q_idx} 个问题缺少 question 文本。"

            options_raw = raw_question.get("options")
            if not isinstance(options_raw, list):
                return None, f"第 {q_idx} 个问题缺少 options 数组。"
            if len(options_raw) < 2 or len(options_raw) > 4:
                return None, f"第 {q_idx} 个问题 options 数量必须为 2-4 个。"

            normalized_options: list[dict[str, str]] = []
            for opt_idx, raw_opt in enumerate(options_raw, start=1):
                if not isinstance(raw_opt, dict):
                    return None, f"第 {q_idx} 个问题的第 {opt_idx} 个选项格式错误。"
                label = str(raw_opt.get("label") or "").strip()
                description = str(raw_opt.get("description") or "").strip()
                if not label:
                    return None, f"第 {q_idx} 个问题的第 {opt_idx} 个选项缺少 label。"
                if not description:
                    return None, f"第 {q_idx} 个问题的第 {opt_idx} 个选项缺少 description。"
                normalized_options.append(
                    {
                        "label": label,
                        "description": description,
                    }
                )

            normalized_item: dict[str, Any] = {
                "question": question,
                "options": normalized_options,
                "multiSelect": bool(raw_question.get("multiSelect", False)),
            }
            header = raw_question.get("header")
            if isinstance(header, str) and header.strip():
                normalized_item["header"] = header.strip()

            allow_text_input = raw_question.get("allowTextInput")
            if isinstance(allow_text_input, bool):
                normalized_item["allowTextInput"] = allow_text_input

            normalized_questions.append(normalized_item)

        return normalized_questions, None

    @staticmethod
    def _normalize_ask_user_question_answers(raw_answers: Any) -> dict[str, str]:
        """标准化用户回答映射。"""
        if not isinstance(raw_answers, dict):
            return {}

        normalized_answers: dict[str, str] = {}
        for raw_key, raw_value in raw_answers.items():
            if not isinstance(raw_key, str):
                continue
            key = raw_key.strip()
            if not key:
                continue

            if isinstance(raw_value, str):
                value = raw_value.strip()
            elif isinstance(raw_value, (list, tuple)):
                parts = [str(item).strip() for item in raw_value if str(item).strip()]
                value = ", ".join(parts)
            elif raw_value is None:
                value = ""
            else:
                value = str(raw_value).strip()

            normalized_answers[key] = value

        return normalized_answers

    async def _execute_tool(
        self,
        session: Session,
        name: str,
        arguments: str,
    ) -> Any:
        """执行一个工具调用。"""
        if self._skill_registry is None:
            return {"error": f"技能系统未初始化，无法执行 {name}"}

        try:
            args = json.loads(arguments)
        except json.JSONDecodeError:
            return {"error": f"工具参数解析失败: {arguments}"}

        try:
            result = await self._skill_registry.execute_with_fallback(name, session=session, **args)
            return result
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("工具 %s 执行失败: %s", name, e, exc_info=True)
            return {"error": f"工具 {name} 执行失败: {e}"}

    def _record_research_profile_activity(
        self,
        *,
        session: Session,
        tool_name: str,
        arguments: str,
    ) -> None:
        """记录研究画像的最近数据集与常用方法。"""
        profile_id = (
            str(getattr(session, "research_profile_id", DEFAULT_RESEARCH_PROFILE_ID) or "").strip()
            or DEFAULT_RESEARCH_PROFILE_ID
        )
        manager = get_research_profile_manager()
        parsed_args = parse_tool_arguments(arguments)

        dataset_name = parsed_args.get("dataset_name")
        if isinstance(dataset_name, str) and dataset_name.strip():
            manager.record_dataset_usage_sync(profile_id, dataset_name.strip())

        if tool_name not in _RESEARCH_PROFILE_ANALYSIS_TOOLS:
            return

        journal_style = parsed_args.get("journal_style")
        manager.record_analysis_sync(
            profile_id,
            tool_name,
            journal_style=(
                journal_style.strip()
                if isinstance(journal_style, str) and journal_style.strip()
                else None
            ),
        )

    @staticmethod
    def _is_context_limit_error(error: Exception) -> bool:
        """判断异常是否属于上下文长度超限。"""
        text = str(error).lower()
        return any(pattern in text for pattern in _CONTEXT_LIMIT_ERROR_PATTERNS)

    async def _compress_session_context(
        self,
        session: Session,
        *,
        current_tokens: int,
        trigger: str,
    ) -> AgentEvent | None:
        """执行一次上下文压缩并构造事件。"""
        threshold = settings.auto_compress_threshold_tokens
        logger.info(
            "自动压缩触发(%s): 当前 %d tokens, 阈值 %d tokens",
            trigger,
            current_tokens,
            threshold,
        )
        try:
            result = await compress_session_history_with_llm(session, ratio=0.5, min_messages=4)
            if result.get("success"):
                archived_count = result.get("archived_count", 0)
                remaining_count = result.get("remaining_count", 0)
                message = (
                    f"检测到上下文超限，已自动压缩，归档了 {archived_count} 条消息"
                    if trigger == "context_limit_error"
                    else f"上下文已自动压缩，归档了 {archived_count} 条消息"
                )
                return eb.build_context_compressed_event(
                    original_tokens=current_tokens,
                    compressed_tokens=current_tokens // 2,
                    compression_ratio=0.5,
                    message=message,
                    archived_count=archived_count,
                    remaining_count=remaining_count,
                    previous_tokens=current_tokens,
                    trigger=trigger,
                )
        except Exception as exc:
            logger.warning("自动压缩失败(%s): %s", trigger, exc, exc_info=True)
        return None

    async def _maybe_auto_compress(
        self,
        session: Session,
        *,
        current_tokens: int | None = None,
    ) -> AgentEvent | None:
        """检查上下文 token 数，超过阈值时自动压缩。"""
        if not settings.auto_compress_enabled:
            return None
        threshold = settings.auto_compress_threshold_tokens
        measured_tokens = (
            int(current_tokens)
            if current_tokens is not None
            else count_messages_tokens(session.messages)
        )
        if measured_tokens <= threshold:
            return None
        return await self._compress_session_context(
            session,
            current_tokens=measured_tokens,
            trigger="threshold",
        )

    async def _force_auto_compress(
        self,
        session: Session,
        *,
        current_tokens: int,
    ) -> AgentEvent | None:
        """忽略阈值强制尝试自动压缩（用于上下文超限恢复）。"""
        if not settings.auto_compress_enabled:
            return None
        return await self._compress_session_context(
            session,
            current_tokens=int(current_tokens),
            trigger="context_limit_error",
        )

    def _persist_code_source(
        self,
        *,
        session: Session,
        func_name: str,
        func_args: str,
    ) -> dict[str, Any] | None:
        """将代码执行技能片段自动保存到工作空间。

        仅在 purpose 为 visualization 或 export 时保存为可交付产物；
        exploration/transformation 的代码只记录到 executions/ 目录。
        """
        if func_name not in {"run_code", "run_r_code"}:
            return None

        try:
            args = json.loads(func_args)
        except Exception:
            return None
        if not isinstance(args, dict):
            return None

        code = args.get("code")
        if not isinstance(code, str) or not code.strip():
            return None

        purpose = str(args.get("purpose", "exploration")).strip()
        label = args.get("label") or None
        is_r_code = func_name == "run_r_code"
        file_ext = "R" if is_r_code else "py"
        language = "r" if is_r_code else "python"

        # exploration/transformation 的代码只写入 executions/，不生成产物
        if purpose not in ("visualization", "export"):
            ws = WorkspaceManager(session.id)
            ws.save_code_execution(
                code=code.rstrip(),
                output="",
                status="pending",
                language=language,
                tool_name=func_name,
                tool_args=args,
                intent=str(args.get("intent") or args.get("label") or "").strip() or None,
            )
            return None

        # visualization/export 保存为可交付产物，使用 label 命名
        ws = WorkspaceManager(session.id)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        if label:
            filename = ws.sanitize_filename(f"{label}.{file_ext}", default_name=f"code.{file_ext}")
        else:
            filename = ws.sanitize_filename(
                f"{func_name}_{ts}.{file_ext}",
                default_name=f"{func_name}.{file_ext}",
            )

        storage = ArtifactStorage(session.id)
        path = storage.save_text(code.rstrip() + "\n", filename)
        ws.add_artifact_record(
            name=filename,
            artifact_type="code",
            file_path=path,
            format_hint=file_ext.lower(),
        )
        return {
            "name": filename,
            "type": "code",
            "format": file_ext.lower(),
            "path": str(path),
            "download_url": ws.build_artifact_download_url(filename),
        }
