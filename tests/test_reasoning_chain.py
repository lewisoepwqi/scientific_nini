"""推理链链接测试。

测试推理链的父子关系链接和追踪功能。
"""

import pytest
from datetime import datetime, timezone

from nini.agent.runner import (
    ReasoningChainTracker,
    _detect_reasoning_type,
    _detect_key_decisions,
    _calculate_confidence_score,
)


class TestReasoningChainTracker:
    """推理链追踪器测试。"""

    def test_initial_state(self):
        """测试初始状态。"""
        tracker = ReasoningChainTracker()
        assert tracker.get_chain() == []
        assert tracker._current_parent_id is None

    def test_add_single_reasoning(self):
        """测试添加单个推理节点。"""
        tracker = ReasoningChainTracker()
        node = tracker.add_reasoning(
            content="选择t_test方法",
            reasoning_type="decision",
            key_decisions=["使用t_test"],
            confidence_score=0.85,
        )

        assert node["id"] == "reasoning_0"
        assert node["content"] == "选择t_test方法"
        assert node["reasoning_type"] == "decision"
        assert node["key_decisions"] == ["使用t_test"]
        assert node["confidence_score"] == 0.85
        assert node["parent_id"] is None
        assert "timestamp" in node

        chain = tracker.get_chain()
        assert len(chain) == 1
        assert chain[0]["id"] == "reasoning_0"

    def test_parent_child_relationship(self):
        """测试父子关系链接。"""
        tracker = ReasoningChainTracker()

        # 添加第一个节点（父节点）
        node1 = tracker.add_reasoning(content="第一步分析")
        assert node1["parent_id"] is None
        assert tracker._current_parent_id == "reasoning_0"

        # 添加第二个节点（子节点）
        node2 = tracker.add_reasoning(content="第二步决策")
        assert node2["parent_id"] == "reasoning_0"
        assert tracker._current_parent_id == "reasoning_1"

        # 添加第三个节点（孙子节点）
        node3 = tracker.add_reasoning(content="第三步执行")
        assert node3["parent_id"] == "reasoning_1"

    def test_chain_order(self):
        """测试链的顺序。"""
        tracker = ReasoningChainTracker()

        tracker.add_reasoning(content="第一步")
        tracker.add_reasoning(content="第二步")
        tracker.add_reasoning(content="第三步")

        chain = tracker.get_chain()
        assert len(chain) == 3
        assert chain[0]["id"] == "reasoning_0"
        assert chain[1]["id"] == "reasoning_1"
        assert chain[2]["id"] == "reasoning_2"

    def test_reset(self):
        """测试重置功能。"""
        tracker = ReasoningChainTracker()

        tracker.add_reasoning(content="第一步")
        tracker.add_reasoning(content="第二步")

        assert len(tracker.get_chain()) == 2
        assert tracker._current_parent_id is not None

        tracker.reset()

        assert tracker.get_chain() == []
        assert tracker._current_parent_id is None

    def test_chain_isolation(self):
        """测试链的隔离性（get_chain返回副本）。"""
        tracker = ReasoningChainTracker()
        tracker.add_reasoning(content="第一步")

        chain1 = tracker.get_chain()
        chain2 = tracker.get_chain()

        # 应该是不同的列表对象
        assert chain1 is not chain2

        # 修改chain1不应该影响tracker
        chain1.append({"id": "fake"})
        assert len(tracker.get_chain()) == 1


class TestDetectReasoningType:
    """推理类型检测测试。"""

    def test_detect_analysis_type(self):
        """检测分析类型。"""
        content = "我需要分析这些数据的分布情况，检查是否符合正态分布"
        result = _detect_reasoning_type(content)
        assert result == "analysis"

    def test_detect_decision_type(self):
        """检测决策类型。"""
        content = "因此我决定使用t检验来进行统计比较，选择这种方法"
        result = _detect_reasoning_type(content)
        assert result == "decision"

    def test_detect_planning_type(self):
        """检测规划类型。"""
        content = "首先加载数据，然后进行清洗，最后执行分析"
        result = _detect_reasoning_type(content)
        assert result == "planning"

    def test_detect_reflection_type(self):
        """检测反思类型。"""
        content = "但是这种方法可能不太适合，我需要重新考虑"
        result = _detect_reasoning_type(content)
        assert result == "reflection"

    def test_detect_english_analysis(self):
        """检测英文分析类型。"""
        content = "Let me analyze the data distribution and examine the patterns"
        result = _detect_reasoning_type(content)
        assert result == "analysis"

    def test_detect_english_decision(self):
        """检测英文决策类型。"""
        content = "Therefore I decide to choose the ANOVA method for this analysis"
        result = _detect_reasoning_type(content)
        assert result == "decision"

    def test_no_match_returns_none(self):
        """无匹配时返回None。"""
        content = "这是一段普通的描述文字"
        result = _detect_reasoning_type(content)
        assert result is None

    def test_priority_when_multiple_types(self):
        """多种类型同时存在时的优先级。"""
        # 应该返回得分最高的类型
        content = "我决定分析这些数据，首先检查分布，然后选择方法"
        result = _detect_reasoning_type(content)
        # analysis有2个关键词(分析,检查)，decision有1个(决定)
        assert result == "analysis"


class TestDetectKeyDecisions:
    """关键决策检测测试。"""

    def test_detect_single_decision(self):
        """检测单个决策。"""
        content = "基于以上分析，我决定使用t检验进行统计比较。"
        result = _detect_key_decisions(content)
        assert len(result) == 1
        assert "决定" in result[0]

    def test_detect_multiple_decisions(self):
        """检测多个决策。"""
        content = "我决定使用ANOVA方法。我还选择alpha=0.05作为显著性水平。"
        result = _detect_key_decisions(content)
        assert len(result) == 2

    def test_detect_english_decisions(self):
        """检测英文决策。"""
        content = "I decide to use the t-test method. I choose alpha=0.05."
        result = _detect_key_decisions(content)
        assert len(result) == 2

    def test_filter_short_sentences(self):
        """过滤过短的句子。"""
        content = "我决定。我选择。确定。"
        result = _detect_key_decisions(content)
        # "确定"太短（只有2个字符）应该被过滤
        assert len(result) <= 2

    def test_limit_to_top_3(self):
        """限制最多返回3个决策。"""
        content = "我决定使用方法A。我决定使用方法B。我选择方法C。我确定使用D。我采用方法E。"
        result = _detect_key_decisions(content)
        assert len(result) <= 3

    def test_no_decisions_returns_empty(self):
        """无决策时返回空列表。"""
        content = "这是一段普通的描述文字，没有任何决策关键词"
        result = _detect_key_decisions(content)
        assert result == []


class TestCalculateConfidenceScore:
    """置信度分数计算测试。"""

    def test_high_confidence_indicators(self):
        """高置信度指标。"""
        content = "这 clearly 是一个 definitely 正确的决定"
        result = _calculate_confidence_score(content)
        assert result is not None
        assert result > 0.5

    def test_low_confidence_indicators(self):
        """低置信度指标。"""
        content = "这可能 maybe 是一个不确定的决策"
        result = _calculate_confidence_score(content)
        assert result is not None
        assert result < 0.5

    def test_mixed_indicators(self):
        """混合指标。"""
        content = "这 clearly 可能 maybe 不确定"
        # 有高置信度也有低置信度
        result = _calculate_confidence_score(content)
        assert result is not None

    def test_no_indicators_returns_none(self):
        """无指标时返回None。"""
        content = "这是一段普通的描述"
        result = _calculate_confidence_score(content)
        assert result is None

    def test_score_clamped_to_valid_range(self):
        """分数限制在有效范围内[0, 1]。"""
        # 大量高置信度词汇
        content = "clearly definitely certainly obviously clearly definitely"
        result = _calculate_confidence_score(content)
        assert result is not None
        assert 0.0 <= result <= 1.0

        # 大量低置信度词汇
        content = "maybe probably possibly uncertain maybe probably"
        result = _calculate_confidence_score(content)
        assert result is not None
        assert 0.0 <= result <= 1.0


class TestReasoningChainIntegration:
    """推理链集成测试。"""

    def test_full_reasoning_flow(self):
        """测试完整推理流程。"""
        tracker = ReasoningChainTracker()

        # 模拟一个完整的分析流程
        # 1. 分析阶段
        content1 = "我需要分析这些数据的分布特征"
        node1 = tracker.add_reasoning(
            content=content1,
            reasoning_type=_detect_reasoning_type(content1),
            key_decisions=_detect_key_decisions(content1),
            confidence_score=_calculate_confidence_score(content1),
        )
        assert node1["reasoning_type"] == "analysis"

        # 2. 决策阶段
        content2 = "基于以上结果，我决定使用ANOVA方法进行比较，选择这种方法更合适"
        node2 = tracker.add_reasoning(
            content=content2,
            reasoning_type=_detect_reasoning_type(content2),
            key_decisions=_detect_key_decisions(content2),
            confidence_score=_calculate_confidence_score(content2),
        )
        # 注意：当多种类型关键词同时存在时，返回得分最高的
        assert node2["reasoning_type"] in ["decision", "analysis"]
        assert node2["parent_id"] == node1["id"]
        assert len(node2["key_decisions"]) > 0

        # 3. 反思阶段
        content3 = "但是，我需要重新考虑，数据可能不符合正态分布"
        node3 = tracker.add_reasoning(
            content=content3,
            reasoning_type=_detect_reasoning_type(content3),
            key_decisions=_detect_key_decisions(content3),
            confidence_score=_calculate_confidence_score(content3),
        )
        assert node3["reasoning_type"] == "reflection"
        assert node3["parent_id"] == node2["id"]

        # 验证完整链条
        chain = tracker.get_chain()
        assert len(chain) == 3

        # 验证链条连接关系
        assert chain[0]["parent_id"] is None
        assert chain[1]["parent_id"] == chain[0]["id"]
        assert chain[2]["parent_id"] == chain[1]["id"]
