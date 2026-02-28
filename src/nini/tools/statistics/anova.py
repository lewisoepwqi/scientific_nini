"""方差分析统计工具。"""

from __future__ import annotations

import logging
from importlib import import_module
from typing import Any

import numpy as np

from nini.agent.session import Session
from nini.tools.base import Skill, SkillResult
from nini.tools.statistics.base import (
    _ensure_finite,
    _get_df,
    _record_stat_result,
    _safe_float,
)
from nini.tools.statistics.multiple_comparison import (
    get_correction_recommendation_reason,
    recommend_correction_method,
)

logger = logging.getLogger(__name__)


class ANOVASkill(Skill):
    """执行单因素方差分析。"""

    @property
    def name(self) -> str:
        return "anova"

    @property
    def category(self) -> str:
        return "statistics"

    @property
    def expose_to_llm(self) -> bool:
        return True

    @property
    def description(self) -> str:
        return "执行单因素方差分析(ANOVA)，比较多个组的均值差异。当 p <= 0.05 且分组数 >= 3 时自动执行 Tukey HSD 事后检验。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "dataset_name": {"type": "string", "description": "数据集名称"},
                "value_column": {"type": "string", "description": "数值列名"},
                "group_column": {"type": "string", "description": "分组列名"},
            },
            "required": ["dataset_name", "value_column", "group_column"],
        }

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        name = kwargs["dataset_name"]
        value_col = kwargs["value_column"]
        group_col = kwargs["group_column"]

        df = _get_df(session, name)
        if df is None:
            return SkillResult(success=False, message=f"数据集 '{name}' 不存在")
        for col in (value_col, group_col):
            if col not in df.columns:
                return SkillResult(success=False, message=f"列 '{col}' 不存在")

        try:
            group_names = df[group_col].dropna().unique()
            groups = []
            valid_group_names = []
            for group_name in group_names:
                group_data = df[df[group_col] == group_name][value_col].dropna()
                if len(group_data) > 0:
                    groups.append(group_data)
                    valid_group_names.append(group_name)

            if len(groups) < 2:
                return SkillResult(
                    success=False,
                    message=(
                        f"ANOVA 至少需要 2 个分组，当前只有 {len(groups)} 个。"
                        "如只有 1 组请使用单样本 t 检验，如只有 2 组请使用 t_test 或 mann_whitney。"
                    ),
                )

            if len(groups) == 2:
                logger.info("检测到 2 个分组，建议使用 t_test 或 mann_whitney")

            statistics_exports = import_module("nini.tools.statistics")
            f_stat, pval = statistics_exports.f_oneway(*groups)
            is_significant = bool(pval <= 0.05)

            n_total = sum(len(group) for group in groups)
            n_groups = len(groups)
            grand_mean = np.concatenate(groups).mean()
            ss_between = sum(len(group) * (group.mean() - grand_mean) ** 2 for group in groups)
            ss_within = sum(((group - group.mean()) ** 2).sum() for group in groups)
            df_between = n_groups - 1
            df_within = n_total - n_groups
            eta_sq = ss_between / (ss_between + ss_within) if (ss_between + ss_within) > 0 else 0

            result: dict[str, Any] = {
                "f_statistic": _ensure_finite(f_stat, "F 统计量"),
                "p_value": _ensure_finite(pval, "p 值"),
                "df_between": df_between,
                "df_within": df_within,
                "eta_squared": _safe_float(eta_sq),
                "n_groups": n_groups,
                "group_sizes": {
                    str(group_name): len(group)
                    for group_name, group in zip(valid_group_names, groups)
                },
                "group_means": {
                    str(group_name): _safe_float(group.mean())
                    for group_name, group in zip(valid_group_names, groups)
                },
                "significant": is_significant,
            }

            if n_groups == 2:
                result["recommendation"] = (
                    "当前仅 2 个分组，通常优先使用 t_test（参数法）或 "
                    "mann_whitney（非参数法）。"
                )

            if pval <= 0.05 and n_groups >= 3:
                try:
                    clean_df = df[[value_col, group_col]].dropna()
                    tukey = statistics_exports.pairwise_tukeyhsd(
                        endog=clean_df[value_col],
                        groups=clean_df[group_col],
                        alpha=0.05,
                    )
                    post_hoc = []
                    idx = 0
                    total_groups = len(tukey.groupsunique)
                    for i in range(total_groups):
                        for j in range(i + 1, total_groups):
                            if idx < len(tukey.pvalues):
                                post_hoc.append(
                                    {
                                        "group1": str(tukey.groupsunique[i]),
                                        "group2": str(tukey.groupsunique[j]),
                                        "mean_diff": _safe_float(tukey.meandiffs[idx]),
                                        "p_value": _safe_float(tukey.pvalues[idx]),
                                        "significant": bool(tukey.reject[idx]),
                                    }
                                )
                            idx += 1
                    result["post_hoc"] = post_hoc
                except Exception as exc:
                    logger.warning("ANOVA 事后检验失败: %s", exc)

            if pval <= 0.05 and n_groups >= 3:
                n_comparisons = n_groups * (n_groups - 1) // 2
                recommended_method = recommend_correction_method(n_comparisons, "exploratory")
                result["post_hoc_recommendation"] = {
                    "triggered": True,
                    "n_comparisons": n_comparisons,
                    "recommended_method": recommended_method,
                    "reason": get_correction_recommendation_reason(
                        recommended_method, "exploratory"
                    ),
                }

            significance_text = "显著" if is_significant else "不显著"
            message = (
                f"ANOVA: F({df_between}, {df_within}) = {f_stat:.3f}, "
                f"p = {pval:.4f} ({significance_text}), η² = {eta_sq:.3f}"
            )
            _record_stat_result(
                session,
                name,
                test_name="ANOVA",
                message=message,
                test_statistic=_safe_float(f_stat),
                p_value=_safe_float(pval),
                degrees_of_freedom=df_between,
                effect_size=_safe_float(eta_sq),
                effect_type="eta_squared",
                significant=is_significant,
            )

            return SkillResult(success=True, data=result, message=message)
        except ValueError as exc:
            return SkillResult(success=False, message=str(exc))
