"""统计模块拆分回归测试。"""

from __future__ import annotations

from nini.tools import statistics


def test_statistics_top_level_exports_use_split_modules() -> None:
    """顶层 statistics 导出应指向拆分后的独立模块。"""
    assert statistics.ANOVATool.__module__ == "nini.tools.statistics.anova"
    assert statistics.CorrelationTool.__module__ == "nini.tools.statistics.correlation"
    assert statistics.RegressionTool.__module__ == "nini.tools.statistics.regression"
    assert statistics.MannWhitneyTool.__module__ == "nini.tools.statistics.nonparametric"
    assert statistics.KruskalWallisTool.__module__ == "nini.tools.statistics.nonparametric"
    assert (
        statistics.MultipleComparisonCorrectionTool.__module__
        == "nini.tools.statistics.multiple_comparison"
    )


def test_statistics_top_level_keeps_anova_monkeypatch_seams() -> None:
    """顶层 statistics 仍应暴露 ANOVA 测试所需的兼容钩子。"""
    assert callable(statistics.f_oneway)
    assert callable(statistics.pairwise_tukeyhsd)
