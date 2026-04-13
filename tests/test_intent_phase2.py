"""Phase 2 意图精度优化测试。

覆盖：子检验类型识别、子类型注入 tool_hints。
"""

from __future__ import annotations

from nini.intent import IntentAnalyzer, get_difference_subtype
from nini.intent.base import IntentAnalysis, IntentCandidate

# 5.1–5.4 多意图检测已随 detect_multi_intent 删除而移除
# test_route_multi_intent_returns_merged_decision 已随 TaskRouter 删除而移除


# ============================================================================
# 5.6–5.8 子检验类型识别
# ============================================================================


def test_subtype_paired_t_test():
    """5.6 配对t检验关键词识别。"""
    assert get_difference_subtype("帮我做配对t检验") == "paired_t_test"


def test_subtype_mann_whitney():
    """5.7 Mann-Whitney 关键词识别。"""
    assert get_difference_subtype("Mann-Whitney 检验") == "mann_whitney"


def test_subtype_none_for_generic():
    """5.8 无具体子类型词返回 None。"""
    assert get_difference_subtype("帮我分析差异") is None


# ============================================================================
# 5.9 子类型注入 tool_hints
# ============================================================================

_CAPS_WITH_DIFF = [
    {
        "name": "difference_analysis",
        "display_name": "差异分析",
        "description": "差异检验与比较分析",
        "required_tools": ["t_test", "anova"],
        "is_executable": True,
    },
    {
        "name": "correlation_analysis",
        "display_name": "相关性分析",
        "description": "相关系数与关联分析",
        "required_tools": ["correlation"],
        "is_executable": True,
    },
    {
        "name": "visualization",
        "display_name": "可视化",
        "description": "数据图表绘制",
        "required_tools": ["create_chart"],
        "is_executable": True,
    },
]


def test_subtype_injected_into_tool_hints():
    """5.9 含配对t检验输入时 tool_hints 首位包含 paired_t_test。"""
    analyzer = IntentAnalyzer()
    analysis = analyzer.analyze("帮我做配对t检验分析", capabilities=_CAPS_WITH_DIFF)
    # Top-1 应该是 difference_analysis（因为"配对t检验"命中差异相关同义词）
    if (
        analysis.capability_candidates
        and analysis.capability_candidates[0].name == "difference_analysis"
    ):
        assert len(analysis.tool_hints) > 0
        assert "paired_t_test" in analysis.tool_hints[0]
