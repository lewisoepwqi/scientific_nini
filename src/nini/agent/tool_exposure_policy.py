"""工具暴露策略。"""

from __future__ import annotations

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


def resolve_surface_stage(session: Any, *, user_message: str | None = None) -> str:
    """将当前会话映射到 profile / analysis / export 三段式阶段。"""
    normalized_message = str(user_message or "").lower()
    if any(token in normalized_message for token in ("导出", "报告", "交付", "下载", "保存")):
        return "export"
    if any(token in normalized_message for token in ("概览", "质量", "摘要", "预览", "字段")):
        return "profile"

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

    stage = str(stage_override or "").strip() or resolve_surface_stage(session, user_message=user_message)
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
