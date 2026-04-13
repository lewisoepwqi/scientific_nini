"""AgentRunner.run() 跨阶段共享状态。

将 run() 中约 30 个局部可变变量提升为显式数据类，
使各阶段方法可以读写同一状态对象，而非依赖闭包捕获。
同时将原 run() 内的闭包辅助函数提升为 RunState 方法，
消除 nonlocal 依赖。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from nini.agent import event_builders as eb
from nini.agent.events import AgentEvent
from nini.agent.components.tool_executor import parse_tool_arguments


@dataclass
class RunState:
    """run() 跨阶段共享状态。"""

    # ---- 迭代控制 ----
    iteration: int = 0
    max_iter: int = 0
    message_seq: int = 0
    current_message_id: str | None = None

    # ---- 超时 ----
    loop_start_time: float = field(default_factory=time.monotonic)
    timeout_excluded_seconds: float = 0.0
    active_timeout_seconds: int = 0
    wall_clock_timeout_seconds: int = 0
    should_stop: Callable[[], bool] = field(default_factory=lambda: lambda: False)

    # ---- 跟踪提示 ----
    pending_followup_prompt: str | None = None
    pending_loop_warn_message: str | None = None
    pending_breaker_fallback_prompt: str | None = None
    tool_followup_retry_used: bool = False
    synthesis_prompt_used: bool = False

    # ---- 分析计划 ----
    active_plan: Any = None  # AnalysisPlan | None
    next_step_idx: int = 0
    plan_event_seq: int = 0

    # ---- Reasoning ----
    reasoning_tracker: Any = None  # ReasoningChainTracker

    # ---- 工具熔断 ----
    tool_failure_chains: dict[str, dict[str, Any]] = field(default_factory=dict)
    consecutive_tool_failure_count: int = 0
    task_state_noop_repeat_count: int = 0
    breaker_threshold: int = 1

    # ---- 允许工具 ----
    allowed_tool_whitelist: set[str] | None = None
    allowed_tool_sources: list[dict[str, Any]] = field(default_factory=list)

    # ---- 活跃 Markdown 工具 ----
    active_markdown_tools: set[str] = field(default_factory=set)

    # ---- 数据预览去重 ----
    emitted_data_preview_signatures: set[str] = field(default_factory=set)
    successful_dataset_profile_signatures: set[str] = field(default_factory=set)
    dataset_profile_max_view_by_name: dict[str, str] = field(default_factory=dict)

    # ---- 报告 ----
    report_markdown_for_turn: str | None = None

    # ---- 上下文比率 ----
    context_ratio: float = 0.0

    def should_continue(self) -> bool:
        """外层循环是否应继续。"""
        return self.max_iter <= 0 or self.iteration < self.max_iter

    # ---- 原 run() 内的闭包辅助函数（提升为 RunState 方法） ----

    def build_tool_args_signature(self, name: str, raw_arguments: str) -> str:
        """构建工具调用的参数签名（用于熔断链路去重）。"""
        parsed = parse_tool_arguments(raw_arguments)
        if parsed:
            normalized = json.dumps(parsed, ensure_ascii=False, sort_keys=True, default=str)
        else:
            normalized = str(raw_arguments).strip()
        return f"{name}::{normalized}"

    @staticmethod
    def to_plan_status(raw_status: str) -> str:
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

    def build_plan_progress_payload(
        self,
        *,
        current_idx: int,
        step_status: str,
        next_hint: str | None = None,
        block_reason: str | None = None,
    ) -> dict[str, Any]:
        """构建 plan_progress 标准载荷。"""
        if self.active_plan is None or not self.active_plan.steps:
            return {
                "current_step_index": 0,
                "total_steps": 0,
                "step_title": "",
                "step_status": "not_started",
                "next_hint": next_hint,
            }

        safe_idx = max(0, min(current_idx, len(self.active_plan.steps) - 1))
        current_step = self.active_plan.steps[safe_idx]
        total_steps = len(self.active_plan.steps)
        resolved_status = self.to_plan_status(step_status)

        auto_next_hint = next_hint
        if auto_next_hint is None:
            next_idx = safe_idx + 1
            if resolved_status in {"failed", "blocked"}:
                auto_next_hint = "可尝试重试当前步骤或补充输入后继续。"
            elif resolved_status == "done" and next_idx < total_steps:
                auto_next_hint = f"下一步：{self.active_plan.steps[next_idx].title}"
            elif resolved_status == "done" and next_idx >= total_steps:
                auto_next_hint = "全部步骤已完成。"
            elif resolved_status == "in_progress":
                auto_next_hint = (
                    f"完成后将进入：{self.active_plan.steps[next_idx].title}"
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

    def new_plan_progress_event(
        self,
        *,
        turn_id: str,
        current_idx: int,
        step_status: str,
        next_hint: str | None = None,
        block_reason: str | None = None,
    ) -> AgentEvent:
        """创建带序号的计划进度事件，便于前端乱序保护。"""
        self.plan_event_seq += 1
        payload = self.build_plan_progress_payload(
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
            seq=self.plan_event_seq,
        )

    def new_analysis_plan_event(
        self,
        plan_data: dict[str, Any],
        *,
        turn_id: str,
    ) -> AgentEvent:
        """创建带序号的分析计划事件，确保前端按同一时钟域处理。"""
        self.plan_event_seq += 1
        return eb.build_analysis_plan_event(
            steps=plan_data.get("steps", []),
            raw_text=plan_data.get("raw_text", ""),
            turn_id=turn_id,
            seq=self.plan_event_seq,
        )

    def new_plan_step_update_event(
        self,
        step_data: dict[str, Any],
        *,
        turn_id: str,
    ) -> AgentEvent:
        """创建带序号的任务步骤更新事件，避免被前端乱序保护丢弃。"""
        self.plan_event_seq += 1
        return eb.build_plan_step_update_event(
            step_id=step_data.get("id", 0),
            status=step_data.get("status", ""),
            error=step_data.get("error"),
            turn_id=turn_id,
            seq=self.plan_event_seq,
        )

    def new_task_attempt_event(
        self,
        *,
        session: Any,
        turn_id: str,
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
        self.plan_event_seq += 1
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
            seq=self.plan_event_seq,
            task_id=task_id,
            attempt_id=attempt_id,
        )
