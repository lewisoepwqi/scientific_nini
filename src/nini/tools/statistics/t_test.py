"""T检验工具模块。"""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy import stats
from scipy.stats import ttest_1samp, ttest_ind, ttest_rel

from nini.agent.session import Session
from nini.tools.base import Skill, SkillResult
from nini.tools.statistics.base import (
    _ensure_finite,
    _get_df,
    _record_stat_result,
    _safe_float,
)


class TTestSkill(Skill):
    """执行 t 检验（独立样本/配对/单样本）。"""

    @property
    def name(self) -> str:
        return "t_test"

    @property
    def category(self) -> str:
        return "statistics"

    @property
    def expose_to_llm(self) -> bool:
        return True

    @property
    def description(self) -> str:
        return (
            "执行 t 检验。支持三种模式：\n"
            "1. 独立样本 t 检验：指定 value_column 和 group_column\n"
            "2. 配对样本 t 检验：指定 value_column 和 group_column，设置 paired=true\n"
            "3. 单样本 t 检验：指定 value_column 和 test_value"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "dataset_name": {"type": "string", "description": "数据集名称"},
                "value_column": {"type": "string", "description": "数值列名"},
                "group_column": {
                    "type": "string",
                    "description": "分组列名（独立样本/配对检验时使用）",
                },
                "test_value": {
                    "type": "number",
                    "description": "检验值（单样本 t 检验时使用）",
                },
                "paired": {
                    "type": "boolean",
                    "description": "是否为配对检验",
                    "default": False,
                },
                "alternative": {
                    "type": "string",
                    "enum": ["two-sided", "less", "greater"],
                    "description": "备择假设方向",
                    "default": "two-sided",
                },
            },
            "required": ["dataset_name", "value_column"],
        }

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        name = kwargs["dataset_name"]
        value_col = kwargs["value_column"]
        group_col = kwargs.get("group_column")
        test_value = kwargs.get("test_value")
        paired = kwargs.get("paired", False)
        alternative = kwargs.get("alternative", "two-sided")

        df = _get_df(session, name)
        if df is None:
            return SkillResult(success=False, message=f"数据集 '{name}' 不存在")
        if value_col not in df.columns:
            return SkillResult(success=False, message=f"列 '{value_col}' 不存在")

        try:
            if group_col:
                # 独立/配对样本 t 检验
                if group_col not in df.columns:
                    return SkillResult(success=False, message=f"分组列 '{group_col}' 不存在")

                groups = df[group_col].dropna().unique()
                if len(groups) != 2:
                    return SkillResult(
                        success=False,
                        message=f"t 检验要求恰好 2 个分组，但 '{group_col}' 有 {len(groups)} 个。如需多组比较请使用 ANOVA。",
                    )

                g1 = df[df[group_col] == groups[0]][value_col].dropna()
                g2 = df[df[group_col] == groups[1]][value_col].dropna()

                if len(g1) < 2 or len(g2) < 2:
                    return SkillResult(success=False, message="每组至少需要 2 个观测值")

                if paired:
                    if len(g1) != len(g2):
                        return SkillResult(success=False, message="配对检验要求两组样本量相等")
                    stat_raw, pval_raw = ttest_rel(g1, g2, alternative=alternative)
                else:
                    stat_raw, pval_raw = ttest_ind(g1, g2, alternative=alternative, equal_var=False)
                stat = float(stat_raw)  # type: ignore[arg-type]
                pval = float(pval_raw)  # type: ignore[arg-type]

                # Cohen's d
                mean_diff = g1.mean() - g2.mean()
                pooled_std = np.sqrt(
                    ((len(g1) - 1) * g1.var() + (len(g2) - 1) * g2.var()) / (len(g1) + len(g2) - 2)
                )
                cohens_d = mean_diff / pooled_std if pooled_std > 0 else 0

                # 置信区间
                se = np.sqrt(g1.var() / len(g1) + g2.var() / len(g2))
                df_degrees = len(g1) + len(g2) - 2
                t_crit = stats.t.ppf(0.975, df_degrees)

                result = {
                    "test_type": "配对样本 t 检验" if paired else "独立样本 t 检验",
                    "group1": str(groups[0]),
                    "group2": str(groups[1]),
                    "n1": len(g1),
                    "n2": len(g2),
                    "mean1": _safe_float(g1.mean()),
                    "mean2": _safe_float(g2.mean()),
                    "t_statistic": _ensure_finite(stat, "t 统计量"),
                    "p_value": _ensure_finite(pval, "p 值"),
                    "df": _ensure_finite(df_degrees, "自由度"),
                    "mean_difference": _safe_float(mean_diff),
                    "cohens_d": _safe_float(cohens_d),
                    "ci_lower": _safe_float(mean_diff - t_crit * se),
                    "ci_upper": _safe_float(mean_diff + t_crit * se),
                    "significant": bool(pval < 0.05),
                }

                sig = "显著" if pval < 0.05 else "不显著"
                msg = (
                    f"{'配对' if paired else '独立'}样本 t 检验结果: "
                    f"t({df_degrees:.0f}) = {stat:.3f}, p = {pval:.4f} ({sig}), "
                    f"Cohen's d = {cohens_d:.3f}"
                )
                _record_stat_result(
                    session,
                    name,
                    test_name=str(result["test_type"]),
                    message=msg,
                    test_statistic=stat,
                    p_value=pval,
                    degrees_of_freedom=int(df_degrees),
                    effect_size=_safe_float(cohens_d),
                    effect_type="cohens_d",
                    significant=bool(pval < 0.05),
                )

            elif test_value is not None:
                # 单样本 t 检验
                data = df[value_col].dropna()
                if len(data) < 2:
                    return SkillResult(success=False, message="至少需要 2 个观测值")

                stat_raw, pval_raw = ttest_1samp(data, test_value, alternative=alternative)
                stat = float(stat_raw)  # type: ignore[arg-type]
                pval = float(pval_raw)  # type: ignore[arg-type]
                mean = data.mean()
                se = data.std() / np.sqrt(len(data))
                df_degrees = len(data) - 1
                t_crit = stats.t.ppf(0.975, df_degrees)

                result = {
                    "test_type": "单样本 t 检验",
                    "n": len(data),
                    "mean": _safe_float(mean),
                    "test_value": test_value,
                    "t_statistic": _ensure_finite(stat, "t 统计量"),
                    "p_value": _ensure_finite(pval, "p 值"),
                    "df": _ensure_finite(df_degrees, "自由度"),
                    "ci_lower": _safe_float(mean - t_crit * se),
                    "ci_upper": _safe_float(mean + t_crit * se),
                    "significant": bool(pval < 0.05),
                }

                sig = "显著" if pval < 0.05 else "不显著"
                msg = f"单样本 t 检验: t({df_degrees}) = {stat:.3f}, p = {pval:.4f} ({sig})"
                _record_stat_result(
                    session,
                    name,
                    test_name="单样本 t 检验",
                    message=msg,
                    test_statistic=stat,
                    p_value=pval,
                    degrees_of_freedom=int(df_degrees),
                    significant=bool(pval < 0.05),
                )

            else:
                return SkillResult(
                    success=False,
                    message="请指定 group_column（两组比较）或 test_value（单样本检验）",
                )

            return SkillResult(success=True, data=result, message=msg)

        except ValueError as e:
            return SkillResult(success=False, message=str(e))
