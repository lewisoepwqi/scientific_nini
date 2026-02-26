"""统计分析技能：t 检验、ANOVA、相关性、回归。

核心计算逻辑来自历史版本实现，现已封装为 Nini Skill 接口。
"""

from __future__ import annotations

import logging
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
from nini.memory.compression import StatisticResult, get_analysis_memory
from nini.tools.base import Skill, SkillResult

logger = logging.getLogger(__name__)

# ---- 多重比较校正 ----


def bonferroni_correction(p_values: list[float], alpha: float = 0.05) -> dict[str, Any]:
    """Bonferroni 校正：最保守的方法，控制族错误率。

    Args:
        p_values: p 值列表
        alpha: 显著性水平

    Returns:
        包含校正后 p 值和显著性判断的字典
    """
    n = len(p_values)
    if n == 0:
        return {"method": "Bonferroni", "corrected_pvalues": [], "significant": []}

    # Bonferroni: p_corrected = p * n
    corrected = [min(p * n, 1.0) for p in p_values]
    # 使用校正后的 p 值与 alpha 比较判断显著性
    significant = [p < alpha for p in corrected]

    return {
        "method": "Bonferroni",
        "alpha": alpha,
        "n_comparisons": n,
        "original_pvalues": p_values,
        "corrected_pvalues": corrected,
        "significant": significant,
        "description": "最保守的方法，将 alpha 除以比较次数",
    }


def holm_correction(p_values: list[float], alpha: float = 0.05) -> dict[str, Any]:
    """Holm-Bonferroni 校正：逐步校正方法，比 Bonferroni 更有统计效能。

    Args:
        p_values: p 值列表
        alpha: 显著性水平

    Returns:
        包含校正后 p 值和显著性判断的字典
    """
    n = len(p_values)
    if n == 0:
        return {"method": "Holm", "corrected_pvalues": [], "significant": []}

    # 保存原始索引
    indexed_pvalues = [(i, p) for i, p in enumerate(p_values)]
    # 按 p 值升序排序
    indexed_pvalues.sort(key=lambda x: x[1])

    corrected = [0.0] * n

    # Holm 校正：
    # 1. 按 p 值从小到大排序
    # 2. 对每个 p_i，计算 p_corrected = p_i * (n - i)，其中 i 是排序后的索引（从0开始）
    # 3. 确保单调性（校正后 p 值不递减）

    # 第一轮：计算原始校正后 p 值
    temp_corrected = []
    for rank, (orig_i, p) in enumerate(indexed_pvalues):
        multiplier = n - rank
        corrected_p = min(p * multiplier, 1.0)
        temp_corrected.append((orig_i, corrected_p))

    # 第二轮：确保单调性（从大到小，确保不递减）
    # 从最大的 p 值开始，确保每个校正后 p 值不小于后面的
    for i in range(len(temp_corrected) - 2, -1, -1):
        orig_i, p_corr = temp_corrected[i]
        next_p = temp_corrected[i + 1][1]
        if p_corr < next_p:
            temp_corrected[i] = (orig_i, next_p)

    # 填充结果
    for orig_i, p_corr in temp_corrected:
        corrected[orig_i] = p_corr

    significant = [p < alpha for p in corrected]

    return {
        "method": "Holm",
        "alpha": alpha,
        "n_comparisons": n,
        "original_pvalues": p_values,
        "corrected_pvalues": corrected,
        "significant": significant,
        "description": "逐步校正方法，比 Bonferroni 更有统计效能",
    }


def fdr_correction(p_values: list[float], alpha: float = 0.05) -> dict[str, Any]:
    """FDR (False Discovery Rate) 校正：Benjamini-Hochberg 方法。

    控制假发现率，适用于探索性分析。

    Args:
        p_values: p 值列表
        alpha: 显著性水平

    Returns:
        包含校正后 p 值和显著性判断的字典
    """
    n = len(p_values)
    if n == 0:
        return {"method": "FDR (Benjamini-Hochberg)", "corrected_pvalues": [], "significant": []}

    # 保存原始索引
    indexed_pvalues = [(i, p) for i, p in enumerate(p_values)]
    # 按 p 值升序排序
    indexed_pvalues.sort(key=lambda x: x[1])

    # 第一轮：计算原始校正后 p 值
    temp_corrected = []
    for rank, (orig_i, p) in enumerate(indexed_pvalues, 1):
        corrected_p = min(p * n / rank, 1.0)
        temp_corrected.append((orig_i, corrected_p))

    # 第二轮：确保单调性（从大到小，确保不递减）
    corrected = [0.0] * n
    min_p = temp_corrected[-1][1] if temp_corrected else 1.0
    for i in range(len(temp_corrected) - 1, -1, -1):
        orig_i, p_corr = temp_corrected[i]
        min_p = min(min_p, p_corr)
        corrected[orig_i] = min_p

    significant = [p < alpha for p in corrected]

    return {
        "method": "FDR (Benjamini-Hochberg)",
        "alpha": alpha,
        "n_comparisons": n,
        "original_pvalues": p_values,
        "corrected_pvalues": corrected,
        "significant": significant,
        "description": "控制假发现率，适用于探索性分析",
    }


def multiple_comparison_correction(
    p_values: list[float],
    method: str = "bonferroni",
    alpha: float = 0.05,
) -> dict[str, Any]:
    """多重比较校正的主函数。

    Args:
        p_values: p 值列表
        method: 校正方法 ("bonferroni", "holm", "fdr")
        alpha: 显著性水平

    Returns:
        校正结果字典
    """
    method = method.lower()

    if method == "bonferroni":
        return bonferroni_correction(p_values, alpha)
    elif method in ["holm", "holm-bonferroni"]:
        return holm_correction(p_values, alpha)
    elif method in ["fdr", "bh", "benjamini-hochberg"]:
        return fdr_correction(p_values, alpha)
    else:
        raise ValueError(f"不支持的校正方法: {method}")


def recommend_correction_method(n_comparisons: int, context: str = "exploratory") -> str:
    """推荐多重比较校正方法。

    Args:
        n_comparisons: 比较次数
        context: 使用场景 ("exploratory", "confirmatory", "high_stakes")

    Returns:
        推荐的方法名称
    """
    if n_comparisons <= 1:
        return "none"

    if context == "high_stakes":
        # 高风险场景（如药物临床试验）：使用最严格的 Bonferroni
        return "bonferroni"
    elif context == "confirmatory":
        # 验证性研究：使用 Holm 方法，平衡效能和错误控制
        return "holm"
    else:
        # 探索性分析：使用 FDR，更有统计效能
        if n_comparisons > 10:
            return "fdr"
        else:
            return "holm"


def get_correction_recommendation_reason(method: str, context: str = "exploratory") -> str:
    """获取多重比较校正方法推荐理由。"""
    reasons = {
        ("bonferroni", "high_stakes"): "高风险场景（如临床试验）应使用最严格的 Bonferroni 校正",
        ("bonferroni", "confirmatory"): "验证性研究建议使用 Bonferroni 或 Holm 方法",
        ("holm", "confirmatory"): "Holm 方法在控制族错误率的同时提供更高的统计效能",
        ("fdr", "exploratory"): "探索性分析建议使用 FDR 控制，以发现更多潜在关联",
        ("holm", "exploratory"): "比较次数较少时，Holm 方法是 FDR 的良好替代",
        ("none", "exploratory"): "单次比较不需要多重校正",
    }
    return reasons.get((method, context), f"基于 {context} 场景推荐 {method} 方法")


warnings.filterwarnings("ignore", category=RuntimeWarning)


# ---- 工具函数 ----


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    fval = float(value)  # type: ignore[arg-type]
    if not math.isfinite(fval):
        return None
    return fval


def _ensure_finite(value: object, label: str) -> float:
    if value is None:
        raise ValueError(f"{label} 计算结果无效，请检查数据")
    fval = float(value)  # type: ignore[arg-type]
    if not math.isfinite(fval):
        raise ValueError(f"{label} 计算结果无效，请检查数据")
    return fval


def _get_df(session: Session, name: str) -> pd.DataFrame | None:
    """从会话中获取数据集。"""
    return session.datasets.get(name)


def _record_stat_result(
    session: Session,
    dataset_name: str,
    *,
    test_name: str,
    message: str,
    test_statistic: float | None = None,
    p_value: float | None = None,
    degrees_of_freedom: int | None = None,
    effect_size: float | None = None,
    effect_type: str = "",
    significant: bool = False,
) -> None:
    """将统计结果记录到 AnalysisMemory 和 KnowledgeMemory。"""
    # AnalysisMemory
    mem = get_analysis_memory(session.id, dataset_name)
    mem.add_statistic(
        StatisticResult(
            test_name=test_name,
            test_statistic=test_statistic,
            p_value=p_value,
            degrees_of_freedom=degrees_of_freedom,
            effect_size=effect_size,
            effect_type=effect_type,
            significant=significant,
        )
    )
    # KnowledgeMemory
    session.knowledge_memory.append(test_name, message)


# ---- T 检验 ----


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


# ---- ANOVA ----


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
        return "执行单因素方差分析(ANOVA)，比较多个组的均值差异。" "当 p <= 0.05 且分组数 >= 3 时自动执行 Tukey HSD 事后检验。"

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
            valid_group_names = []
            for gn in group_names:
                gdata = df[df[group_col] == gn][value_col].dropna()
                if len(gdata) > 0:
                    groups.append(gdata)
                    valid_group_names.append(gn)

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

            f_stat, pval = f_oneway(*groups)
            is_significant = bool(pval <= 0.05)

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
                "group_sizes": {str(gn): len(g) for gn, g in zip(valid_group_names, groups)},
                "group_means": {
                    str(gn): _safe_float(g.mean()) for gn, g in zip(valid_group_names, groups)
                },
                "significant": is_significant,
            }

            if k == 2:
                result["recommendation"] = "当前仅 2 个分组，通常优先使用 t_test（参数法）或 mann_whitney（非参数法）。"

            # 事后检验
            if pval <= 0.05 and k >= 3:
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
                except Exception as e:
                    logger.warning("ANOVA 事后检验失败: %s", e)

            if pval <= 0.05 and k >= 3:
                n_comparisons = k * (k - 1) // 2
                recommended_method = recommend_correction_method(n_comparisons, "exploratory")
                result["post_hoc_recommendation"] = {
                    "triggered": True,
                    "n_comparisons": n_comparisons,
                    "recommended_method": recommended_method,
                    "reason": get_correction_recommendation_reason(
                        recommended_method, "exploratory"
                    ),
                }

            sig = "显著" if is_significant else "不显著"
            msg = f"ANOVA: F({df_between}, {df_within}) = {f_stat:.3f}, p = {pval:.4f} ({sig}), η² = {eta_sq:.3f}"
            _record_stat_result(
                session,
                name,
                test_name="ANOVA",
                message=msg,
                test_statistic=_safe_float(f_stat),
                p_value=_safe_float(pval),
                degrees_of_freedom=df_between,
                effect_size=_safe_float(eta_sq),
                effect_type="eta_squared",
                significant=is_significant,
            )

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
    def category(self) -> str:
        return "statistics"

    @property
    def expose_to_llm(self) -> bool:
        return True

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
        func_map: dict[str, Any] = {
            "pearson": pearsonr,
            "spearman": spearmanr,
            "kendall": kendalltau,
        }
        corr_func: Any = func_map.get(method, pearsonr)

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

        msg = f"{method.title()} 相关性分析完成（{len(columns)} 个变量, n={len(data)}）"
        _record_stat_result(
            session,
            name,
            test_name=f"{method.title()} 相关性分析",
            message=msg,
        )

        return SkillResult(success=True, data=result, message=msg)


# ---- 线性回归 ----


class RegressionSkill(Skill):
    """执行线性回归分析。"""

    @property
    def name(self) -> str:
        return "regression"

    @property
    def category(self) -> str:
        return "statistics"

    @property
    def expose_to_llm(self) -> bool:
        return True

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
            _record_stat_result(
                session,
                name,
                test_name="线性回归",
                message=msg,
                test_statistic=_safe_float(model.fvalue),
                p_value=_safe_float(model.f_pvalue),
                effect_size=_safe_float(model.rsquared),
                effect_type="r_squared",
                significant=bool(model.f_pvalue < 0.05) if model.f_pvalue is not None else False,
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
    def category(self) -> str:
        return "statistics"

    @property
    def expose_to_llm(self) -> bool:
        return True

    @property
    def description(self) -> str:
        return "执行 Mann-Whitney U 检验（Wilcoxon 秩和检验）。" "用于比较两组独立样本的分布差异，不需要正态性假设。"

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
            stat, pval = stats.mannwhitneyu(g1, g2, alternative=alternative)

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
            _record_stat_result(
                session,
                name,
                test_name="Mann-Whitney U 检验",
                message=msg,
                test_statistic=float(stat),
                p_value=float(pval),
                effect_size=_safe_float(r_effect),
                effect_type="r",
                significant=bool(pval < 0.05),
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
    def category(self) -> str:
        return "statistics"

    @property
    def expose_to_llm(self) -> bool:
        return True

    @property
    def description(self) -> str:
        return "执行 Kruskal-Wallis H 检验。" "用于比较多组独立样本的分布差异，不需要正态性假设。"

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
                    str(name): float(data.median()) for name, data in zip(groups, group_data)
                },
                "significant": bool(pval < 0.05),
            }

            sig = "显著" if pval < 0.05 else "不显著"
            msg = (
                f"Kruskal-Wallis H 检验: H({k-1}) = {h_stat:.3f}, "
                f"p = {pval:.4f} ({sig}), η² = {eta_squared:.3f}"
            )
            _record_stat_result(
                session,
                name,
                test_name="Kruskal-Wallis H 检验",
                message=msg,
                test_statistic=float(h_stat),
                p_value=float(pval),
                degrees_of_freedom=k - 1,
                effect_size=_safe_float(eta_squared),
                effect_type="eta_squared",
                significant=bool(pval < 0.05),
            )

            return SkillResult(success=True, data=result, message=msg)

        except Exception as e:
            return SkillResult(success=False, message=f"Kruskal-Wallis H 检验失败: {e}")


class MultipleComparisonCorrectionSkill(Skill):
    """执行多重比较校正。

    支持 Bonferroni、Holm-Bonferroni、FDR (Benjamini-Hochberg) 等校正方法。
    """

    @property
    def name(self) -> str:
        return "multiple_comparison_correction"

    @property
    def category(self) -> str:
        return "statistics"

    @property
    def expose_to_llm(self) -> bool:
        return True

    @property
    def description(self) -> str:
        return (
            "对多个 p 值进行多重比较校正。支持 Bonferroni（最保守）、"
            "Holm（平衡）、FDR（探索性）三种方法。当进行多次统计检验时，"
            "使用此工具控制族错误率或假发现率。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "p_values": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "p 值列表（例如来自多次 t 检验或相关性分析）",
                },
                "method": {
                    "type": "string",
                    "enum": ["bonferroni", "holm", "fdr"],
                    "description": "校正方法：bonferroni=最保守，holm=平衡，fdr=探索性",
                    "default": "bonferroni",
                },
                "alpha": {
                    "type": "number",
                    "description": "显著性水平",
                    "default": 0.05,
                },
                "context": {
                    "type": "string",
                    "enum": ["exploratory", "confirmatory", "high_stakes"],
                    "description": "研究场景，用于方法推荐",
                    "default": "exploratory",
                },
            },
            "required": ["p_values"],
        }

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        p_values = kwargs["p_values"]
        method = kwargs.get("method", "bonferroni")
        alpha = kwargs.get("alpha", 0.05)
        context = kwargs.get("context", "exploratory")

        # 验证输入
        if not p_values:
            return SkillResult(success=False, message="p_values 不能为空")

        if not all(0 <= p <= 1 for p in p_values):
            return SkillResult(success=False, message="所有 p 值必须在 [0, 1] 范围内")

        try:
            # 执行校正
            result = multiple_comparison_correction(p_values, method, alpha)

            # 添加推荐信息
            recommended = recommend_correction_method(len(p_values), context)
            result["recommended_method"] = recommended
            result["recommendation_reason"] = self._get_recommendation_reason(recommended, context)

            # 统计显著结果数
            n_significant = sum(result["significant"])

            msg = (
                f"{result['method']} 校正完成: "
                f"{n_significant}/{len(p_values)} 个比较显著 "
                f"(α = {alpha})"
            )

            return SkillResult(success=True, data=result, message=msg)

        except Exception as e:
            return SkillResult(success=False, message=f"多重比较校正失败: {e}")

    def _get_recommendation_reason(self, method: str, context: str) -> str:
        """获取方法推荐理由。"""
        return get_correction_recommendation_reason(method, context)
