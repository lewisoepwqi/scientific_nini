"""测试复合技能模板。

TDD 方式：先写测试，再写实现。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from nini.agent.session import Session
from nini.skills.base import SkillResult


class TestCompleteComparisonSkill:
    """测试完整两组比较分析技能。"""

    @pytest.mark.asyncio
    async def test_skill_execution_full_flow(self):
        """测试完整分析流程。"""
        from nini.skills.templates.complete_comparison import CompleteComparisonSkill

        skill = CompleteComparisonSkill()
        session = Session()

        # 创建测试数据
        test_data = pd.DataFrame({
            "value": [10.2, 11.5, 9.8, 10.5, 11.1, 20.1, 21.5, 19.8, 20.5, 21.2],
            "group": ["A"] * 5 + ["B"] * 5,
        })
        session.datasets["test_data"] = test_data

        # 执行
        result = await skill.execute(
            session,
            dataset_name="test_data",
            value_column="value",
            group_column="group",
        )

        assert isinstance(result, SkillResult)
        assert result.success is True
        assert result.data is not None

    @pytest.mark.asyncio
    async def test_skill_includes_data_quality_check(self):
        """测试技能包含数据质量检查。"""
        from nini.skills.templates.complete_comparison import CompleteComparisonSkill

        skill = CompleteComparisonSkill()
        session = Session()

        # 包含缺失值的数据
        test_data = pd.DataFrame({
            "value": [10.2, None, 9.8, 10.5, 11.1, 20.1, 21.5, None, 20.5, 21.2],
            "group": ["A"] * 5 + ["B"] * 5,
        })
        session.datasets["test_data"] = test_data

        result = await skill.execute(
            session,
            dataset_name="test_data",
            value_column="value",
            group_column="group",
        )

        # 应该包含数据质量报告
        assert "data_quality" in result.data or "quality" in str(result.data).lower()

    @pytest.mark.asyncio
    async def test_skill_performs_assumption_tests(self):
        """测试技能执行前提检验。"""
        from nini.skills.templates.complete_comparison import CompleteComparisonSkill

        skill = CompleteComparisonSkill()
        session = Session()

        test_data = pd.DataFrame({
            "value": [10.2, 11.5, 9.8, 10.5, 11.1, 20.1, 21.5, 19.8, 20.5, 21.2],
            "group": ["A"] * 5 + ["B"] * 5,
        })
        session.datasets["test_data"] = test_data

        result = await skill.execute(
            session,
            dataset_name="test_data",
            value_column="value",
            group_column="group",
        )

        # 应该包含前提检验结果
        assert "assumptions" in result.data or "normality" in str(result.data).lower()

    @pytest.mark.asyncio
    async def test_skill_calculates_effect_size(self):
        """测试技能计算效应量。"""
        from nini.skills.templates.complete_comparison import CompleteComparisonSkill

        skill = CompleteComparisonSkill()
        session = Session()

        test_data = pd.DataFrame({
            "value": [10.2, 11.5, 9.8, 10.5, 11.1, 20.1, 21.5, 19.8, 20.5, 21.2],
            "group": ["A"] * 5 + ["B"] * 5,
        })
        session.datasets["test_data"] = test_data

        result = await skill.execute(
            session,
            dataset_name="test_data",
            value_column="value",
            group_column="group",
        )

        # 应该包含 Cohen's d
        data = result.data
        if isinstance(data, dict):
            assert "cohens_d" in data or "effect_size" in str(data).lower()

    @pytest.mark.asyncio
    async def test_skill_generates_visualization(self):
        """测试技能生成可视化。"""
        from nini.skills.templates.complete_comparison import CompleteComparisonSkill

        skill = CompleteComparisonSkill()
        session = Session()

        test_data = pd.DataFrame({
            "value": [10.2, 11.5, 9.8, 10.5, 11.1, 20.1, 21.5, 19.8, 20.5, 21.2],
            "group": ["A"] * 5 + ["B"] * 5,
        })
        session.datasets["test_data"] = test_data

        result = await skill.execute(
            session,
            dataset_name="test_data",
            value_column="value",
            group_column="group",
        )

        # 应该生成图表
        assert result.has_chart is True
        assert result.chart_data is not None

    @pytest.mark.asyncio
    async def test_skill_generates_apa_report(self):
        """测试技能生成 APA 格式报告。"""
        from nini.skills.templates.complete_comparison import CompleteComparisonSkill

        skill = CompleteComparisonSkill()
        session = Session()

        test_data = pd.DataFrame({
            "value": [10.2, 11.5, 9.8, 10.5, 11.1, 20.1, 21.5, 19.8, 20.5, 21.2],
            "group": ["A"] * 5 + ["B"] * 5,
        })
        session.datasets["test_data"] = test_data

        result = await skill.execute(
            session,
            dataset_name="test_data",
            value_column="value",
            group_column="group",
        )

        # 应该包含报告文本
        assert result.message != ""
        data = result.data
        if isinstance(data, dict):
            assert "report" in data or "conclusion" in str(data).lower()

    @pytest.mark.asyncio
    async def test_skill_handles_non_normal_data(self):
        """测试技能处理非正态数据（自动降级到非参数检验）。"""
        from nini.skills.templates.complete_comparison import CompleteComparisonSkill

        skill = CompleteComparisonSkill()
        session = Session()

        # 明显偏态的数据
        test_data = pd.DataFrame({
            "value": [1, 1, 1, 2, 2, 100, 150, 200, 250, 300],
            "group": ["A"] * 5 + ["B"] * 5,
        })
        session.datasets["test_data"] = test_data

        result = await skill.execute(
            session,
            dataset_name="test_data",
            value_column="value",
            group_column="group",
        )

        assert result.success is True
        # 应该使用非参数方法
        data = result.data
        if isinstance(data, dict):
            test_result = data.get("test_result", {})
            test_type = test_result.get("test_type", "")
            # 如果前提检验显示使用非参数，则验证 test_type
            assumptions = data.get("assumptions", {})
            if assumptions.get("use_non_parametric"):
                assert "mann" in test_type.lower() or "whitney" in test_type.lower()

    @pytest.mark.asyncio
    async def test_skill_handles_missing_dataset(self):
        """测试技能处理缺失数据集。"""
        from nini.skills.templates.complete_comparison import CompleteComparisonSkill

        skill = CompleteComparisonSkill()
        session = Session()

        result = await skill.execute(
            session,
            dataset_name="nonexistent",
            value_column="value",
            group_column="group",
        )

        assert result.success is False
        assert "不存在" in result.message or "not found" in result.message.lower()


class TestCompleteANOVASkill:
    """测试完整 ANOVA 分析技能。"""

    @pytest.mark.asyncio
    async def test_skill_execution_three_groups(self):
        """测试三组比较分析。"""
        from nini.skills.templates.complete_anova import CompleteANOVASkill

        skill = CompleteANOVASkill()
        session = Session()

        # 三组数据
        test_data = pd.DataFrame({
            "value": [10, 11, 10, 12, 11, 20, 21, 20, 22, 21, 30, 31, 30, 32, 31],
            "group": ["A"] * 5 + ["B"] * 5 + ["C"] * 5,
        })
        session.datasets["test_data"] = test_data

        result = await skill.execute(
            session,
            dataset_name="test_data",
            value_column="value",
            group_column="group",
        )

        assert result.success is True
        data = result.data
        if isinstance(data, dict):
            assert "anova" in str(data).lower() or "f_statistic" in data

    @pytest.mark.asyncio
    async def test_skill_performs_post_hoc(self):
        """测试执行事后检验。"""
        from nini.skills.templates.complete_anova import CompleteANOVASkill

        skill = CompleteANOVASkill()
        session = Session()

        test_data = pd.DataFrame({
            "value": [10, 11, 10, 12, 11, 20, 21, 20, 22, 21, 30, 31, 30, 32, 31],
            "group": ["A"] * 5 + ["B"] * 5 + ["C"] * 5,
        })
        session.datasets["test_data"] = test_data

        result = await skill.execute(
            session,
            dataset_name="test_data",
            value_column="value",
            group_column="group",
        )

        # 当 ANOVA 显著时应该有事后检验
        data = result.data
        if isinstance(data, dict):
            assert "post_hoc" in data or "tukey" in str(data).lower()


class TestCorrelationAnalysisSkill:
    """测试相关性分析技能。"""

    @pytest.mark.asyncio
    async def test_skill_execution_multiple_variables(self):
        """测试多变量相关性分析。"""
        from nini.skills.templates.correlation_analysis import CorrelationAnalysisSkill

        skill = CorrelationAnalysisSkill()
        session = Session()

        # 多变量数据
        import numpy as np
        np.random.seed(42)
        test_data = pd.DataFrame({
            "var1": np.random.randn(20),
            "var2": np.random.randn(20) * 0.5 + np.random.randn(20) * 0.5,
            "var3": np.random.randn(20),
        })
        session.datasets["test_data"] = test_data

        result = await skill.execute(
            session,
            dataset_name="test_data",
            columns=["var1", "var2", "var3"],
            method="pearson",
        )

        assert result.success is True
        data = result.data
        if isinstance(data, dict):
            assert "correlation_matrix" in data or "correlation" in str(data).lower()

    @pytest.mark.asyncio
    async def test_skill_generates_heatmap(self):
        """测试生成相关矩阵热图。"""
        from nini.skills.templates.correlation_analysis import CorrelationAnalysisSkill

        skill = CorrelationAnalysisSkill()
        session = Session()

        import numpy as np
        np.random.seed(42)
        test_data = pd.DataFrame({
            "var1": np.random.randn(20),
            "var2": np.random.randn(20),
        })
        session.datasets["test_data"] = test_data

        result = await skill.execute(
            session,
            dataset_name="test_data",
            columns=["var1", "var2"],
            method="pearson",
        )

        # 应该生成图表
        assert result.has_chart is True

    @pytest.mark.asyncio
    async def test_supports_different_methods(self):
        """测试支持不同相关系数方法。"""
        from nini.skills.templates.correlation_analysis import CorrelationAnalysisSkill

        skill = CorrelationAnalysisSkill()
        session = Session()

        import numpy as np
        np.random.seed(42)
        test_data = pd.DataFrame({
            "var1": np.random.randn(20),
            "var2": np.random.randn(20),
        })
        session.datasets["test_data"] = test_data

        for method in ["pearson", "spearman", "kendall"]:
            result = await skill.execute(
                session,
                dataset_name="test_data",
                columns=["var1", "var2"],
                method=method,
            )
            assert result.success is True


class TestCompoundSkillRegistration:
    """测试复合技能注册。"""

    def test_compound_skills_registered(self):
        """测试复合技能正确注册。"""
        from nini.skills.registry import SkillRegistry

        registry = SkillRegistry()

        # 检查新技能是否可注册
        skill_names = registry.list_skills()

        # 注册后应该包含
        from nini.skills.templates.complete_comparison import CompleteComparisonSkill
        from nini.skills.templates.complete_anova import CompleteANOVASkill
        from nini.skills.templates.correlation_analysis import CorrelationAnalysisSkill

        registry.register(CompleteComparisonSkill())
        registry.register(CompleteANOVASkill())
        registry.register(CorrelationAnalysisSkill())

        updated_names = registry.list_skills()
        assert "complete_comparison" in updated_names
        assert "complete_anova" in updated_names
        assert "correlation_analysis" in updated_names

    def test_compound_skill_tool_definitions(self):
        """测试复合技能工具定义。"""
        from nini.skills.templates.complete_comparison import CompleteComparisonSkill
        from nini.skills.templates.complete_anova import CompleteANOVASkill
        from nini.skills.templates.correlation_analysis import CorrelationAnalysisSkill

        skills = [
            CompleteComparisonSkill(),
            CompleteANOVASkill(),
            CorrelationAnalysisSkill(),
        ]

        for skill in skills:
            tool_def = skill.get_tool_definition()
            assert tool_def["type"] == "function"
            assert "name" in tool_def["function"]
            assert "description" in tool_def["function"]
            assert "parameters" in tool_def["function"]

            # 描述应该清晰说明这是一站式分析
            desc = tool_def["function"]["description"].lower()
            assert "完整" in desc or "comprehensive" in desc or "分析" in desc
