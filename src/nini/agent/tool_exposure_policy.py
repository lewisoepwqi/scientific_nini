"""工具暴露策略。

提供两套接口：
- ToolExposurePolicy 数据类：面向子 Agent 工具子集构建，支持白名单/黑名单/前缀黑名单过滤。
- compute_tool_exposure_policy()：面向主 Agent，基于会话阶段动态计算暴露面。

设计原则：
- 当前轮工具面优先由“当前激活任务”决定，避免未来步骤污染当前执行阶段。
- visualization 与 export 分离：画图不等于导出交付。
- 若阶段判定异常导致当前任务缺少执行工具，自动补入最小执行集合并记录告警。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nini.agent.components.analysis_stage_detector import AnalysisStage, detect_current_stage

_ALWAYS_ALLOWED = {
    "ask_user_question",
    "task_state",
    "task_write",
    "detect_phase",
    "query_evidence",
}

_PROFILE_TOOLS = {
    "load_dataset",
    "data_summary",
    "dataset_catalog",
    "dataset_transform",
    "clean_data",
    "data_quality",
    "analysis_memory",
}

_ANALYSIS_TOOLS = {
    "stat_test",
    "sample_size",
    "stat_model",
    "stat_interpret",
    "t_test",
    "anova",
    "mann_whitney",
    "kruskal_wallis",
    "correlation",
    "regression",
    "multiple_comparison",
    "code_session",
    "run_code",
    "run_r_code",
    "collect_artifacts",
    "analysis_memory",
    "search_literature",
    "search_archive",
}

_VISUALIZATION_TOOLS = {
    "chart_session",
    "code_session",
    "collect_artifacts",
    "analysis_memory",
}

_EXPORT_TOOLS = {
    "export_chart",
    "export_document",
    "generate_report",
    "report_session",
    "export_report",
    "workspace_session",
    "collect_artifacts",
    "organize_workspace",
    "generate_widget",
    "edit_file",
}

_EXECUTION_TOOLS = {
    "load_dataset",
    "data_summary",
    "dataset_catalog",
    "dataset_transform",
    "clean_data",
    "data_quality",
    "stat_test",
    "sample_size",
    "stat_model",
    "stat_interpret",
    "t_test",
    "anova",
    "mann_whitney",
    "kruskal_wallis",
    "correlation",
    "regression",
    "multiple_comparison",
    "code_session",
    "run_code",
    "run_r_code",
}

_PRESENTATION_TOOLS = {"generate_widget"}

_HIGH_RISK_TOOLS = {
    "edit_file",
    "export_chart",
    "export_document",
    "export_report",
    "organize_workspace",
    "workspace_session",
}

_SUBAGENT_TOOL_PROFILES: dict[str, tuple[str, ...]] = {
    "planning_execution": ("task_state", "dataset_catalog", "analysis_memory", "workspace_session"),
    "cleaning_execution": (
        "dataset_catalog",
        "dataset_transform",
        "code_session",
        "analysis_memory",
    ),
    "analysis_execution": (
        "dataset_catalog",
        "code_session",
        "stat_test",
        "stat_model",
        "stat_interpret",
        "analysis_memory",
    ),
    "chart_execution": ("chart_session", "code_session", "analysis_memory"),
    "writing_execution": ("report_session", "workspace_session", "analysis_memory"),
    "literature_search": ("workspace_session", "analysis_memory", "search_literature"),
    "literature_reading": ("workspace_session", "analysis_memory"),
    "citation_management": ("workspace_session", "analysis_memory"),
    "review_execution": ("workspace_session", "analysis_memory"),
}

_EXPORT_MESSAGE_HINTS = ("导出", "报告", "交付", "下载", "保存")
_PROFILE_MESSAGE_HINTS = ("概览", "质量", "摘要", "预览", "字段")


@dataclass(frozen=True)
class ToolExposurePolicy:
    """子 Agent 工具暴露策略（不可变）。

    用于从完整 ToolRegistry 中构建受限子集，取代 registry.create_subset(allowed_tools)。
    过滤顺序：白名单（allowed_tools 非空时生效）→ deny_names 黑名单 → deny_prefixes 前缀黑名单。

    示例::
        policy = ToolExposurePolicy(allowed_tools=("stat_test", "chart_session"))
        subset = policy.apply(tool_registry)
    """

    allowed_tools: tuple[str, ...] = field(default_factory=tuple)
    deny_names: frozenset[str] = field(default_factory=frozenset)
    deny_prefixes: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_agent_def(cls, agent_def: Any) -> "ToolExposurePolicy":
        """从 AgentDefinition 构建策略（始终排除 dispatch_agents 防递归）。"""
        tool_profile = str(getattr(agent_def, "tool_profile", "") or "").strip()
        if tool_profile and tool_profile in _SUBAGENT_TOOL_PROFILES:
            allowed = _SUBAGENT_TOOL_PROFILES[tool_profile]
        else:
            allowed = tuple(getattr(agent_def, "allowed_tools", ()) or ())
        return cls(
            allowed_tools=allowed,
            deny_names=frozenset({"dispatch_agents"}),
        )

    def apply(self, tool_registry: Any) -> Any:
        """在 tool_registry 上应用策略，返回过滤后的子集注册表。"""
        if tool_registry is None:
            return tool_registry
        # 优先使用 allowed_tools 白名单
        if self.allowed_tools:
            filtered = list(self.allowed_tools)
        else:
            all_tools = tool_registry.list_tools() if hasattr(tool_registry, "list_tools") else []
            filtered = list(all_tools)

        # deny_names 黑名单
        if self.deny_names:
            filtered = [t for t in filtered if t not in self.deny_names]

        # deny_prefixes 前缀黑名单
        if self.deny_prefixes:
            filtered = [t for t in filtered if not any(t.startswith(p) for p in self.deny_prefixes)]

        return tool_registry.create_subset(filtered)


def _collect_task_tool_hints(session: Any) -> list[str]:
    """从任务计划中提取 tool_hint，供 surface 判定参考。"""
    if session is None or not hasattr(session, "task_manager"):
        return []
    manager = getattr(session, "task_manager", None)
    if manager is None or not hasattr(manager, "to_analysis_plan_dict"):
        return []
    plan = manager.to_analysis_plan_dict()
    steps = plan.get("steps") if isinstance(plan, dict) else None
    if not isinstance(steps, list):
        return []

    hints: list[str] = []
    for item in steps:
        if not isinstance(item, dict):
            continue
        raw_hint = str(item.get("tool_hint", "") or "").strip()
        if not raw_hint:
            continue
        # LLM 可能使用 "/" 分隔多个候选工具，如 "stat_test/code_session"
        for hint in raw_hint.split("/"):
            hint = hint.strip()
            if hint and hint not in hints:
                hints.append(hint)
    return hints


def _split_tool_hint(tool_hint: str | None) -> list[str]:
    """拆分 tool_hint 中的候选工具列表。"""
    raw_hint = str(tool_hint or "").strip()
    if not raw_hint:
        return []
    hints: list[str] = []
    for item in raw_hint.split("/"):
        normalized = item.strip()
        if normalized and normalized not in hints:
            hints.append(normalized)
    return hints


def is_execution_tool(tool_name: str) -> bool:
    """判断工具是否属于真实执行工具。"""
    return str(tool_name or "").strip() in _EXECUTION_TOOLS


def is_presentation_tool(tool_name: str) -> bool:
    """判断工具是否属于纯展示工具。"""
    return str(tool_name or "").strip() in _PRESENTATION_TOOLS


def resolve_stage_from_tool_hint(tool_hint: str | None) -> str | None:
    """根据单个 task tool_hint 解析阶段。

    按 hint 声明顺序解析，保留任务编写者的优先意图。
    """
    for hint in _split_tool_hint(tool_hint):
        if hint in _PROFILE_TOOLS:
            return "profile"
        if hint in _ANALYSIS_TOOLS or hint in _EXECUTION_TOOLS:
            return "analysis"
        if hint in _VISUALIZATION_TOOLS:
            return "visualization"
        if hint in _EXPORT_TOOLS:
            return "export"
    return None


def tool_satisfies_tool_hint(tool_name: str, tool_hint: str | None) -> bool:
    """判断某工具是否可满足当前任务提示。

    规则偏保守：展示工具不允许替代执行型任务。
    """
    normalized_name = str(tool_name or "").strip()
    hints = _split_tool_hint(tool_hint)
    if not normalized_name or not hints:
        return False
    if normalized_name in hints:
        return True
    if normalized_name in _PRESENTATION_TOOLS:
        return False
    if is_execution_tool(normalized_name) and any(is_execution_tool(hint) for hint in hints):
        return True
    if normalized_name in _VISUALIZATION_TOOLS and any(
        hint in _VISUALIZATION_TOOLS for hint in hints
    ):
        return True
    if normalized_name in _EXPORT_TOOLS and any(hint in _EXPORT_TOOLS for hint in hints):
        return True
    if normalized_name in _PROFILE_TOOLS and any(hint in _PROFILE_TOOLS for hint in hints):
        return True
    return False


def _resolve_stage_from_task_manager(session: Any) -> tuple[str | None, str | None, Any | None]:
    """根据任务状态解析当前阶段，优先使用 in_progress 任务。"""
    if session is None or not hasattr(session, "task_manager"):
        return None, None, None
    manager = getattr(session, "task_manager", None)
    tasks = getattr(manager, "tasks", None)
    if not isinstance(tasks, list) or not tasks:
        return None, None, None

    for task in tasks:
        if getattr(task, "status", None) != "in_progress":
            continue
        stage = resolve_stage_from_tool_hint(getattr(task, "tool_hint", None))
        if stage:
            return stage, "active_task", task

    for task in tasks:
        if getattr(task, "status", None) != "pending":
            continue
        stage = resolve_stage_from_tool_hint(getattr(task, "tool_hint", None))
        if stage:
            return stage, "next_pending_task", task

    for task in reversed(tasks):
        if getattr(task, "status", None) not in {"completed", "failed", "blocked", "skipped"}:
            continue
        stage = resolve_stage_from_tool_hint(getattr(task, "tool_hint", None))
        if stage:
            return stage, "recent_task", task

    return None, None, None


def _resolve_stage_from_recent_messages(session: Any) -> tuple[str | None, str]:
    """根据最近真实工具轨迹解析阶段。"""
    stage = detect_current_stage(session) if session is not None else AnalysisStage.UNKNOWN
    if stage in {AnalysisStage.PLANNING, AnalysisStage.DATA_PREP, AnalysisStage.UNKNOWN}:
        return "profile", "recent_messages"
    if stage == AnalysisStage.VISUALIZATION:
        return "visualization", "recent_messages"
    if stage == AnalysisStage.REPORTING:
        return "export", "recent_messages"
    return "analysis", "recent_messages"


def resolve_surface_stage(session: Any, *, user_message: str | None = None) -> str:
    """将当前会话映射到 profile / analysis / visualization / export 阶段。"""
    task_stage, _, _task = _resolve_stage_from_task_manager(session)
    if task_stage:
        return task_stage

    normalized_message = str(user_message or "").lower()
    if any(token in normalized_message for token in _EXPORT_MESSAGE_HINTS):
        return "export"
    if any(token in normalized_message for token in _PROFILE_MESSAGE_HINTS):
        return "profile"

    recent_stage, _reason = _resolve_stage_from_recent_messages(session)
    return recent_stage or "profile"


# 阶段 → 工具集的映射（用于 look-ahead）
_STAGE_TOOLS_MAP: dict[str, set[str]] = {
    "profile": _PROFILE_TOOLS,
    "analysis": _ANALYSIS_TOOLS,
    "visualization": _VISUALIZATION_TOOLS,
    "export": _EXPORT_TOOLS,
}


def _resolve_next_pending_stage(session: Any) -> str | None:
    """查找下一个 pending 任务的阶段（look-ahead 用）。

    只检查第一个 pending 任务，不递归查找。
    """
    if session is None or not hasattr(session, "task_manager"):
        return None
    manager = getattr(session, "task_manager", None)
    tasks = getattr(manager, "tasks", None)
    if not isinstance(tasks, list):
        return None
    for task in tasks:
        if getattr(task, "status", None) == "pending":
            return resolve_stage_from_tool_hint(getattr(task, "tool_hint", None))
    return None


def compute_tool_exposure_policy(
    *,
    session: Any,
    tool_registry: Any,
    user_message: str | None = None,
    stage_override: str | None = None,
) -> dict[str, Any]:
    """计算当前轮允许暴露的工具面。"""
    all_tools = []
    if tool_registry is not None and hasattr(tool_registry, "list_tools"):
        listed = tool_registry.list_tools()
        if isinstance(listed, list):
            all_tools = [str(item).strip() for item in listed if str(item).strip()]

    active_task_id: int | None = None
    active_task_title: str | None = None
    active_task_hint: str | None = None
    stage_reason = "fallback_profile"
    if stage_override:
        stage = str(stage_override).strip()
        stage_reason = "stage_override"
    else:
        task_stage, task_reason, active_task = _resolve_stage_from_task_manager(session)
        if task_stage:
            stage = task_stage
            stage_reason = str(task_reason or "task_manager")
            active_task_id = getattr(active_task, "id", None)
            active_task_title = getattr(active_task, "title", None)
            active_task_hint = getattr(active_task, "tool_hint", None)
        else:
            normalized_message = str(user_message or "").lower()
            if any(token in normalized_message for token in _EXPORT_MESSAGE_HINTS):
                stage = "export"
                stage_reason = "user_message_export"
            elif any(token in normalized_message for token in _PROFILE_MESSAGE_HINTS):
                stage = "profile"
                stage_reason = "user_message_profile"
            else:
                stage, recent_reason = _resolve_stage_from_recent_messages(session)
                stage_reason = recent_reason

    authorization_state: dict[str, bool] = {}
    forced_visible_tools: list[str] = []
    policy_warnings: list[str] = []

    allowed = set(_ALWAYS_ALLOWED)
    if stage == "profile":
        allowed |= _PROFILE_TOOLS
    elif stage == "visualization":
        allowed |= _VISUALIZATION_TOOLS
    elif stage == "export":
        allowed |= _EXPORT_TOOLS
    else:
        allowed |= _ANALYSIS_TOOLS

    # ── look-ahead：当前任务未标记 completed 时，预解锁下一阶段工具 ──
    if stage in {"profile", "visualization"} and session is not None:
        next_pending_stage = _resolve_next_pending_stage(session)
        if next_pending_stage and next_pending_stage != stage:
            lookahead_tools = _STAGE_TOOLS_MAP.get(next_pending_stage, set())
            lookahead_visible = [name for name in all_tools if name in lookahead_tools]
            if lookahead_visible:
                allowed.update(lookahead_visible)
                policy_warnings.append(
                    f"当前阶段为 {stage}，但下一待执行任务属于 {next_pending_stage} 阶段，"
                    "已预解锁其工具（look-ahead）。"
                    "请完成当前任务后调用 task_state 更新状态。"
                )

    for tool_name in list(allowed):
        if tool_name not in _HIGH_RISK_TOOLS:
            continue
        approved = False
        if session is not None and hasattr(session, "has_tool_approval"):
            approved = bool(session.has_tool_approval(tool_name))
        authorization_state[tool_name] = approved
        if stage != "export" and not approved:
            allowed.discard(tool_name)

    if active_task_hint:
        compatible_tools = [
            name for name in all_tools if tool_satisfies_tool_hint(name, active_task_hint)
        ]
        if compatible_tools and not any(name in allowed for name in compatible_tools):
            forced_visible_tools = list(compatible_tools)
            allowed.update(compatible_tools)
            policy_warnings.append(
                f"当前任务提示 `{active_task_hint}` 对应工具未出现在 {stage} 阶段工具面，已强制补入兼容工具。"
            )

    if stage in {"analysis", "visualization"}:
        visible_execution_tools = [name for name in allowed if is_execution_tool(name)]
        if not visible_execution_tools:
            fallback_execution_tools = [
                name
                for name in ("code_session", "run_code", "run_r_code", "stat_test")
                if name in all_tools
            ]
            if fallback_execution_tools:
                for name in fallback_execution_tools:
                    if name not in forced_visible_tools:
                        forced_visible_tools.append(name)
                allowed.update(fallback_execution_tools)
                policy_warnings.append("当前阶段缺少执行工具，已自动补入最小执行集合。")

    visible_tools = [name for name in all_tools if name in allowed]
    hidden_tools = [name for name in all_tools if name not in allowed]
    removed_by_policy = [name for name in hidden_tools if name not in _ALWAYS_ALLOWED]

    # ── 构建阶段过渡提示（供 runner 注入 LLM 上下文）──
    stage_transition_hint: str | None = None
    if removed_by_policy and active_task_id is not None:
        next_stage = _resolve_next_pending_stage(session)
        if next_stage:
            representative_tools = [
                name for name in removed_by_policy[:3]
                if name not in _ALWAYS_ALLOWED
            ]
            tool_list = "、".join(f"`{n}`" for n in representative_tools)
            if len(removed_by_policy) > 3:
                tool_list += f"等 {len(removed_by_policy)} 个工具"
            stage_transition_hint = (
                f"当前处于「{stage}」阶段，{tool_list} 等工具暂不可用。"
                f"完成任务{active_task_id}后调用 task_state 更新状态，"
                f"将自动解锁「{next_stage}」阶段工具。"
            )

    return {
        "stage": stage,
        "stage_reason": stage_reason,
        "active_task_id": active_task_id,
        "active_task_title": active_task_title,
        "active_task_hint": active_task_hint,
        "visible_tools": visible_tools,
        "hidden_tools": hidden_tools,
        "removed_by_policy": removed_by_policy,
        "authorization_state": authorization_state,
        "high_risk_tools": [name for name in all_tools if name in _HIGH_RISK_TOOLS],
        "forced_visible_tools": forced_visible_tools,
        "policy_warnings": policy_warnings,
        "stage_transition_hint": stage_transition_hint,
    }
