"""统计模块拆分回归测试。"""

from __future__ import annotations

from nini.tools import _statistics_legacy
from nini.tools import statistics


def test_statistics_top_level_exports_use_split_modules() -> None:
    """顶层 statistics 导出应指向拆分后的独立模块。"""
    assert statistics.ANOVASkill.__module__ == "nini.tools.statistics.anova"
    assert statistics.CorrelationSkill.__module__ == "nini.tools.statistics.correlation"
    assert statistics.RegressionSkill.__module__ == "nini.tools.statistics.regression"
    assert statistics.MannWhitneySkill.__module__ == "nini.tools.statistics.nonparametric"
    assert statistics.KruskalWallisSkill.__module__ == "nini.tools.statistics.nonparametric"
    assert (
        statistics.MultipleComparisonCorrectionSkill.__module__
        == "nini.tools.statistics.multiple_comparison"
    )


def test_statistics_top_level_keeps_anova_monkeypatch_seams() -> None:
    """顶层 statistics 仍应暴露 ANOVA 测试所需的兼容钩子。"""
    assert callable(statistics.f_oneway)
    assert callable(statistics.pairwise_tukeyhsd)


def test_statistics_legacy_module_reexports_split_modules() -> None:
    """旧兼容模块应继续导出拆分后的实现。"""
    assert _statistics_legacy.ANOVASkill is statistics.ANOVASkill
    assert _statistics_legacy.CorrelationSkill is statistics.CorrelationSkill
    assert _statistics_legacy.RegressionSkill is statistics.RegressionSkill
    assert _statistics_legacy.MannWhitneySkill is statistics.MannWhitneySkill
