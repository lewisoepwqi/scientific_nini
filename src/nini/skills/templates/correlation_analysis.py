"""相关性分析技能。

执行完整的变量关联分析，包括：
1. 数据质量检查
2. 相关矩阵计算
3. p 值计算
4. 可视化（热图 + 散点图矩阵）
5. 生成报告
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import kendalltau, pearsonr, spearmanr

from nini.agent.session import Session
from nini.skills.base import Skill, SkillResult
from nini.utils.chart_fonts import CJK_FONT_FAMILY

logger = logging.getLogger(__name__)


class CorrelationAnalysisSkill(Skill):
    """相关性分析技能（模板）。"""

    @property
    def name(self) -> str:
        return "correlation_analysis"

    @property
    def category(self) -> str:
        return "composite"

    @property
    def description(self) -> str:
        return (
            "执行完整的变量关联分析，一站式输出：\n"
            "1. 相关矩阵计算（Pearson/Spearman/Kendall）\n"
            "2. p 值矩阵\n"
            "3. 显著性标记\n"
            "4. 相关矩阵热图\n"
            "5. 散点图矩阵（可选）\n"
            "6. 结果解释\n\n"
            "适用于探索多个连续变量之间的线性或单调关系。"
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
                "journal_style": {
                    "type": "string",
                    "description": "期刊风格（nature、science、cell、apa 等）",
                    "default": "nature",
                },
            },
            "required": ["dataset_name", "columns"],
        }

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        """执行完整分析。"""
        dataset_name = kwargs["dataset_name"]
        columns = kwargs["columns"]
        method = kwargs.get("method", "pearson")
        journal_style = kwargs.get("journal_style", "nature")

        # 获取数据
        df = session.datasets.get(dataset_name)
        if df is None:
            return SkillResult(success=False, message=f"数据集 '{dataset_name}' 不存在")

        # 验证列
        for col in columns:
            if col not in df.columns:
                return SkillResult(success=False, message=f"列 '{col}' 不存在")

        if len(columns) < 2:
            return SkillResult(success=False, message="至少需要 2 列进行相关性分析")

        # 步骤1: 准备数据
        clean_df = df[columns].dropna()
        if len(clean_df) < 3:
            return SkillResult(success=False, message="至少需要 3 个完整观测值")

        # 步骤2: 计算相关矩阵和 p 值矩阵
        corr_matrix, pvalue_matrix = self._calculate_correlation_matrices(clean_df, columns, method)

        # 步骤3: 识别显著相关
        significant_pairs = self._identify_significant_correlations(
            corr_matrix, pvalue_matrix, columns
        )

        # 步骤4: 可视化
        chart_data = self._create_visualization(corr_matrix, pvalue_matrix, columns, journal_style)

        # 步骤5: 生成报告
        report = self._generate_report(
            corr_matrix, pvalue_matrix, significant_pairs, method, len(clean_df)
        )

        # 组装结果
        result_data = {
            "method": method,
            "sample_size": len(clean_df),
            "correlation_matrix": corr_matrix,
            "pvalue_matrix": pvalue_matrix,
            "significant_pairs": significant_pairs,
            "report": report,
        }

        return SkillResult(
            success=True,
            data=result_data,
            message=report["summary"],
            has_chart=True,
            chart_data=chart_data,
        )

    def _calculate_correlation_matrices(
        self, df: pd.DataFrame, columns: list[str], method: str
    ) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, float]]]:
        """计算相关矩阵和 p 值矩阵。"""
        # 选择相关函数
        func_map = {
            "pearson": pearsonr,
            "spearman": spearmanr,
            "kendall": kendalltau,
        }
        corr_func = func_map.get(method, pearsonr)

        # 计算相关矩阵
        corr_matrix: dict[str, dict[str, float]] = {}
        pvalue_matrix: dict[str, dict[str, float]] = {}

        for col1 in columns:
            corr_matrix[col1] = {}
            pvalue_matrix[col1] = {}
            for col2 in columns:
                if col1 == col2:
                    corr_matrix[col1][col2] = 1.0
                    pvalue_matrix[col1][col2] = 0.0
                else:
                    r, p = corr_func(df[col1].values, df[col2].values)
                    corr_matrix[col1][col2] = float(r) if np.isfinite(r) else 0.0
                    pvalue_matrix[col1][col2] = float(p) if np.isfinite(p) else 1.0

        return corr_matrix, pvalue_matrix

    def _identify_significant_correlations(
        self,
        corr_matrix: dict[str, dict[str, float]],
        pvalue_matrix: dict[str, dict[str, float]],
        columns: list[str],
    ) -> list[dict[str, Any]]:
        """识别显著相关的变量对。"""
        significant_pairs = []

        for i, col1 in enumerate(columns):
            for col2 in columns[i + 1 :]:
                r = corr_matrix[col1][col2]
                p = pvalue_matrix[col1][col2]

                if p < 0.05:
                    significant_pairs.append(
                        {
                            "var1": col1,
                            "var2": col2,
                            "correlation": r,
                            "p_value": p,
                            "interpretation": self._interpret_correlation(r),
                        }
                    )

        # 按相关系数绝对值排序
        significant_pairs.sort(key=lambda x: abs(x["correlation"]), reverse=True)

        return significant_pairs

    def _interpret_correlation(self, r: float) -> str:
        """解释相关系数大小。"""
        abs_r = abs(r)
        if abs_r < 0.1:
            strength = "极弱"
        elif abs_r < 0.3:
            strength = "弱"
        elif abs_r < 0.5:
            strength = "中等"
        elif abs_r < 0.7:
            strength = "较强"
        else:
            strength = "强"

        direction = "正" if r > 0 else "负"
        return f"{strength}{direction}相关"

    def _create_visualization(
        self,
        corr_matrix: dict[str, dict[str, float]],
        pvalue_matrix: dict[str, dict[str, float]],
        columns: list[str],
        journal_style: str,
    ) -> dict[str, Any]:
        """创建相关矩阵热图。"""
        import plotly.graph_objects as go

        # 准备矩阵数据
        z_values = []
        for col1 in columns:
            row = []
            for col2 in columns:
                row.append(corr_matrix[col1][col2])
            z_values.append(row)

        # 创建热图
        fig = go.Figure(
            data=go.Heatmap(
                z=z_values,
                x=columns,
                y=columns,
                colorscale="RdBu",
                zmid=0,
                text=[
                    [
                        f"r={corr_matrix[columns[i]][columns[j]]:.3f}<br>"
                        f"p={pvalue_matrix[columns[i]][columns[j]]:.4f}"
                        for j in range(len(columns))
                    ]
                    for i in range(len(columns))
                ],
                texttemplate="%{text}",
                textfont={"size": 10},
                colorbar={"title": "相关系数"},
            )
        )

        # 应用期刊风格
        self._apply_journal_style(fig, journal_style)

        fig.update_layout(
            title="变量相关矩阵",
            xaxis={"side": "bottom"},
            yaxis={"autorange": "reversed"},
        )

        return {
            "figure": fig.to_dict(),
            "chart_type": "heatmap",
        }

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
        corr_matrix: dict[str, dict[str, float]],
        pvalue_matrix: dict[str, dict[str, float]],
        significant_pairs: list[dict[str, Any]],
        method: str,
        sample_size: int,
    ) -> dict[str, str]:
        """生成报告。"""
        method_name = {
            "pearson": "Pearson",
            "spearman": "Spearman",
            "kendall": "Kendall",
        }.get(method, method)

        # 基本统计
        stats_text = f"{method_name} 相关性分析（n={sample_size}）。"

        # 显著相关对
        if significant_pairs:
            pair_texts = []
            for pair in significant_pairs[:5]:  # 最多显示 5 对
                pair_texts.append(
                    f"{pair['var1']} 与 {pair['var2']}: "
                    f"r={pair['correlation']:.3f}, p={pair['p_value']:.4f} "
                    f"({pair['interpretation']})"
                )
            pairs_text = "显著相关: " + "; ".join(pair_texts)
        else:
            pairs_text = "未发现显著的变量间相关（p < 0.05）。"

        summary = f"{stats_text} {pairs_text}"

        return {
            "summary": summary,
            "statistics": stats_text,
            "significant_pairs": pairs_text,
        }
