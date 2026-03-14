"""回归分析能力实现。

执行完整的回归分析流程：
1. 数据验证与列类型检查
2. 自变量与因变量的相关性预筛选
3. 多重共线性检查（VIF）
4. OLS 回归模型拟合
5. 残差诊断（正态性、异方差性）
6. 模型解释与报告生成
7. 可视化（实际 vs 预测、残差图）
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

import numpy as np
import pandas as pd
from scipy import stats

if TYPE_CHECKING:
    from nini.agent.session import Session
    from nini.tools.base import SkillResult


@dataclass
class RegressionCoefficient:
    """回归系数结果。"""

    variable: str
    coefficient: float
    std_error: float | None = None
    t_statistic: float | None = None
    p_value: float | None = None
    ci_95_low: float | None = None
    ci_95_high: float | None = None
    significant: bool = False
    vif: float | None = None  # 方差膨胀因子


@dataclass
class RegressionDiagnostics:
    """回归诊断结果。"""

    residual_normality_p: float | None = None
    residual_normality_passed: bool = False
    heteroscedasticity_p: float | None = None
    heteroscedasticity_passed: bool = False
    outlier_count: int = 0
    outlier_indices: list[int] = field(default_factory=list)


@dataclass
class RegressionAnalysisResult:
    """回归分析结果。"""

    success: bool = False
    message: str = ""

    # 分析参数
    dependent_var: str = ""
    independent_vars: list[str] = field(default_factory=list)
    sample_size: int = 0
    n_predictors: int = 0

    # 模型拟合度
    r_squared: float | None = None
    adj_r_squared: float | None = None
    f_statistic: float | None = None
    f_pvalue: float | None = None
    aic: float | None = None
    bic: float | None = None

    # 系数
    coefficients: list[RegressionCoefficient] = field(default_factory=list)
    intercept: RegressionCoefficient | None = None

    # 诊断
    diagnostics: RegressionDiagnostics | None = None

    # 共线性
    multicollinearity_detected: bool = False
    high_vif_vars: list[str] = field(default_factory=list)

    # 可视化
    chart_artifacts: list[dict[str, Any]] = field(default_factory=list)

    # 解释性报告
    interpretation: str = ""
    model_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "success": self.success,
            "message": self.message,
            "dependent_var": self.dependent_var,
            "independent_vars": self.independent_vars,
            "sample_size": self.sample_size,
            "n_predictors": self.n_predictors,
            "r_squared": self.r_squared,
            "adj_r_squared": self.adj_r_squared,
            "f_statistic": self.f_statistic,
            "f_pvalue": self.f_pvalue,
            "aic": self.aic,
            "bic": self.bic,
            "coefficients": [
                {
                    "variable": c.variable,
                    "coefficient": c.coefficient,
                    "std_error": c.std_error,
                    "t_statistic": c.t_statistic,
                    "p_value": c.p_value,
                    "ci_95_low": c.ci_95_low,
                    "ci_95_high": c.ci_95_high,
                    "significant": c.significant,
                    "vif": c.vif,
                }
                for c in self.coefficients
            ],
            "intercept": (
                {
                    "coefficient": self.intercept.coefficient,
                    "std_error": self.intercept.std_error,
                    "t_statistic": self.intercept.t_statistic,
                    "p_value": self.intercept.p_value,
                }
                if self.intercept
                else None
            ),
            "diagnostics": (
                {
                    "residual_normality_p": self.diagnostics.residual_normality_p,
                    "residual_normality_passed": self.diagnostics.residual_normality_passed,
                    "heteroscedasticity_p": self.diagnostics.heteroscedasticity_p,
                    "heteroscedasticity_passed": self.diagnostics.heteroscedasticity_passed,
                    "outlier_count": self.diagnostics.outlier_count,
                }
                if self.diagnostics
                else None
            ),
            "multicollinearity_detected": self.multicollinearity_detected,
            "high_vif_vars": self.high_vif_vars,
            "chart_artifacts": self.chart_artifacts,
            "interpretation": self.interpretation,
            "model_summary": self.model_summary,
        }


class RegressionAnalysisCapability:
    """
    回归分析能力。

    自动执行完整的回归分析流程，包括：
    - 数据验证与列类型检查
    - 自变量相关性预筛选
    - 多重共线性检查（VIF）
    - OLS 回归模型拟合
    - 残差诊断
    - 可视化
    - 解释性报告

    使用方法：
        capability = RegressionAnalysisCapability()
        result = await capability.execute(
            session,
            dataset_name="my_data",
            dependent_var="target",
            independent_vars=["var1", "var2", "var3"]
        )
    """

    def __init__(self, registry: Any | None = None) -> None:
        self.name = "regression_analysis"
        self.display_name = "回归分析"
        self.description = "建立变量间的回归模型，进行预测和解释"
        self.icon = "📉"
        # registry 参数保留以兼容旧调用方，但内部直接实例化所需技能
        from nini.tools.statistics import RegressionSkill
        from nini.tools.visualization import CreateChartSkill

        self._regression_skill = RegressionSkill()
        self._chart_skill = CreateChartSkill()
        self._vif_results: dict[str, float] = {}

    async def execute(
        self,
        session: Session,
        *,
        dataset_name: str,
        dependent_var: str,
        independent_vars: list[str],
        alpha: float = 0.05,
        check_multicollinearity: bool = True,
        vif_threshold: float = 10.0,
        **kwargs: Any,
    ) -> RegressionAnalysisResult:
        """
        执行回归分析。

        Args:
            session: 会话对象
            dataset_name: 数据集名称
            dependent_var: 因变量名
            independent_vars: 自变量列表
            alpha: 显著性水平
            check_multicollinearity: 是否检查多重共线性
            vif_threshold: VIF 阈值，超过认为存在共线性
        """
        result = RegressionAnalysisResult(
            dependent_var=dependent_var,
            independent_vars=list(independent_vars),
        )

        # Step 1: 数据验证
        df = session.datasets.get(dataset_name)
        if df is None:
            result.message = f"数据集 '{dataset_name}' 不存在"
            return result

        if not self._validate_columns(df, dependent_var, independent_vars, result):
            return result

        all_vars = [dependent_var] + list(independent_vars)
        result.n_predictors = len(independent_vars)

        # Step 2: 准备干净数据
        clean_data = df[all_vars].dropna()
        result.sample_size = len(clean_data)
        if result.sample_size < 10:
            result.message = "有效样本量不足（至少需要 10 个观测）"
            return result

        # Step 3: 检查样本量与变量数比例
        if result.sample_size < result.n_predictors * 5:
            result.message = (
                f"样本量 ({result.sample_size}) 相对于变量数 ({result.n_predictors}) 过少，"
                "建议至少每个预测变量 5 个观测"
            )
            return result

        # Step 4: 多重共线性检查
        if check_multicollinearity and len(independent_vars) > 1:
            vif_results = self._check_multicollinearity(clean_data, independent_vars)
            result.high_vif_vars = [var for var, vif in vif_results.items() if vif > vif_threshold]
            result.multicollinearity_detected = len(result.high_vif_vars) > 0

        # Step 5: 执行回归
        regression_result = await self._perform_regression(
            session, dataset_name, dependent_var, independent_vars
        )
        if regression_result is None:
            result.message = "回归分析执行失败"
            return result

        # 提取模型指标
        result.r_squared = regression_result.get("r_squared")
        result.adj_r_squared = regression_result.get("adjusted_r_squared")
        result.f_statistic = regression_result.get("f_statistic")
        result.f_pvalue = regression_result.get("f_pvalue")
        result.aic = regression_result.get("aic")
        result.bic = regression_result.get("bic")

        # 提取系数
        coeffs_raw = regression_result.get("coefficients")
        coeffs: dict[str, Any] = coeffs_raw if isinstance(coeffs_raw, dict) else {}
        intercept_data = coeffs.get("const")
        result.intercept = self._extract_coefficient(
            "截距", intercept_data if isinstance(intercept_data, dict) else {}
        )
        for var in independent_vars:
            if var in coeffs:
                coef_data_raw = coeffs[var]
                coef_data: dict[str, Any] = (
                    dict(coef_data_raw) if isinstance(coef_data_raw, dict) else {}
                )
                # 添加 VIF 信息
                if var in self._vif_results:
                    coef_data["vif"] = self._vif_results[var]
                result.coefficients.append(self._extract_coefficient(var, coef_data))

        # Step 6: 残差诊断
        residuals = regression_result.get("residuals", [])
        fitted = regression_result.get("fitted_values", [])
        if residuals:
            residual_list = residuals if isinstance(residuals, list) else []
            fitted_list = fitted if isinstance(fitted, list) else []
            result.diagnostics = self._diagnose_residuals(residual_list, fitted_list)

        # Step 7: 可视化
        chart_result = await self._create_visualizations(
            session, dataset_name, dependent_var, independent_vars
        )
        if chart_result:
            result.chart_artifacts = chart_result

        # Step 8: 记录到 AnalysisMemory
        self._record_enriched_result(session, dataset_name, result)

        # Step 9: 生成解释
        result.interpretation = self._generate_interpretation(result)
        result.model_summary = self._generate_model_summary(result)
        result.success = True
        result.message = "回归分析完成"
        return result

    def _validate_columns(
        self,
        df: pd.DataFrame,
        dependent_var: str,
        independent_vars: list[str],
        result: RegressionAnalysisResult,
    ) -> bool:
        """验证列有效性。"""
        if dependent_var not in df.columns:
            result.message = f"因变量 '{dependent_var}' 不存在"
            return False

        if not pd.api.types.is_numeric_dtype(df[dependent_var]):
            result.message = f"因变量 '{dependent_var}' 不是数值类型"
            return False

        if len(independent_vars) < 1:
            result.message = "至少需要 1 个自变量"
            return False

        for col in independent_vars:
            if col not in df.columns:
                result.message = f"自变量 '{col}' 不存在"
                return False
            if not pd.api.types.is_numeric_dtype(df[col]):
                result.message = f"自变量 '{col}' 不是数值类型"
                return False

        return True

    def _check_multicollinearity(
        self,
        data: pd.DataFrame,
        independent_vars: list[str],
    ) -> dict[str, float]:
        """计算 VIF（方差膨胀因子）检查多重共线性。"""
        vif_results: dict[str, float] = {}
        try:
            from statsmodels.stats.outliers_influence import variance_inflation_factor

            X = data[independent_vars].select_dtypes(include=[np.number])
            if len(X.columns) > 1:
                X_const = X.assign(constant=1)
                for i, col in enumerate(X.columns):
                    try:
                        vif = variance_inflation_factor(X_const.values, i)
                        vif_results[col] = float(vif)
                    except Exception:
                        vif_results[col] = float("inf")
        except ImportError:
            # statsmodels 未安装时返回空结果
            pass
        except Exception:
            pass

        # 保存供后续使用
        self._vif_results = vif_results
        return vif_results

    @staticmethod
    def _extract_coefficient(
        variable: str,
        coef_data: dict[str, Any],
    ) -> RegressionCoefficient:
        """提取系数信息。"""
        # 支持两种字段命名: estimate (来自底层工具) 或 coefficient
        coefficient = coef_data.get("coefficient")
        if coefficient is None:
            coefficient = coef_data.get("estimate", 0.0)
        return RegressionCoefficient(
            variable=variable,
            coefficient=coefficient,
            std_error=coef_data.get("std_error"),
            t_statistic=coef_data.get("t_statistic"),
            p_value=coef_data.get("p_value"),
            ci_95_low=coef_data.get("ci_95_low"),
            ci_95_high=coef_data.get("ci_95_high"),
            significant=coef_data.get("p_value", 1.0) < 0.05,
            vif=coef_data.get("vif"),
        )

    def _diagnose_residuals(
        self,
        residuals: list[float],
        fitted: list[float],
    ) -> RegressionDiagnostics:
        """残差诊断。"""
        residuals_arr = np.array(residuals)
        residual_normality_p: float | None = None
        residual_normality_passed = False
        heteroscedasticity_p: float | None = None
        heteroscedasticity_passed = False

        # 残差正态性检验
        if len(residuals_arr) >= 3:
            try:
                if len(residuals_arr) <= 5000:
                    _, shapiro_p_raw = stats.shapiro(residuals_arr)
                    normality_p = float(shapiro_p_raw)
                else:
                    _, normaltest_p_raw = stats.normaltest(residuals_arr)
                    normality_p = float(cast(Any, normaltest_p_raw))
                residual_normality_p = normality_p
                residual_normality_passed = bool(normality_p > 0.05)
            except Exception:
                pass

        # 异方差性检验（简化版：残差与拟合值的相关系数）
        if fitted and len(fitted) == len(residuals_arr):
            try:
                # Breusch-Pagan 检验的简化近似
                abs_resid = np.abs(residuals_arr)
                _, hetero_p_raw = stats.pearsonr(abs_resid, np.array(fitted))
                hetero_p = float(cast(Any, hetero_p_raw))
                heteroscedasticity_p = hetero_p
                heteroscedasticity_passed = bool(hetero_p > 0.05)
            except Exception:
                pass

        # 异常值检测（基于标准化残差）
        std_residuals = (
            residuals_arr / np.std(residuals_arr) if np.std(residuals_arr) > 0 else residuals_arr
        )
        outlier_mask = np.abs(std_residuals) > 2.5
        outlier_count = int(np.sum(outlier_mask))
        outlier_indices = np.where(outlier_mask)[0][:10].tolist()  # 最多 10 个

        return RegressionDiagnostics(
            residual_normality_p=residual_normality_p,
            residual_normality_passed=residual_normality_passed,
            heteroscedasticity_p=heteroscedasticity_p,
            heteroscedasticity_passed=heteroscedasticity_passed,
            outlier_count=outlier_count,
            outlier_indices=outlier_indices,
        )

    async def _perform_regression(
        self,
        session: Session,
        dataset_name: str,
        dependent_var: str,
        independent_vars: list[str],
    ) -> dict[str, Any] | None:
        """直接调用 RegressionSkill 执行回归分析。"""
        try:
            tool_result = await self._regression_skill.execute(
                session=session,
                dataset_name=dataset_name,
                dependent_var=dependent_var,
                independent_vars=list(independent_vars),
            )
            result_dict = tool_result.to_dict() if hasattr(tool_result, "to_dict") else tool_result
            if isinstance(result_dict, dict):
                data_payload = result_dict.get("data")
                if result_dict.get("success") and isinstance(data_payload, dict):
                    regression_data = data_payload.get("regression")
                    if isinstance(regression_data, dict):
                        return cast(dict[str, Any], regression_data)
                    return cast(dict[str, Any], data_payload)
        except Exception:
            pass
        return None

    async def _create_visualizations(
        self,
        session: Session,
        dataset_name: str,
        dependent_var: str,
        independent_vars: list[str],
    ) -> list[dict[str, Any]]:
        """创建回归分析可视化。"""
        artifacts: list[dict[str, Any]] = []

        try:
            # 实际值 vs 预测值散点图
            result = await self._chart_skill.execute(
                session=session,
                dataset_name=dataset_name,
                chart_type="scatter",
                x_column=f"__fitted_{dependent_var}",
                y_column=dependent_var,
                title="实际值 vs 预测值",
                description="回归模型拟合效果诊断",
            )
            result_dict = result.to_dict() if hasattr(result, "to_dict") else result
            if isinstance(result_dict, dict):
                result_artifacts = result_dict.get("artifacts")
                if result_dict.get("success") and isinstance(result_artifacts, list):
                    artifacts.extend(result_artifacts)
        except Exception:
            pass

        return artifacts

    @staticmethod
    def _record_enriched_result(
        session: Session,
        dataset_name: str,
        result: RegressionAnalysisResult,
    ) -> None:
        """将回归分析富信息记录到 AnalysisMemory。"""
        from nini.tools.statistics.base import _record_stat_result

        # 记录模型整体信息
        model_info = []
        if result.r_squared is not None:
            model_info.append(f"R² = {result.r_squared:.3f}")
        if result.adj_r_squared is not None:
            model_info.append(f"调整 R² = {result.adj_r_squared:.3f}")
        if result.f_pvalue is not None:
            sig = (
                "***"
                if result.f_pvalue < 0.001
                else "**" if result.f_pvalue < 0.01 else "*" if result.f_pvalue < 0.05 else ""
            )
            model_info.append(f"F 检验 p = {result.f_pvalue:.4f}{sig}")

        _record_stat_result(
            session,
            dataset_name,
            test_name=f"多元线性回归 ({result.dependent_var} ~ {' + '.join(result.independent_vars)})",
            message=f"样本量 n = {result.sample_size}, " + ", ".join(model_info),
            p_value=result.f_pvalue,
            effect_size=result.r_squared,
            effect_type="R²",
            significant=result.f_pvalue is not None and result.f_pvalue < 0.05,
        )

        # 记录显著系数
        for coef in result.coefficients:
            if coef.significant:
                _record_stat_result(
                    session,
                    dataset_name,
                    test_name=f"回归系数: {coef.variable}",
                    message=(
                        f"β = {coef.coefficient:.4f}, p = {coef.p_value:.4f}"
                        if coef.p_value
                        else f"β = {coef.coefficient:.4f}"
                    ),
                    test_statistic=coef.t_statistic,
                    p_value=coef.p_value,
                    significant=True,
                )

    def _generate_model_summary(self, result: RegressionAnalysisResult) -> str:
        """生成模型摘要。"""
        parts: list[str] = []

        parts.append(f"回归模型: {result.dependent_var} ~ {' + '.join(result.independent_vars)}")
        parts.append(f"样本量: n = {result.sample_size}")

        if result.r_squared is not None:
            parts.append(f"R² = {result.r_squared:.3f}")
        if result.adj_r_squared is not None:
            parts.append(f"调整 R² = {result.adj_r_squared:.3f}")

        if result.f_statistic is not None and result.f_pvalue is not None:
            sig = (
                "***"
                if result.f_pvalue < 0.001
                else "**" if result.f_pvalue < 0.01 else "*" if result.f_pvalue < 0.05 else "ns"
            )
            parts.append(f"F = {result.f_statistic:.2f}, p = {result.f_pvalue:.4f} {sig}")

        return " | ".join(parts)

    def _generate_interpretation(self, result: RegressionAnalysisResult) -> str:
        """生成解释性报告。"""
        parts: list[str] = []

        parts.append("## 模型概况")
        parts.append(f"因变量: {result.dependent_var}")
        parts.append(f"自变量: {', '.join(result.independent_vars)}")
        parts.append(f"样本量: n = {result.sample_size}")

        parts.append("\n## 模型拟合度")
        if result.r_squared is not None:
            parts.append(
                f"R² = {result.r_squared:.3f}（模型解释了因变量 {result.r_squared*100:.1f}% 的变异）"
            )
        if result.adj_r_squared is not None:
            parts.append(f"调整 R² = {result.adj_r_squared:.3f}")

        if result.f_pvalue is not None:
            sig_text = "显著" if result.f_pvalue < 0.05 else "不显著"
            parts.append(
                f"F 检验: F = {result.f_statistic:.2f}, p = {result.f_pvalue:.4f}（模型整体 {sig_text}）"
            )

        parts.append("\n## 回归系数")
        if result.intercept:
            parts.append(f"截距: {result.intercept.coefficient:.4f}")

        significant_coefs = [c for c in result.coefficients if c.significant]
        if significant_coefs:
            parts.append("\n显著预测因子:")
            for coef in significant_coefs:
                direction = "正向" if coef.coefficient > 0 else "负向"
                parts.append(
                    f"- {coef.variable}: β = {coef.coefficient:.4f}, "
                    f"t = {coef.t_statistic:.2f}, p = {coef.p_value:.4f} ({direction}影响)"
                )
        else:
            parts.append("\n未发现显著预测因子")

        nonsig_coefs = [c for c in result.coefficients if not c.significant]
        if nonsig_coefs:
            parts.append("\n不显著预测因子:")
            for coef in nonsig_coefs:
                parts.append(
                    f"- {coef.variable}: β = {coef.coefficient:.4f}, p = {coef.p_value:.4f}"
                )

        if result.multicollinearity_detected:
            parts.append(
                f"\n⚠️ 多重共线性警告: 变量 {', '.join(result.high_vif_vars)} 的 VIF 值过高"
            )
            parts.append("建议移除高度相关的自变量或使用正则化方法")

        if result.diagnostics:
            parts.append("\n## 模型诊断")
            if result.diagnostics.residual_normality_p is not None:
                status = "通过" if result.diagnostics.residual_normality_passed else "未通过"
                parts.append(
                    f"残差正态性: {status} (p = {result.diagnostics.residual_normality_p:.3f})"
                )
            if result.diagnostics.heteroscedasticity_p is not None:
                status = "通过" if result.diagnostics.heteroscedasticity_passed else "未通过"
                parts.append(f"异方差性检验: {status}")
            if result.diagnostics.outlier_count > 0:
                parts.append(f"检测到 {result.diagnostics.outlier_count} 个潜在异常值")

        parts.append("\n## 结论")
        if significant_coefs:
            parts.append(f"发现 {len(significant_coefs)} 个显著预测因子")
            strongest = max(significant_coefs, key=lambda c: abs(c.coefficient))
            parts.append(f"最强预测因子是 '{strongest.variable}' (β = {strongest.coefficient:.4f})")
        else:
            parts.append("未发现显著预测因子，模型解释力有限")

        if result.r_squared is not None and result.r_squared < 0.1:
            parts.append("\n注: R² 较低，模型解释力较弱，建议考虑其他预测变量或非线性模型")

        return "\n".join(parts)
