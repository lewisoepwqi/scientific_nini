"""分析阶段检测器。

根据会话最近的工具调用历史推断当前所处的分析阶段，
用于调整知识注入等上下文资源的配额。
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class AnalysisStage(str, Enum):
    """分析阶段枚举。"""

    PLANNING = "planning"
    DATA_PREP = "data_prep"
    ANALYSIS = "analysis"
    VISUALIZATION = "visualization"
    REPORTING = "reporting"
    UNKNOWN = "unknown"


# 工具名称到阶段的映射
_TOOL_STAGE_MAP: dict[str, AnalysisStage] = {
    "task_state": AnalysisStage.PLANNING,
    "task_write": AnalysisStage.PLANNING,
    "dataset_catalog": AnalysisStage.DATA_PREP,
    "dataset_transform": AnalysisStage.DATA_PREP,
    "load_dataset": AnalysisStage.DATA_PREP,
    "preview_data": AnalysisStage.DATA_PREP,
    "data_summary": AnalysisStage.DATA_PREP,
    "clean_data": AnalysisStage.DATA_PREP,
    "data_quality": AnalysisStage.DATA_PREP,
    "dispatch_agents": AnalysisStage.ANALYSIS,
    "stat_test": AnalysisStage.ANALYSIS,
    "stat_model": AnalysisStage.ANALYSIS,
    "stat_interpret": AnalysisStage.ANALYSIS,
    "t_test": AnalysisStage.ANALYSIS,
    "anova": AnalysisStage.ANALYSIS,
    "correlation": AnalysisStage.ANALYSIS,
    "regression": AnalysisStage.ANALYSIS,
    "mann_whitney": AnalysisStage.ANALYSIS,
    "kruskal_wallis": AnalysisStage.ANALYSIS,
    "multiple_comparison": AnalysisStage.ANALYSIS,
    "interpretation": AnalysisStage.ANALYSIS,
    "chart_session": AnalysisStage.VISUALIZATION,
    "create_chart": AnalysisStage.VISUALIZATION,
    "export_chart": AnalysisStage.VISUALIZATION,
    "visualization": AnalysisStage.VISUALIZATION,
    "report_session": AnalysisStage.REPORTING,
    "generate_report": AnalysisStage.REPORTING,
    "export_report": AnalysisStage.REPORTING,
    "export_document": AnalysisStage.REPORTING,
}

# 各阶段的知识注入系数（越小表示知识注入越少）
STAGE_KNOWLEDGE_MULTIPLIER: dict[AnalysisStage, float] = {
    AnalysisStage.PLANNING: 0.5,
    AnalysisStage.DATA_PREP: 0.7,
    AnalysisStage.ANALYSIS: 1.0,
    AnalysisStage.VISUALIZATION: 0.6,
    AnalysisStage.REPORTING: 0.4,
    AnalysisStage.UNKNOWN: 1.0,
}


def detect_current_stage(session: Any) -> AnalysisStage:
    """检测当前分析阶段。

    遍历会话消息尾部 10 条，找最后一个 tool_call 的工具名称，返回对应阶段。
    如果找不到则返回 UNKNOWN。

    Args:
        session: 会话对象，包含 messages 列表

    Returns:
        当前分析阶段
    """
    messages: list[dict[str, Any]] = getattr(session, "messages", []) or []
    # 从尾部取最多 10 条消息
    recent = messages[-10:] if len(messages) > 10 else messages

    last_tool_name: str | None = None
    for msg in reversed(recent):
        role = msg.get("role")
        # 检查 assistant 消息中的 tool_calls
        if role == "assistant" and msg.get("tool_calls"):
            tool_calls = msg["tool_calls"]
            if isinstance(tool_calls, list) and tool_calls:
                last_call = tool_calls[-1]
                if isinstance(last_call, dict):
                    fn = last_call.get("function", {})
                    if isinstance(fn, dict):
                        last_tool_name = str(fn.get("name", "") or "").strip()
                        break
        # 检查 tool 消息的 tool_name 字段
        elif role == "tool" and msg.get("tool_name"):
            last_tool_name = str(msg["tool_name"]).strip()
            break

    if last_tool_name:
        return _TOOL_STAGE_MAP.get(last_tool_name, AnalysisStage.UNKNOWN)
    return AnalysisStage.UNKNOWN


def get_knowledge_max_chars(base_max_chars: int, stage: AnalysisStage) -> int:
    """根据当前分析阶段计算知识注入的有效上限。

    Args:
        base_max_chars: 基础最大字符数（来自 settings.knowledge_max_chars）
        stage: 当前分析阶段

    Returns:
        调整后的最大字符数
    """
    multiplier = STAGE_KNOWLEDGE_MULTIPLIER.get(stage, 1.0)
    return max(200, int(base_max_chars * multiplier))
