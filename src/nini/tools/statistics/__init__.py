"""统计工具模块。"""

from __future__ import annotations

from scipy.stats import f_oneway
from statsmodels.stats.multicomp import pairwise_tukeyhsd

from nini.tools.statistics.anova import ANOVASkill
from nini.tools.statistics.base import _ensure_finite, _get_df, _record_stat_result, _safe_float
from nini.tools.statistics.correlation import CorrelationSkill
from nini.tools.statistics.multiple_comparison import (
    MultipleComparisonCorrectionSkill,
    bonferroni_correction,
    fdr_correction,
    get_correction_recommendation_reason,
    holm_correction,
    multiple_comparison_correction,
    recommend_correction_method,
)
from nini.tools.statistics.nonparametric import KruskalWallisSkill, MannWhitneySkill
from nini.tools.statistics.regression import RegressionSkill
from nini.tools.statistics.t_test import TTestSkill

__all__ = [
    "_safe_float",
    "_ensure_finite",
    "_get_df",
    "_record_stat_result",
    "bonferroni_correction",
    "holm_correction",
    "fdr_correction",
    "multiple_comparison_correction",
    "recommend_correction_method",
    "get_correction_recommendation_reason",
    "f_oneway",
    "pairwise_tukeyhsd",
    "TTestSkill",
    "ANOVASkill",
    "CorrelationSkill",
    "RegressionSkill",
    "MannWhitneySkill",
    "KruskalWallisSkill",
    "MultipleComparisonCorrectionSkill",
]
