"""统计工具模块。"""

from __future__ import annotations

from scipy.stats import f_oneway
from statsmodels.stats.multicomp import pairwise_tukeyhsd

from nini.tools.statistics.anova import ANOVATool
from nini.tools.statistics.base import _ensure_finite, _get_df, _record_stat_result, _safe_float
from nini.tools.statistics.correlation import CorrelationTool
from nini.tools.statistics.multiple_comparison import (
    MultipleComparisonCorrectionTool,
    bonferroni_correction,
    fdr_correction,
    get_correction_recommendation_reason,
    holm_correction,
    multiple_comparison_correction,
    recommend_correction_method,
)
from nini.tools.statistics.nonparametric import KruskalWallisTool, MannWhitneyTool
from nini.tools.statistics.regression import RegressionTool
from nini.tools.statistics.t_test import TTestTool

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
    "TTestTool",
    "ANOVATool",
    "CorrelationTool",
    "RegressionTool",
    "MannWhitneyTool",
    "KruskalWallisTool",
    "MultipleComparisonCorrectionTool",
]
