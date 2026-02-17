"""多重比较校正测试。"""

from __future__ import annotations

import pytest

from nini.tools.statistics import (
    MultipleComparisonCorrectionSkill,
    bonferroni_correction,
    fdr_correction,
    holm_correction,
    multiple_comparison_correction,
    recommend_correction_method,
)


class TestBonferroniCorrection:
    """测试 Bonferroni 校正。"""

    def test_single_pvalue(self):
        result = bonferroni_correction([0.05], alpha=0.05)
        assert result["method"] == "Bonferroni"
        assert result["corrected_pvalues"] == [0.05]
        # p = 0.05, alpha = 0.05, p < alpha is False
        assert result["significant"] == [False]

    def test_single_significant_pvalue(self):
        result = bonferroni_correction([0.01], alpha=0.05)
        assert result["significant"] == [True]

    def test_multiple_pvalues(self):
        p_values = [0.01, 0.02, 0.03, 0.04, 0.05]
        result = bonferroni_correction(p_values, alpha=0.05)

        # Bonferroni: p * n
        expected = [0.05, 0.10, 0.15, 0.20, 0.25]
        assert result["corrected_pvalues"] == expected
        # Only p < alpha is significant (0.05 < 0.05 is False)
        assert result["significant"] == [False, False, False, False, False]

    def test_multiple_pvalues_with_significant(self):
        p_values = [0.001, 0.01, 0.03, 0.04, 0.05]
        result = bonferroni_correction(p_values, alpha=0.05)
        # 0.001 * 5 = 0.005 < 0.05 -> significant
        # 0.01 * 5 = 0.05 < 0.05 -> False (not strictly less)
        assert result["significant"][0] is True  # 0.005 < 0.05

    def test_capped_at_1(self):
        # 校正后 p 值不应超过 1.0
        result = bonferroni_correction([0.4, 0.5, 0.6], alpha=0.05)
        assert all(p <= 1.0 for p in result["corrected_pvalues"])

    def test_empty_list(self):
        result = bonferroni_correction([])
        assert result["corrected_pvalues"] == []


class TestHolmCorrection:
    """测试 Holm 校正。"""

    def test_single_pvalue(self):
        result = holm_correction([0.05], alpha=0.05)
        assert result["method"] == "Holm"
        # p = 0.05, alpha = 0.05, p < alpha is False
        assert result["significant"] == [False]

    def test_single_significant_pvalue(self):
        result = holm_correction([0.01], alpha=0.05)
        assert result["significant"] == [True]

    def test_stepwise_correction(self):
        # Holm 是逐步校正，比 Bonferroni 更有统计效能
        p_values = [0.001, 0.02, 0.04, 0.06]
        result = holm_correction(p_values, alpha=0.05)

        # Holm 校正应该产生合理的校正后 p 值
        assert len(result["corrected_pvalues"]) == len(p_values)
        assert all(p >= 0 for p in result["corrected_pvalues"])
        assert all(p <= 1 for p in result["corrected_pvalues"])

    def test_more_powerful_than_bonferroni(self):
        # Holm 应该比 Bonferroni 发现更多显著结果（或相等）
        p_values = [0.01, 0.02, 0.03, 0.04, 0.05]
        holm_result = holm_correction(p_values, alpha=0.05)
        bonferroni_result = bonferroni_correction(p_values, alpha=0.05)

        holm_sig = sum(holm_result["significant"])
        bonferroni_sig = sum(bonferroni_result["significant"])
        assert holm_sig >= bonferroni_sig


class TestFDRCorrection:
    """测试 FDR (Benjamini-Hochberg) 校正。"""

    def test_single_pvalue(self):
        result = fdr_correction([0.05], alpha=0.05)
        assert result["method"] == "FDR (Benjamini-Hochberg)"
        # p = 0.05, alpha = 0.05, p < alpha is False
        assert result["significant"] == [False]

    def test_single_significant_pvalue(self):
        result = fdr_correction([0.01], alpha=0.05)
        assert result["significant"] == [True]

    def test_exploratory_friendly(self):
        # FDR 比 Bonferroni 更宽松，适合探索性分析
        p_values = [0.01, 0.02, 0.03, 0.04, 0.05]

        bonferroni_result = bonferroni_correction(p_values, alpha=0.05)
        fdr_result = fdr_correction(p_values, alpha=0.05)

        # FDR 应该发现更多显著结果（或相等）
        bonferroni_sig = sum(bonferroni_result["significant"])
        fdr_sig = sum(fdr_result["significant"])
        assert fdr_sig >= bonferroni_sig

    def test_monotonicity(self):
        # 校正后 p 值应保持单调性（不递增）
        p_values = [0.01, 0.02, 0.04, 0.06, 0.10]
        result = fdr_correction(p_values, alpha=0.05)

        corrected = result["corrected_pvalues"]
        for i in range(len(corrected) - 1):
            assert corrected[i] <= corrected[i + 1] + 1e-10  # 允许浮点误差


class TestMultipleComparisonCorrection:
    """测试多重比较校正主函数。"""

    def test_bonferroni_method(self):
        p_values = [0.01, 0.02, 0.05]
        result = multiple_comparison_correction(p_values, method="bonferroni")
        assert result["method"] == "Bonferroni"

    def test_holm_method(self):
        p_values = [0.01, 0.02, 0.05]
        result = multiple_comparison_correction(p_values, method="holm")
        assert result["method"] == "Holm"

    def test_fdr_method(self):
        p_values = [0.01, 0.02, 0.05]
        result = multiple_comparison_correction(p_values, method="fdr")
        assert result["method"] == "FDR (Benjamini-Hochberg)"

    def test_case_insensitive(self):
        p_values = [0.05]
        result1 = multiple_comparison_correction(p_values, method="BONFERRONI")
        result2 = multiple_comparison_correction(p_values, method="bonferroni")
        assert result1["method"] == result2["method"]

    def test_invalid_method(self):
        with pytest.raises(ValueError, match="不支持的校正方法"):
            multiple_comparison_correction([0.05], method="invalid")


class TestRecommendCorrectionMethod:
    """测试校正方法推荐。"""

    def test_single_comparison(self):
        assert recommend_correction_method(1) == "none"
        assert recommend_correction_method(0) == "none"

    def test_high_stakes(self):
        # 高风险场景使用 Bonferroni
        assert recommend_correction_method(5, "high_stakes") == "bonferroni"

    def test_confirmatory(self):
        # 验证性研究使用 Holm
        assert recommend_correction_method(5, "confirmatory") == "holm"

    def test_exploratory_many_comparisons(self):
        # 探索性分析，比较次数多时使用 FDR
        assert recommend_correction_method(20, "exploratory") == "fdr"

    def test_exploratory_few_comparisons(self):
        # 探索性分析，比较次数少时使用 Holm
        assert recommend_correction_method(5, "exploratory") == "holm"


@pytest.mark.asyncio
class TestMultipleComparisonCorrectionSkill:
    """测试多重比较校正技能。"""

    async def test_skill_execution_bonferroni(self):
        skill = MultipleComparisonCorrectionSkill()
        result = await skill.execute(
            session=None,  # 不需要会话
            p_values=[0.01, 0.02, 0.05],
            method="bonferroni",
            alpha=0.05,
        )

        assert result.success is True
        assert "corrected_pvalues" in result.data
        assert result.data["method"] == "Bonferroni"

    async def test_skill_with_recommendation(self):
        skill = MultipleComparisonCorrectionSkill()
        result = await skill.execute(
            session=None,
            p_values=[0.01, 0.02, 0.05],
            method="bonferroni",
            context="exploratory",
        )

        assert result.success is True
        assert "recommended_method" in result.data
        assert "recommendation_reason" in result.data

    async def test_skill_empty_pvalues(self):
        skill = MultipleComparisonCorrectionSkill()
        result = await skill.execute(
            session=None,
            p_values=[],
            method="bonferroni",
        )

        assert result.success is False
        assert "不能为空" in result.message

    async def test_skill_invalid_pvalues(self):
        skill = MultipleComparisonCorrectionSkill()
        result = await skill.execute(
            session=None,
            p_values=[0.5, 1.5, -0.1],  # 包含无效 p 值
            method="bonferroni",
        )

        assert result.success is False
        assert "必须在 [0, 1] 范围内" in result.message

    async def test_skill_counts_significant(self):
        skill = MultipleComparisonCorrectionSkill()
        result = await skill.execute(
            session=None,
            p_values=[0.001, 0.01, 0.1, 0.2],
            method="bonferroni",
            alpha=0.05,
        )

        assert result.success is True
        # 验证消息中包含显著结果计数
        assert "个比较显著" in result.message
