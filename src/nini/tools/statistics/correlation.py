"""相关性分析统计工具。"""

from __future__ import annotations

from typing import Any, Callable, cast

import pandas as pd
from scipy.stats import kendalltau, pearsonr, spearmanr

from nini.agent.session import Session
from nini.tools.base import Tool, ToolResult
from nini.tools.statistics.base import _ensure_finite, _get_df, _record_stat_result, _safe_float


class CorrelationTool(Tool):
    """计算变量间的相关性。"""

    @property
    def name(self) -> str:
        return "correlation"

    @property
    def category(self) -> str:
        return "statistics"

    @property
    def expose_to_llm(self) -> bool:
        return False

    @property
    def description(self) -> str:
        return (
            "计算多个数值列之间的相关性矩阵和 p 值矩阵。支持 Pearson、Spearman、Kendall 三种方法。"
        )

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

    async def execute(self, session: Session, **kwargs: Any) -> ToolResult:
        name = kwargs["dataset_name"]
        columns = kwargs["columns"]
        method = kwargs.get("method", "pearson")

        df = _get_df(session, name)
        if df is None:
            return ToolResult(success=False, message=f"数据集 '{name}' 不存在")

        for col in columns:
            if col not in df.columns:
                return ToolResult(success=False, message=f"列 '{col}' 不存在")
            if not pd.api.types.is_numeric_dtype(df[col]):
                return ToolResult(success=False, message=f"列 '{col}' 不是数值类型")

        data = df[columns].dropna()
        if len(data) < 3:
            return ToolResult(success=False, message="至少需要 3 个完整观测值")

        corr_matrix = data.corr(method=method)
        pvalue_matrix: dict[str, dict[str, float]] = {}
        corr_func = {
            "pearson": pearsonr,
            "spearman": spearmanr,
            "kendall": kendalltau,
        }.get(method, pearsonr)
        corr_func_callable = cast(Callable[[Any, Any], tuple[Any, Any]], corr_func)
        pairwise_results: list[dict[str, Any]] = []

        for col1 in columns:
            pvalue_matrix[col1] = {}
            for col2 in columns:
                if col1 == col2:
                    pvalue_matrix[col1][col2] = 0.0
                    continue
                _, pval = corr_func_callable(data[col1].values, data[col2].values)
                pvalue_matrix[col1][col2] = _ensure_finite(pval, f"{col1}-{col2} p 值")
                if columns.index(col2) <= columns.index(col1):
                    continue
                coefficient = _safe_float(corr_matrix.loc[col1, col2])
                pairwise_results.append(
                    {
                        "var_a": col1,
                        "var_b": col2,
                        "coefficient": coefficient,
                        "p_value": pvalue_matrix[col1][col2],
                        "significant": bool(pvalue_matrix[col1][col2] < 0.05),
                    }
                )

        result = {
            "method": method,
            "sample_size": len(data),
            "correlation_matrix": {
                col: {other: _safe_float(corr_matrix.loc[col, other]) for other in columns}
                for col in columns
            },
            "pvalue_matrix": pvalue_matrix,
            "stat_summary": {
                "kind": "correlation",
                "method": method,
                "sample_size": len(data),
                "pairwise": pairwise_results,
            },
        }

        message = f"{method.title()} 相关性分析完成（{len(columns)} 个变量, n={len(data)}）"
        for pair in pairwise_results:
            coefficient = pair["coefficient"]
            p_value = pair["p_value"]
            _record_stat_result(
                session,
                name,
                test_name=f"{method.title()} 相关性分析（{pair['var_a']} vs {pair['var_b']}）",
                message=message,
                p_value=float(p_value) if p_value is not None else None,
                effect_size=float(coefficient) if coefficient is not None else None,
                effect_type=f"{method.lower()}_correlation",
                significant=bool(pair["significant"]),
                metadata={
                    "dataset_name": name,
                    "method": method,
                    "sample_size": len(data),
                    "variables": [pair["var_a"], pair["var_b"]],
                    "var_a": pair["var_a"],
                    "var_b": pair["var_b"],
                    "coefficient": coefficient,
                },
            )
        return ToolResult(success=True, data=result, message=message)
