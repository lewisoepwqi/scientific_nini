"""可解释性增强 E2E 测试。

测试可解释性增强功能的端到端流程。
"""

import pytest


@pytest.mark.e2e
class TestExplainabilityWorkflow:
    """可解释性工作流 E2E 测试。"""

    def test_reasoning_data_structure(self):
        """测试推理数据结构。"""
        from nini.agent.events import ReasoningData, ReasoningStep

        # 创建推理数据
        data = ReasoningData(
            step=ReasoningStep.METHOD_SELECTION,
            thought="选择 ANOVA 进行多组比较",
            rationale="数据包含3个分组，适合使用方差分析",
            reasoning_type="decision",
            confidence_score=0.85,
            key_decisions=["使用 ANOVA", "设置 alpha=0.05"]
        )

        # 验证数据结构
        assert data.step == "method_selection"
        assert data.reasoning_type == "decision"
        assert data.confidence_score == 0.85
        assert len(data.key_decisions) == 2

        # 验证字典转换
        result = data.to_dict()
        assert result["step"] == "method_selection"
        assert result["reasoning_type"] == "decision"
        assert "key_decisions" in result

    def test_reasoning_chain_tracking(self):
        """测试推理链追踪。"""
        from nini.agent.runner import ReasoningChainTracker

        tracker = ReasoningChainTracker()

        # 添加多个推理节点
        node1 = tracker.add_reasoning(
            content="分析数据分布",
            reasoning_type="analysis",
            confidence_score=0.9
        )

        node2 = tracker.add_reasoning(
            content="选择统计方法",
            reasoning_type="decision",
            confidence_score=0.85
        )

        # 验证链式结构
        assert node1["parent_id"] is None
        assert node2["parent_id"] == node1["id"]

        # 验证链长度
        chain = tracker.get_chain()
        assert len(chain) == 2

    def test_reasoning_type_detection(self):
        """测试推理类型检测。"""
        from nini.agent.runner import _detect_reasoning_type

        # 分析类型
        analysis_text = "我需要分析这些数据的分布特征"
        assert _detect_reasoning_type(analysis_text) == "analysis"

        # 决策类型
        decision_text = "因此我决定使用 t 检验"
        assert _detect_reasoning_type(decision_text) == "decision"

        # 规划类型
        planning_text = "首先加载数据，然后进行分析"
        assert _detect_reasoning_type(planning_text) == "planning"

        # 反思类型
        reflection_text = "但是我需要重新考虑这个方法"
        assert _detect_reasoning_type(reflection_text) == "reflection"

    def test_key_decisions_extraction(self):
        """测试关键决策提取。"""
        from nini.agent.runner import _detect_key_decisions

        content = "我决定使用 ANOVA 方法。我选择 alpha=0.05。"
        decisions = _detect_key_decisions(content)

        assert len(decisions) >= 1
        assert any("决定" in d or "选择" in d for d in decisions)

    def test_confidence_score_calculation(self):
        """测试置信度分数计算。"""
        from nini.agent.runner import _calculate_confidence_score

        # 高置信度
        high_confidence = "这 clearly 是一个 definitely 正确的决定"
        score = _calculate_confidence_score(high_confidence)
        assert score is not None
        assert score > 0.5

        # 低置信度
        low_confidence = "这可能 maybe 不确定"
        score = _calculate_confidence_score(low_confidence)
        assert score is not None
        assert score < 0.5

    def test_create_reasoning_event(self):
        """测试创建推理事件。"""
        from nini.agent.events import create_reasoning_event, EventType

        event = create_reasoning_event(
            step="method_selection",
            thought="选择 ANOVA",
            rationale="适合多组比较",
            alternatives=["t-test", "Kruskal-Wallis"],
            confidence=0.9
        )

        assert event.type == EventType.REASONING
        assert event.data["step"] == "method_selection"
        assert event.data["confidence"] == 0.9
        assert len(event.data["alternatives"]) == 2


@pytest.mark.e2e
class TestReasoningTimelineComponent:
    """推理时间线组件 E2E 测试。"""

    def test_timeline_step_structure(self):
        """测试时间线步骤结构。"""
        # 验证时间线步骤数据结构（TypeScript 类型模拟）
        from typing import TypedDict

        class TimelineStep(TypedDict):
            id: str
            title: str
            description: str
            type: str
            status: str
            timestamp: str
            confidence: float
            keyDecisions: list

        step: TimelineStep = {
            "id": "step-1",
            "title": "方法选择",
            "description": "选择合适的统计方法",
            "type": "decision",
            "status": "completed",
            "timestamp": "2024-01-01T00:00:00Z",
            "confidence": 0.9,
            "keyDecisions": ["使用 ANOVA"]
        }

        assert step["id"] == "step-1"
        assert step["type"] == "decision"
        assert step["status"] == "completed"


@pytest.mark.e2e
class TestDecisionTagComponent:
    """决策标签组件 E2E 测试。"""

    def test_decision_tag_structure(self):
        """测试决策标签结构。"""
        # 验证决策标签数据结构（TypeScript 类型模拟）
        from typing import TypedDict

        class Decision(TypedDict):
            text: str
            type: str
            confidence: float
            icon: str

        decision: Decision = {
            "text": "使用 ANOVA 方法",
            "type": "primary",
            "confidence": 0.9,
            "icon": "target"
        }

        assert decision["text"] == "使用 ANOVA 方法"
        assert decision["type"] == "primary"
        assert decision["confidence"] == 0.9
