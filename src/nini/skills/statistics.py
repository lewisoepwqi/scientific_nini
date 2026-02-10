"""统计分析技能：t 检验、ANOVA、相关性、回归。

核心计算逻辑来自历史版本实现，现已封装为 Nini Skill 接口。
"""

from __future__ import annotations

import math
import warnings
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import (
    f_oneway,
    kendalltau,
    pearsonr,
    spearmanr,
    ttest_1samp,
    ttest_ind,
    ttest_rel,
)
from statsmodels.stats.multicomp import pairwise_tukeyhsd
import statsmodels.api as sm

from nini.agent.session import Session
from nini.skills.base import Skill, SkillResult

warnings.filterwarnings("ignore", category=RuntimeWarning)


# ---- 工具函数 ----


def _safe_float(value: float | None) -> float | None:
    if value is None:
        return None
    if not math.isfinite(value):
        return None
    return float(value)


def _ensure_finite(value: float, label: str) -> float:
    if value is None or not math.isfinite(value):
        raise ValueError(f"{label} 计算结果无效，请检查数据")
    return float(value)


def _get_df(session: Session, name: str) -> pd.DataFrame | None:
    """从会话中获取数据集。"""
    return session.datasets.get(name)


# ---- T 检验 ----


class TTestSkill(Skill):
    """执行 t 检验（独立样本/配对/单样本）。"""

    @property
    def name(self) -> str:
        return "t_test"

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
                    stat, pval = ttest_rel(g1, g2, alternative=alternative)
                else:
                    stat, pval = ttest_ind(g1, g2, alternative=alternative, equal_var=False)

                # Cohen's d
                mean_diff = g1.mean() - g2.mean()
                pooled_std = np.sqrt(
                    ((len(g1) - 1) * g1.var() + (len(g2) - 1) * g2.var())
                    / (len(g1) + len(g2) - 2)
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

            elif test_value is not None:
                # 单样本 t 检验
                data = df[value_col].dropna()
                if len(data) < 2:
                    return SkillResult(success=False, message="至少需要 2 个观测值")

                stat, pval = ttest_1samp(data, test_value, alternative=alternative)
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

            else:
                return SkillResult(
                    success=False,
                    message="请指定 group_column（两组比较）或 test_value（单样本检验）",
                )

            return SkillResult(success=True, data=result, message=msg)

        except ValueError as e:
            return SkillResult(success=False, message=str(e))


# ---- ANOVA ----


class ANOVASkill(Skill):
    """执行单因素方差分析。"""

    @property
    def name(self) -> str:
        return "anova"

    @property
    def description(self) -> str:
        return "执行单因素方差分析(ANOVA)，比较多个组的均值差异。当 p < 0.05 时自动执行 Tukey HSD 事后检验。"

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
            # 分组数据
            group_names = df[group_col].dropna().unique()
            groups = []
            for gn in group_names:
                gdata = df[df[group_col] == gn][value_col].dropna()
                if len(gdata) > 0:
                    groups.append(gdata)

            if len(groups) < 2:
                return SkillResult(success=False, message="至少需要 2 个分组")

            f_stat, pval = f_oneway(*groups)

            n_total = sum(len(g) for g in groups)
            k = len(groups)
            grand_mean = np.concatenate(groups).mean()
            ss_between = sum(len(g) * (g.mean() - grand_mean) ** 2 for g in groups)
            ss_within = sum(((g - g.mean()) ** 2).sum() for g in groups)
            df_between = k - 1
            df_within = n_total - k
            eta_sq = ss_between / (ss_between + ss_within) if (ss_between + ss_within) > 0 else 0

            result: dict[str, Any] = {
                "f_statistic": _ensure_finite(f_stat, "F 统计量"),
                "p_value": _ensure_finite(pval, "p 值"),
                "df_between": df_between,
                "df_within": df_within,
                "eta_squared": _safe_float(eta_sq),
                "n_groups": k,
                "group_sizes": {str(gn): len(g) for gn, g in zip(group_names, groups)},
                "group_means": {str(gn): _safe_float(g.mean()) for gn, g in zip(group_names, groups)},
                "significant": bool(pval < 0.05),
            }

            # 事后检验
            if pval < 0.05:
                try:
                    clean_df = df[[value_col, group_col]].dropna()
                    tukey = pairwise_tukeyhsd(
                        endog=clean_df[value_col],
                        groups=clean_df[group_col],
                        alpha=0.05,
                    )
                    post_hoc = []
                    n_groups = len(tukey.groupsunique)
                    idx = 0
                    for i in range(n_groups):
                        for j in range(i + 1, n_groups):
                            if idx < len(tukey.pvalues):
                                post_hoc.append({
                                    "group1": str(tukey.groupsunique[i]),
                                    "group2": str(tukey.groupsunique[j]),
                                    "mean_diff": _safe_float(tukey.meandiffs[idx]),
                                    "p_value": _safe_float(tukey.pvalues[idx]),
                                    "significant": bool(tukey.reject[idx]),
                                })
                            idx += 1
                    result["post_hoc"] = post_hoc
                except Exception:
                    pass

            sig = "显著" if pval < 0.05 else "不显著"
            msg = f"ANOVA: F({df_between}, {df_within}) = {f_stat:.3f}, p = {pval:.4f} ({sig}), η² = {eta_sq:.3f}"

            return SkillResult(success=True, data=result, message=msg)

        except ValueError as e:
            return SkillResult(success=False, message=str(e))


# ---- 相关性分析 ----


class CorrelationSkill(Skill):
    """计算变量间的相关性。"""

    @property
    def name(self) -> str:
        return "correlation"

    @property
    def description(self) -> str:
        return "计算多个数值列之间的相关性矩阵和 p 值矩阵。支持 Pearson、Spearman、Kendall 三种方法。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "dataset_name": {"type": "string", "description": "数据集名称"},
                "columns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要分析的列名列表（至少 2 列）",
                },
                "method": {
                    "type": "string",
                    "enum": ["pearson", "spearman", "kendall"],
                    "description": "相关系数类型",
                    "default": "pearson",
                },
            },
            "required": ["dataset_name", "columns"],
        }

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        name = kwargs["dataset_name"]
        columns = kwargs["columns"]
        method = kwargs.get("method", "pearson")

        df = _get_df(session, name)
        if df is None:
            return SkillResult(success=False, message=f"数据集 '{name}' 不存在")

        for col in columns:
            if col not in df.columns:
                return SkillResult(success=False, message=f"列 '{col}' 不存在")
            if not pd.api.types.is_numeric_dtype(df[col]):
                return SkillResult(success=False, message=f"列 '{col}' 不是数值类型")

        data = df[columns].dropna()
        if len(data) < 3:
            return SkillResult(success=False, message="至少需要 3 个完整观测值")

        corr_matrix = data.corr(method=method)

        # 计算 p 值矩阵
        pvalue_matrix: dict[str, dict[str, float]] = {}
        func_map = {"pearson": pearsonr, "spearman": spearmanr, "kendall": kendalltau}
        corr_func = func_map.get(method, pearsonr)

        for col1 in columns:
            pvalue_matrix[col1] = {}
            for col2 in columns:
                if col1 == col2:
                    pvalue_matrix[col1][col2] = 0.0
                else:
                    _, pval = corr_func(data[col1].values, data[col2].values)
                    pvalue_matrix[col1][col2] = _ensure_finite(pval, f"{col1}-{col2} p 值")

        result = {
            "method": method,
            "sample_size": len(data),
            "correlation_matrix": {
                col: {col2: _safe_float(corr_matrix.loc[col, col2]) for col2 in columns}
                for col in columns
            },
            "pvalue_matrix": pvalue_matrix,
        }

        return SkillResult(
            success=True,
            data=result,
            message=f"{method.title()} 相关性分析完成（{len(columns)} 个变量, n={len(data)}）",
        )


# ---- 线性回归 ----


class RegressionSkill(Skill):
    """执行线性回归分析。"""

    @property
    def name(self) -> str:
        return "regression"

    @property
    def description(self) -> str:
        return "执行线性回归分析，返回系数、R²、F 统计量等。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "dataset_name": {"type": "string", "description": "数据集名称"},
                "dependent_var": {"type": "string", "description": "因变量（Y）列名"},
                "independent_vars": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "自变量（X）列名列表",
                },
            },
            "required": ["dataset_name", "dependent_var", "independent_vars"],
        }

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        name = kwargs["dataset_name"]
        dep_var = kwargs["dependent_var"]
        indep_vars = kwargs["independent_vars"]

        df = _get_df(session, name)
        if df is None:
            return SkillResult(success=False, message=f"数据集 '{name}' 不存在")

        all_vars = [dep_var] + indep_vars
        for v in all_vars:
            if v not in df.columns:
                return SkillResult(success=False, message=f"列 '{v}' 不存在")

        data = df[all_vars].dropna()
        if len(data) < len(indep_vars) + 2:
            return SkillResult(success=False, message="数据量不足以进行回归分析")

        try:
            X = data[indep_vars]
            y = data[dep_var]
            X = sm.add_constant(X)
            model = sm.OLS(y, X).fit()

            coefficients = {}
            for var in model.params.index:
                coefficients[var] = {
                    "estimate": _ensure_finite(model.params[var], f"{var} 系数"),
                    "std_error": _safe_float(model.bse[var]),
                    "t_statistic": _safe_float(model.tvalues[var]),
                    "p_value": _safe_float(model.pvalues[var]),
                }

            result = {
                "r_squared": _ensure_finite(model.rsquared, "R²"),
                "adjusted_r_squared": _safe_float(model.rsquared_adj),
                "f_statistic": _safe_float(model.fvalue),
                "f_pvalue": _safe_float(model.f_pvalue),
                "n_observations": int(model.nobs),
                "coefficients": coefficients,
            }

            msg = (
                f"回归分析: R² = {model.rsquared:.4f}, "
                f"F = {model.fvalue:.3f}, p = {model.f_pvalue:.4f}"
            )
            return SkillResult(success=True, data=result, message=msg)

        except Exception as e:
            return SkillResult(success=False, message=f"回归分析失败: {e}")


# ---- 非参数检验 ----


class MannWhitneySkill(Skill):
    """执行 Mann-Whitney U 检验（两组独立样本的非参数检验）。"""

    @property
    def name(self) -> str:
        return "mann_whitney"

    @property
    def description(self) -> str:
        return (
            "执行 Mann-Whitney U 检验（Wilcoxon 秩和检验）。"
            "用于比较两组独立样本的分布差异，不需要正态性假设。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "dataset_name": {"type": "string", "description": "数据集名称"},
                "value_column": {"type": "string", "description": "数值列名"},
                "group_column": {"type": "string", "description": "分组列名"},
                "alternative": {
                    "type": "string",
                    "enum": ["two-sided", "less", "greater"],
                    "description": "备择假设方向",
                    "default": "two-sided",
                },
            },
            "required": ["dataset_name", "value_column", "group_column"],
        }

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        name = kwargs["dataset_name"]
        value_col = kwargs["value_column"]
        group_col = kwargs["group_column"]
        alternative = kwargs.get("alternative", "two-sided")

        df = _get_df(session, name)
        if df is None:
            return SkillResult(success=False, message=f"数据集 '{name}' 不存在")
        if value_col not in df.columns:
            return SkillResult(success=False, message=f"列 '{value_col}' 不存在")
        if group_col not in df.columns:
            return SkillResult(success=False, message=f"分组列 '{group_col}' 不存在")

        groups = df[group_col].dropna().unique()
        if len(groups) != 2:
            return SkillResult(
                success=False,
                message=f"Mann-Whitney U 检验要求恰好 2 个分组，当前有 {len(groups)} 个",
            )

        g1 = df[df[group_col] == groups[0]][value_col].dropna()
        g2 = df[df[group_col] == groups[1]][value_col].dropna()

        if len(g1) < 2 or len(g2) < 2:
            return SkillResult(success=False, message="每组至少需要 2 个观测值")

        try:
            stat, pval = stats.mannwhitneyu(
                g1, g2, alternative=alternative
            )

            # 计算效应量（r = Z / sqrt(N)）
            # 使用正态近似计算 Z
            n1, n2 = len(g1), len(g2)
            mean_u = n1 * n2 / 2
            sigma_u = (n1 * n2 * (n1 + n2 + 1) / 12) ** 0.5
            z_score = (stat - mean_u) / sigma_u if sigma_u > 0 else 0
            r_effect = abs(z_score) / (n1 + n2) ** 0.5

            result = {
                "test_type": "Mann-Whitney U 检验",
                "u_statistic": float(stat),
                "p_value": float(pval),
                "z_score": _safe_float(z_score),
                "effect_size_r": _safe_float(r_effect),
                "median1": float(g1.median()),
                "median2": float(g2.median()),
                "n1": len(g1),
                "n2": len(g2),
                "significant": bool(pval < 0.05),
            }

            sig = "显著" if pval < 0.05 else "不显著"
            msg = (
                f"Mann-Whitney U 检验: U = {stat:.0f}, "
                f"p = {pval:.4f} ({sig}), "
                f"r = {r_effect:.3f}"
            )

            return SkillResult(success=True, data=result, message=msg)

        except Exception as e:
            return SkillResult(success=False, message=f"Mann-Whitney U 检验失败: {e}")


class KruskalWallisSkill(Skill):
    """执行 Kruskal-Wallis H 检验（多组独立样本的非参数检验）。"""

    @property
    def name(self) -> str:
        return "kruskal_wallis"

    @property
    def description(self) -> str:
        return (
            "执行 Kruskal-Wallis H 检验。"
            "用于比较多组独立样本的分布差异，不需要正态性假设。"
        )

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
        if value_col not in df.columns:
            return SkillResult(success=False, message=f"列 '{value_col}' 不存在")
        if group_col not in df.columns:
            return SkillResult(success=False, message=f"分组列 '{group_col}' 不存在")

        groups = df[group_col].dropna().unique()
        if len(groups) < 2:
            return SkillResult(success=False, message="至少需要 2 个分组")

        group_data = []
        for group in groups:
            gdata = df[df[group_col] == group][value_col].dropna()
            if len(gdata) > 0:
                group_data.append(gdata)

        if len(group_data) < 2:
            return SkillResult(success=False, message="至少需要 2 个有效分组")

        try:
            h_stat, pval = stats.kruskal(*group_data)

            n_total = sum(len(g) for g in group_data)
            k = len(group_data)

            # 计算 eta squared（效应量）
            eta_squared = (h_stat - k + 1) / (n_total - k) if n_total > k else 0

            result = {
                "test_type": "Kruskal-Wallis H 检验",
                "h_statistic": float(h_stat),
                "p_value": float(pval),
                "df": k - 1,
                "eta_squared": _safe_float(eta_squared),
                "n_groups": k,
                "group_medians": {
                    str(name): float(data.median())
                    for name, data in zip(groups, group_data)
                },
                "significant": bool(pval < 0.05),
            }

            sig = "显著" if pval < 0.05 else "不显著"
            msg = (
                f"Kruskal-Wallis H 检验: H({k-1}) = {h_stat:.3f}, "
                f"p = {pval:.4f} ({sig}), η² = {eta_squared:.3f}"
            )

            return SkillResult(success=True, data=result, message=msg)

        except Exception as e:
            return SkillResult(success=False, message=f"Kruskal-Wallis H 检验失败: {e}")

