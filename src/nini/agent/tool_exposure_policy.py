"""工具暴露策略。

提供两套接口：
- ToolExposurePolicy 数据类：面向子 Agent 工具子集构建，支持白名单/黑名单/前缀黑名单过滤。
- compute_tool_exposure_policy()：面向主 Agent，基于会话阶段动态计算暴露面。
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
    "chart_session",
    "collect_artifacts",
    "analysis_memory",
    "search_literature",
    "search_archive",
}

_EXPORT_TOOLS = {
    "chart_session",
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


def resolve_surface_stage(session: Any, *, user_message: str | None = None) -> str:
    """将当前会话映射到 profile / analysis / export 三段式阶段。"""
    normalized_message = str(user_message or "").lower()
    if any(token in normalized_message for token in ("导出", "报告", "交付", "下载", "保存")):
        return "export"
    if any(token in normalized_message for token in ("概览", "质量", "摘要", "预览", "字段")):
        return "profile"

    task_tool_hints = _collect_task_tool_hints(session)
    if any(hint in _EXPORT_TOOLS for hint in task_tool_hints):
        return "export"
    if any(hint in _ANALYSIS_TOOLS for hint in task_tool_hints):
        return "analysis"

    stage = detect_current_stage(session) if session is not None else AnalysisStage.UNKNOWN
    if stage in {AnalysisStage.PLANNING, AnalysisStage.DATA_PREP, AnalysisStage.UNKNOWN}:
        return "profile"
    if stage in {AnalysisStage.REPORTING, AnalysisStage.VISUALIZATION}:
        return "export"
    return "analysis"


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

    stage = str(stage_override or "").strip() or resolve_surface_stage(
        session, user_message=user_message
    )
    allowed = set(_ALWAYS_ALLOWED)
    if stage == "profile":
        allowed |= _PROFILE_TOOLS
    elif stage == "export":
        allowed |= _EXPORT_TOOLS
    else:
        allowed |= _ANALYSIS_TOOLS

    authorization_state: dict[str, bool] = {}
    for tool_name in list(allowed):
        if tool_name not in _HIGH_RISK_TOOLS:
            continue
        approved = False
        if session is not None and hasattr(session, "has_tool_approval"):
            approved = bool(session.has_tool_approval(tool_name))
        authorization_state[tool_name] = approved
        if stage != "export" and not approved:
            allowed.discard(tool_name)

    visible_tools = [name for name in all_tools if name in allowed]
    hidden_tools = [name for name in all_tools if name not in allowed]
    removed_by_policy = [name for name in hidden_tools if name not in _ALWAYS_ALLOWED]
    return {
        "stage": stage,
        "visible_tools": visible_tools,
        "hidden_tools": hidden_tools,
        "removed_by_policy": removed_by_policy,
        "authorization_state": authorization_state,
        "high_risk_tools": [name for name in all_tools if name in _HIGH_RISK_TOOLS],
    }
