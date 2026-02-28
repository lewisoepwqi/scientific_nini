"""线性回归统计工具。"""

from __future__ import annotations

from typing import Any

import statsmodels.api as sm

from nini.agent.session import Session
from nini.tools.base import Skill, SkillResult
from nini.tools.statistics.base import _ensure_finite, _get_df, _record_stat_result, _safe_float


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
        dependent_var = kwargs["dependent_var"]
        independent_vars = kwargs["independent_vars"]

        df = _get_df(session, name)
        if df is None:
            return SkillResult(success=False, message=f"数据集 '{name}' 不存在")

        all_vars = [dependent_var] + independent_vars
        for var in all_vars:
            if var not in df.columns:
                return SkillResult(success=False, message=f"列 '{var}' 不存在")

        data = df[all_vars].dropna()
        if len(data) < len(independent_vars) + 2:
            return SkillResult(success=False, message="数据量不足以进行回归分析")

        try:
            x_values = sm.add_constant(data[independent_vars])
            y_values = data[dependent_var]
            model = sm.OLS(y_values, x_values).fit()

            coefficients = {
                var: {
                    "estimate": _ensure_finite(model.params[var], f"{var} 系数"),
                    "std_error": _safe_float(model.bse[var]),
                    "t_statistic": _safe_float(model.tvalues[var]),
                    "p_value": _safe_float(model.pvalues[var]),
                }
                for var in model.params.index
            }

            result = {
                "r_squared": _ensure_finite(model.rsquared, "R²"),
                "adjusted_r_squared": _safe_float(model.rsquared_adj),
                "f_statistic": _safe_float(model.fvalue),
                "f_pvalue": _safe_float(model.f_pvalue),
                "n_observations": int(model.nobs),
                "coefficients": coefficients,
            }

            message = (
                f"回归分析: R² = {model.rsquared:.4f}, "
                f"F = {model.fvalue:.3f}, p = {model.f_pvalue:.4f}"
            )
            _record_stat_result(
                session,
                name,
                test_name="线性回归",
                message=message,
                test_statistic=_safe_float(model.fvalue),
                p_value=_safe_float(model.f_pvalue),
                effect_size=_safe_float(model.rsquared),
                effect_type="r_squared",
                significant=bool(model.f_pvalue < 0.05) if model.f_pvalue is not None else False,
            )
            return SkillResult(success=True, data=result, message=message)
        except Exception as exc:
            return SkillResult(success=False, message=f"回归分析失败: {exc}")
