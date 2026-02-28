"""差异分析 Capability 测试。"""

from __future__ import annotations

import pytest
import pandas as pd
import numpy as np

from nini.agent.session import Session
from nini.capabilities.implementations import DifferenceAnalysisCapability, DifferenceAnalysisResult


@pytest.fixture
def sample_data_session():
    """创建包含示例数据的会话。"""
    # 使用 numpy 创建随机数据
    np.random.seed(42)

    # 创建两组数据
    group_a = np.random.normal(100, 15, 30)
    group_b = np.random.normal(110, 15, 30)

    df = pd.DataFrame({
        'value': np.concatenate([group_a, group_b]),
        'group': ['A'] * 30 + ['B'] * 30
    })

    session = Session()
    session.datasets['test_data'] = df
    return session


@pytest.fixture
def capability():
    """创建差异分析能力实例。"""
    from nini.tools.registry import create_default_tool_registry
    registry = create_default_tool_registry()
    return DifferenceAnalysisCapability(registry=registry)


class TestDifferenceAnalysisCapability:
    """测试差异分析能力。"""

    @pytest.mark.asyncio
    async def test_basic_two_group_analysis(self, capability, sample_data_session):
        """测试基本的两组差异分析。"""
        result = await capability.execute(
            sample_data_session,
            dataset_name='test_data',
            value_column='value',
            group_column='group',
        )

        assert isinstance(result, DifferenceAnalysisResult)
        assert result.success
        assert result.n_groups == 2
        assert result.selected_method in ['t_test', 'mann_whitney']
        assert result.p_value is not None
        assert result.test_statistic is not None

    @pytest.mark.asyncio
    async def test_result_structure(self, capability, sample_data_session):
        """测试结果结构完整性。"""
        result = await capability.execute(
            sample_data_session,
            dataset_name='test_data',
            value_column='value',
            group_column='group',
        )

        # 验证所有必需字段
        assert result.success
        assert result.message
        assert result.n_groups > 0
        assert isinstance(result.group_sizes, dict)
        assert isinstance(result.group_means, dict)
        assert result.selected_method
        assert result.method_reason

        # 验证统计结果
        if result.p_value is not None:
            assert 0 <= result.p_value <= 1
        if result.effect_size is not None:
            assert isinstance(result.effect_size, (int, float))

    @pytest.mark.asyncio
    async def test_data_validation(self, capability, sample_data_session):
        """测试数据验证。"""
        # 测试不存在的数据集
        result = await capability.execute(
            sample_data_session,
            dataset_name='nonexistent',
            value_column='value',
        )
        assert not result.success
        assert '不存在' in result.message

        # 测试不存在的列
        result = await capability.execute(
            sample_data_session,
            dataset_name='test_data',
            value_column='nonexistent_column',
        )
        assert not result.success
        assert '不存在' in result.message

    @pytest.mark.asyncio
    async def test_method_selection(self, capability, sample_data_session):
        """测试方法选择逻辑。"""
        # 两组数据
        result = await capability.execute(
            sample_data_session,
            dataset_name='test_data',
            value_column='value',
            group_column='group',
            auto_select_method=True,
        )

        # 验证选择了合适的方法
        assert result.selected_method in ['t_test', 'mann_whitney', 'anova', 'kruskal_wallis']
        assert result.method_reason
        assert result.normality_tests
        assert result.equal_variance_test is not None

    def test_method_reason_generation(self, capability):
        """测试方法原因生成。"""
        reasons = [
            capability._get_method_reason('t_test', {}),
            capability._get_method_reason('mann_whitney', {}),
            capability._get_method_reason('anova', {}),
            capability._get_method_reason('kruskal_wallis', {}),
        ]

        for reason in reasons:
            assert isinstance(reason, str)
            assert len(reason) > 0

    def test_interpretation_generation(self, capability):
        """测试解释生成。"""
        result = DifferenceAnalysisResult(
            success=True,
            n_groups=2,
            selected_method='t_test',
            p_value=0.01,
            test_statistic=2.5,
            effect_size=0.6,
            effect_type='cohens_d',
            significant=True,
        )

        interpretation = capability._generate_interpretation(result)

        assert isinstance(interpretation, str)
        assert '分析方法' in interpretation
        assert '统计结果' in interpretation
        assert '结论' in interpretation
        assert 't_test' in interpretation or 't 检验' in interpretation

    def test_result_to_dict(self, capability):
        """测试结果转换为字典。"""
        result = DifferenceAnalysisResult(
            success=True,
            message='测试完成',
            n_groups=2,
            selected_method='t_test',
            p_value=0.05,
        )

        data = result.to_dict()

        assert data['success'] is True
        assert data['message'] == '测试完成'
        assert data['n_groups'] == 2
        assert data['selected_method'] == 't_test'
        assert data['p_value'] == 0.05
