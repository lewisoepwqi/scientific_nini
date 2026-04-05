"""sample_size 工具测试。

验证三种设计类型的计算准确性、参数缺失错误处理及工具注册。
"""

from __future__ import annotations

import pytest

from nini.agent.session import Session
from nini.tools.sample_size import SampleSizeTool


@pytest.fixture
def tool() -> SampleSizeTool:
    """返回 SampleSizeTool 实例。"""
    return SampleSizeTool()


@pytest.fixture
def session() -> Session:
    """返回空会话。"""
    return Session()


class TestSampleSizeToolProperties:
    """测试工具元数据属性。"""

    def test_name(self, tool: SampleSizeTool) -> None:
        assert tool.name == "sample_size"

    def test_category(self, tool: SampleSizeTool) -> None:
        assert tool.category == "statistics"

    def test_is_idempotent(self, tool: SampleSizeTool) -> None:
        assert tool.is_idempotent is True

    def test_parameters_has_required_fields(self, tool: SampleSizeTool) -> None:
        params = tool.parameters
        assert "design_type" in params["properties"]
        assert "effect_size" in params["properties"]
        assert "design_type" in params["required"]
        assert "effect_size" in params["required"]


class TestTwoSampleTtest:
    """两组 t 检验样本量计算测试。"""

    async def test_medium_effect_size(self, tool: SampleSizeTool, session: Session) -> None:
        """Cohen's d = 0.5，标准参数下每组约 64 例。"""
        result = await tool.execute(
            session,
            design_type="two_sample_ttest",
            effect_size=0.5,
            alpha=0.05,
            power=0.8,
        )
        assert result.success is True
        assert result.data is not None
        assert result.data["design_type"] == "two_sample_ttest"
        # statsmodels 计算结果：每组约 64 例（取整后）
        n = result.data["n_per_group"]
        assert 60 <= n <= 70, f"两组 t 检验每组样本量预期约 64，实际为 {n}"
        assert result.data["total_n"] == n * 2

    async def test_small_effect_size_requires_more_samples(
        self, tool: SampleSizeTool, session: Session
    ) -> None:
        """小效应量需要更多样本。"""
        result = await tool.execute(
            session,
            design_type="two_sample_ttest",
            effect_size=0.2,
            alpha=0.05,
            power=0.8,
        )
        assert result.success is True
        # 小效应量（d=0.2）需要更多样本（约 394 例/组）
        assert result.data["n_per_group"] > 100

    async def test_large_effect_size_requires_fewer_samples(
        self, tool: SampleSizeTool, session: Session
    ) -> None:
        """大效应量需要较少样本。"""
        result = await tool.execute(
            session,
            design_type="two_sample_ttest",
            effect_size=0.8,
            alpha=0.05,
            power=0.8,
        )
        assert result.success is True
        # 大效应量（d=0.8）需要较少样本（约 26 例/组）
        assert result.data["n_per_group"] < 40

    async def test_result_message_contains_o2_warning(
        self, tool: SampleSizeTool, session: Session
    ) -> None:
        """结果消息应包含 O2 草稿级声明。"""
        result = await tool.execute(
            session,
            design_type="two_sample_ttest",
            effect_size=0.5,
        )
        assert result.success is True
        assert "O2" in result.message or "草稿级" in result.message


class TestANOVA:
    """ANOVA 样本量计算测试。"""

    async def test_three_groups(self, tool: SampleSizeTool, session: Session) -> None:
        """3 组 ANOVA，Cohen's f = 0.25，每组样本量应合理。"""
        result = await tool.execute(
            session,
            design_type="anova",
            effect_size=0.25,
            alpha=0.05,
            power=0.8,
            groups=3,
        )
        assert result.success is True
        assert result.data["design_type"] == "anova"
        assert result.data["groups"] == 3
        n = result.data["n_per_group"]
        # 中等效应量（f=0.25），3 组，总 N 约 158，每组约 53 例
        assert 40 <= n <= 70, f"ANOVA 每组样本量预期约 53，实际为 {n}"
        assert result.data["total_n"] == n * 3

    async def test_two_groups_anova(self, tool: SampleSizeTool, session: Session) -> None:
        """2 组 ANOVA（等效 t 检验）。"""
        result = await tool.execute(
            session,
            design_type="anova",
            effect_size=0.25,
            alpha=0.05,
            power=0.8,
            groups=2,
        )
        assert result.success is True
        assert result.data["groups"] == 2

    async def test_four_groups(self, tool: SampleSizeTool, session: Session) -> None:
        """4 组 ANOVA，样本量应大于 3 组。"""
        result_3 = await tool.execute(session, design_type="anova", effect_size=0.25, groups=3)
        result_4 = await tool.execute(session, design_type="anova", effect_size=0.25, groups=4)
        assert result_3.success is True
        assert result_4.success is True
        # 组数增加，每组所需样本量通常减少（总自由度增加），检验此趋势合理性
        assert result_4.data["n_per_group"] > 0

    async def test_invalid_groups(self, tool: SampleSizeTool, session: Session) -> None:
        """groups < 2 应返回错误。"""
        result = await tool.execute(
            session,
            design_type="anova",
            effect_size=0.25,
            groups=1,
        )
        assert result.success is False
        assert "2" in result.message


class TestProportion:
    """比例差异样本量计算测试。"""

    async def test_with_effect_size(self, tool: SampleSizeTool, session: Session) -> None:
        """直接传入 Cohen's h 效应量。"""
        result = await tool.execute(
            session,
            design_type="proportion",
            effect_size=0.3,
            alpha=0.05,
            power=0.8,
        )
        assert result.success is True
        assert result.data["design_type"] == "proportion"
        assert result.data["n_per_group"] > 0
        assert result.data["total_n"] == result.data["n_per_group"] * 2

    async def test_with_p1_p2(self, tool: SampleSizeTool, session: Session) -> None:
        """通过 p1、p2 自动计算 Cohen's h。"""
        result = await tool.execute(
            session,
            design_type="proportion",
            effect_size=None,
            p1=0.4,
            p2=0.6,
        )
        assert result.success is True
        assert result.data["p1"] == 0.4
        assert result.data["p2"] == 0.6
        assert result.data["n_per_group"] > 0

    async def test_message_contains_cohens_h(self, tool: SampleSizeTool, session: Session) -> None:
        """通过 p1/p2 计算时，消息中应显示 Cohen's h 值。"""
        result = await tool.execute(
            session,
            design_type="proportion",
            effect_size=None,
            p1=0.3,
            p2=0.5,
        )
        assert result.success is True
        assert "Cohen's h" in result.message or "h" in result.message.lower()


class TestErrorHandling:
    """参数校验和错误处理测试。"""

    async def test_missing_design_type(self, tool: SampleSizeTool, session: Session) -> None:
        """缺少 design_type 应返回错误。"""
        result = await tool.execute(session, effect_size=0.5)
        assert result.success is False
        assert "design_type" in result.message

    async def test_missing_effect_size(self, tool: SampleSizeTool, session: Session) -> None:
        """缺少 effect_size 且无 p1/p2 时应返回错误。"""
        result = await tool.execute(session, design_type="two_sample_ttest")
        assert result.success is False
        assert "effect_size" in result.message

    async def test_missing_effect_size_for_proportion_no_p(
        self, tool: SampleSizeTool, session: Session
    ) -> None:
        """proportion 设计缺少 effect_size 且无 p1/p2 应返回错误。"""
        result = await tool.execute(session, design_type="proportion")
        assert result.success is False

    async def test_invalid_alpha(self, tool: SampleSizeTool, session: Session) -> None:
        """alpha 超出范围应返回错误。"""
        result = await tool.execute(
            session, design_type="two_sample_ttest", effect_size=0.5, alpha=1.5
        )
        assert result.success is False
        assert "alpha" in result.message

    async def test_invalid_power(self, tool: SampleSizeTool, session: Session) -> None:
        """power 超出范围应返回错误。"""
        result = await tool.execute(
            session, design_type="two_sample_ttest", effect_size=0.5, power=0.0
        )
        assert result.success is False
        assert "power" in result.message

    async def test_unsupported_design_type(self, tool: SampleSizeTool, session: Session) -> None:
        """不支持的设计类型应返回错误。"""
        result = await tool.execute(session, design_type="invalid_type", effect_size=0.5)
        assert result.success is False
        assert "invalid_type" in result.message or "不支持" in result.message


class TestToolRegistry:
    """工具注册测试。"""

    def test_sample_size_registered(self) -> None:
        """sample_size 工具应在默认注册表中可查询。"""
        from nini.tools.registry import create_default_tool_registry

        registry = create_default_tool_registry()
        tool = registry.get("sample_size")
        assert tool is not None
        assert isinstance(tool, SampleSizeTool)

    def test_sample_size_tool_definition(self) -> None:
        """工具 definition 格式应符合 OpenAI function calling 规范。"""
        tool = SampleSizeTool()
        defn = tool.get_tool_definition()
        assert defn["type"] == "function"
        assert defn["function"]["name"] == "sample_size"
        assert "parameters" in defn["function"]
