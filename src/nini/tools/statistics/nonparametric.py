"""非参数统计检验工具。"""

from __future__ import annotations

from typing import Any

from scipy import stats

from nini.agent.session import Session
from nini.tools.base import Skill, SkillResult
from nini.tools.statistics.base import _get_df, _record_stat_result, _safe_float


class MannWhitneySkill(Skill):
    """执行 Mann-Whitney U 检验。"""

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
        return "执行 Mann-Whitney U 检验（Wilcoxon 秩和检验）。用于比较两组独立样本的分布差异，不需要正态性假设。"

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

        group1 = df[df[group_col] == groups[0]][value_col].dropna()
        group2 = df[df[group_col] == groups[1]][value_col].dropna()
        if len(group1) < 2 or len(group2) < 2:
            return SkillResult(success=False, message="每组至少需要 2 个观测值")

        try:
            stat, pval = stats.mannwhitneyu(group1, group2, alternative=alternative)
            n1, n2 = len(group1), len(group2)
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
                "median1": float(group1.median()),
                "median2": float(group2.median()),
                "n1": len(group1),
                "n2": len(group2),
                "significant": bool(pval < 0.05),
            }

            significance_text = "显著" if pval < 0.05 else "不显著"
            message = (
                f"Mann-Whitney U 检验: U = {stat:.0f}, "
                f"p = {pval:.4f} ({significance_text}), "
                f"r = {r_effect:.3f}"
            )
            _record_stat_result(
                session,
                name,
                test_name="Mann-Whitney U 检验",
                message=message,
                test_statistic=float(stat),
                p_value=float(pval),
                effect_size=_safe_float(r_effect),
                effect_type="r",
                significant=bool(pval < 0.05),
            )
            return SkillResult(success=True, data=result, message=message)
        except Exception as exc:
            return SkillResult(success=False, message=f"Mann-Whitney U 检验失败: {exc}")


class KruskalWallisSkill(Skill):
    """执行 Kruskal-Wallis H 检验。"""

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
        return "执行 Kruskal-Wallis H 检验。用于比较多组独立样本的分布差异，不需要正态性假设。"

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
        valid_group_names = []
        for group_name in groups:
            data = df[df[group_col] == group_name][value_col].dropna()
            if len(data) > 0:
                group_data.append(data)
                valid_group_names.append(group_name)

        if len(group_data) < 2:
            return SkillResult(success=False, message="至少需要 2 个有效分组")

        try:
            h_stat, pval = stats.kruskal(*group_data)
            n_total = sum(len(group) for group in group_data)
            n_groups = len(group_data)
            eta_squared = (h_stat - n_groups + 1) / (n_total - n_groups) if n_total > n_groups else 0

            result = {
                "test_type": "Kruskal-Wallis H 检验",
                "h_statistic": float(h_stat),
                "p_value": float(pval),
                "df": n_groups - 1,
                "eta_squared": _safe_float(eta_squared),
                "n_groups": n_groups,
                "group_medians": {
                    str(group_name): float(data.median())
                    for group_name, data in zip(valid_group_names, group_data)
                },
                "significant": bool(pval < 0.05),
            }

            significance_text = "显著" if pval < 0.05 else "不显著"
            message = (
                f"Kruskal-Wallis H 检验: H({n_groups - 1}) = {h_stat:.3f}, "
                f"p = {pval:.4f} ({significance_text}), η² = {eta_squared:.3f}"
            )
            _record_stat_result(
                session,
                name,
                test_name="Kruskal-Wallis H 检验",
                message=message,
                test_statistic=float(h_stat),
                p_value=float(pval),
                degrees_of_freedom=n_groups - 1,
                effect_size=_safe_float(eta_squared),
                effect_type="eta_squared",
                significant=bool(pval < 0.05),
            )
            return SkillResult(success=True, data=result, message=message)
        except Exception as exc:
            return SkillResult(success=False, message=f"Kruskal-Wallis H 检验失败: {exc}")
