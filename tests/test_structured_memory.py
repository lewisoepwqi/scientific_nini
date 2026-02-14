"""测试结构化记忆压缩功能。

TDD 方式：先写测试，再写实现。
"""

from __future__ import annotations

from dataclasses import asdict

import pytest

from nini.memory.compression import AnalysisMemory, Finding, StatisticResult, Decision


class TestFinding:
    """测试 Finding 数据类。"""

    def test_finding_creation(self):
        """测试创建发现记录。"""
        finding = Finding(
            category="statistical_significance",
            summary="两组间存在显著差异",
            detail="t(18) = 3.45, p = 0.003",
            confidence=0.95,
        )

        assert finding.category == "statistical_significance"
        assert finding.summary == "两组间存在显著差异"
        assert finding.confidence == 0.95

    def test_finding_serialization(self):
        """测试发现记录序列化。"""
        finding = Finding(
            category="effect_size",
            summary="大效应量",
            detail="Cohen's d = 1.2",
        )

        data = asdict(finding)
        assert "category" in data
        assert "summary" in data


class TestStatisticResult:
    """测试 StatisticResult 数据类。"""

    def test_statistic_result_creation(self):
        """测试创建统计结果。"""
        result = StatisticResult(
            test_name="独立样本 t 检验",
            test_statistic=3.45,
            p_value=0.003,
            degrees_of_freedom=18,
            effect_size=1.2,
            effect_type="cohens_d",
        )

        assert result.test_name == "独立样本 t 检验"
        assert result.p_value == 0.003

    def test_statistic_result_with_ci(self):
        """测试带置信区间的统计结果。"""
        result = StatisticResult(
            test_name="独立样本 t 检验",
            test_statistic=3.45,
            p_value=0.003,
            confidence_interval_lower=0.5,
            confidence_interval_upper=2.5,
            confidence_level=0.95,
        )

        assert result.confidence_interval_lower == 0.5
        assert result.confidence_interval_upper == 2.5


class TestDecision:
    """测试 Decision 数据类。"""

    def test_decision_creation(self):
        """测试创建决策记录。"""
        decision = Decision(
            decision_type="method_selection",
            chosen="ANOVA",
            alternatives=["t 检验", "Kruskal-Wallis"],
            rationale="数据包含 3 个分组",
            confidence=0.9,
        )

        assert decision.decision_type == "method_selection"
        assert decision.chosen == "ANOVA"
        assert len(decision.alternatives) == 2


class TestAnalysisMemory:
    """测试 AnalysisMemory 数据类。"""

    def test_memory_creation(self):
        """测试创建分析记忆。"""
        memory = AnalysisMemory(
            session_id="test_session",
            dataset_name="experiment_data",
        )

        assert memory.session_id == "test_session"
        assert memory.dataset_name == "experiment_data"

    def test_memory_add_finding(self):
        """测试添加发现。"""
        memory = AnalysisMemory(
            session_id="test_session",
            dataset_name="experiment_data",
        )

        finding = Finding(
            category="statistical_significance",
            summary="显著差异",
        )

        memory.add_finding(finding)

        assert len(memory.findings) == 1
        assert memory.findings[0].summary == "显著差异"

    def test_memory_add_statistic(self):
        """测试添加统计结果。"""
        memory = AnalysisMemory(
            session_id="test_session",
            dataset_name="experiment_data",
        )

        statistic = StatisticResult(
            test_name="t 检验",
            test_statistic=3.45,
            p_value=0.003,
        )

        memory.add_statistic(statistic)

        assert len(memory.statistics) == 1

    def test_memory_add_decision(self):
        """测试添加决策记录。"""
        memory = AnalysisMemory(
            session_id="test_session",
            dataset_name="experiment_data",
        )

        decision = Decision(
            decision_type="method_selection",
            chosen="ANOVA",
            rationale="多组比较",
        )

        memory.add_decision(decision)

        assert len(memory.decisions) == 1

    def test_memory_add_artifact(self):
        """测试添加产出文件。"""
        memory = AnalysisMemory(
            session_id="test_session",
            dataset_name="experiment_data",
        )

        memory.add_artifact(
            artifact_type="chart",
            path="/path/to/chart.png",
            description="箱线图",
        )

        assert len(memory.artifacts) == 1

    def test_memory_to_context(self):
        """测试转换为可注入的上下文。"""
        memory = AnalysisMemory(
            session_id="test_session",
            dataset_name="experiment_data",
        )

        # 添加一些数据
        memory.add_finding(
            Finding(
                category="statistical_significance",
                summary="显著差异",
                detail="p < 0.05",
            )
        )

        memory.add_statistic(
            StatisticResult(
                test_name="t 检验",
                test_statistic=3.45,
                p_value=0.003,
            )
        )

        context = memory.to_context()

        assert "findings" in context
        assert "statistics" in context
        # 验证数据内容
        assert context["findings"][0]["summary"] == "显著差异"
        assert context["findings"][0]["detail"] == "p < 0.05"

    def test_memory_summary(self):
        """测试生成摘要。"""
        memory = AnalysisMemory(
            session_id="test_session",
            dataset_name="experiment_data",
        )

        memory.add_finding(
            Finding(
                category="statistical_significance",
                summary="显著差异",
            )
        )

        summary = memory.summary()

        assert summary is not None
        assert len(summary) > 0

    def test_memory_to_dict(self):
        """测试转换为字典。"""
        memory = AnalysisMemory(
            session_id="test_session",
            dataset_name="experiment_data",
        )

        memory.add_finding(
            Finding(
                category="statistical_significance",
                summary="显著差异",
            )
        )

        data = memory.to_dict()

        assert "session_id" in data
        assert "findings" in data


class TestMemoryCategories:
    """测试记忆分类。"""

    def test_finding_categories(self):
        """测试发现分类。"""
        valid_categories = [
            "statistical_significance",
            "effect_size",
            "assumption_violation",
            "data_quality_issue",
            "pattern",
        ]

        for category in valid_categories:
            finding = Finding(
                category=category,
                summary="测试",
            )
            assert finding.category == category

    def test_decision_types(self):
        """测试决策类型。"""
        valid_types = [
            "method_selection",
            "parameter_selection",
            "assumption_check",
            "fallback_decision",
            "chart_selection",
        ]

        for decision_type in valid_types:
            decision = Decision(
                decision_type=decision_type,
                chosen="test",
                rationale="测试",
            )
            assert decision.decision_type == decision_type


class TestMemoryIntegration:
    """测试记忆集成。"""

    def test_memory_from_analysis_result(self):
        """测试从分析结果创建记忆。"""
        # 模拟分析结果
        analysis_result = {
            "test_type": "独立样本 t 检验",
            "t_statistic": 3.45,
            "p_value": 0.003,
            "significant": True,
        }

        memory = AnalysisMemory(
            session_id="test_session",
            dataset_name="experiment_data",
        )

        # 添加统计结果
        memory.add_statistic(
            StatisticResult(
                test_name=analysis_result["test_type"],
                test_statistic=analysis_result["t_statistic"],
                p_value=analysis_result["p_value"],
            )
        )

        # 添加发现
        if analysis_result["significant"]:
            memory.add_finding(
                Finding(
                    category="statistical_significance",
                    summary="结果显示显著差异",
                    detail=f"p = {analysis_result['p_value']}",
                )
            )

        assert len(memory.statistics) == 1
        assert len(memory.findings) == 1

    def test_memory_context_injection(self):
        """测试记忆上下文注入。"""
        memory = AnalysisMemory(
            session_id="test_session",
            dataset_name="experiment_data",
        )

        # 添加完整的分析记录
        memory.add_decision(
            Decision(
                decision_type="method_selection",
                chosen="t 检验",
                alternatives=["ANOVA", "Mann-Whitney"],
                rationale="两组比较，数据符合正态性",
            )
        )

        memory.add_statistic(
            StatisticResult(
                test_name="独立样本 t 检验",
                test_statistic=3.45,
                p_value=0.003,
                degrees_of_freedom=18,
            )
        )

        memory.add_finding(
            Finding(
                category="statistical_significance",
                summary="组间存在显著差异",
                detail="t(18) = 3.45, p = 0.003",
                confidence=0.95,
            )
        )

        # 转换为上下文
        context = memory.to_context()

        # 验证上下文包含关键信息
        assert len(context["decisions"]) > 0
        assert len(context["statistics"]) > 0
        assert context["decisions"][0]["chosen"] == "t 检验"
        assert context["statistics"][0]["p_value"] == 0.003
