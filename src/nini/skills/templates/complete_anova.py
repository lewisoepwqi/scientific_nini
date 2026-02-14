"""完整 ANOVA 分析技能。

执行完整的多组均值比较分析，包括：
1. 数据质量检查
2. 单因素方差分析
3. 事后检验（Tukey HSD）
4. 效应量计算（Eta squared）
5. 可视化
6. 生成 APA 格式结果描述
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multicomp import pairwise_tukeyhsd

from nini.agent.session import Session
from nini.skills.base import Skill, SkillResult
from nini.utils.chart_fonts import CJK_FONT_FAMILY

if TYPE_CHECKING:
    import plotly.graph_objects as go

logger = logging.getLogger(__name__)


class CompleteANOVASkill(Skill):
    """完整 ANOVA 分析技能（模板）。"""

    @property
    def name(self) -> str:
        return "complete_anova"

    @property
    def category(self) -> str:
        return "workflow"

    @property
    def description(self) -> str:
        return (
            "执行完整的多组均值比较分析（ANOVA），一站式输出：\n"
            "1. 数据质量检查\n"
            "2. 单因素方差分析\n"
            "3. Tukey HSD 事后检验\n"
            "4. 效应量计算（Eta squared）\n"
            "5. 箱线图可视化\n"
            "6. APA 格式结果描述\n\n"
            "适用于3组或更多独立样本的均值比较。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "dataset_name": {
                    "type": "string",
                    "description": "数据集名称",
                },
                "value_column": {
                    "type": "string",
                    "description": "数值列名（因变量）",
                },
                "group_column": {
                    "type": "string",
                    "description": "分组列名（自变量）",
                },
                "journal_style": {
                    "type": "string",
                    "description": "期刊风格（nature、science、cell、apa 等）",
                    "default": "nature",
                },
            },
            "required": ["dataset_name", "value_column", "group_column"],
        }

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        """执行完整分析。"""
        dataset_name = kwargs["dataset_name"]
        value_column = kwargs["value_column"]
        group_column = kwargs["group_column"]
        journal_style = kwargs.get("journal_style", "nature")

        # 获取数据
        df = session.datasets.get(dataset_name)
        if df is None:
            return SkillResult(success=False, message=f"数据集 '{dataset_name}' 不存在")

        if value_column not in df.columns:
            return SkillResult(success=False, message=f"列 '{value_column}' 不存在")
        if group_column not in df.columns:
            return SkillResult(success=False, message=f"分组列 '{group_column}' 不存在")

        # 步骤1: 数据质量检查
        clean_df = df[[value_column, group_column]].dropna()

        groups = clean_df[group_column].unique()
        if len(groups) < 2:
            return SkillResult(
                success=False,
                message="至少需要 2 个分组进行 ANOVA 分析",
            )

        # 步骤2: 准备分组数据
        group_data = []
        for group in groups:
            group_data.append(clean_df[clean_df[group_column] == group][value_column])

        # 步骤3: 执行 ANOVA
        anova_result = self._perform_anova(group_data, groups)

        # 步骤4: 事后检验
        post_hoc_result = None
        if anova_result["p_value"] < 0.05:
            post_hoc_result = self._perform_post_hoc(clean_df, value_column, group_column)

        # 步骤5: 效应量
        effect_size = self._calculate_effect_size(group_data, anova_result)

        # 步骤6: 可视化
        chart_data = self._create_visualization(clean_df, value_column, group_column, journal_style)

        # 步骤7: 生成报告
        report = self._generate_report(anova_result, post_hoc_result, effect_size, journal_style)

        # 组装结果
        result_data = {
            "anova": anova_result,
            "post_hoc": post_hoc_result,
            "effect_size": effect_size,
            "report": report,
            "n_groups": len(groups),
            "group_names": [str(g) for g in groups],
        }

        return SkillResult(
            success=True,
            data=result_data,
            message=report["summary"],
            has_chart=True,
            chart_data=chart_data,
        )

    def _perform_anova(self, group_data: list[pd.Series], groups: list[Any]) -> dict[str, Any]:
        """执行单因素方差分析。"""
        f_stat, p_val = stats.f_oneway(*group_data)

        # 计算自由度
        k = len(group_data)
        n_total = sum(len(g) for g in group_data)
        df_between = k - 1
        df_within = n_total - k

        # 计算组均值和总均值
        group_means = [float(g.mean()) for g in group_data]
        group_sizes = [len(g) for g in group_data]
        grand_mean = float(np.concatenate(group_data).mean())

        # 计算平方和
        ss_between = sum(len(g) * (g.mean() - grand_mean) ** 2 for g in group_data)
        ss_within = sum(((g - g.mean()) ** 2).sum() for g in group_data)
        ss_total = ss_between + ss_within

        return {
            "test_type": "单因素方差分析 (One-way ANOVA)",
            "f_statistic": float(f_stat),
            "p_value": float(p_val),
            "df_between": df_between,
            "df_within": df_within,
            "ss_between": float(ss_between),
            "ss_within": float(ss_within),
            "ss_total": float(ss_total),
            "significant": bool(p_val < 0.05),
            "group_means": {str(name): mean for name, mean in zip(groups, group_means)},
            "group_sizes": {str(name): size for name, size in zip(groups, group_sizes)},
            "grand_mean": grand_mean,
        }

    def _perform_post_hoc(
        self, df: pd.DataFrame, value_column: str, group_column: str
    ) -> dict[str, Any]:
        """执行 Tukey HSD 事后检验。"""
        try:
            tukey = pairwise_tukeyhsd(
                endog=df[value_column],
                groups=df[group_column],
                alpha=0.05,
            )

            comparisons: list[dict[str, Any]] = []
            n_groups = len(tukey.groupsunique)

            # 提取成对比较结果
            for i in range(n_groups):
                for j in range(i + 1, n_groups):
                    idx = len(comparisons)
                    if idx < len(tukey.pvalues):
                        comparisons.append(
                            {
                                "group1": str(tukey.groupsunique[i]),
                                "group2": str(tukey.groupsunique[j]),
                                "mean_diff": float(tukey.meandiffs[idx]),
                                "p_value": float(tukey.pvalues[idx]),
                                "significant": bool(tukey.reject[idx]),
                                "ci_lower": float(tukey.confint[idx][0]),
                                "ci_upper": float(tukey.confint[idx][1]),
                            }
                        )

            return {
                "test_type": "Tukey HSD 事后检验",
                "comparisons": comparisons,
                "significant_pairs": sum(1 for c in comparisons if c["significant"]),
            }
        except Exception as e:
            logger.warning("事后检验失败: %s", e)
            return {"error": str(e)}

    def _calculate_effect_size(
        self, group_data: list[pd.Series], anova_result: dict[str, Any]
    ) -> dict[str, Any]:
        """计算效应量（Eta squared）。"""
        ss_between = anova_result["ss_between"]
        ss_total = anova_result["ss_total"]

        eta_squared = ss_between / ss_total if ss_total > 0 else 0

        return {
            "type": "eta_squared",
            "value": float(eta_squared),
            "interpretation": self._interpret_eta_squared(eta_squared),
        }

    def _interpret_eta_squared(self, eta_sq: float) -> str:
        """解释 Eta squared 大小。"""
        if eta_sq < 0.01:
            return "微小效应"
        elif eta_sq < 0.06:
            return "小效应"
        elif eta_sq < 0.14:
            return "中等效应"
        else:
            return "大效应"

    def _create_visualization(
        self,
        df: pd.DataFrame,
        value_column: str,
        group_column: str,
        journal_style: str,
    ) -> dict[str, Any]:
        """创建箱线图。"""
        import plotly.graph_objects as go

        groups = df[group_column].unique()
        fig = go.Figure()

        for group in groups:
            group_data = df[df[group_column] == group][value_column]
            fig.add_trace(
                go.Box(
                    y=group_data,
                    name=str(group),
                    boxpoints="outliers",
                )
            )

        # 应用期刊风格
        self._apply_journal_style(fig, journal_style)

        fig.update_layout(
            title=f"{value_column} 按 {group_column} 分组",
            yaxis_title=value_column,
            xaxis_title=group_column,
        )

        chart_payload = cast(dict[str, Any], fig.to_plotly_json())
        chart_payload["chart_type"] = "box"
        chart_payload["schema_version"] = "1.0"
        return chart_payload

    def _apply_journal_style(self, fig: go.Figure, journal_style: str) -> None:
        """应用期刊样式。"""
        style_configs = {
            "nature": {
                "font": {"family": CJK_FONT_FAMILY, "size": 12},
                "plot_bgcolor": "white",
                "paper_bgcolor": "white",
            },
            "science": {
                "font": {"family": CJK_FONT_FAMILY, "size": 11},
                "plot_bgcolor": "white",
                "paper_bgcolor": "white",
            },
            "cell": {
                "font": {"family": CJK_FONT_FAMILY, "size": 10},
                "plot_bgcolor": "white",
                "paper_bgcolor": "white",
            },
            "apa": {
                "font": {"family": CJK_FONT_FAMILY, "size": 12},
                "plot_bgcolor": "white",
                "paper_bgcolor": "white",
            },
        }

        config = style_configs.get(journal_style, style_configs["nature"])
        fig.update_layout(**config)

    def _generate_report(
        self,
        anova_result: dict[str, Any],
        post_hoc_result: dict[str, Any] | None,
        effect_size: dict[str, Any],
        journal_style: str,
    ) -> dict[str, str]:
        """生成 APA 格式报告。"""
        f_stat = anova_result["f_statistic"]
        df_between = anova_result["df_between"]
        df_within = anova_result["df_within"]
        p_val = anova_result["p_value"]
        significant = anova_result["significant"]

        # APA 格式报告
        stats_text = (
            f"单因素方差分析结果显示："
            f"F({df_between}, {df_within}) = {f_stat:.3f}, p = {p_val:.4f}"
        )

        # 效应量
        effect_text = f"η² = {effect_size['value']:.3f} ({effect_size['interpretation']})"

        # 事后检验结果
        post_hoc_text = ""
        if post_hoc_result and "comparisons" in post_hoc_result:
            sig_pairs = [
                f"{c['group1']} vs {c['group2']}"
                for c in post_hoc_result["comparisons"]
                if c["significant"]
            ]
            if sig_pairs:
                post_hoc_text = f"事后检验显示显著差异组别：{', '.join(sig_pairs)}。"
            else:
                post_hoc_text = "事后检验未发现组间显著差异。"

        # 结论
        if significant:
            conclusion = "各组均值间存在显著差异。"
        else:
            conclusion = "各组均值间差异无统计学意义。"

        parts = [stats_text, effect_text]
        if post_hoc_text:
            parts.append(post_hoc_text)
        parts.append(conclusion)

        summary = " ".join(parts)

        return {
            "summary": summary,
            "statistics": stats_text,
            "effect_size": effect_text,
            "post_hoc": post_hoc_text,
            "conclusion": conclusion,
        }
