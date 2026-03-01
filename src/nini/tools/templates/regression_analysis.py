"""回归分析技能。

执行完整的回归分析，包括：
1. 数据质量检查
2. 假设检验（正态性、异方差性、多重共线性）
3. 线性/多元回归计算
4. 残差诊断
5. 可视化（回归图 + 残差图）
6. 生成 APA 格式报告
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import kstest, shapiro

from nini.agent.session import Session
from nini.tools.base import Skill, SkillResult
from nini.utils.chart_fonts import CJK_FONT_FAMILY

if TYPE_CHECKING:
    import plotly.graph_objects as go

logger = logging.getLogger(__name__)


class RegressionAnalysisSkill(Skill):
    """回归分析技能（模板）。"""

    @property
    def name(self) -> str:
        return "regression_analysis"

    @property
    def category(self) -> str:
        return "workflow"

    @property
    def description(self) -> str:
        return (
            "执行完整的回归分析，一站式输出：\n"
            "1. 数据质量检查（缺失值、异常值）\n"
            "2. 假设检验（正态性、异方差性、多重共线性）\n"
            "3. 线性/多元回归模型拟合\n"
            "4. 残差诊断与可视化\n"
            "5. 模型指标与系数解释\n"
            "6. APA 格式结果报告\n\n"
            "适用于建立变量间的预测模型和探索因果关系。"
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
                "dependent_var": {
                    "type": "string",
                    "description": "因变量（被预测变量）",
                },
                "independent_vars": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "自变量列表（预测变量）",
                },
                "journal_style": {
                    "type": "string",
                    "description": "期刊风格（nature、science、cell、apa 等）",
                    "default": "nature",
                },
            },
            "required": ["dataset_name", "dependent_var", "independent_vars"],
        }

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        """执行完整回归分析。"""
        dataset_name = kwargs["dataset_name"]
        dependent_var = kwargs["dependent_var"]
        independent_vars = kwargs["independent_vars"]
        journal_style = kwargs.get("journal_style", "nature")

        # 获取数据
        df = session.datasets.get(dataset_name)
        if df is None:
            return SkillResult(success=False, message=f"数据集 '{dataset_name}' 不存在")

        # 验证列
        all_vars = [dependent_var] + list(independent_vars)
        for var in all_vars:
            if var not in df.columns:
                return SkillResult(success=False, message=f"列 '{var}' 不存在")

        # 步骤1: 数据质量检查
        quality_report = self._check_data_quality(df, all_vars)
        if quality_report["has_critical_issues"]:
            return SkillResult(
                success=False,
                message=f"数据质量问题: {quality_report['issues'][0]}"
            )

        # 步骤2: 准备数据（处理缺失值）
        clean_df = df[all_vars].dropna()
        if len(clean_df) < 10:
            return SkillResult(success=False, message="有效样本量不足（至少需要 10 个观测）")

        # 步骤3: 假设检验
        assumptions = self._check_assumptions(clean_df, dependent_var, independent_vars)

        # 步骤4: 执行回归分析
        regression_result = self._perform_regression(
            clean_df, dependent_var, independent_vars
        )

        # 步骤5: 残差诊断
        residual_diagnostics = self._diagnose_residuals(
            clean_df, dependent_var, independent_vars, regression_result
        )

        # 步骤6: 可视化
        chart_data = self._create_visualizations(
            clean_df, dependent_var, independent_vars,
            regression_result, residual_diagnostics, journal_style
        )

        # 步骤7: 生成报告
        report = self._generate_report(
            regression_result, assumptions, residual_diagnostics,
            len(clean_df), dependent_var, independent_vars
        )

        # 组装结果
        result_data = {
            "sample_size": len(clean_df),
            "dependent_var": dependent_var,
            "independent_vars": independent_vars,
            "quality_report": quality_report,
            "assumptions": assumptions,
            "regression": regression_result,
            "residuals": residual_diagnostics,
            "report": report,
        }

        return SkillResult(
            success=True,
            data=result_data,
            message=report["summary"],
            has_chart=True,
            chart_data=chart_data,
        )

    def _check_data_quality(
        self, df: pd.DataFrame, columns: list[str]
    ) -> dict[str, Any]:
        """检查数据质量。"""
        issues = []
        warnings_list = []

        for col in columns:
            series = df[col]
            missing_pct = series.isna().mean() * 100

            if missing_pct > 50:
                issues.append(f"列 '{col}' 缺失值过多 ({missing_pct:.1f}%)")
            elif missing_pct > 10:
                warnings_list.append(f"列 '{col}' 有 {missing_pct:.1f}% 缺失值")

            # 检查是否为数值型
            if not pd.api.types.is_numeric_dtype(series):
                try:
                    pd.to_numeric(series, errors='raise')
                except (ValueError, TypeError):
                    issues.append(f"列 '{col}' 不是数值类型，无法用于回归分析")

            # 检查方差
            numeric_series = pd.to_numeric(series, errors='coerce').dropna()
            if len(numeric_series) > 1 and numeric_series.var() == 0:
                issues.append(f"列 '{col}' 方差为零，无法用于回归")

        return {
            "has_critical_issues": len(issues) > 0,
            "issues": issues,
            "warnings": warnings_list,
        }

    def _check_assumptions(
        self,
        df: pd.DataFrame,
        dependent_var: str,
        independent_vars: list[str],
    ) -> dict[str, Any]:
        """检验回归假设。"""
        assumptions = {}

        # 正态性检验（Shapiro-Wilk 或 Kolmogorov-Smirnov）
        y = df[dependent_var].dropna()
        if len(y) <= 5000:
            # Shapiro-Wilk 适用于小样本
            stat, p_value = shapiro(y)
            test_name = "Shapiro-Wilk"
        else:
            # KS 检验适用于大样本
            stat, p_value = kstest(y, 'norm', args=(y.mean(), y.std()))
            test_name = "Kolmogorov-Smirnov"

        assumptions["normality"] = {
            "test": test_name,
            "statistic": float(stat),
            "p_value": float(p_value),
            "satisfied": p_value > 0.05,
            "note": "因变量正态性检验",
        }

        # 多重共线性检查（VIF）
        if len(independent_vars) > 1:
            try:
                from statsmodels.stats.outliers_influence import variance_inflation_factor

                X = df[independent_vars].select_dtypes(include=[np.number])
                if len(X.columns) > 1:
                    X_const = X.assign(constant=1)
                    vif_data = {}
                    for i, col in enumerate(X.columns):
                        vif = variance_inflation_factor(X_const.values, i)
                        vif_data[col] = {
                            "vif": float(vif),
                            "satisfied": vif < 10,  # VIF < 10 通常认为无严重共线性
                        }
                    assumptions["multicollinearity"] = vif_data
            except ImportError:
                assumptions["multicollinearity"] = {
                    "note": "statsmodels 未安装，跳过 VIF 检验"
                }

        return assumptions

    def _perform_regression(
        self,
        df: pd.DataFrame,
        dependent_var: str,
        independent_vars: list[str],
    ) -> dict[str, Any]:
        """执行 OLS 回归分析。"""
        try:
            import statsmodels.api as sm
        except ImportError:
            # 使用 numpy 的简化版本
            return self._perform_simple_regression(df, dependent_var, independent_vars)

        y = df[dependent_var]
        X = df[independent_vars].select_dtypes(include=[np.number])

        # 添加常数项
        X = sm.add_constant(X)

        # 拟合模型
        model = sm.OLS(y, X).fit()

        # 提取关键指标
        coefficients = {}
        for var in independent_vars:
            if var in model.params.index:
                coef = model.params[var]
                pval = model.pvalues[var]
                ci_low, ci_high = model.conf_int().loc[var]
                coefficients[var] = {
                    "coefficient": float(coef),
                    "std_error": float(model.bse[var]),
                    "t_statistic": float(model.tvalues[var]),
                    "p_value": float(pval),
                    "ci_95_low": float(ci_low),
                    "ci_95_high": float(ci_high),
                    "significant": pval < 0.05,
                }

        return {
            "r_squared": float(model.rsquared),
            "adj_r_squared": float(model.rsquared_adj),
            "f_statistic": float(model.fvalue),
            "f_pvalue": float(model.f_pvalue),
            "aic": float(model.aic),
            "bic": float(model.bic),
            "coefficients": coefficients,
            "residuals": model.resid.tolist(),
            "fitted_values": model.fittedvalues.tolist(),
        }

    def _perform_simple_regression(
        self,
        df: pd.DataFrame,
        dependent_var: str,
        independent_vars: list[str],
    ) -> dict[str, Any]:
        """使用 numpy 执行简化回归（无 statsmodels 时备用）。"""
        y = df[dependent_var].values
        X = df[independent_vars].select_dtypes(include=[np.number]).values

        # 添加常数列
        X_with_const = np.column_stack([np.ones(len(X)), X])

        # 最小二乘法: (X'X)^-1 X'y
        try:
            beta = np.linalg.lstsq(X_with_const, y, rcond=None)[0]
            y_pred = X_with_const @ beta
            residuals = y - y_pred

            # 计算 R-squared
            ss_res = np.sum(residuals ** 2)
            ss_tot = np.sum((y - y.mean()) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

            coefficients = {"const": {"coefficient": float(beta[0])}}
            for i, var in enumerate(independent_vars):
                if i < len(beta) - 1:
                    coefficients[var] = {"coefficient": float(beta[i + 1])}

            return {
                "r_squared": float(r_squared),
                "adj_r_squared": None,  # 简化版本不计算调整 R²
                "f_statistic": None,
                "f_pvalue": None,
                "aic": None,
                "bic": None,
                "coefficients": coefficients,
                "residuals": residuals.tolist(),
                "fitted_values": y_pred.tolist(),
                "note": "简化版本（statsmodels 未安装）",
            }
        except np.linalg.LinAlgError:
            return {
                "error": "矩阵不可逆，可能存在完全共线性",
                "coefficients": {},
            }

    def _diagnose_residuals(
        self,
        df: pd.DataFrame,
        dependent_var: str,
        independent_vars: list[str],
        regression_result: dict[str, Any],
    ) -> dict[str, Any]:
        """残差诊断。"""
        residuals = regression_result.get("residuals", [])
        fitted = regression_result.get("fitted_values", [])

        if not residuals:
            return {"error": "无法获取残差"}

        residuals_arr = np.array(residuals)

        # 异方差性检验（简单版本：残差与拟合值的相关系数）
        if fitted:
            het_corr = np.corrcoef(np.abs(residuals_arr), np.array(fitted))[0, 1]
            heteroscedasticity = {
                "abs_resid_fitted_corr": float(het_corr) if not np.isnan(het_corr) else None,
                "note": "|残差|与拟合值的相关系数，绝对值 > 0.3 提示可能存在异方差",
            }
        else:
            heteroscedasticity = {"note": "无法计算（缺少拟合值）"}

        # 残差正态性
        if len(residuals_arr) >= 3:
            stat, p_value = shapiro(residuals_arr)
            residual_normality = {
                "test": "Shapiro-Wilk",
                "statistic": float(stat),
                "p_value": float(p_value),
                "satisfied": p_value > 0.05,
            }
        else:
            residual_normality = {"note": "样本量不足，无法检验"}

        # 异常值检测（基于标准化残差）
        std_residuals = residuals_arr / np.std(residuals_arr) if np.std(residuals_arr) > 0 else residuals_arr
        outliers = np.where(np.abs(std_residuals) > 2.5)[0].tolist()

        return {
            "mean": float(np.mean(residuals_arr)),
            "std": float(np.std(residuals_arr)),
            "min": float(np.min(residuals_arr)),
            "max": float(np.max(residuals_arr)),
            "heteroscedasticity": heteroscedasticity,
            "normality": residual_normality,
            "outliers": {
                "count": len(outliers),
                "indices": outliers[:10],  # 最多报告 10 个
            },
        }

    def _create_visualizations(
        self,
        df: pd.DataFrame,
        dependent_var: str,
        independent_vars: list[str],
        regression_result: dict[str, Any],
        residual_diagnostics: dict[str, Any],
        journal_style: str,
    ) -> dict[str, Any]:
        """创建回归分析可视化。"""
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        # 创建子图：实际 vs 预测 + Q-Q 图
        fig = make_subplots(
            rows=1, cols=2,
            subplot_titles=("实际值 vs 预测值", "残差 Q-Q 图"),
        )

        fitted = regression_result.get("fitted_values", [])
        actual = df[dependent_var].values

        if fitted and len(fitted) == len(actual):
            # 实际 vs 预测
            fig.add_trace(
                go.Scatter(
                    x=fitted,
                    y=actual,
                    mode="markers",
                    name="观测值",
                    marker=dict(size=8, opacity=0.6),
                ),
                row=1, col=1
            )
            # 添加对角线（完美预测线）
            min_val = min(min(fitted), min(actual))
            max_val = max(max(fitted), max(actual))
            fig.add_trace(
                go.Scatter(
                    x=[min_val, max_val],
                    y=[min_val, max_val],
                    mode="lines",
                    name="完美预测",
                    line=dict(dash="dash", color="red"),
                ),
                row=1, col=1
            )

        # Q-Q 图
        residuals = regression_result.get("residuals", [])
        if residuals:
            residuals_arr = np.array(residuals)
            # 理论分位数
            theoretical = stats.norm.ppf(
                np.linspace(0.01, 0.99, len(residuals_arr))
            )
            # 实际分位数
            actual_quantiles = np.percentile(
                residuals_arr,
                np.linspace(1, 99, len(residuals_arr))
            )

            fig.add_trace(
                go.Scatter(
                    x=theoretical,
                    y=actual_quantiles,
                    mode="markers",
                    name="Q-Q 点",
                    marker=dict(size=6, opacity=0.6),
                ),
                row=1, col=2
            )
            # 添加参考线
            fig.add_trace(
                go.Scatter(
                    x=[theoretical.min(), theoretical.max()],
                    y=[theoretical.min(), theoretical.max()],
                    mode="lines",
                    name="参考线",
                    line=dict(dash="dash", color="red"),
                ),
                row=1, col=2
            )

        # 应用期刊风格
        self._apply_journal_style(fig, journal_style)

        fig.update_layout(
            title_text="回归分析诊断图",
            showlegend=False,
            height=400,
        )

        chart_payload = cast(dict[str, Any], fig.to_plotly_json())
        chart_payload["chart_type"] = "regression_diagnostics"
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
        regression_result: dict[str, Any],
        assumptions: dict[str, Any],
        residual_diagnostics: dict[str, Any],
        sample_size: int,
        dependent_var: str,
        independent_vars: list[str],
    ) -> dict[str, str]:
        """生成 APA 格式报告。"""
        if "error" in regression_result:
            return {
                "summary": f"回归分析失败: {regression_result['error']}",
                "statistics": "",
                "details": "",
            }

        r_squared = regression_result.get("r_squared")
        adj_r_squared = regression_result.get("adj_r_squared")
        f_stat = regression_result.get("f_statistic")
        f_pvalue = regression_result.get("f_pvalue")

        # 构建模型拟合描述
        if f_stat is not None and f_pvalue is not None:
            sig_marker = "***" if f_pvalue < 0.001 else "**" if f_pvalue < 0.01 else "*" if f_pvalue < 0.05 else ""
            model_fit = (
                f"R² = {r_squared:.3f}, 调整 R² = {adj_r_squared:.3f}, "
                f"F = {f_stat:.2f}, p = {f_pvalue:.4f}{sig_marker}"
            )
        else:
            model_fit = f"R² = {r_squared:.3f}"

        # 显著系数
        sig_coeffs = []
        coeffs = regression_result.get("coefficients", {})
        for var, info in coeffs.items():
            if var == "const":
                continue
            if info.get("significant"):
                coef = info.get("coefficient", 0)
                pval = info.get("p_value", 1)
                sig_marker = "***" if pval < 0.001 else "**" if pval < 0.01 else "*"
                sig_coeffs.append(f"{var}: β = {coef:.3f}{sig_marker}")

        # 假设检验结果
        assumption_notes = []
        if "normality" in assumptions:
            norm = assumptions["normality"]
            if norm.get("satisfied"):
                assumption_notes.append("因变量满足正态性假设")
            else:
                assumption_notes.append("因变量可能不满足正态性假设，结果解释需谨慎")

        outlier_count = residual_diagnostics.get("outliers", {}).get("count", 0)
        if outlier_count > 0:
            assumption_notes.append(f"检测到 {outlier_count} 个潜在异常值")

        # 组装摘要
        summary_parts = [
            f"以 {dependent_var} 为因变量，"
            f"{'、'.join(independent_vars)} 为自变量建立回归模型（n={sample_size}）。",
            model_fit + "。",
        ]

        if sig_coeffs:
            summary_parts.append(f"显著预测因子: {'; '.join(sig_coeffs)}。")

        if assumption_notes:
            summary_parts.append(f"[诊断] {'; '.join(assumption_notes)}。")

        summary = " ".join(summary_parts)

        # 详细统计
        stats_lines = ["回归系数:"]
        for var, info in coeffs.items():
            coef = info.get("coefficient", 0)
            if var == "const":
                stats_lines.append(f"  截距: {coef:.4f}")
            else:
                pval = info.get("p_value")
                tstat = info.get("t_statistic")
                if pval is not None and tstat is not None:
                    sig = "***" if pval < 0.001 else "**" if pval < 0.01 else "*" if pval < 0.05 else ""
                    stats_lines.append(
                        f"  {var}: β = {coef:.4f}, t = {tstat:.2f}, p = {pval:.4f}{sig}"
                    )
                else:
                    stats_lines.append(f"  {var}: β = {coef:.4f}")

        return {
            "summary": summary,
            "statistics": "\n".join(stats_lines),
            "details": f"样本量: {sample_size}, 自变量数: {len(independent_vars)}",
        }
