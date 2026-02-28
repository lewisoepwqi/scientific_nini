"""相关性分析统计工具。"""

from __future__ import annotations

from typing import Any

import pandas as pd
from scipy.stats import kendalltau, pearsonr, spearmanr

from nini.agent.session import Session
from nini.tools.base import Skill, SkillResult
from nini.tools.statistics.base import _ensure_finite, _get_df, _record_stat_result, _safe_float


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
        pvalue_matrix: dict[str, dict[str, float]] = {}
        corr_func = {
            "pearson": pearsonr,
            "spearman": spearmanr,
            "kendall": kendalltau,
        }.get(method, pearsonr)

        for col1 in columns:
            pvalue_matrix[col1] = {}
            for col2 in columns:
                if col1 == col2:
                    pvalue_matrix[col1][col2] = 0.0
                    continue
                _, pval = corr_func(data[col1].values, data[col2].values)
                pvalue_matrix[col1][col2] = _ensure_finite(pval, f"{col1}-{col2} p 值")

        result = {
            "method": method,
            "sample_size": len(data),
            "correlation_matrix": {
                col: {other: _safe_float(corr_matrix.loc[col, other]) for other in columns}
                for col in columns
            },
            "pvalue_matrix": pvalue_matrix,
        }

        message = f"{method.title()} 相关性分析完成（{len(columns)} 个变量, n={len(data)}）"
        _record_stat_result(
            session,
            name,
            test_name=f"{method.title()} 相关性分析",
            message=message,
        )
        return SkillResult(success=True, data=result, message=message)
