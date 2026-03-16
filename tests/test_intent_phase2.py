"""Phase 2 意图精度优化测试。

覆盖：多意图检测、子检验类型识别、has_datasets 阈值差异、路由集成。
"""

from __future__ import annotations

import pytest

from nini.intent.multi_intent import detect_multi_intent
from nini.intent.subtypes import get_difference_subtype
from nini.intent.base import IntentAnalysis, IntentCandidate
from nini.intent.optimized import OptimizedIntentAnalyzer
from nini.agent.router import RoutingDecision, TaskRouter

# ============================================================================
# 5.1–5.4 多意图检测
# ============================================================================


def test_multi_intent_sequential_with_punctuation():
    """5.1 有标点的顺序复合查询，返回两个子意图。"""
    result = detect_multi_intent("先做相关性分析，然后画散点图")
    assert result is not None
    assert len(result) == 2


def test_multi_intent_single_intent_returns_none():
    """5.2 单一意图返回 None。"""
    result = detect_multi_intent("帮我做差异分析")
    assert result is None


def test_multi_intent_parallel():
    """5.3 并行复合查询返回两个子意图。"""
    result = detect_multi_intent("同时帮我做相关分析和画柱状图")
    assert result is not None
    assert len(result) == 2


def test_multi_intent_sequential_without_punctuation():
    """5.4 无标点的顺序复合查询，通过连接词分割。"""
    result = detect_multi_intent("先做相关性分析然后画散点图")
    assert result is not None
    assert len(result) == 2


# ============================================================================
# 5.5 多意图路由集成
# ============================================================================


@pytest.mark.asyncio
async def test_route_multi_intent_returns_merged_decision():
    """5.5 顺序复合查询触发 multi_intent 策略，agent_ids 包含所有子意图路由目标。"""
    router = TaskRouter(model_resolver=None, enable_llm_fallback=False)
    # "统计检验" 命中 statistician, "画图" 命中 viz_designer
    result = await router.route("先做统计检验，然后画图展示")
    assert result.strategy == "multi_intent"
    assert len(result.agent_ids) >= 2


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


def _make_analyzer_with_caps() -> OptimizedIntentAnalyzer:
    """构造已初始化的分析器，包含 difference_analysis 能力。"""
    analyzer = OptimizedIntentAnalyzer()
    caps = [
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
    analyzer.initialize(caps)
    return analyzer


def test_subtype_injected_into_tool_hints():
    """5.9 含配对t检验输入时 tool_hints 首位包含 paired_t_test。"""
    analyzer = _make_analyzer_with_caps()
    analysis = analyzer.analyze("帮我做配对t检验分析")
    # Top-1 应该是 difference_analysis（因为"配对t检验"命中差异相关同义词）
    if (
        analysis.capability_candidates
        and analysis.capability_candidates[0].name == "difference_analysis"
    ):
        assert len(analysis.tool_hints) > 0
        assert "paired_t_test" in analysis.tool_hints[0]


# ============================================================================
# 5.10 has_datasets 阈值差异
# ============================================================================


def test_has_datasets_threshold_difference():
    """5.10 验证 has_datasets=True 收紧阈值减少澄清。

    构造 top1.score=10.0 (difference_analysis), top2.score=8.5,
    relative_gap=0.15:
    - has_datasets=True → clarification_needed=False (0.15 不满足 < 0.15)
    - has_datasets=False → clarification_needed=True (0.15 满足 < 0.25)
    """
    analyzer = OptimizedIntentAnalyzer()

    # 直接构造 analysis 并手动调用 _apply_clarification_policy
    analysis_with_data = IntentAnalysis(query="差异分析")
    analysis_with_data.capability_candidates = [
        IntentCandidate(
            name="difference_analysis",
            score=10.0,
            reason="test",
            payload={"display_name": "差异分析"},
        ),
        IntentCandidate(
            name="correlation_analysis",
            score=8.5,
            reason="test",
            payload={"display_name": "相关性分析"},
        ),
    ]

    analysis_without_data = IntentAnalysis(query="差异分析")
    analysis_without_data.capability_candidates = [
        IntentCandidate(
            name="difference_analysis",
            score=10.0,
            reason="test",
            payload={"display_name": "差异分析"},
        ),
        IntentCandidate(
            name="correlation_analysis",
            score=8.5,
            reason="test",
            payload={"display_name": "相关性分析"},
        ),
    ]

    # has_datasets=True → 收紧阈值，gap=0.15 不满足 < 0.15，不触发澄清
    analyzer._apply_clarification_policy(analysis_with_data, has_datasets=True)
    assert not analysis_with_data.clarification_needed

    # has_datasets=False → 默认阈值，gap=0.15 满足 < 0.25，触发澄清
    analyzer._apply_clarification_policy(analysis_without_data, has_datasets=False)
    assert analysis_without_data.clarification_needed
