"""Agent ReAct 主循环。

接收用户消息 → 构建上下文 → 调用 LLM → 执行工具 → 循环。
所有事件通过 callback 推送到调用方（WebSocket / CLI）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Awaitable, Callable

from nini.agent.model_resolver import (
    model_resolver,
)
from nini.agent.prompt_policy import AGENTS_MD_MAX_CHARS
from nini.agent.providers import ReasoningStreamParser
from nini.agent.session import Session, session_manager
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
from nini.agent.plan_parser import AnalysisPlan, parse_analysis_plan

# 导入类型安全的事件构造器（逐步迁移中）
from nini.agent import event_builders as eb

from nini.agent.loop_guard import LoopGuard, LoopGuardDecision, build_loop_warn_message
from nini.capabilities import create_default_capabilities
from nini.models.risk import OutputLevel, TRUST_CEILING_MAP, TrustLevel
from nini.models.skill_contract import SkillContract
from nini.skills.contract_executor import ContractSkillExecutor

# 导入组件模块
from nini.agent.components import (
    ContextBuilder,
    ReasoningChainTracker,
    detect_reasoning_type,
    detect_key_decisions,
    calculate_confidence_score,
    execute_tool,
    naturalize_internal_status_text,
    parse_tool_arguments,
    serialize_tool_result_for_memory,
    sanitize_for_system_context,
    get_last_user_message,
    replace_arguments,
)

logger = logging.getLogger(__name__)

# 仅主 Agent 可调用的 Orchestrator 工具集（子 Agent 不暴露，防止递归派发）
ORCHESTRATOR_TOOL_NAMES: frozenset[str] = frozenset({"dispatch_agents"})
GENERIC_ASK_OPTION_LABEL_RE = re.compile(
    r"^(?:[A-Da-d]|[1-4]|选项[一二三四1234A-Da-d]?|方案[一二三四1234A-Da-d]?)$"
)
_OUTPUT_LEVEL_TOKEN_RE = re.compile(r"\b(o[1-4])\b", re.IGNORECASE)

# 兼容别名：测试通过下划线前缀名称访问此函数
_replace_arguments = replace_arguments

# 图表格式偏好关键词检测
_INTERACTIVE_KEYWORDS = frozenset({"交互", "interactive", "可缩放", "动态", "plotly", "可交互"})
_IMAGE_KEYWORDS = frozenset(
    {"图片", "png", "静态", "保存", "发表", "截图", "导出", "论文", "pdf", "svg"}
)


def _detect_chart_preference(msg: str) -> str | None:
    """从用户消息中检测图表输出格式偏好。

    Returns:
        "interactive" / "image" / None（未检测到偏好）
    """
    lower = msg.lower()
    if any(k in lower for k in _INTERACTIVE_KEYWORDS):
        return "interactive"
    if any(k in lower for k in _IMAGE_KEYWORDS):
        return "image"
    return None


# 判断问题是否与图表格式相关的关键词
_CHART_QUESTION_KEYWORDS = frozenset({"图表", "chart", "plotly", "matplotlib", "渲染", "render"})


def _detect_chart_preference_from_answers(questions: list[dict], answers: dict) -> str | None:
    """从 ask_user_question 的答案中检测图表输出格式偏好。

    遍历问题列表，找到图表相关问题，再从对应答案（含选项标签）中检测偏好。

    Returns:
        "interactive" / "image" / None
    """
    for q in questions:
        q_id = str(q.get("id", "")).lower()
        q_label = str(q.get("label", "")).lower()
        # 判断是否是图表偏好问题
        if not any(k in q_id or k in q_label for k in _CHART_QUESTION_KEYWORDS):
            continue
        answer_val = answers.get(q.get("id", ""))
        if answer_val is None:
            continue
        # 从选项中找到答案对应的标签，拼接后进行关键词匹配
        options = q.get("options", [])
        combined = str(answer_val)
        for opt in options:
            if opt.get("value") == answer_val:
                combined = f"{answer_val} {opt.get('label', '')}"
                break
        pref = _detect_chart_preference(combined)
        if pref:
            return pref
    return None


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
_TRANSITIONAL_EXECUTION_RE = re.compile(
    r"(让我|我来|我将|我会|我现在需要|接下来|下一步|先|首先|现在先|尝试).{0,48}"
    r"(调用|查看|获取|检查|分析|运行|执行|绘制|生成|预览|读取|加载|更新|整理)"
)
_COMPLETION_SIGNAL_RE = re.compile(
    r"(已完成|完成分析|最终答案|最终回复|结论|总结如下|分析结果|结果如下|如下所示)"
)
_REASONING_TOOL_WRAP_RE = re.compile(
    r"</?(tool_call|arg_key|arg_value)>|</arg_key><arg_value>",
    re.IGNORECASE,
)
_REASONING_TOOL_LEAK_RE = re.compile(
    r"(content|file_path|operation|tasks|chart_id)</arg_key><arg_value>",
    re.IGNORECASE,
)
_TOOL_FOLLOWUP_RECOVERY_PROMPT = (
    "继续执行当前任务，不要只描述下一步。"
    "如果需要操作，请直接调用最合适的工具；只有在任务确实完成时才输出最终结论。"
)

_ALLOWED_TOOLS_ALWAYS_ALLOW = {
    "ask_user_question",
    "load_dataset",
    "task_state",
    "task_write",
}
_ALLOWED_TOOLS_HIGH_RISK = {
    "edit_file",
    "export_chart",
    "export_document",
    "export_report",
    "fetch_url",
    "organize_workspace",
}
_ALLOWED_TOOLS_HIGH_RISK_OPERATIONS: dict[str, set[str]] = {
    "chart_session": {"export"},
    "report_session": {"export"},
    "workspace_session": {"append", "edit", "fetch_url", "organize", "write"},
}
_ALLOWED_TOOLS_RISK_HINTS: dict[str, str] = {
    "chart_session": "其中 export 属于高风险越界操作，未授权时会请求用户确认。",
    "report_session": "其中 export 属于高风险越界操作，未授权时会请求用户确认。",
    "workspace_session": (
        "其中 write、append、edit、organize、fetch_url 属于高风险越界操作，"
        "未授权时会请求用户确认。"
    ),
}
_ALLOWED_TOOLS_APPROVAL_ALLOW_ONCE = "仅放行这一次"
_ALLOWED_TOOLS_APPROVAL_ALLOW_SESSION = "本会话同类工具都放行"
_ALLOWED_TOOLS_APPROVAL_DENY = "拒绝此次调用"
_SANDBOX_IMPORT_APPROVAL_ALLOW_ONCE = "仅本次允许"
_SANDBOX_IMPORT_APPROVAL_ALLOW_SESSION = "本会话允许"
_SANDBOX_IMPORT_APPROVAL_ALWAYS_ALLOW = "始终允许"
_SANDBOX_IMPORT_APPROVAL_DENY = "拒绝"


@dataclass(frozen=True)
class AllowedToolDecision:
    """当前工具调用在 allowed-tools 下的执行策略。"""

    mode: str
    risk_level: str
    approval_key: str | None = None
    operation: str | None = None


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


def _normalize_assistant_text_output(raw_text: str) -> tuple[str, bool]:
    """将误输出的内部状态 JSON 收敛为自然语言。"""
    normalized = naturalize_internal_status_text(raw_text)
    if normalized is None:
        return raw_text, False
    return normalized, normalized != raw_text


def _looks_like_reasoning_pollution(text: str) -> bool:
    """识别被工具调用包装片段污染的 reasoning。"""
    normalized = str(text or "").strip()
    if not normalized:
        return False
    if _REASONING_TOOL_WRAP_RE.search(normalized):
        return True
    if _REASONING_TOOL_LEAK_RE.search(normalized):
        return True
    return (
        len(normalized) > 240
        and "</arg_key><arg_value>" in normalized
        and "</arg_value>" in normalized
    )


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


def _build_data_preview_signature(data_preview: dict[str, Any]) -> str:
    """构造数据预览签名，用于同一轮内的重复事件去重。"""
    if not isinstance(data_preview, dict):
        return ""

    normalized = {
        "id": data_preview.get("id"),
        "name": data_preview.get("name"),
        "url": data_preview.get("url"),
        "total_rows": data_preview.get("total_rows"),
        "preview_rows": data_preview.get("preview_rows"),
        "preview_strategy": data_preview.get("preview_strategy"),
        "columns": data_preview.get("columns"),
        "data": data_preview.get("data"),
    }
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True, default=str)


def _parse_dataset_profile_request(arguments: str) -> tuple[str, str] | None:
    """解析 dataset_catalog(profile) 调用，返回 (dataset_name, view)。"""
    parsed_args = parse_tool_arguments(arguments)
    if not parsed_args:
        return None
    if str(parsed_args.get("operation", "")).strip().lower() != "profile":
        return None
    dataset_name = str(parsed_args.get("dataset_name", "")).strip()
    if not dataset_name:
        return None
    view = str(parsed_args.get("view", "basic")).strip().lower() or "basic"
    return dataset_name, view


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
        tool_registry: Any = None,
        knowledge_loader: Any | None = None,
        ask_user_question_handler: (
            Callable[[Session, str, dict[str, Any]], Awaitable[dict[str, str]]] | None
        ) = None,
    ):
        self._resolver = resolver or model_resolver
        self._tool_registry = tool_registry
        self._knowledge_loader = knowledge_loader or KnowledgeLoader(settings.knowledge_dir)
        self._context_builder = ContextBuilder(
            knowledge_loader=self._knowledge_loader,
            tool_registry=tool_registry,
        )
        self._ask_user_question_handler = ask_user_question_handler
        # 跟踪 context 使用率（0.0 初始，用于自适应工具结果截断预算）
        self._context_ratio: float = 0.0
        # 循环检测守卫
        self._loop_guard = LoopGuard()
        # 累计需要从 Agent 超时预算中扣除的人工等待时长
        self._timeout_excluded_seconds: float = 0.0

    async def _await_user_question_answers(
        self,
        session: Session,
        tool_call_id: str,
        payload: dict[str, Any],
    ) -> dict[str, str]:
        """等待 ask_user_question 回答，并将人工等待时间从超时预算中扣除。"""
        if self._ask_user_question_handler is None:
            raise RuntimeError("当前未配置 ask_user_question_handler")

        wait_started_at = time.monotonic()
        try:
            return await self._ask_user_question_handler(session, tool_call_id, payload)
        finally:
            waited = max(0.0, time.monotonic() - wait_started_at)
            self._timeout_excluded_seconds += waited

    async def run(
        self,
        session: Session,
        user_message: str,
        *,
        append_user_message: bool = True,
        stop_event: asyncio.Event | None = None,
        turn_id: str | None = None,
        stage_override: str | None = None,
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
        turn_id = turn_id or uuid.uuid4().hex[:12]
        if append_user_message:
            session.add_message("user", user_message, turn_id=turn_id)

        skill_detection_text = get_last_user_message(session) or user_message
        active_markdown_tools = self._select_active_markdown_tools(skill_detection_text)

        # ---- 图表格式偏好检测 ----
        detected_pref = _detect_chart_preference(user_message)
        if detected_pref and detected_pref != session.chart_output_preference:
            session.chart_output_preference = detected_pref
            session_manager.save_session_chart_preference(session.id, detected_pref)

        # ---- 中断恢复：重播任务状态到前端 ----
        if session.task_manager.has_tasks():
            plan_dict = session.task_manager.to_analysis_plan_dict()
            yield eb.build_analysis_plan_event(
                steps=plan_dict["steps"],
                raw_text=plan_dict["raw_text"],
                turn_id=turn_id,
                seq=0,
            )

        # ---- 试用模式前置检查 ----
        from nini.config_manager import (
            activate_trial,
            get_active_provider_id,
            get_trial_status,
            list_user_configured_provider_ids,
        )

        active_provider = await get_active_provider_id()
        configured_provider_ids = await list_user_configured_provider_ids()
        if not active_provider:
            trial_status = await get_trial_status()
            if trial_status["expired"] and not configured_provider_ids:
                # 试用已到期且无自有密钥 → 推送阻断事件后立即返回
                yield AgentEvent(
                    type=EventType.TRIAL_EXPIRED,
                    data={
                        "message": "系统内置试用额度已全部用完，请在「AI 设置」中配置自己的模型服务商继续使用。"
                    },
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

        contract_invocation = self._resolve_explicit_contract_skill_invocation(skill_detection_text)
        if contract_invocation is not None:
            async for contract_event in self._run_contract_markdown_skill(
                session=session,
                user_message=user_message,
                skill_item=contract_invocation["skill"],
                skill_arguments=contract_invocation["arguments"],
                turn_id=turn_id,
            ):
                yield contract_event
            return

        max_iter = settings.agent_max_iterations
        active_timeout_seconds = (
            int(settings.agent_active_execution_timeout_seconds)
            if settings.agent_active_execution_timeout_seconds is not None
            else int(settings.agent_max_timeout_seconds)
        )
        wall_clock_timeout_seconds = int(settings.agent_run_wall_clock_timeout_seconds)
        loop_start_time = time.monotonic()
        self._timeout_excluded_seconds = 0.0
        should_stop = stop_event.is_set if stop_event else (lambda: False)
        report_markdown_for_turn: str | None = None
        active_plan: AnalysisPlan | None = None
        next_step_idx: int = 0
        plan_event_seq: int = 0
        iteration = 0
        # 消息序列号，用于生成 message_id (格式: {turn_id}-{sequence})
        message_seq: int = 0
        # 当前消息ID，用于关联同一消息的多个流式片段
        current_message_id: str | None = None
        reasoning_tracker = ReasoningChainTracker()
        # 同一轮内的工具失败链路：用于重复错误熔断
        tool_failure_chains: dict[str, dict[str, Any]] = {}
        # 跟踪 task_state(update) 无操作重复调用次数，用于打破 LLM 循环
        task_state_noop_repeat_count: int = 0
        breaker_threshold = max(1, int(settings.tool_circuit_breaker_threshold))
        allowed_tool_whitelist, allowed_tool_sources = self._resolve_allowed_tool_recommendations(
            user_message
        )
        tool_followup_retry_used = False
        pending_followup_prompt: str | None = None
        # 循环检测警告消息，在下一轮 LLM 请求时注入为 system 消息
        pending_loop_warn_message: str | None = None
        # 工具熔断后的 CoT fallback 提示，在下一轮 LLM 请求时注入
        pending_breaker_fallback_prompt: str | None = None
        # 结论合成提示是否已使用（防止重复触发）
        synthesis_prompt_used: bool = False
        emitted_data_preview_signatures: set[str] = set()
        successful_dataset_profile_signatures: set[str] = set()
        dataset_profile_max_view_by_name: dict[str, str] = {}

        # 仅在初始轮（非 recovery pass）触发意图澄清，避免 HarnessRunner 重试时重复发问
        if stage_override is None:
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
            task_id = str(session.deep_task_state.get("task_id", "")).strip() or None
            attempt_id = None
            if task_id:
                action_part = str(action_id or tool_name or "action").strip() or "action"
                attempt_id = f"{task_id}:{action_part}:{attempt}"
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
                task_id=task_id,
                attempt_id=attempt_id,
            )

        # 自动上下文压缩检查
        compress_event = await self._maybe_auto_compress(session)
        if compress_event is not None:
            yield compress_event

        while max_iter <= 0 or iteration < max_iter:
            if should_stop():
                yield eb.build_done_event(turn_id=turn_id)
                return

            # Wall-clock 超时检查
            total_elapsed = max(0.0, time.monotonic() - loop_start_time)
            effective_elapsed = max(
                0.0,
                total_elapsed - self._timeout_excluded_seconds,
            )
            if wall_clock_timeout_seconds > 0 and total_elapsed > wall_clock_timeout_seconds:
                logger.warning(
                    "Agent 整轮超时: session=%s, total_elapsed=%.1fs, effective_elapsed=%.1fs, excluded_wait=%.1fs, limit=%ds",
                    session.id,
                    total_elapsed,
                    effective_elapsed,
                    self._timeout_excluded_seconds,
                    wall_clock_timeout_seconds,
                )
                yield eb.build_error_event(
                    message=(
                        f"Agent 运行总时长超时（已运行 {int(total_elapsed)} 秒，"
                        f"限制 {wall_clock_timeout_seconds} 秒）"
                    ),
                    turn_id=turn_id,
                )
                return
            # 动态超时扩展——PDCA 任务数已知时，用任务数计算超时下限，
            # 避免多步骤分析在任务初始化后因静态超时过早终止。
            if session.task_manager.initialized and session.task_manager.has_tasks():
                dynamic_floor = 120 + len(session.task_manager.tasks) * 90
                effective_active_timeout = max(active_timeout_seconds, dynamic_floor)
            else:
                effective_active_timeout = active_timeout_seconds
            if effective_active_timeout > 0 and effective_elapsed > effective_active_timeout:
                logger.warning(
                    "Agent 主动执行超时: session=%s, effective_elapsed=%.1fs, total_elapsed=%.1fs, excluded_wait=%.1fs, limit=%ds",
                    session.id,
                    effective_elapsed,
                    total_elapsed,
                    self._timeout_excluded_seconds,
                    effective_active_timeout,
                )
                yield eb.build_error_event(
                    message=(
                        f"Agent 主动执行超时（已运行 {int(effective_elapsed)} 秒，"
                        f"限制 {effective_active_timeout} 秒）"
                    ),
                    turn_id=turn_id,
                )
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

            # 获取工具定义（传入 session 以区分主 Agent / 子 Agent，控制 Orchestrator 工具暴露）
            tools = self._get_tool_definitions(
                preferred_tools=allowed_tool_whitelist, session=session
            )
            followup_prompt_for_purpose = pending_followup_prompt
            if pending_followup_prompt:
                messages = [
                    *messages,
                    {
                        "role": "user",
                        "content": pending_followup_prompt,
                    },
                ]
                pending_followup_prompt = None

            # 注入循环检测警告消息（上一轮 WARN 决策设置）
            if pending_loop_warn_message:
                messages = [
                    *messages,
                    {
                        "role": "system",
                        "content": pending_loop_warn_message,
                    },
                ]
                pending_loop_warn_message = None

            # 注入工具熔断后的 CoT fallback 提示
            if pending_breaker_fallback_prompt:
                messages = [
                    *messages,
                    {
                        "role": "system",
                        "content": pending_breaker_fallback_prompt,
                    },
                ]
                pending_breaker_fallback_prompt = None

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
                call_purpose = self._resolve_model_purpose(
                    iteration=iteration,
                    pending_followup_prompt=followup_prompt_for_purpose,
                    stage_override=stage_override,
                )
                try:
                    async for chunk in self._resolver.chat(
                        messages,
                        tools or None,
                        purpose=call_purpose,
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
                                combined_reasoning = streamed_reasoning_buffer + stripped
                                streamed_reasoning_buffer += stripped
                                if _looks_like_reasoning_pollution(combined_reasoning):
                                    logger.warning(
                                        "检测到被工具参数污染的 reasoning，已跳过流式推送: session=%s turn=%s",
                                        session.id,
                                        turn_id,
                                    )
                                else:
                                    if current_reasoning_id is None:
                                        current_reasoning_id = str(uuid.uuid4())
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
                                # 使用 UUID 后缀避免 HarnessRunner 多次调用时同一 turn_id 下 ID 碰撞
                                if current_message_id is None:
                                    current_message_id = f"{turn_id}-{uuid.uuid4().hex[:8]}"
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
                                purpose=call_purpose,
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
                    logger.error("LLM 调用失败: %s", e, exc_info=True)
                    yield eb.build_error_event(message=str(e), turn_id=turn_id)
                    return
                break

            final_reasoning = full_reasoning.strip()
            if final_reasoning and settings.enable_reasoning:
                if _looks_like_reasoning_pollution(final_reasoning):
                    logger.warning(
                        "检测到被工具参数污染的 reasoning，已跳过持久化: session=%s turn=%s",
                        session.id,
                        turn_id,
                    )
                    final_reasoning = ""

            if final_reasoning and settings.enable_reasoning:
                # Detect enhanced reasoning metadata
                reasoning_type = detect_reasoning_type(final_reasoning)
                key_decisions = detect_key_decisions(final_reasoning)
                confidence_score = calculate_confidence_score(final_reasoning)

                # Track in reasoning chain
                reasoning_node = reasoning_tracker.add_reasoning(
                    content=final_reasoning,
                    reasoning_type=reasoning_type,
                    key_decisions=key_decisions,
                    confidence_score=confidence_score,
                )

                # 发送最终 reasoning 事件（标记为完成）
                # 如果有流式 reasoning，使用相同的 reasoning_id 以便前端合并
                final_reasoning_id = current_reasoning_id or reasoning_node.get("id")
                # 先保存到 session 持久化
                session.add_reasoning(
                    content=final_reasoning,
                    reasoning_type=reasoning_type,
                    key_decisions=key_decisions,
                    confidence_score=confidence_score,
                    reasoning_id=final_reasoning_id,
                    parent_id=reasoning_node.get("parent_id"),
                    turn_id=turn_id,
                )
                yield eb.build_reasoning_event(
                    content=final_reasoning,
                    reasoning_id=final_reasoning_id,
                    reasoning_live=False,
                    turn_id=turn_id,
                    reasoning_type=reasoning_type,
                    key_decisions=key_decisions,
                    confidence_score=confidence_score,
                    parent_id=reasoning_node.get("parent_id"),
                )

            # 更新 context 使用率（用于下一轮自适应工具结果截断预算）
            if usage:
                input_tokens = usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0)
                if input_tokens > 0:
                    # 动态获取当前模型的 context window，未知模型 fallback 128K
                    context_window = self._resolver.get_model_context_window() or 128_000
                    self._context_ratio = min(1.0, input_tokens / context_window)

            # 记录 token 消耗
            if usage and settings.enable_cost_tracking:
                model_info = effective_model_info or self._resolver.get_active_model_info(
                    purpose=call_purpose
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
                # 多步分析完成时注入结论合成提示（一次性）
                if (
                    active_plan is not None
                    and not synthesis_prompt_used
                    and iteration >= 3
                    and sum(1 for s in active_plan.steps if s.status == "completed")
                    >= len(active_plan.steps) * 0.6
                ):
                    synthesis_prompt_used = True
                    pending_followup_prompt = (
                        "分析步骤已基本完成，请确保最终回复包含：\n"
                        "1. 回顾最初研究问题\n"
                        "2. 逐步总结每步关键发现（含统计证据）\n"
                        "3. 综合结论\n"
                        "4. 局限性与下一步建议"
                    )
                    iteration += 1
                    continue

                final_text = full_text or raw_full_text
                final_text, normalized_internal_status = _normalize_assistant_text_output(
                    final_text
                )
                if self._should_retry_transitional_text(
                    final_text,
                    active_plan=active_plan,
                    retry_used=tool_followup_retry_used,
                    tools=tools,
                ):
                    tool_followup_retry_used = True
                    recovery_note = (
                        "检测到模型输出了过渡性执行文本但未实际调用工具，"
                        "系统将自动要求其继续执行当前任务。"
                    )
                    session.add_reasoning(
                        recovery_note,
                        reasoning_type="decision",
                        turn_id=turn_id,
                        tags=["tool_followup_recovery"],
                    )
                    yield eb.build_reasoning_event(
                        content=recovery_note,
                        turn_id=turn_id,
                        reasoning_live=False,
                        source="tool_followup_recovery",
                    )
                    pending_followup_prompt = _TOOL_FOLLOWUP_RECOVERY_PROMPT
                    iteration += 1
                    continue
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
                        raw_answers = await self._await_user_question_answers(
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
                final_output_level = self._infer_turn_output_level(
                    final_text=final_text,
                    active_markdown_tools=active_markdown_tools,
                )
                final_message_extra: dict[str, Any] = {}
                if effective_model_info:
                    final_message_extra["effective_model"] = effective_model_info
                if fallback_chain:
                    final_message_extra["fallback_chain"] = fallback_chain
                if final_output_level is not None:
                    final_message_extra["output_level"] = final_output_level.value
                session.add_message(
                    "assistant",
                    final_text,
                    turn_id=turn_id,
                    message_id=final_message_id,
                    operation="complete",
                    **final_message_extra,
                )
                if current_message_id and normalized_internal_status:
                    yield eb.build_text_event(
                        content=final_text,
                        turn_id=turn_id,
                        metadata={
                            "message_id": final_message_id,
                            "operation": "replace",
                            "source": "internal_status_normalized",
                        },
                    )
                # must_haves 对照检查（不阻断，仅日志 + validation_warning 事件）
                if active_plan is not None and active_plan.must_haves:
                    for mh in active_plan.must_haves:
                        mh_type = mh.get("type", "")
                        mh_desc = mh.get("description", "")
                        logger.warning(
                            "must_have 待确认: type=%s description=%s session_id=%s",
                            mh_type,
                            mh_desc,
                            session.id,
                        )
                        yield AgentEvent(
                            type=EventType.ERROR,
                            data={
                                "level": "validation_warning",
                                "must_have_type": mh_type,
                                "message": f"[must_have/{mh_type}] {mh_desc}",
                            },
                            turn_id=turn_id,
                        )

                yield eb.build_done_event(
                    turn_id=turn_id,
                    output_level=(
                        final_output_level.value if final_output_level is not None else None
                    ),
                )

                # 会话结束后异步沉淀分析记忆为跨会话长期记忆
                try:
                    from nini.memory.long_term_memory import consolidate_session_memories
                    from nini.utils.background_tasks import track_background_task

                    track_background_task(consolidate_session_memories(session.id))
                except Exception:
                    logger.debug("长期记忆沉淀失败", exc_info=True)

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

            # ── Orchestrator 钩子：拦截 dispatch_agents 工具调用 ────────────────
            # 在通用工具执行循环前检测，若存在 dispatch_agents 则走 Orchestrator 路径。
            _dispatch_tc = next(
                (
                    tc
                    for tc in tool_calls
                    if tc.get("function", {}).get("name") == "dispatch_agents"
                ),
                None,
            )
            if _dispatch_tc is not None:
                async for _evt in self._handle_dispatch_agents(_dispatch_tc, session, turn_id):
                    yield _evt
                iteration += 1
                continue
            # ── Orchestrator 钩子结束 ─────────────────────────────────────────

            # ── 循环检测守卫 ──────────────────────────────────────────────────
            _loop_decision, _loop_tool_names = self._loop_guard.check(tool_calls, session.id)
            if _loop_decision == LoopGuardDecision.FORCE_STOP:
                # 强制终止：跳过工具执行，推送说明性文本事件后退出循环
                _stop_msg = (
                    "⚠️ 检测到工具调用死循环（相同工具组合已重复调用多次），"
                    "系统已自动终止当前任务。请尝试调整问题描述或手动干预。"
                )
                logger.warning(
                    "循环守卫触发 FORCE_STOP: session=%s iteration=%d tools=%s",
                    session.id,
                    iteration,
                    _loop_tool_names,
                )
                yield eb.build_text_event(
                    content=_stop_msg,
                    turn_id=turn_id,
                    metadata={"source": "loop_guard", "decision": "force_stop"},
                )
                session.add_message(
                    "assistant",
                    _stop_msg,
                    turn_id=turn_id,
                    operation="complete",
                )
                yield eb.build_done_event(turn_id=turn_id)
                return
            elif _loop_decision == LoopGuardDecision.WARN:
                # 警告：当前轮正常执行，但在下一轮注入针对性反思提示
                pending_loop_warn_message = build_loop_warn_message(_loop_tool_names)
                logger.info(
                    "循环守卫触发 WARN: session=%s iteration=%d tools=%s",
                    session.id,
                    iteration,
                    _loop_tool_names,
                )
            # ── 循环检测守卫结束 ──────────────────────────────────────────────

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
                        logger.debug(
                            "解析工具调用 intent 元数据失败: tool=%s",
                            func_name,
                            exc_info=True,
                        )

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

                # allowed-tools 分级约束：
                # - 内部系统工具与数据加载工具直接豁免
                # - 低风险越界继续执行，但记录 soft_violation
                # - 高风险越界进入 ask_user_question 确认流程
                if (
                    allowed_tool_whitelist is not None
                    and func_name not in allowed_tool_whitelist
                    and func_name not in _ALLOWED_TOOLS_ALWAYS_ALLOW
                ):
                    decision = self._decide_allowed_tool_handling(func_name, func_args)
                    if decision.mode == "allow":
                        warning_msg = self._build_allowed_tools_notice(
                            tool_name=func_name,
                            allowed_tool_whitelist=allowed_tool_whitelist,
                            allowed_tool_sources=allowed_tool_sources,
                            continued=True,
                        )
                        logger.warning("工具低风险越界继续执行: %s", warning_msg)
                        session.add_reasoning(
                            warning_msg,
                            reasoning_type="decision",
                            tags=["allowed_tools", "soft_violation"],
                            turn_id=turn_id,
                        )
                        yield AgentEvent(
                            type=EventType.ERROR,
                            data={
                                "level": "allowed_tools_soft_violation",
                                "tool": func_name,
                                "risk_level": decision.risk_level,
                                "message": warning_msg,
                            },
                            turn_id=turn_id,
                        )
                    else:
                        if decision.approval_key is None:
                            raise RuntimeError("内部错误: approval_key 不应为 None")
                        if session.has_tool_approval(decision.approval_key):
                            logger.info(
                                "复用会话级工具放行: session=%s tool=%s approval_key=%s",
                                session.id,
                                func_name,
                                decision.approval_key,
                            )
                        else:
                            approval_payload = self._build_tool_approval_payload(
                                tool_name=func_name,
                                operation=decision.operation,
                                allowed_tool_whitelist=allowed_tool_whitelist,
                                allowed_tool_sources=allowed_tool_sources,
                            )
                            choice, approval_events = await self._request_tool_approval(
                                session,
                                turn_id=turn_id,
                                tool_name=func_name,
                                approval_payload=approval_payload,
                                approval_key=decision.approval_key,
                            )
                            for approval_event in approval_events:
                                yield approval_event

                            if choice == "allow_session":
                                session.grant_tool_approval(decision.approval_key, scope="session")
                            elif choice == "allow_once":
                                pass
                            else:
                                error_msg = self._build_allowed_tools_notice(
                                    tool_name=func_name,
                                    allowed_tool_whitelist=allowed_tool_whitelist,
                                    allowed_tool_sources=allowed_tool_sources,
                                    continued=False,
                                )
                                if choice == "unavailable":
                                    error_msg = f"{error_msg[:-1]}，且当前通道不支持 ask_user_question 人工确认。"
                                else:
                                    error_msg = f"{error_msg[:-1]}，用户未批准此次高风险调用。"
                                session.add_tool_result(
                                    tc_id,
                                    error_msg,
                                    tool_name=func_name,
                                    status="error",
                                    turn_id=turn_id,
                                )
                                yield AgentEvent(
                                    type=EventType.ERROR,
                                    data={
                                        "level": "allowed_tools_violation",
                                        "tool": func_name,
                                        "risk_level": decision.risk_level,
                                        "approval_key": decision.approval_key,
                                        "message": error_msg,
                                    },
                                    turn_id=turn_id,
                                )
                                iteration += 1
                                continue

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
                                _first_task = (
                                    session.task_manager.tasks[0]
                                    if session.task_manager.tasks
                                    else None
                                )
                                yield _new_plan_progress_event(
                                    current_idx=0,
                                    step_status=(_first_task.status if _first_task else "pending"),
                                    next_hint=(_first_task.title if _first_task else None),
                                )
                            else:  # update
                                # 收集需要发送事件的任务 ID：当前只包含显式更新项；
                                # 保留 auto_completed_ids 兼容旧返回结构。
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

                    # ── task_state(update) 无操作重复检测 ─────────────────────
                    # 跟踪连续的 task_state(update) 无操作调用，超过阈值后替换为强重定向消息
                    _ts_result_data = result.get("data", {}) if isinstance(result, dict) else {}
                    if (
                        not has_error
                        and isinstance(_ts_result_data, dict)
                        and _ts_result_data.get("no_op_ids")
                        and isinstance(result, dict)
                    ):
                        task_state_noop_repeat_count += 1
                        if task_state_noop_repeat_count >= 2:
                            logger.warning(
                                "检测到 task_state 无操作重复调用: session=%s "
                                "repeat_count=%d, 替换为重定向消息",
                                session.id,
                                task_state_noop_repeat_count,
                            )
                            result["message"] = (
                                "⚠️ 你已连续多次调用 task_state(update) 但任务状态未发生变化，"
                                "这表明你陷入了循环。"
                                "请立即调用实际的分析工具（如 stat_test、run_code、create_chart）"
                                "执行当前任务，绝对不要再调用 task_state。"
                            )
                    else:
                        # 有实际状态变更，重置计数
                        task_state_noop_repeat_count = 0
                    # ── task_state 无操作重复检测结束 ─────────────────────────

                    result_str = serialize_tool_result_for_memory(result, tool_name=func_name)
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
                        if questions is None:
                            raise RuntimeError("内部错误: questions 不应为 None")
                        yield eb.build_ask_user_question_event(
                            questions=questions,
                            turn_id=turn_id,
                            tool_call_id=tc_id,
                            tool_name=func_name,
                        )
                        try:
                            raw_answers = await self._await_user_question_answers(
                                session,
                                tc_id,
                                {"questions": questions},
                            )
                            normalized_answers = self._normalize_ask_user_question_answers(
                                raw_answers
                            )
                            # 从答案中检测图表格式偏好并持久化
                            detected_pref = _detect_chart_preference_from_answers(
                                questions, normalized_answers
                            )
                            if detected_pref and detected_pref != session.chart_output_preference:
                                session.chart_output_preference = detected_pref
                                session_manager.save_session_chart_preference(
                                    session.id, detected_pref
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
                    result_str = serialize_tool_result_for_memory(result, tool_name=func_name)
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

                profile_request = (
                    _parse_dataset_profile_request(func_args)
                    if func_name == "dataset_catalog"
                    else None
                )
                if profile_request is not None:
                    dataset_name, requested_view = profile_request
                    max_view = dataset_profile_max_view_by_name.get(dataset_name)
                    duplicate_profile_reason: str | None = None
                    recovery_hint = (
                        "你已完成数据概况分析，禁止再次调用 dataset_catalog(profile)。"
                        "下一步：直接调用 run_code / code_session 进行统计分析，"
                        "或调用 task_state 更新任务进度，或输出分析结论。"
                    )
                    if tool_args_signature in successful_dataset_profile_signatures:
                        duplicate_profile_reason = (
                            f"同一轮中已成功调用过相同的 dataset_catalog(profile): {dataset_name}"
                        )
                    elif max_view == "full":
                        duplicate_profile_reason = (
                            f"同一轮中已成功获得数据集 '{dataset_name}' 的完整概况(full)，"
                            f"无需再次请求 {requested_view} 视图"
                        )

                    if duplicate_profile_reason is not None:
                        result = {
                            "success": False,
                            "message": duplicate_profile_reason,
                            "error_code": "DUPLICATE_DATASET_PROFILE_CALL",
                            "recovery_hint": recovery_hint,
                            "data": {
                                "dataset_name": dataset_name,
                                "requested_view": requested_view,
                                "max_completed_view": max_view or requested_view,
                                "recovery_hint": recovery_hint,
                            },
                            "metadata": {
                                "duplicate_profile_blocked": True,
                                "action_id": matched_action_id,
                                "retry_count": 0,
                                "max_retries": max_retries,
                            },
                        }
                        has_error = True
                        status = "error"
                        result_str = serialize_tool_result_for_memory(result, tool_name=func_name)
                        session.add_tool_result(
                            tc_id,
                            result_str,
                            tool_name=func_name,
                            status=status,
                            intent=tool_call_metadata.get("intent"),
                            turn_id=turn_id,
                            message_id=f"tool-result-{tc_id}",
                        )
                        yield _new_task_attempt_event(
                            step_id=matched_step_id,
                            action_id=matched_action_id,
                            tool_name=func_name,
                            attempt=1,
                            max_attempts=1,
                            status="failed",
                            error=duplicate_profile_reason,
                            note="重复的数据集概况调用已在执行前拦截",
                        )
                        raw_result_metadata = result.get("metadata")
                        event_metadata = (
                            raw_result_metadata if isinstance(raw_result_metadata, dict) else None
                        )
                        yield eb.build_tool_result_event(
                            tool_call_id=tc_id,
                            name=func_name,
                            status=status,
                            message=duplicate_profile_reason,
                            data={"result": result},
                            turn_id=turn_id,
                            metadata=event_metadata,
                        )
                        existing_chain = tool_failure_chains.get(tool_args_signature)
                        if (
                            isinstance(existing_chain, dict)
                            and str(existing_chain.get("error_code", ""))
                            == "DUPLICATE_DATASET_PROFILE_CALL"
                        ):
                            existing_chain["count"] = int(existing_chain.get("count", 0)) + 1
                            existing_chain["message"] = duplicate_profile_reason
                            existing_chain["recovery_hint"] = recovery_hint
                        else:
                            tool_failure_chains[tool_args_signature] = {
                                "count": 1,
                                "error_code": "DUPLICATE_DATASET_PROFILE_CALL",
                                "message": duplicate_profile_reason,
                                "recovery_hint": recovery_hint,
                            }
                        continue

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
                    result_str = serialize_tool_result_for_memory(result, tool_name=func_name)
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
                    # 熔断触发后注入 CoT fallback 提示，引导模型切换策略
                    chain_count = int(chain_state.get("count", 0))
                    pending_breaker_fallback_prompt = (
                        f"工具 {func_name} 已触发熔断（连续失败 {chain_count} 次），"
                        "请不要再尝试相同的方法。\n"
                        f"上次错误提示：{recovery_hint}\n"
                        "你可以：(1) 尝试完全不同的工具或方法 "
                        "(2) 基于目前已获得的信息直接给出最佳结论，"
                        "明确标注哪些结论缺乏工具验证。"
                    )
                    continue

                # 执行工具（max_retries 已在 TOOL_CALL 事件发出前计算）
                retry_attempt = 0
                max_attempts = max_retries + 1
                tool_exec_args = func_args
                sandbox_review_retry_used = False
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
                    result = await self._execute_tool(session, func_name, tool_exec_args)

                    # 检查是否发生了统计降级 fallback
                    if isinstance(result, dict) and result.get("fallback"):
                        fallback_event = create_reasoning_event(
                            step="statistical_fallback",
                            thought=f"由于{result.get('fallback_reason', '前提条件不满足')}，自动降级为非参数检验",
                            rationale=f"原始方法 '{result.get('original_tool')}' 被降级为 '{result.get('fallback_tool')}'",
                            confidence=0.9,
                            original_tool=result.get("original_tool"),
                            fallback_tool=result.get("fallback_tool"),
                            reason=result.get("fallback_reason"),
                        )
                        yield fallback_event

                    sandbox_review = self._extract_sandbox_review_request(result)
                    if sandbox_review is not None and func_name == "run_code":
                        packages = sandbox_review["packages"]
                        approval_payload = self._build_sandbox_import_approval_payload(
                            packages=packages,
                            violations=sandbox_review.get("violations", []),
                        )

                        if sandbox_review_retry_used:
                            result = {
                                "success": False,
                                "message": (
                                    "同一次 run_code 调用在完成一次沙盒审批后仍再次请求审批，"
                                    "已停止继续重试。"
                                ),
                                "error_code": "SANDBOX_IMPORT_APPROVAL_REPEAT",
                                "data": {
                                    "requested_packages": packages,
                                    "sandbox_violations": sandbox_review.get("violations", []),
                                },
                            }
                        else:
                            choice = "unavailable"
                            if self._ask_user_question_handler is not None:
                                approval_call_id = f"sandbox-ask-{uuid.uuid4().hex[:8]}"
                                approval_arguments = json.dumps(
                                    approval_payload,
                                    ensure_ascii=False,
                                )
                                approval_metadata = {
                                    "source": "sandbox_import_approval",
                                    "source_tool_call_id": tc_id,
                                    "packages": packages,
                                }
                                session.add_tool_call(
                                    approval_call_id,
                                    "ask_user_question",
                                    approval_arguments,
                                    turn_id=turn_id,
                                    message_id=f"tool-call-{approval_call_id}",
                                )
                                yield eb.build_tool_call_event(
                                    tool_call_id=approval_call_id,
                                    name="ask_user_question",
                                    arguments={
                                        "name": "ask_user_question",
                                        "arguments": approval_arguments,
                                    },
                                    turn_id=turn_id,
                                    metadata=approval_metadata,
                                )
                                yield eb.build_ask_user_question_event(
                                    questions=approval_payload.get("questions", []),
                                    turn_id=turn_id,
                                    tool_call_id=approval_call_id,
                                    tool_name="ask_user_question",
                                    metadata=approval_metadata,
                                )

                                try:
                                    raw_answers = await self._await_user_question_answers(
                                        session,
                                        approval_call_id,
                                        approval_payload,
                                    )
                                    normalized_answers = self._normalize_ask_user_question_answers(
                                        raw_answers
                                    )
                                    approval_result = {
                                        "success": True,
                                        "message": "已收到用户的沙盒扩展包审批决定。",
                                        "data": {
                                            "questions": approval_payload["questions"],
                                            "answers": normalized_answers,
                                            "packages": packages,
                                            "source_tool_call_id": tc_id,
                                        },
                                    }
                                    choice = self._resolve_sandbox_import_approval_choice(
                                        normalized_answers
                                    )
                                except asyncio.CancelledError:
                                    raise
                                except Exception as exc:
                                    logger.warning(
                                        "沙盒扩展包审批失败: session=%s tc_id=%s packages=%s err=%s",
                                        session.id,
                                        tc_id,
                                        packages,
                                        exc,
                                    )
                                    approval_result = {
                                        "success": False,
                                        "message": f"等待沙盒扩展包审批失败: {exc}",
                                    }
                                    choice = "deny"

                                approval_has_error = bool(
                                    isinstance(approval_result, dict)
                                    and (
                                        approval_result.get("error")
                                        or approval_result.get("success") is False
                                    )
                                )
                                approval_result_str = serialize_tool_result_for_memory(
                                    approval_result
                                )
                                session.add_tool_result(
                                    approval_call_id,
                                    approval_result_str,
                                    tool_name="ask_user_question",
                                    status="error" if approval_has_error else "success",
                                    intent="sandbox_import_approval",
                                    turn_id=turn_id,
                                    message_id=f"tool-result-{approval_call_id}",
                                )
                                yield eb.build_tool_result_event(
                                    tool_call_id=approval_call_id,
                                    name="ask_user_question",
                                    status="error" if approval_has_error else "success",
                                    message=_tool_result_message(
                                        approval_result,
                                        is_error=approval_has_error,
                                    ),
                                    data={"result": approval_result},
                                    turn_id=turn_id,
                                    metadata=approval_metadata,
                                )

                            if choice == "allow_session":
                                session.grant_sandbox_import_approval(packages, scope="session")
                            elif choice == "always_allow":
                                session.grant_sandbox_import_approval(packages, scope="always")
                            elif choice == "allow_once":
                                pass
                            else:
                                result = {
                                    "success": False,
                                    "message": (
                                        "用户拒绝放行沙盒扩展包导入: " + "、".join(packages)
                                    ),
                                    "error_code": "SANDBOX_IMPORT_APPROVAL_DENIED",
                                    "data": {
                                        "requested_packages": packages,
                                        "sandbox_violations": sandbox_review.get("violations", []),
                                    },
                                }

                            if choice in {"allow_once", "allow_session", "always_allow"}:
                                sandbox_review_retry_used = True
                                tool_exec_args = self._merge_sandbox_retry_arguments(
                                    tool_exec_args,
                                    packages,
                                )
                                yield _new_task_attempt_event(
                                    step_id=matched_step_id,
                                    action_id=matched_action_id,
                                    tool_name=func_name,
                                    attempt=attempt_no,
                                    max_attempts=max_attempts,
                                    status="retrying",
                                    note="已获得沙盒扩展包授权，准备按原始参数重试 run_code",
                                )
                                continue

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
                        if profile_request is not None:
                            dataset_name, completed_view = profile_request
                            successful_dataset_profile_signatures.add(tool_args_signature)
                            if completed_view == "full":
                                dataset_profile_max_view_by_name[dataset_name] = "full"
                            else:
                                dataset_profile_max_view_by_name.setdefault(
                                    dataset_name, completed_view
                                )
                            # 持久化到 session，供 context_builder 在后续轮次的运行时上下文中提醒 LLM
                            completed_profiles: set[str] = getattr(
                                session, "_completed_dataset_profiles", set()
                            )
                            completed_profiles.add(dataset_name)
                            setattr(session, "_completed_dataset_profiles", completed_profiles)
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
                result_str = serialize_tool_result_for_memory(result, tool_name=func_name)

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
                        preview_signature = _build_data_preview_signature(data_preview)
                        if (
                            preview_signature
                            and preview_signature in emitted_data_preview_signatures
                        ):
                            logger.info(
                                "跳过重复数据预览事件: session=%s turn=%s tool=%s",
                                session.id,
                                turn_id,
                                func_name,
                            )
                        else:
                            if preview_signature:
                                emitted_data_preview_signatures.add(preview_signature)
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
                        if isinstance(artifacts_raw, list) and artifacts_raw:
                            # 批量写入一条 session 事件，减少上下文膨胀
                            session.add_assistant_event(
                                "artifact",
                                f"已生成 {len(artifacts_raw)} 个产物",
                                turn_id=turn_id,
                                artifacts=artifacts_raw,
                            )
                            # 仍然为每个 artifact 发送独立的 WebSocket 事件（前端需逐个渲染）
                            for artifact in artifacts_raw:
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
                    logger.debug("工具结果事件发送失败", exc_info=True)

            # generate_report 已返回完整报告时，直接将同一内容作为最终回复。
            # 这样可确保页面展示与保存文件完全一致，避免模型二次改写造成偏差。
            if report_markdown_for_turn:
                # 如果有当前消息ID，使用 replace 操作替换之前的内容
                # 否则创建新的消息ID
                report_message_id = current_message_id or f"{turn_id}-{message_seq}"
                if current_message_id is None:
                    message_seq += 1
                report_output_level = self._infer_turn_output_level(
                    final_text=report_markdown_for_turn,
                    active_markdown_tools=active_markdown_tools,
                )
                report_message_extra: dict[str, Any] = {}
                if effective_model_info:
                    report_message_extra["effective_model"] = effective_model_info
                if fallback_chain:
                    report_message_extra["fallback_chain"] = fallback_chain
                if report_output_level is not None:
                    report_message_extra["output_level"] = report_output_level.value
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
                yield eb.build_done_event(
                    turn_id=turn_id,
                    output_level=(
                        report_output_level.value if report_output_level is not None else None
                    ),
                )
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
        # 将模型上下文窗口信息传递给 session，供 ContextBuilder 选择 prompt profile
        if not hasattr(session, "_model_context_window"):
            _get_cw = getattr(self._resolver, "get_model_context_window", None)
            setattr(
                session,
                "_model_context_window",
                _get_cw() if callable(_get_cw) else None,
            )
        start_time = time.monotonic()
        messages, retrieval_event = await self._context_builder.build_messages_and_retrieval(
            session, context_ratio=self._context_ratio
        )
        logger.info(
            "Agent 上下文构建完成: session=%s messages=%d retrieval=%s duration_ms=%d",
            session.id,
            len(messages),
            "yes" if retrieval_event is not None else "no",
            int((time.monotonic() - start_time) * 1000),
        )
        return messages, retrieval_event

    def _build_explicit_skill_context(self, user_message: str) -> str:
        """兼容旧测试入口，委托给 canonical context builder。"""
        return self._context_builder.build_explicit_tool_context(user_message)

    def _build_intent_runtime_context(self, user_message: str) -> str:
        """兼容旧测试入口，委托给 canonical context builder。"""
        return self._context_builder.build_intent_runtime_context(user_message)

    @staticmethod
    def _resolve_model_purpose(
        *,
        iteration: int,
        pending_followup_prompt: str | None,
        stage_override: str | None,
    ) -> str:
        """根据运行阶段选择模型用途路由。"""
        normalized_override = str(stage_override or "").strip().lower()
        if normalized_override == "verification":
            return "verification"
        if normalized_override == "planning":
            return "planning"
        if iteration == 0:
            return "planning"
        if pending_followup_prompt:
            return "verification"
        return "chat"

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
        analysis = _get_intent_analyzer().analyze(
            user_message,
            capabilities=capability_catalog,
            has_datasets=bool(session.datasets),
        )
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
            raw_answers = await self._await_user_question_answers(
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

    def _match_tools_by_context(self, user_message: str) -> list[dict[str, Any]]:
        """兼容旧测试入口，委托给 canonical context builder。"""
        return self._context_builder._match_tools_by_context(user_message)

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

    def _build_tool_runtime_resources_note(self, tool_name: str) -> str:
        """兼容旧测试入口，委托给 canonical context builder。"""
        return self._context_builder._build_tool_runtime_resources_note(tool_name)

    def _select_active_markdown_tools(self, user_message: str) -> list[dict[str, Any]]:
        """选择本轮激活的 Markdown Skills（显式 slash 优先，缺失时走自动匹配）。"""
        if not user_message or self._tool_registry is None:
            return []
        if not hasattr(self._tool_registry, "list_markdown_tools"):
            return []

        markdown_items = self._tool_registry.list_markdown_tools()
        if not isinstance(markdown_items, list):
            return []
        return default_intent_analyzer.select_active_skills(
            user_message,
            markdown_items,
            explicit_limit=self._context_builder.inline_tool_max_count,
            auto_limit=self._context_builder.auto_tool_max_count,
        )

    def _resolve_explicit_contract_skill_invocation(
        self,
        user_message: str,
    ) -> dict[str, Any] | None:
        """解析显式 `/skill` 调用中的 contract Markdown Skill。"""
        if not user_message or self._tool_registry is None:
            return None
        if not hasattr(self._tool_registry, "list_markdown_tools"):
            return None
        if not hasattr(self._tool_registry, "get_tool_instruction"):
            return None

        markdown_items = self._tool_registry.list_markdown_tools()
        if not isinstance(markdown_items, list):
            return None

        skill_map = {
            str(item.get("name", "")).strip(): item
            for item in markdown_items
            if isinstance(item, dict)
        }
        for call in default_intent_analyzer.parse_explicit_skill_calls(user_message, limit=1):
            item = skill_map.get(call["name"])
            if not isinstance(item, dict) or not bool(item.get("enabled", True)):
                continue
            metadata = item.get("metadata")
            if not isinstance(metadata, dict) or metadata.get("contract") is None:
                continue
            return {
                "skill": item,
                "arguments": str(call.get("arguments", "") or "").strip(),
            }
        return None

    async def _run_contract_markdown_skill(
        self,
        *,
        session: Session,
        user_message: str,
        skill_item: dict[str, Any],
        skill_arguments: str,
        turn_id: str,
    ) -> AsyncGenerator[AgentEvent, None]:
        """执行显式调用的 contract Markdown Skill。"""
        skill_name = str(skill_item.get("name", "")).strip()
        if not skill_name:
            yield eb.build_error_event("contract Skill 名称为空，无法执行", turn_id=turn_id)
            yield eb.build_done_event(reason="failed", turn_id=turn_id)
            return

        if self._tool_registry is None or not hasattr(self._tool_registry, "get_tool_instruction"):
            yield eb.build_error_event(
                "工具注册中心未初始化，无法执行 contract Skill", turn_id=turn_id
            )
            yield eb.build_done_event(reason="failed", turn_id=turn_id)
            return

        instruction_payload = self._tool_registry.get_tool_instruction(skill_name)
        if not isinstance(instruction_payload, dict):
            yield eb.build_error_event(
                f"未找到 {skill_name} 的技能正文，无法执行 contract Skill",
                turn_id=turn_id,
            )
            yield eb.build_done_event(reason="failed", turn_id=turn_id)
            return

        metadata = skill_item.get("metadata")
        contract_raw = metadata.get("contract") if isinstance(metadata, dict) else None
        try:
            contract = (
                contract_raw
                if isinstance(contract_raw, SkillContract)
                else SkillContract.model_validate(contract_raw)
            )
        except Exception as exc:
            yield eb.build_error_event(
                f"{skill_name} 的 contract 配置无效: {exc}",
                turn_id=turn_id,
            )
            yield eb.build_done_event(reason="failed", turn_id=turn_id)
            return

        event_queue: asyncio.Queue[AgentEvent] = asyncio.Queue()

        async def callback(event_type: str, data: Any) -> None:
            event_type_enum = {
                "skill_step": EventType.SKILL_STEP,
                "skill_summary": EventType.SKILL_SUMMARY,
            }.get(event_type)
            if event_type_enum is None:
                return
            payload = data.model_dump(mode="json") if hasattr(data, "model_dump") else data
            await event_queue.put(
                AgentEvent(
                    type=event_type_enum,
                    data=payload,
                    turn_id=turn_id,
                )
            )

        executor = ContractSkillExecutor(
            skill_name=skill_name,
            instruction=str(instruction_payload.get("instruction", "") or ""),
            contract=contract,
            tool_registry=self._tool_registry,
            resolver=self._resolver,
            callback=callback,
        )
        execution_task = asyncio.create_task(
            executor.execute(
                session=session,
                user_message=user_message,
                skill_arguments=skill_arguments,
            )
        )

        while True:
            if execution_task.done() and event_queue.empty():
                break

            queue_get_task = asyncio.create_task(event_queue.get())
            done, pending = await asyncio.wait(
                {execution_task, queue_get_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if queue_get_task in done:
                yield queue_get_task.result()
            else:
                queue_get_task.cancel()
                with suppress(asyncio.CancelledError):
                    await queue_get_task

        try:
            outcome = await execution_task
        except Exception as exc:
            logger.error("contract Skill 执行失败: skill=%s err=%s", skill_name, exc, exc_info=True)
            yield eb.build_error_event(
                f"{skill_name} 执行失败: {exc}",
                turn_id=turn_id,
            )
            yield eb.build_done_event(reason="failed", turn_id=turn_id)
            return

        final_text = outcome.final_text.strip()
        final_output_level = outcome.output_level or self._infer_turn_output_level(
            final_text=final_text,
            active_markdown_tools=[skill_item],
        )
        message_id = f"{turn_id}-0"
        session.add_message(
            "assistant",
            final_text,
            turn_id=turn_id,
            message_id=message_id,
            operation="complete",
            output_level=final_output_level.value if final_output_level is not None else None,
        )
        yield eb.build_text_event(
            content=final_text,
            turn_id=turn_id,
            metadata={
                "message_id": message_id,
                "operation": "complete",
            },
        )
        yield eb.build_done_event(
            reason=outcome.contract_result.status,
            turn_id=turn_id,
            output_level=final_output_level.value if final_output_level is not None else None,
        )

    def _resolve_allowed_tool_recommendations(
        self,
        user_message: str,
    ) -> tuple[set[str] | None, list[str]]:
        """根据激活的 Markdown Skills 解析 allowed_tools 推荐集合。"""
        items = self._select_active_markdown_tools(user_message)
        return default_intent_analyzer.collect_allowed_tools(items)

    @staticmethod
    def _output_level_from_text(text: str) -> OutputLevel | None:
        """从文本中提取显式输出等级标记。"""
        if not text:
            return None
        match = _OUTPUT_LEVEL_TOKEN_RE.search(text)
        if match is None:
            return None
        token = match.group(1).lower()
        try:
            return OutputLevel(token)
        except ValueError:
            return None

    @staticmethod
    def _output_level_from_active_markdown_tools(
        markdown_items: list[dict[str, Any]],
    ) -> OutputLevel | None:
        """根据激活的 Markdown Skills 推断本轮输出等级上限。"""
        best_level: OutputLevel | None = None
        best_rank = 0
        for item in markdown_items:
            metadata = item.get("metadata")
            if not isinstance(metadata, dict):
                continue
            contract = metadata.get("contract")
            if not isinstance(contract, dict):
                continue
            raw_ceiling = str(contract.get("trust_ceiling", "") or "").strip().lower()
            try:
                trust_ceiling = TrustLevel(raw_ceiling)
            except ValueError:
                continue
            allowed_levels = TRUST_CEILING_MAP.get(trust_ceiling, [])
            if not allowed_levels:
                continue
            candidate = allowed_levels[-1]
            candidate_rank = int(candidate.value[1:])
            if candidate_rank > best_rank:
                best_rank = candidate_rank
                best_level = candidate
        return best_level

    def _infer_turn_output_level(
        self,
        *,
        final_text: str,
        active_markdown_tools: list[dict[str, Any]],
    ) -> OutputLevel | None:
        """优先从最终文本提取输出等级，缺失时回退到激活 Skill 的 trust ceiling。"""
        return self._output_level_from_text(
            final_text
        ) or self._output_level_from_active_markdown_tools(active_markdown_tools)

    @classmethod
    def _discover_agents_md(cls) -> str:
        """兼容旧测试入口，委托给 canonical context builder。"""
        ContextBuilder._agents_md_scanned = cls._agents_md_scanned
        ContextBuilder._agents_md_cache = cls._agents_md_cache
        result = ContextBuilder._discover_agents_md()
        cls._agents_md_scanned = ContextBuilder._agents_md_scanned
        cls._agents_md_cache = ContextBuilder._agents_md_cache
        return result

    def _get_tool_definitions(
        self,
        preferred_tools: set[str] | None = None,
        session: Any = None,
    ) -> list[dict[str, Any]]:
        """获取所有已注册技能的工具定义。

        主 Agent（非 SubSession）额外暴露 ORCHESTRATOR_TOOL_NAMES 中的工具；
        子 Agent（SubSession）不暴露这些工具，防止递归派发。
        """
        from nini.agent.sub_session import SubSession

        is_sub_session = isinstance(session, SubSession)

        tools: list[dict[str, Any]] = []
        visible_tool_names: set[str] | None = None
        if self._tool_registry is not None:
            try:
                from nini.agent.tool_exposure_policy import compute_tool_exposure_policy

                policy = compute_tool_exposure_policy(
                    session=session,
                    tool_registry=self._tool_registry,
                )
                visible_tool_names = set(policy.get("visible_tools", []))
            except Exception:
                visible_tool_names = None
            raw = self._tool_registry.get_tool_definitions()
            if isinstance(raw, list):
                tools = [
                    item
                    for item in raw
                    if isinstance(item, dict)
                    and (
                        visible_tool_names is None
                        or str(item.get("function", {}).get("name", "")).strip()
                        in visible_tool_names
                    )
                ]

        # Orchestrator 工具：从注册表中直接获取 tool_definition（不走 expose_to_llm 过滤）
        if (
            not is_sub_session
            and self._tool_registry is not None
            and hasattr(self._tool_registry, "get")
        ):
            for orch_name in ORCHESTRATOR_TOOL_NAMES:
                # 检查是否已经在 tools 列表中
                already_in = any(
                    isinstance(t.get("function"), dict) and t["function"].get("name") == orch_name
                    for t in tools
                )
                if not already_in:
                    skill = self._tool_registry.get(orch_name)
                    if skill is not None and hasattr(skill, "get_tool_definition"):
                        tools.append(skill.get_tool_definition())

        # 内建用户问答工具：允许模型暂停并向用户发起澄清问题。
        has_ask_user_question = any(
            isinstance(item, dict)
            and isinstance(item.get("function"), dict)
            and item["function"].get("name") == "ask_user_question"
            for item in tools
        )
        if not has_ask_user_question:
            tools.append(self._ask_user_question_tool_definition())

        normalized_preferred = {
            str(name).strip() for name in preferred_tools or set() if str(name).strip()
        }
        annotated = [
            self._annotate_tool_definition(item, preferred_tools=normalized_preferred)
            for item in tools
        ]
        if not normalized_preferred:
            return annotated
        return sorted(
            annotated,
            key=lambda item: (
                (
                    0
                    if isinstance(item.get("function"), dict)
                    and item["function"].get("name") in normalized_preferred
                    else 1
                ),
                str(item.get("function", {}).get("name", "")),
            ),
        )

    @staticmethod
    def _annotate_tool_definition(
        item: dict[str, Any],
        *,
        preferred_tools: set[str],
    ) -> dict[str, Any]:
        """为当前回合工具补充首选/风险提示。"""
        annotated = dict(item)
        function = annotated.get("function")
        if not isinstance(function, dict):
            return annotated

        func_copy = dict(function)
        name = str(func_copy.get("name", "")).strip()
        description = str(func_copy.get("description", "")).strip()
        notes: list[str] = []
        if name in preferred_tools:
            notes.append("当前激活技能的首选工具。")
        if name in _ALLOWED_TOOLS_HIGH_RISK:
            notes.append("该工具属于高风险操作，越界使用时需要用户确认。")
        risk_hint = _ALLOWED_TOOLS_RISK_HINTS.get(name)
        if risk_hint:
            notes.append(risk_hint)
        if notes:
            prefix = " ".join(notes)
            func_copy["description"] = f"{prefix} {description}".strip()
        annotated["function"] = func_copy
        return annotated

    @staticmethod
    def _ask_user_question_tool_definition() -> dict[str, Any]:
        """ask_user_question 工具定义（Claude Code 兼容风格）。"""
        return {
            "type": "function",
            "function": {
                "name": "ask_user_question",
                "description": (
                    "向用户发起 1-4 个澄清问题，等待用户完成回答后继续任务。"
                    " options.label 必须是短标题，options.description 必须是消除歧义的完整说明。"
                ),
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
                                    "question": {
                                        "type": "string",
                                        "description": "用户真正要回答的问题文本。",
                                    },
                                    "header": {
                                        "type": "string",
                                        "description": "问题分组标题，建议为 2-6 个字的主题短语。",
                                    },
                                    "options": {
                                        "type": "array",
                                        "minItems": 2,
                                        "maxItems": 4,
                                        "description": (
                                            "候选选项。label 用于短标题展示，description 用于解释该选项的具体含义。"
                                        ),
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "label": {
                                                    "type": "string",
                                                    "description": (
                                                        "短标题/总结性短语。禁止使用 A/B/C、1/2/3、选项一 等占位写法。"
                                                    ),
                                                },
                                                "description": {
                                                    "type": "string",
                                                    "description": (
                                                        "消除歧义的完整说明，解释选择该项后意味着什么，不能仅重复 label。"
                                                    ),
                                                },
                                            },
                                            "required": ["label", "description"],
                                        },
                                    },
                                    "multiSelect": {
                                        "type": "boolean",
                                        "description": "是否允许同一问题多选。",
                                    },
                                    "allowTextInput": {
                                        "type": "boolean",
                                        "description": "是否允许用户额外输入自由文本。",
                                    },
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
                if GENERIC_ASK_OPTION_LABEL_RE.fullmatch(label):
                    return (
                        None,
                        f"第 {q_idx} 个问题的第 {opt_idx} 个选项 label 不能使用 A/B/C、1/2/3 或“选项一/方案一”这类占位标题。",
                    )
                if label == description:
                    return (
                        None,
                        f"第 {q_idx} 个问题的第 {opt_idx} 个选项 description 不能与 label 完全相同。",
                    )
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

    @staticmethod
    def _looks_like_transitional_execution_text(text: str) -> bool:
        """判断文本是否像“下一步要执行，但尚未真正执行”的中间态。"""
        normalized = str(text or "").strip()
        if not normalized:
            return False
        if len(normalized) > 120:
            return False
        if _COMPLETION_SIGNAL_RE.search(normalized):
            return False
        return _TRANSITIONAL_EXECUTION_RE.search(normalized) is not None

    def _should_retry_transitional_text(
        self,
        text: str,
        *,
        active_plan: AnalysisPlan | None,
        retry_used: bool,
        tools: list[dict[str, Any]],
    ) -> bool:
        """对明显未完成的过渡文本做一次自动续跑。"""
        if retry_used:
            return False
        if not tools:
            return False
        if not self._looks_like_transitional_execution_text(text):
            return False
        if active_plan is None:
            return True
        return any(step.status != "completed" for step in active_plan.steps)

    @staticmethod
    def _extract_tool_operation(arguments: str) -> str | None:
        """从工具参数中提取 operation。"""
        try:
            payload = json.loads(arguments)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        operation = payload.get("operation")
        if not isinstance(operation, str):
            return None
        normalized = operation.strip().lower()
        return normalized or None

    def _decide_allowed_tool_handling(
        self,
        tool_name: str,
        arguments: str,
    ) -> AllowedToolDecision:
        """判定越界工具是软放行还是需要人工确认。"""
        if tool_name in _ALLOWED_TOOLS_ALWAYS_ALLOW:
            return AllowedToolDecision(mode="allow", risk_level="internal")

        operation = self._extract_tool_operation(arguments)
        if tool_name in _ALLOWED_TOOLS_HIGH_RISK:
            approval_key = f"{tool_name}:{operation}" if operation else tool_name
            return AllowedToolDecision(
                mode="confirm",
                risk_level="high",
                approval_key=approval_key,
                operation=operation,
            )

        risky_operations = _ALLOWED_TOOLS_HIGH_RISK_OPERATIONS.get(tool_name, set())
        if operation and operation in risky_operations:
            return AllowedToolDecision(
                mode="confirm",
                risk_level="high",
                approval_key=f"{tool_name}:{operation}",
                operation=operation,
            )

        return AllowedToolDecision(mode="allow", risk_level="low", operation=operation)

    @staticmethod
    def _build_allowed_tools_notice(
        *,
        tool_name: str,
        allowed_tool_whitelist: set[str],
        allowed_tool_sources: list[str],
        continued: bool,
    ) -> str:
        source_text = ", ".join(allowed_tool_sources) if allowed_tool_sources else "当前技能"
        allowed_sorted = ", ".join(sorted(allowed_tool_whitelist))
        action_text = "本次已按低风险越界继续执行" if continued else "当前不会直接执行"
        return (
            f"工具 '{tool_name}' 不在当前技能声明的 allowed-tools 首选集合内"
            f"（来源技能: {source_text}；首选: {allowed_sorted}）；{action_text}。"
        )

    @staticmethod
    def _build_tool_approval_payload(
        *,
        tool_name: str,
        operation: str | None,
        allowed_tool_whitelist: set[str],
        allowed_tool_sources: list[str],
    ) -> dict[str, Any]:
        """构造高风险越界时的确认问题。"""
        source_text = ", ".join(allowed_tool_sources) if allowed_tool_sources else "当前技能"
        allowed_sorted = ", ".join(sorted(allowed_tool_whitelist))
        display_name = f"{tool_name}({operation})" if operation else tool_name
        return {
            "questions": [
                {
                    "header": "工具放行",
                    "question": (
                        f"工具 `{display_name}` 不在当前技能声明的 allowed-tools 首选集合内。"
                        f"来源技能: {source_text}；首选工具: {allowed_sorted}。是否允许继续执行这次高风险操作？"
                    ),
                    "options": [
                        {
                            "label": _ALLOWED_TOOLS_APPROVAL_ALLOW_ONCE,
                            "description": "仅放行这一次，后续同类操作仍需再次确认。",
                        },
                        {
                            "label": _ALLOWED_TOOLS_APPROVAL_ALLOW_SESSION,
                            "description": "当前会话内同类工具/operation 后续自动放行，新会话重置。",
                        },
                        {
                            "label": _ALLOWED_TOOLS_APPROVAL_DENY,
                            "description": "拒绝这次调用，让 Agent 改走其他路径。",
                        },
                    ],
                    "multiSelect": False,
                    "allowTextInput": True,
                }
            ]
        }

    @staticmethod
    def _resolve_tool_approval_choice(answers: dict[str, str]) -> str:
        """归一化工具授权回答。"""
        for raw_value in answers.values():
            text = str(raw_value or "").strip()
            if not text:
                continue
            if "会话" in text:
                return "allow_session"
            if "一次" in text or "本次" in text:
                return "allow_once"
            if "拒绝" in text or "deny" in text.lower():
                return "deny"
        return "deny"

    async def _request_tool_approval(
        self,
        session: Session,
        *,
        turn_id: str,
        tool_name: str,
        approval_payload: dict[str, Any],
        approval_key: str,
    ) -> tuple[str, list[AgentEvent]]:
        """通过 ask_user_question 请求用户确认高风险越界调用。"""
        if self._ask_user_question_handler is None:
            return "unavailable", []

        tool_call_id = f"approval-ask-{uuid.uuid4().hex[:8]}"
        arguments = json.dumps(approval_payload, ensure_ascii=False)
        session.add_tool_call(
            tool_call_id,
            "ask_user_question",
            arguments,
            turn_id=turn_id,
            message_id=f"tool-call-{tool_call_id}",
        )
        events: list[AgentEvent] = [
            eb.build_tool_call_event(
                tool_call_id=tool_call_id,
                name="ask_user_question",
                arguments={"name": "ask_user_question", "arguments": arguments},
                turn_id=turn_id,
                metadata={"source": "allowed_tools_approval", "approval_key": approval_key},
            ),
            eb.build_ask_user_question_event(
                questions=approval_payload.get("questions", []),
                turn_id=turn_id,
                tool_call_id=tool_call_id,
                tool_name="ask_user_question",
                metadata={"source": "allowed_tools_approval", "approval_key": approval_key},
            ),
        ]

        try:
            raw_answers = await self._await_user_question_answers(
                session, tool_call_id, approval_payload
            )
            normalized_answers = self._normalize_ask_user_question_answers(raw_answers)
            result = {
                "success": True,
                "message": "已收到用户的工具放行决定。",
                "data": {
                    "questions": approval_payload["questions"],
                    "answers": normalized_answers,
                    "approval_key": approval_key,
                },
            }
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "工具放行确认失败: session=%s tool=%s approval_key=%s err=%s",
                session.id,
                tool_name,
                approval_key,
                exc,
            )
            normalized_answers = {}
            result = {
                "success": False,
                "message": f"等待工具放行确认失败: {exc}",
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
            intent="allowed_tools_approval",
            turn_id=turn_id,
            message_id=f"tool-result-{tool_call_id}",
        )
        events.append(
            eb.build_tool_result_event(
                tool_call_id=tool_call_id,
                name="ask_user_question",
                status="error" if has_error else "success",
                message=_tool_result_message(result, is_error=has_error),
                data={"result": result},
                turn_id=turn_id,
                metadata={"source": "allowed_tools_approval", "approval_key": approval_key},
            )
        )
        if has_error:
            return "deny", events
        return self._resolve_tool_approval_choice(normalized_answers), events

    @staticmethod
    def _extract_sandbox_review_request(result: Any) -> dict[str, Any] | None:
        """从工具结果中提取沙盒扩展包审批请求。"""
        if not isinstance(result, dict) or result.get("success") is not False:
            return None
        data = result.get("data")
        if not isinstance(data, dict) or data.get("_sandbox_review_required") is not True:
            return None
        packages = data.get("requested_packages")
        violations = data.get("sandbox_violations")
        if not isinstance(packages, list) or not packages:
            return None
        normalized_packages = sorted(
            {
                str(item or "").strip()
                for item in packages
                if isinstance(item, str) and str(item or "").strip()
            }
        )
        if not normalized_packages:
            return None
        return {
            "packages": normalized_packages,
            "violations": violations if isinstance(violations, list) else [],
        }

    @staticmethod
    def _build_sandbox_import_approval_payload(
        *,
        packages: list[str],
        violations: list[dict[str, Any]] | list[Any],
    ) -> dict[str, Any]:
        """构造沙盒扩展包审批问题。"""
        package_text = "、".join(packages)
        descriptions = []
        for item in violations:
            if not isinstance(item, dict):
                continue
            message = str(item.get("message") or "").strip()
            if message:
                descriptions.append(message)
        detail = (
            "；".join(descriptions[:2])
            if descriptions
            else "这些扩展包属于低风险科研扩展，但默认仍保持拒绝。"
        )
        return {
            "questions": [
                {
                    "header": "沙盒审批",
                    "question": (
                        f"`run_code` 需要导入扩展包：{package_text}。"
                        f"{detail}。请选择是否放行这次导入。"
                    ),
                    "options": [
                        {
                            "label": _SANDBOX_IMPORT_APPROVAL_ALLOW_ONCE,
                            "description": "仅重试当前这次 run_code，不写入会话或永久记录。",
                        },
                        {
                            "label": _SANDBOX_IMPORT_APPROVAL_ALLOW_SESSION,
                            "description": "当前会话后续再次导入这些包时自动放行，新会话重置。",
                        },
                        {
                            "label": _SANDBOX_IMPORT_APPROVAL_ALWAYS_ALLOW,
                            "description": "写入永久审批记录，新会话也继续自动放行。",
                        },
                        {
                            "label": _SANDBOX_IMPORT_APPROVAL_DENY,
                            "description": "拒绝这次导入，让 Agent 改走其他路径。",
                        },
                    ],
                    "multiSelect": False,
                    "allowTextInput": True,
                }
            ]
        }

    @staticmethod
    def _resolve_sandbox_import_approval_choice(answers: dict[str, str]) -> str:
        """归一化沙盒扩展包授权回答。"""
        for raw_value in answers.values():
            text = str(raw_value or "").strip()
            if not text:
                continue
            if "始终" in text or "永久" in text:
                return "always_allow"
            if "会话" in text:
                return "allow_session"
            if "本次" in text or "一次" in text:
                return "allow_once"
            if "拒绝" in text or "deny" in text.lower():
                return "deny"
        return "deny"

    async def _request_sandbox_import_approval(
        self,
        session: Session,
        *,
        turn_id: str,
        tool_call_id: str,
        packages: list[str],
        approval_payload: dict[str, Any],
    ) -> tuple[str, list[AgentEvent]]:
        """通过 ask_user_question 请求用户确认沙盒扩展包导入。"""
        if self._ask_user_question_handler is None:
            return "unavailable", []

        approval_call_id = f"sandbox-ask-{uuid.uuid4().hex[:8]}"
        arguments = json.dumps(approval_payload, ensure_ascii=False)
        session.add_tool_call(
            approval_call_id,
            "ask_user_question",
            arguments,
            turn_id=turn_id,
            message_id=f"tool-call-{approval_call_id}",
        )
        metadata = {
            "source": "sandbox_import_approval",
            "source_tool_call_id": tool_call_id,
            "packages": packages,
        }
        events: list[AgentEvent] = [
            eb.build_tool_call_event(
                tool_call_id=approval_call_id,
                name="ask_user_question",
                arguments={"name": "ask_user_question", "arguments": arguments},
                turn_id=turn_id,
                metadata=metadata,
            ),
            eb.build_ask_user_question_event(
                questions=approval_payload.get("questions", []),
                turn_id=turn_id,
                tool_call_id=approval_call_id,
                tool_name="ask_user_question",
                metadata=metadata,
            ),
        ]

        try:
            raw_answers = await self._await_user_question_answers(
                session,
                approval_call_id,
                approval_payload,
            )
            normalized_answers = self._normalize_ask_user_question_answers(raw_answers)
            result = {
                "success": True,
                "message": "已收到用户的沙盒扩展包审批决定。",
                "data": {
                    "questions": approval_payload["questions"],
                    "answers": normalized_answers,
                    "packages": packages,
                    "source_tool_call_id": tool_call_id,
                },
            }
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "沙盒扩展包审批失败: session=%s tc_id=%s packages=%s err=%s",
                session.id,
                tool_call_id,
                packages,
                exc,
            )
            normalized_answers = {}
            result = {
                "success": False,
                "message": f"等待沙盒扩展包审批失败: {exc}",
            }

        has_error = bool(
            isinstance(result, dict) and (result.get("error") or result.get("success") is False)
        )
        result_str = serialize_tool_result_for_memory(result)
        session.add_tool_result(
            approval_call_id,
            result_str,
            tool_name="ask_user_question",
            status="error" if has_error else "success",
            intent="sandbox_import_approval",
            turn_id=turn_id,
            message_id=f"tool-result-{approval_call_id}",
        )
        events.append(
            eb.build_tool_result_event(
                tool_call_id=approval_call_id,
                name="ask_user_question",
                status="error" if has_error else "success",
                message=_tool_result_message(result, is_error=has_error),
                data={"result": result},
                turn_id=turn_id,
                metadata=metadata,
            )
        )
        if has_error:
            return "deny", events
        return self._resolve_sandbox_import_approval_choice(normalized_answers), events

    @staticmethod
    def _merge_sandbox_retry_arguments(arguments: str, packages: list[str]) -> str:
        """将本次批准的扩展包写入工具重试参数。"""
        payload = parse_tool_arguments(arguments)
        extra_allowed_imports = payload.get("extra_allowed_imports")
        merged_packages: set[str] = set(packages)
        if isinstance(extra_allowed_imports, list):
            merged_packages.update(
                str(item or "").strip()
                for item in extra_allowed_imports
                if isinstance(item, str) and str(item or "").strip()
            )
        payload["extra_allowed_imports"] = sorted(merged_packages)
        return json.dumps(payload, ensure_ascii=False)

    async def _handle_dispatch_agents(
        self,
        dispatch_tc: dict[str, Any],
        session: Any,
        turn_id: str,
    ) -> AsyncGenerator[AgentEvent, None]:
        """处理 dispatch_agents 工具调用，执行多 Agent 派发流程。

        解析工具参数 → 调用 DispatchAgentsTool.execute() → 将融合结果以
        tool_result 消息注入 session → yield 相关事件。

        Args:
            dispatch_tc: dispatch_agents 工具调用对象（含 id, function.name/arguments）
            session: 当前会话
            turn_id: 当前轮次 ID
        """
        tc_id = dispatch_tc.get("id", f"dispatch-{turn_id}")
        func_args_raw = dispatch_tc.get("function", {}).get("arguments", "{}")

        # 解析工具参数
        try:
            func_args = json.loads(func_args_raw) if isinstance(func_args_raw, str) else {}
        except json.JSONDecodeError:
            func_args = {}

        tasks_list: list[str] = func_args.get("tasks", [])
        context_str: str = func_args.get("context", "")

        # 获取 dispatch_agents 工具实例
        if self._tool_registry is None:
            error_msg = "dispatch_agents: ToolRegistry 未初始化"
            logger.error(error_msg)
            session.add_tool_result(
                tc_id,
                error_msg,
                tool_name="dispatch_agents",
                status="error",
                turn_id=turn_id,
            )
            yield eb.build_tool_result_event(
                tool_call_id=tc_id,
                name="dispatch_agents",
                status="error",
                message=error_msg,
                data={"result": {"error": error_msg}},
                turn_id=turn_id,
            )
            return

        skill = self._tool_registry.get("dispatch_agents")
        if skill is None:
            error_msg = "dispatch_agents: 工具未注册"
            logger.error(error_msg)
            session.add_tool_result(
                tc_id,
                error_msg,
                tool_name="dispatch_agents",
                status="error",
                turn_id=turn_id,
            )
            yield eb.build_tool_result_event(
                tool_call_id=tc_id,
                name="dispatch_agents",
                status="error",
                message=error_msg,
                data={"result": {"error": error_msg}},
                turn_id=turn_id,
            )
            return

        # 执行 dispatch_agents（内部完成路由 → 并行执行 → 融合，同时推送 agent_start/complete/error 事件）
        try:
            skill_result = await skill.execute(
                session,
                tasks=tasks_list,
                context=context_str,
                turn_id=turn_id,
                tool_call_id=tc_id,
            )
        except Exception as exc:
            error_msg = f"dispatch_agents 执行异常: {exc}"
            logger.exception(error_msg)
            session.add_tool_result(
                tc_id,
                error_msg,
                tool_name="dispatch_agents",
                status="error",
                turn_id=turn_id,
            )
            yield eb.build_tool_result_event(
                tool_call_id=tc_id,
                name="dispatch_agents",
                status="error",
                message=error_msg,
                data={"result": {"error": error_msg}},
                turn_id=turn_id,
            )
            return

        # 将融合结果注入 session（作为 tool_result 消息）
        result_content = skill_result.message or ""
        result_dict = skill_result.to_dict()
        session.add_tool_result(
            tc_id,
            result_content,
            tool_name="dispatch_agents",
            status="success" if skill_result.success else "error",
            turn_id=turn_id,
        )

        yield eb.build_tool_result_event(
            tool_call_id=tc_id,
            name="dispatch_agents",
            status="success" if skill_result.success else "error",
            message=result_content or "多 Agent 任务执行完成",
            data={"result": result_dict},
            turn_id=turn_id,
        )

    async def _execute_tool(
        self,
        session: Session,
        name: str,
        arguments: str,
    ) -> Any:
        """执行一个工具调用。"""
        if self._tool_registry is None:
            return {"error": f"技能系统未初始化，无法执行 {name}"}

        try:
            args = json.loads(arguments)
        except json.JSONDecodeError:
            return {"error": f"工具参数解析失败: {arguments}"}

        start_time = time.monotonic()
        try:
            result = await self._tool_registry.execute_with_fallback(name, session=session, **args)
            return result
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("工具 %s 执行失败: %s", name, e, exc_info=True)
            return {"error": f"工具 {name} 执行失败: {e}"}
        finally:
            logger.info(
                "工具执行结束: session=%s tool=%s duration_ms=%d",
                session.id,
                name,
                int((time.monotonic() - start_time) * 1000),
            )

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
            ws = WorkspaceManager(session)
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
        ws = WorkspaceManager(session)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        if label:
            filename = ws.sanitize_filename(f"{label}.{file_ext}", default_name=f"code.{file_ext}")
        else:
            filename = ws.sanitize_filename(
                f"{func_name}_{ts}.{file_ext}",
                default_name=f"{func_name}.{file_ext}",
            )

        storage = ArtifactStorage(session)
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
            "download_url": ws.build_artifact_file_download_url(filename),
        }
