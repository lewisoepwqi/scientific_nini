"""统计结果智能解读模块测试。"""

from __future__ import annotations

import pytest

from nini.skills.interpretation import (
    ResultInterpreter,
    interpret_result,
)


class TestResultInterpreter:
    """测试 ResultInterpreter 类。"""

    def test_interpret_t_test_independent_significant(self):
        """测试独立样本 t 检验显著结果解读。"""
        result = {
            "test_type": "独立样本 t 检验",
            "t_statistic": 2.5,
            "p_value": 0.015,
            "significant": True,
            "mean1": 15.2,
            "mean2": 12.8,
            "cohens_d": 0.8,
            "n1": 30,
            "n2": 30,
        }

        interpretation = ResultInterpreter.interpret_t_test(result)

        assert "独立样本 t 检验解读" in interpretation
        assert "p = 0.0150" in interpretation
        assert "显著性" in interpretation
        assert "15.200" in interpretation
        assert "12.800" in interpretation
        assert "Cohen's d = 0.800" in interpretation
        assert "大效应" in interpretation

    def test_interpret_t_test_not_significant(self):
        """测试 t 检验不显著结果解读。"""
        result = {
            "test_type": "独立样本 t 检验",
            "t_statistic": 1.2,
            "p_value": 0.25,
            "significant": False,
            "mean1": 10.0,
            "mean2": 9.5,
            "cohens_d": 0.2,
            "n1": 30,
            "n2": 30,
        }

        interpretation = ResultInterpreter.interpret_t_test(result)

        assert "不具有统计学显著性" in interpretation
        assert "p = 0.2500" in interpretation
        assert "样本量不足" in interpretation or "效应量较小" in interpretation

    def test_interpret_t_test_one_sample(self):
        """测试单样本 t 检验解读。"""
        result = {
            "test_type": "单样本 t 检验",
            "t_statistic": 3.0,
            "p_value": 0.005,
            "significant": True,
            "mean": 15.5,
            "test_value": 10.0,
            "n": 25,
        }

        interpretation = ResultInterpreter.interpret_t_test(result)

        assert "单样本 t 检验解读" in interpretation
        assert "15.500" in interpretation
        assert "10.000" in interpretation

    def test_interpret_anova_significant(self):
        """测试 ANOVA 显著结果解读。"""
        result = {
            "f_statistic": 5.2,
            "p_value": 0.008,
            "significant": True,
            "df_between": 2,
            "df_within": 87,
            "eta_squared": 0.12,
            "n_groups": 3,
            "group_sizes": {"A": 30, "B": 30, "C": 30},
            "group_means": {"A": 10.0, "B": 12.5, "C": 11.0},
            "post_hoc": [
                {"group1": "A", "group2": "B", "mean_diff": -2.5, "p_value": 0.005, "significant": True},
                {"group1": "A", "group2": "C", "mean_diff": -1.0, "p_value": 0.35, "significant": False},
                {"group1": "B", "group2": "C", "mean_diff": 1.5, "p_value": 0.12, "significant": False},
            ],
        }

        interpretation = ResultInterpreter.interpret_anova(result)

        assert "方差分析" in interpretation
        assert "p = 0.0080" in interpretation
        assert "η² = 0.120" in interpretation
        assert "中等效应" in interpretation
        assert "Tukey HSD" in interpretation
        assert "A vs B" in interpretation

    def test_interpret_anova_not_significant(self):
        """测试 ANOVA 不显著结果解读。"""
        result = {
            "f_statistic": 1.5,
            "p_value": 0.23,
            "significant": False,
            "df_between": 2,
            "df_within": 87,
            "eta_squared": 0.03,
            "n_groups": 3,
            "group_sizes": {"A": 30, "B": 30, "C": 30},
            "group_means": {"A": 10.0, "B": 10.5, "C": 10.2},
        }

        interpretation = ResultInterpreter.interpret_anova(result)

        assert "不具有统计学显著性" in interpretation
        assert "小效应" in interpretation

    def test_interpret_correlation(self):
        """测试相关分析解读。"""
        result = {
            "method": "pearson",
            "sample_size": 100,
            "correlation_matrix": {
                "A": {"A": 1.0, "B": 0.65, "C": 0.15},
                "B": {"A": 0.65, "B": 1.0, "C": 0.25},
                "C": {"A": 0.15, "B": 0.25, "C": 1.0},
            },
            "pvalue_matrix": {
                "A": {"A": 0.0, "B": 0.001, "C": 0.15},
                "B": {"A": 0.001, "B": 0.0, "C": 0.02},
                "C": {"A": 0.15, "B": 0.02, "C": 0.0},
            },
        }

        interpretation = ResultInterpreter.interpret_correlation(result)

        assert "Pearson 相关分析解读" in interpretation
        assert "n = 100" in interpretation
        assert "A ↔ B" in interpretation
        assert "r = 0.650" in interpretation
        assert "强相关" in interpretation

    def test_interpret_regression(self):
        """测试回归分析解读。"""
        result = {
            "r_squared": 0.45,
            "adjusted_r_squared": 0.43,
            "f_statistic": 25.5,
            "f_pvalue": 0.0001,
            "n_observations": 100,
            "coefficients": {
                "const": {"estimate": 2.5, "p_value": 0.01},
                "X1": {"estimate": 0.8, "p_value": 0.001},
                "X2": {"estimate": -0.3, "p_value": 0.05},
            },
        }

        interpretation = ResultInterpreter.interpret_regression(result)

        assert "线性回归分析解读" in interpretation
        assert "R² = 0.4500" in interpretation
        assert "45.00%" in interpretation
        assert "X1" in interpretation
        assert "正向影响" in interpretation
        assert "X2" in interpretation
        assert "负向影响" in interpretation

    def test_interpret_mann_whitney(self):
        """测试 Mann-Whitney U 检验解读。"""
        result = {
            "test_type": "Mann-Whitney U 检验",
            "u_statistic": 350,
            "p_value": 0.03,
            "significant": True,
            "median1": 15.0,
            "median2": 12.0,
            "effect_size_r": 0.35,
            "n1": 30,
            "n2": 30,
        }

        interpretation = ResultInterpreter.interpret_mann_whitney(result)

        assert "Mann-Whitney U 检验解读" in interpretation
        assert "非参数检验" in interpretation
        assert "中位数" in interpretation
        assert "r = 0.350" in interpretation

    def test_interpret_kruskal_wallis(self):
        """测试 Kruskal-Wallis H 检验解读。"""
        result = {
            "test_type": "Kruskal-Wallis H 检验",
            "h_statistic": 8.5,
            "p_value": 0.015,
            "significant": True,
            "df": 2,
            "eta_squared": 0.08,
            "n_groups": 3,
            "group_medians": {"A": 10.0, "B": 15.0, "C": 12.0},
        }

        interpretation = ResultInterpreter.interpret_kruskal_wallis(result)

        assert "Kruskal-Wallis H 检验解读" in interpretation
        assert "H(2)" in interpretation
        assert "各组中位数" in interpretation
        assert "Dunn 检验" in interpretation


class TestEffectSizeInterpretation:
    """测试效应量解读。"""

    def test_interpret_cohens_d(self):
        """测试 Cohen's d 解读。"""
        assert ResultInterpreter._interpret_cohens_d(0.1) == "可忽略效应"
        assert ResultInterpreter._interpret_cohens_d(0.3) == "小效应"
        assert ResultInterpreter._interpret_cohens_d(0.6) == "中等效应"
        assert ResultInterpreter._interpret_cohens_d(0.9) == "大效应"

    def test_interpret_eta_squared(self):
        """测试 eta squared 解读。"""
        assert ResultInterpreter._interpret_eta_squared(0.005) == "可忽略效应"
        assert ResultInterpreter._interpret_eta_squared(0.03) == "小效应"
        assert ResultInterpreter._interpret_eta_squared(0.08) == "中等效应"
        assert ResultInterpreter._interpret_eta_squared(0.20) == "大效应"

    def test_interpret_correlation_strength(self):
        """测试相关系数强度解读。"""
        assert ResultInterpreter._interpret_correlation_strength(0.05) == "可忽略"
        assert ResultInterpreter._interpret_correlation_strength(0.2) == "弱相关"
        assert ResultInterpreter._interpret_correlation_strength(0.4) == "中等相关"
        assert ResultInterpreter._interpret_correlation_strength(0.6) == "强相关"
        assert ResultInterpreter._interpret_correlation_strength(0.8) == "极强相关"

    def test_interpret_r_squared(self):
        """测试 R² 解读。"""
        assert ResultInterpreter._interpret_r_squared(0.01) == "可忽略"
        assert ResultInterpreter._interpret_r_squared(0.05) == "小效应"
        assert ResultInterpreter._interpret_r_squared(0.18) == "中等效应"
        assert ResultInterpreter._interpret_r_squared(0.30) == "大效应"


class TestInterpretResultDispatcher:
    """测试 interpret_result 分发函数。"""

    def test_interpret_result_t_test(self):
        """测试 t_test 分发。"""
        result = {"test_type": "独立样本 t 检验", "p_value": 0.01, "significant": True}
        interpretation = interpret_result("t_test", result)
        assert "t 检验解读" in interpretation

    def test_interpret_result_anova(self):
        """测试 anova 分发。"""
        result = {"p_value": 0.01, "significant": True, "n_groups": 3}
        interpretation = interpret_result("anova", result)
        assert "方差分析" in interpretation

    def test_interpret_result_correlation(self):
        """测试 correlation 分发。"""
        result = {
            "method": "pearson",
            "sample_size": 50,
            "correlation_matrix": {"A": {"A": 1.0, "B": 0.5}, "B": {"A": 0.5, "B": 1.0}},
            "pvalue_matrix": {"A": {"A": 0.0, "B": 0.01}, "B": {"A": 0.01, "B": 0.0}},
        }
        interpretation = interpret_result("correlation", result)
        assert "相关分析解读" in interpretation

    def test_interpret_result_regression(self):
        """测试 regression 分发。"""
        result = {"r_squared": 0.5, "n_observations": 100, "coefficients": {}}
        interpretation = interpret_result("regression", result)
        assert "回归分析解读" in interpretation

    def test_interpret_result_mann_whitney(self):
        """测试 mann_whitney 分发。"""
        result = {"p_value": 0.01, "significant": True}
        interpretation = interpret_result("mann_whitney", result)
        assert "Mann-Whitney" in interpretation

    def test_interpret_result_kruskal_wallis(self):
        """测试 kruskal_wallis 分发。"""
        result = {"p_value": 0.01, "significant": True, "n_groups": 3}
        interpretation = interpret_result("kruskal_wallis", result)
        assert "Kruskal-Wallis" in interpretation

    def test_interpret_result_unsupported(self):
        """测试不支持的类型。"""
        interpretation = interpret_result("unknown_test", {})
        assert "暂不支持" in interpretation
