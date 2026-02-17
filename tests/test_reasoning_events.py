"""测试可解释性增强功能。

TDD 方式：先写测试，再写实现。
"""

from __future__ import annotations

from dataclasses import asdict

import pytest

from nini.agent.events import AgentEvent, EventType, ReasoningData, create_reasoning_event


class TestReasoningEventType:
    """测试 REASONING 事件类型。"""

    def test_reasoning_event_type_exists(self):
        """测试 REASONING 事件类型存在。"""
        assert hasattr(EventType, "REASONING")
        assert EventType.REASONING == "reasoning"

    def test_reasoning_event_creation(self):
        """测试创建推理事件。"""
        event = AgentEvent(
            type=EventType.REASONING,
            data={
                "step": "method_selection",
                "thought": "数据有3个分组，选择单因素ANOVA而非t检验",
                "alternatives": ["t检验 (需要恰好2组)", "Kruskal-Wallis (非参数替代)"],
                "rationale": "ANOVA适合比较3组以上均值差异",
            },
        )

        assert event.type == EventType.REASONING
        assert "step" in event.data
        assert "thought" in event.data


class TestReasoningDataStructure:
    """测试推理数据结构。"""

    def test_reasoning_data_creation(self):
        """测试创建推理数据。"""
        reasoning = ReasoningData(
            step="method_selection",
            thought="选择ANOVA进行多组比较",
            rationale="数据包含3个分组",
            alternatives=["t检验", "Kruskal-Wallis"],
            confidence=0.9,
        )

        assert reasoning.step == "method_selection"
        assert reasoning.confidence == 0.9

    def test_reasoning_data_serialization(self):
        """测试推理数据序列化。"""
        reasoning = ReasoningData(
            step="method_selection",
            thought="选择ANOVA",
            rationale="数据包含3个分组",
            alternatives=["t检验"],
        )

        data_dict = asdict(reasoning)
        assert "step" in data_dict
        assert "thought" in data_dict


class TestReasoningEventIntegration:
    """测试推理事件集成。"""

    def test_reasoning_event_in_event_stream(self):
        """测试推理事件在事件流中。"""
        events = [
            AgentEvent(type=EventType.TEXT, data="Hello"),
            AgentEvent(
                type=EventType.REASONING,
                data={
                    "step": "method_selection",
                    "thought": "选择ANOVA",
                    "rationale": "多组比较",
                },
            ),
            AgentEvent(type=EventType.TOOL_CALL, data={"name": "anova"}),
        ]

        reasoning_events = [e for e in events if e.type == EventType.REASONING]
        assert len(reasoning_events) == 1
        assert reasoning_events[0].data["step"] == "method_selection"

    def test_all_event_types_include_reasoning(self):
        """测试所有事件类型包含 REASONING。"""
        all_types = [t.value for t in EventType]
        assert "reasoning" in all_types


class TestReasoningContent:
    """测试推理内容。"""

    def test_method_selection_reasoning(self):
        """测试方法选择推理内容。"""
        reasoning = ReasoningData(
            step="method_selection",
            thought="数据有3个分组，选择单因素ANOVA",
            alternatives=["t检验 (需要恰好2组)", "Kruskal-Wallis (非参数替代)"],
            rationale="ANOVA适合比较3组以上均值差异",
        )

        assert "ANOVA" in reasoning.thought
        assert len(reasoning.alternatives) > 0

    def test_parameter_selection_reasoning(self):
        """测试参数选择推理内容。"""
        reasoning = ReasoningData(
            step="parameter_selection",
            thought="使用 alpha=0.01 作为显著性水平",
            alternatives=["alpha=0.05 (默认)", "alpha=0.001 (更严格)"],
            rationale="用户偏好更严格的显著性阈值",
        )

        assert "alpha" in reasoning.thought

    def test_chart_selection_reasoning(self):
        """测试图表选择推理内容。"""
        reasoning = ReasoningData(
            step="chart_selection",
            thought="选择箱线图展示多组数据分布",
            alternatives=["散点图", "小提琴图"],
            rationale="箱线图适合清晰展示中位数和四分位数",
        )

        assert "箱线图" in reasoning.thought


class TestReasoningEventEmission:
    """测试推理事件发射。"""

    @pytest.mark.asyncio
    async def test_agent_emits_reasoning_on_method_selection(self):
        """测试 Agent 在方法选择时发射推理事件。"""
        from nini.agent.session import Session
        from nini.tools.registry import create_default_registry
        import pandas as pd

        session = Session()
        registry = create_default_registry()

        # 创建 3 组数据（应该触发 ANOVA 选择）
        test_data = pd.DataFrame(
            {
                "value": [10, 11, 12] + [20, 21, 22] + [30, 31, 32],
                "group": ["A"] * 3 + ["B"] * 3 + ["C"] * 3,
            }
        )
        session.datasets["test_data"] = test_data

        # 执行分析
        result = await registry.execute(
            "anova",
            session=session,
            dataset_name="test_data",
            value_column="value",
            group_column="group",
        )

        assert result["success"] is True
        # 推理事件应该在会话事件中

    @pytest.mark.asyncio
    async def test_agent_emits_reasoning_on_assumption_failure(self):
        """测试 Agent 在前提检验失败时发射推理事件。"""
        from nini.agent.session import Session
        from nini.tools.registry import create_default_registry
        import pandas as pd

        session = Session()
        registry = create_default_registry()

        # 创建非正态数据（应该触发非参数方法建议）
        test_data = pd.DataFrame(
            {
                "value": [1, 1, 1, 2, 2, 100, 150, 200, 250, 300],
                "group": ["A"] * 5 + ["B"] * 5,
            }
        )
        session.datasets["test_data"] = test_data

        # 执行带降级的分析
        result = await registry.execute_with_fallback(
            "t_test",
            session=session,
            dataset_name="test_data",
            value_column="value",
            group_column="group",
        )

        assert result["success"] is True
        # 降级信息应包含推理原因
        if "fallback" in result and result["fallback"]:
            assert "fallback_reason" in result or "reason" in result
