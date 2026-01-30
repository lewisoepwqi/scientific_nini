"""
Statistical analysis service.
"""
from typing import Dict, Any, List, Optional, Tuple
import warnings
import math

import pandas as pd
import numpy as np
from scipy import stats
from scipy.stats import (
    ttest_1samp, ttest_ind, ttest_rel,
    f_oneway, kruskal, mannwhitneyu, wilcoxon,
    chi2_contingency, pearsonr, spearmanr, kendalltau,
    shapiro, levene, bartlett
)
from statsmodels.stats.multicomp import pairwise_tukeyhsd
from statsmodels.stats.anova import anova_lm
from statsmodels.formula.api import ols, logit
from statsmodels.stats.outliers_influence import variance_inflation_factor
import statsmodels.api as sm

from app.core.exceptions import AnalysisException
from app.services.data_service import data_service
from app.schemas.analysis import (
    TTestResult, ANOVAResult, CorrelationResult,
    RegressionResult, DescriptiveStatsResult
)


class AnalysisService:
    """Service for statistical analysis."""
    
    def __init__(self):
        warnings.filterwarnings("ignore", category=RuntimeWarning)

    @staticmethod
    def _safe_float(value: Optional[float]) -> Optional[float]:
        """将非有限数值转换为 None。"""
        if value is None:
            return None
        if not math.isfinite(value):
            return None
        return float(value)

    @staticmethod
    def _ensure_finite(value: float, label: str) -> float:
        """确保数值有效，否则抛出异常。"""
        if value is None or not math.isfinite(value):
            raise AnalysisException(f"{label} 计算结果无效，请检查数据是否包含常数列或样本量不足")
        return float(value)
    
    # ==================== Descriptive Statistics ====================
    
    def descriptive_stats(
        self,
        df: pd.DataFrame,
        columns: Optional[List[str]] = None,
        group_by: Optional[str] = None,
        include_percentiles: List[float] = [0.25, 0.5, 0.75]
    ) -> List[DescriptiveStatsResult]:
        """Compute descriptive statistics."""
        if columns is None:
            columns = df.select_dtypes(include=[np.number]).columns.tolist()
        
        results = []
        
        if group_by and group_by in df.columns:
            # Grouped statistics
            for group_name, group_df in df.groupby(group_by):
                for col in columns:
                    if col in group_df.columns and pd.api.types.is_numeric_dtype(group_df[col]):
                        stats_result = self._compute_descriptive_stats(
                            group_df[col], col, include_percentiles
                        )
                        stats_result.column = f"{col} (group={group_name})"
                        results.append(stats_result)
        else:
            # Overall statistics
            for col in columns:
                if col in df.columns and pd.api.types.is_numeric_dtype(df[col]):
                    results.append(
                        self._compute_descriptive_stats(df[col], col, include_percentiles)
                    )
        
        return results
    
    def _compute_descriptive_stats(
        self,
        series: pd.Series,
        column_name: str,
        percentiles: List[float]
    ) -> DescriptiveStatsResult:
        """Compute descriptive statistics for a series."""
        non_null = series.dropna()
        
        result = DescriptiveStatsResult(
            column=column_name,
            count=len(non_null)
        )
        
        if len(non_null) > 0:
            result.mean = self._safe_float(non_null.mean())
            result.std = self._safe_float(non_null.std())
            result.min = self._safe_float(non_null.min())
            result.max = self._safe_float(non_null.max())
            result.median = self._safe_float(non_null.median())
            
            # Percentiles
            percentile_values = {}
            for p in percentiles:
                value = self._safe_float(non_null.quantile(p))
                if value is not None:
                    percentile_values[f"p{int(p*100)}"] = value
            result.percentiles = percentile_values or None
            
            # Distribution shape
            if len(non_null) >= 8:
                result.skewness = self._safe_float(non_null.skew())
                result.kurtosis = self._safe_float(non_null.kurtosis())
        
        return result
    
    # ==================== T-Tests ====================
    
    def t_test(
        self,
        df: pd.DataFrame,
        column: str,
        group_column: Optional[str] = None,
        test_value: Optional[float] = None,
        alternative: str = "two-sided",
        paired: bool = False,
        confidence_level: float = 0.95
    ) -> TTestResult:
        """Perform t-test."""
        if column not in df.columns:
            raise AnalysisException(f"Column '{column}' not found")
        
        alpha = 1 - confidence_level
        
        if group_column:
            # Independent samples t-test
            groups = df[group_column].dropna().unique()
            if len(groups) != 2:
                raise AnalysisException(
                    f"Group column must have exactly 2 groups, found {len(groups)}"
                )
            
            group1_data = df[df[group_column] == groups[0]][column].dropna()
            group2_data = df[df[group_column] == groups[1]][column].dropna()

            if len(group1_data) < 2 or len(group2_data) < 2:
                raise AnalysisException("每组至少需要 2 个观测值")
            
            if paired:
                if len(group1_data) != len(group2_data):
                    raise AnalysisException(
                        "Paired t-test requires equal group sizes"
                    )
                statistic, pvalue = ttest_rel(group1_data, group2_data, alternative=alternative)
            else:
                statistic, pvalue = ttest_ind(
                    group1_data, group2_data,
                    alternative=alternative, equal_var=False
                )
            
            # Effect size (Cohen's d)
            mean_diff = group1_data.mean() - group2_data.mean()
            pooled_std = np.sqrt(
                ((len(group1_data) - 1) * group1_data.var() +
                 (len(group2_data) - 1) * group2_data.var()) /
                (len(group1_data) + len(group2_data) - 2)
            )
            cohens_d = mean_diff / pooled_std if pooled_std > 0 else 0
            
            # Confidence interval
            se = np.sqrt(
                group1_data.var() / len(group1_data) +
                group2_data.var() / len(group2_data)
            )
            df_degrees = len(group1_data) + len(group2_data) - 2
            t_crit = stats.t.ppf(1 - alpha/2, df_degrees)
            ci_lower = mean_diff - t_crit * se
            ci_upper = mean_diff + t_crit * se
            
            return TTestResult(
                statistic=self._ensure_finite(statistic, "t 统计量"),
                pvalue=self._ensure_finite(pvalue, "p 值"),
                df=self._ensure_finite(df_degrees, "自由度"),
                confidence_interval=[
                    self._ensure_finite(ci_lower, "置信区间下限"),
                    self._ensure_finite(ci_upper, "置信区间上限")
                ],
                effect_size=self._safe_float(cohens_d),
                mean_diff=self._safe_float(mean_diff),
                std_diff=self._safe_float(np.sqrt(group1_data.var() + group2_data.var()))
            )
        
        elif test_value is not None:
            # One-sample t-test
            data = df[column].dropna()
            if len(data) < 2:
                raise AnalysisException("至少需要 2 个观测值进行 t 检验")
            statistic, pvalue = ttest_1samp(data, test_value, alternative=alternative)
            
            # Confidence interval
            mean = data.mean()
            se = data.std() / np.sqrt(len(data))
            df_degrees = len(data) - 1
            t_crit = stats.t.ppf(1 - alpha/2, df_degrees)
            ci_lower = mean - t_crit * se
            ci_upper = mean + t_crit * se
            
            return TTestResult(
                statistic=self._ensure_finite(statistic, "t 统计量"),
                pvalue=self._ensure_finite(pvalue, "p 值"),
                df=self._ensure_finite(df_degrees, "自由度"),
                confidence_interval=[
                    self._ensure_finite(ci_lower, "置信区间下限"),
                    self._ensure_finite(ci_upper, "置信区间上限")
                ],
                mean_diff=self._safe_float(mean - test_value)
            )
        
        else:
            raise AnalysisException(
                "Either group_column or test_value must be specified"
            )
    
    # ==================== ANOVA ====================
    
    def one_way_anova(
        self,
        df: pd.DataFrame,
        value_column: str,
        group_column: str,
        post_hoc: bool = True,
        post_hoc_method: str = "tukey"
    ) -> ANOVAResult:
        """Perform one-way ANOVA."""
        if value_column not in df.columns:
            raise AnalysisException(f"Value column '{value_column}' not found")
        if group_column not in df.columns:
            raise AnalysisException(f"Group column '{group_column}' not found")
        
        # Prepare data
        groups = []
        group_names = df[group_column].dropna().unique()
        
        for name in group_names:
            group_data = df[df[group_column] == name][value_column].dropna()
            if len(group_data) > 0:
                groups.append(group_data)
        
        if len(groups) < 2:
            raise AnalysisException("Need at least 2 groups for ANOVA")
        
        # Perform ANOVA
        f_stat, pvalue = f_oneway(*groups)
        
        # Calculate degrees of freedom and sum of squares
        n_total = sum(len(g) for g in groups)
        k = len(groups)
        
        grand_mean = np.concatenate(groups).mean()
        ss_between = sum(len(g) * (g.mean() - grand_mean) ** 2 for g in groups)
        ss_within = sum(((g - g.mean()) ** 2).sum() for g in groups)
        
        df_between = k - 1
        df_within = n_total - k
        if df_between <= 0 or df_within <= 0:
            raise AnalysisException("自由度不足，无法进行方差分析")
        ms_between = ss_between / df_between
        ms_within = ss_within / df_within
        
        # Effect size (eta-squared)
        ss_total = ss_between + ss_within
        eta_squared = ss_between / ss_total if ss_total > 0 else 0
        
        result = ANOVAResult(
            f_statistic=self._ensure_finite(f_stat, "F 统计量"),
            pvalue=self._ensure_finite(pvalue, "p 值"),
            df_between=self._ensure_finite(df_between, "组间自由度"),
            df_within=self._ensure_finite(df_within, "组内自由度"),
            sum_sq_between=self._ensure_finite(ss_between, "组间平方和"),
            sum_sq_within=self._ensure_finite(ss_within, "组内平方和"),
            mean_sq_between=self._ensure_finite(ms_between, "组间均方"),
            mean_sq_within=self._ensure_finite(ms_within, "组内均方"),
            eta_squared=self._safe_float(eta_squared)
        )
        
        # Post-hoc tests
        if post_hoc and pvalue < 0.05:
            result.post_hoc_results = self._post_hoc_test(
                df, value_column, group_column, post_hoc_method
            )
        
        return result
    
    def _post_hoc_test(
        self,
        df: pd.DataFrame,
        value_column: str,
        group_column: str,
        method: str = "tukey"
    ) -> List[Dict[str, Any]]:
        """执行事后检验。"""
        if method == "tukey":
            # 移除含有缺失值的行
            clean_df = df[[value_column, group_column]].dropna()

            tukey = pairwise_tukeyhsd(
                endog=clean_df[value_column],
                groups=clean_df[group_column],
                alpha=0.05
            )

            results = []
            n_groups = len(tukey.groupsunique)
            comparison_idx = 0

            # 遍历所有配对比较
            for i in range(n_groups):
                for j in range(i + 1, n_groups):
                    group1 = tukey.groupsunique[i]
                    group2 = tukey.groupsunique[j]

                    # 直接使用 tukey 对象的属性获取结果
                    mean_diff = self._safe_float(tukey.meandiffs[comparison_idx])
                    pvalue = self._safe_float(tukey.pvalues[comparison_idx])
                    ci_lower = self._safe_float(tukey.confint[comparison_idx, 0])
                    ci_upper = self._safe_float(tukey.confint[comparison_idx, 1])
                    reject = bool(tukey.reject[comparison_idx])

                    if mean_diff is not None and pvalue is not None:
                        results.append({
                            "group1": str(group1),
                            "group2": str(group2),
                            "mean_diff": mean_diff,
                            "pvalue": pvalue,
                            "reject": reject,
                            "ci_lower": ci_lower,
                            "ci_upper": ci_upper
                        })

                    comparison_idx += 1

            return results

        return []
    
    # ==================== Correlation ====================
    
    def correlation(
        self,
        df: pd.DataFrame,
        columns: List[str],
        method: str = "pearson"
    ) -> CorrelationResult:
        """Compute correlation matrix."""
        # Validate columns
        for col in columns:
            if col not in df.columns:
                raise AnalysisException(f"Column '{col}' not found")
            if not pd.api.types.is_numeric_dtype(df[col]):
                raise AnalysisException(f"Column '{col}' must be numeric")
        
        # Select data
        data = df[columns].dropna()
        
        if len(data) < 3:
            raise AnalysisException("Need at least 3 observations for correlation")
        
        # Compute correlation
        corr_matrix = data.corr(method=method)
        
        # Compute p-values
        pvalue_matrix = {}
        for col1 in columns:
            pvalue_matrix[col1] = {}
            for col2 in columns:
                if col1 == col2:
                    pvalue_matrix[col1][col2] = 0.0
                else:
                    x = data[col1].values
                    y = data[col2].values
                    
                    if method == "pearson":
                        _, pval = pearsonr(x, y)
                    elif method == "spearman":
                        _, pval = spearmanr(x, y)
                    elif method == "kendall":
                        _, pval = kendalltau(x, y)
                    else:
                        pval = 1.0
                    
                    pvalue_matrix[col1][col2] = self._ensure_finite(
                        pval,
                        f"{col1} 与 {col2} 的相关性 p 值"
                    )
        
        # Convert correlation matrix to dict
        corr_dict = {
            col: {
                col2: self._ensure_finite(
                    corr_matrix.loc[col, col2],
                    f"{col} 与 {col2} 的相关系数"
                )
                for col2 in columns
            }
            for col in columns
        }
        
        return CorrelationResult(
            correlation_matrix=corr_dict,
            pvalue_matrix=pvalue_matrix,
            method=method,
            sample_size=len(data)
        )
    
    # ==================== Regression ====================
    
    def linear_regression(
        self,
        df: pd.DataFrame,
        dependent_var: str,
        independent_vars: List[str],
        include_intercept: bool = True
    ) -> RegressionResult:
        """Perform linear regression."""
        # Validate columns
        if dependent_var not in df.columns:
            raise AnalysisException(f"Dependent variable '{dependent_var}' not found")
        
        for var in independent_vars:
            if var not in df.columns:
                raise AnalysisException(f"Independent variable '{var}' not found")
        
        # Prepare data
        all_vars = [dependent_var] + independent_vars
        data = df[all_vars].dropna()
        
        if len(data) < len(independent_vars) + 2:
            raise AnalysisException("Insufficient data for regression")
        
        # Fit model
        X = data[independent_vars]
        y = data[dependent_var]
        
        if include_intercept:
            X = sm.add_constant(X)
        
        model = sm.OLS(y, X).fit()
        
        # Extract coefficients
        coefficients = {}
        for var in model.params.index:
            coefficients[var] = {
                "estimate": self._ensure_finite(model.params[var], f"{var} 系数估计"),
                "std_error": self._ensure_finite(model.bse[var], f"{var} 标准误"),
                "t_statistic": self._ensure_finite(model.tvalues[var], f"{var} t 统计量"),
                "pvalue": self._ensure_finite(model.pvalues[var], f"{var} p 值"),
                "ci_lower": self._ensure_finite(model.conf_int()[0][var], f"{var} 置信区间下限"),
                "ci_upper": self._ensure_finite(model.conf_int()[1][var], f"{var} 置信区间上限")
            }
        
        # Residuals summary
        residuals_summary = {
            "mean": self._safe_float(model.resid.mean()),
            "std": self._safe_float(model.resid.std()),
            "min": self._safe_float(model.resid.min()),
            "max": self._safe_float(model.resid.max())
        }
        if any(value is None for value in residuals_summary.values()):
            residuals_summary = None
        
        return RegressionResult(
            r_squared=self._ensure_finite(model.rsquared, "R²"),
            adjusted_r_squared=self._ensure_finite(model.rsquared_adj, "调整后 R²"),
            f_statistic=self._ensure_finite(model.fvalue, "F 统计量"),
            f_pvalue=self._ensure_finite(model.f_pvalue, "F 检验 p 值"),
            coefficients=coefficients,
            residuals_summary=residuals_summary
        )
    
    # ==================== Normality Tests ====================
    
    def shapiro_wilk(self, df: pd.DataFrame, column: str) -> Dict[str, Any]:
        """Perform Shapiro-Wilk normality test."""
        data = df[column].dropna()
        
        if len(data) < 3:
            raise AnalysisException("Need at least 3 observations for Shapiro-Wilk test")
        
        if len(data) > 5000:
            # Shapiro-Wilk is not reliable for large samples
            # Use Kolmogorov-Smirnov test instead
            statistic, pvalue = stats.kstest(data, "norm", args=(data.mean(), data.std()))
            test_name = "Kolmogorov-Smirnov"
        else:
            statistic, pvalue = shapiro(data)
            test_name = "Shapiro-Wilk"
        
        return {
            "test": test_name,
            "statistic": self._ensure_finite(statistic, f"{test_name} 统计量"),
            "pvalue": self._ensure_finite(pvalue, f"{test_name} p 值"),
            "is_normal": pvalue > 0.05,
            "sample_size": len(data)
        }
    
    # ==================== Assumption Tests ====================
    
    def test_equal_variance(
        self,
        df: pd.DataFrame,
        value_column: str,
        group_column: str
    ) -> Dict[str, Any]:
        """Test for equal variances (Levene's test)."""
        groups = []
        for name in df[group_column].unique():
            group_data = df[df[group_column] == name][value_column].dropna()
            if len(group_data) > 0:
                groups.append(group_data)
        
        if len(groups) < 2:
            raise AnalysisException("Need at least 2 groups")
        
        statistic, pvalue = levene(*groups)
        
        return {
            "test": "Levene",
            "statistic": self._ensure_finite(statistic, "Levene 统计量"),
            "pvalue": self._ensure_finite(pvalue, "Levene p 值"),
            "equal_variance": pvalue > 0.05
        }


# Singleton instance
analysis_service = AnalysisService()
