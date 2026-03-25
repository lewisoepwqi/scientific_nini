"""完整两组比较分析技能。

执行完整的两组比较分析，包括：
1. 数据质量检查
2. 正态性与方差齐性检验
3. 根据前提选择合适的统计检验
4. 效应量计算
5. 可视化
6. 生成 APA 格式结果描述
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

import numpy as np
import pandas as pd
from scipy import stats

from nini.agent.session import Session
from nini.tools.analysis_workflow import AnalysisWorkflowEngine
from nini.tools.base import Tool, ToolResult
from nini.utils.chart_fonts import CJK_FONT_FAMILY

if TYPE_CHECKING:
    import plotly.graph_objects as go

logger = logging.getLogger(__name__)


class CompleteComparisonTool(Tool):
    """完整两组比较分析技能（模板）。"""

    @property
    def name(self) -> str:
        return "complete_comparison"

    @property
    def category(self) -> str:
        return "workflow"

    @property
    def description(self) -> str:
        return (
            "执行完整的两组比较分析，一站式输出：\n"
            "1. 数据质量检查（样本量、缺失值、异常值）\n"
            "2. 正态性与方差齐性检验\n"
            "3. 自动选择合适的统计方法（t检验/Mann-Whitney U检验）\n"
            "4. 效应量计算（Cohen's d）\n"
            "5. 箱线图可视化\n"
            "6. APA 格式结果描述\n\n"
            "适用于两组独立样本的均值比较。"
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
                "paired": {
                    "type": "boolean",
                    "description": "是否为配对样本",
                    "default": False,
                },
            },
            "required": ["dataset_name", "value_column", "group_column"],
        }

    async def execute(self, session: Session, **kwargs: Any) -> ToolResult:
        """执行完整分析。"""
        engine = AnalysisWorkflowEngine()
        return await engine.complete_comparison(
            session,
            dataset_name=kwargs["dataset_name"],
            value_column=kwargs["value_column"],
            group_column=kwargs["group_column"],
            journal_style=kwargs.get("journal_style", "nature"),
            paired=bool(kwargs.get("paired", False)),
        )

    def _check_data_quality(
        self, df: pd.DataFrame, value_column: str, group_column: str
    ) -> dict[str, Any]:
        """检查数据质量。"""
        report: dict[str, Any] = {
            "valid": True,
            "error": "",
            "total_rows": len(df),
            "missing_values": int(df[value_column].isna().sum()),
            "groups": df[group_column].dropna().unique().tolist(),
        }

        # 检查是否有足够的组
        if report["missing_values"] > len(df) * 0.5:
            report["valid"] = False
            report["error"] = f"数值列 '{value_column}' 缺失值超过 50%"

        return report

    def _test_assumptions(self, data1: pd.Series, data2: pd.Series) -> dict[str, Any]:
        """检验统计前提。"""
        assumptions: dict[str, Any] = {
            "normality_test1": None,
            "normality_test2": None,
            "variance_test": None,
            "use_non_parametric": False,
            "reason": "",
        }

        # Shapiro-Wilk 正态性检验
        if len(data1) >= 3 and len(data1) <= 5000:
            try:
                stat1, p1 = stats.shapiro(data1)
                assumptions["normality_test1"] = {
                    "statistic": float(stat1),
                    "p_value": float(p1),
                    "normal": p1 > 0.05,
                }
            except ValueError:
                assumptions["normality_test1"] = {"error": "检验失败"}

        if len(data2) >= 3 and len(data2) <= 5000:
            try:
                stat2, p2 = stats.shapiro(data2)
                assumptions["normality_test2"] = {
                    "statistic": float(stat2),
                    "p_value": float(p2),
                    "normal": p2 > 0.05,
                }
            except ValueError:
                assumptions["normality_test2"] = {"error": "检验失败"}

        # Levene 方差齐性检验
        try:
            stat, p = stats.levene(data1, data2)
            assumptions["variance_test"] = {
                "statistic": float(stat),
                "p_value": float(p),
                "equal_variance": p > 0.05,
            }
        except ValueError:
            assumptions["variance_test"] = {"error": "检验失败"}

        # 决定是否使用非参数方法
        reasons = []
        use_non_param = False

        if assumptions.get("normality_test1") and not assumptions["normality_test1"]["normal"]:
            use_non_param = True
            reasons.append("组1不符合正态分布")
        if assumptions.get("normality_test2") and not assumptions["normality_test2"]["normal"]:
            use_non_param = True
            reasons.append("组2不符合正态分布")

        assumptions["use_non_parametric"] = use_non_param
        assumptions["reason"] = "; ".join(reasons) if reasons else "满足正态性假设"

        return assumptions

    def _t_test(
        self,
        data1: pd.Series,
        data2: pd.Series,
        group1_name: str,
        group2_name: str,
        paired: bool,
    ) -> dict[str, Any]:
        """执行 t 检验。"""
        if paired:
            stat_raw, pval_raw = stats.ttest_rel(data1, data2)
            test_type = "配对样本 t 检验"
        else:
            stat_raw, pval_raw = stats.ttest_ind(data1, data2, equal_var=False)
            test_type = "独立样本 t 检验（Welch 校正）"
        stat = float(stat_raw)  # type: ignore[arg-type]
        pval = float(pval_raw)  # type: ignore[arg-type]

        mean1 = float(data1.mean())  # type: ignore[arg-type]
        mean2 = float(data2.mean())  # type: ignore[arg-type]
        mean_diff = mean1 - mean2

        # 计算置信区间
        se = float(np.sqrt(float(data1.var()) / len(data1) + float(data2.var()) / len(data2)))
        df_degrees = len(data1) + len(data2) - 2
        t_crit = stats.t.ppf(0.975, df_degrees)

        return {
            "test_type": test_type,
            "statistic": float(stat),
            "p_value": float(pval),
            "df": float(df_degrees),
            "mean1": mean1,
            "mean2": mean2,
            "mean_difference": mean_diff,
            "ci_lower": float(mean_diff - t_crit * se),
            "ci_upper": float(mean_diff + t_crit * se),
            "significant": bool(pval < 0.05),
        }

    def _mann_whitney_test(
        self,
        data1: pd.Series,
        data2: pd.Series,
        group1_name: str,
        group2_name: str,
    ) -> dict[str, Any]:
        """执行 Mann-Whitney U 检验。"""
        stat, pval = stats.mannwhitneyu(data1, data2, alternative="two-sided")

        return {
            "test_type": "Mann-Whitney U 检验",
            "statistic": float(stat),
            "p_value": float(pval),
            "median1": float(data1.median()),
            "median2": float(data2.median()),
            "significant": bool(pval < 0.05),
        }

    def _calculate_effect_size(
        self, data1: pd.Series, data2: pd.Series, assumptions: dict[str, Any]
    ) -> dict[str, Any]:
        """计算效应量。"""
        if assumptions["use_non_parametric"]:
            # 非参数：使用秩二相关（Cliff's Delta 的简化版本）
            n1, n2 = len(data1), len(data2)
            u_stat, _ = stats.mannwhitneyu(data1, data2, alternative="two-sided")
            # r = Z / sqrt(N)
            # 这里使用简化的效应量估计
            r = 1 - (2 * u_stat) / (n1 * n2)
            return {
                "type": "rank_biserial_correlation",
                "value": abs(float(r)),
                "interpretation": self._interpret_effect_size(abs(r)),
            }
        else:
            # 参数：Cohen's d
            n1, n2 = len(data1), len(data2)
            mean_diff = data1.mean() - data2.mean()
            pooled_std = np.sqrt(((n1 - 1) * data1.var() + (n2 - 1) * data2.var()) / (n1 + n2 - 2))
            cohens_d = mean_diff / pooled_std if pooled_std > 0 else 0

            return {
                "type": "cohens_d",
                "value": abs(float(cohens_d)),
                "interpretation": self._interpret_effect_size(abs(cohens_d)),
            }

    def _interpret_effect_size(self, value: float) -> str:
        """解释效应量大小。"""
        abs_val = abs(value)
        if abs_val < 0.2:
            return "微小效应"
        elif abs_val < 0.5:
            return "小效应"
        elif abs_val < 0.8:
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

        groups = df[group_column].dropna().unique()
        fig = go.Figure()

        for group in groups:
            group_data = df[df[group_column] == group][value_column].dropna()
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
        quality_report: dict[str, Any],
        assumptions: dict[str, Any],
        test_result: dict[str, Any],
        effect_size: dict[str, Any],
        journal_style: str,
    ) -> dict[str, str]:
        """生成 APA 格式报告。"""
        test_type = test_result["test_type"]
        p_val = test_result["p_value"]
        significant = test_result["significant"]

        # APA 格式报告
        if "t 检验" in test_type:
            stat = test_result["statistic"]
            df = test_result["df"]
            mean_diff = test_result["mean_difference"]
            ci_lower = test_result["ci_lower"]
            ci_upper = test_result["ci_upper"]

            stats_text = (
                f"{test_type}结果显示："
                f"t({df:.0f}) = {stat:.3f}, p = {p_val:.4f}, "
                f"95% CI [{ci_lower:.3f}, {ci_upper:.3f}]"
            )
        else:
            stat = test_result["statistic"]
            stats_text = f"{test_type}结果显示：" f"U = {stat:.0f}, p = {p_val:.4f}"

        # 效应量
        effect_text = (
            f"{effect_size['type']} = {effect_size['value']:.3f} "
            f"({effect_size['interpretation']})"
        )

        # 结论
        if significant:
            conclusion = "两组间存在显著差异。"
        else:
            conclusion = "两组间差异无统计学意义。"

        summary = f"{stats_text}，{effect_text}，{conclusion}"

        return {
            "summary": summary,
            "statistics": stats_text,
            "effect_size": effect_text,
            "conclusion": conclusion,
        }
