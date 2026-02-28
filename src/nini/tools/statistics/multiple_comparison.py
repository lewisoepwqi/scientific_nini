"""多重比较校正工具。"""

from __future__ import annotations

from typing import Any

from nini.tools.base import Skill, SkillResult


def bonferroni_correction(p_values: list[float], alpha: float = 0.05) -> dict[str, Any]:
    """Bonferroni 校正：最保守的方法，控制族错误率。"""
    n_comparisons = len(p_values)
    if n_comparisons == 0:
        return {"method": "Bonferroni", "corrected_pvalues": [], "significant": []}

    corrected = [min(p_value * n_comparisons, 1.0) for p_value in p_values]
    significant = [p_value < alpha for p_value in corrected]
    return {
        "method": "Bonferroni",
        "alpha": alpha,
        "n_comparisons": n_comparisons,
        "original_pvalues": p_values,
        "corrected_pvalues": corrected,
        "significant": significant,
        "description": "最保守的方法，将 alpha 除以比较次数",
    }


def holm_correction(p_values: list[float], alpha: float = 0.05) -> dict[str, Any]:
    """Holm-Bonferroni 校正：逐步校正方法。"""
    n_comparisons = len(p_values)
    if n_comparisons == 0:
        return {"method": "Holm", "corrected_pvalues": [], "significant": []}

    indexed_pvalues = sorted(enumerate(p_values), key=lambda item: item[1])
    corrected = [0.0] * n_comparisons

    temp_corrected = []
    for rank, (orig_index, p_value) in enumerate(indexed_pvalues):
        multiplier = n_comparisons - rank
        temp_corrected.append((orig_index, min(p_value * multiplier, 1.0)))

    for i in range(len(temp_corrected) - 2, -1, -1):
        orig_index, corrected_pvalue = temp_corrected[i]
        next_corrected = temp_corrected[i + 1][1]
        if corrected_pvalue < next_corrected:
            temp_corrected[i] = (orig_index, next_corrected)

    for orig_index, corrected_pvalue in temp_corrected:
        corrected[orig_index] = corrected_pvalue

    significant = [p_value < alpha for p_value in corrected]
    return {
        "method": "Holm",
        "alpha": alpha,
        "n_comparisons": n_comparisons,
        "original_pvalues": p_values,
        "corrected_pvalues": corrected,
        "significant": significant,
        "description": "逐步校正方法，比 Bonferroni 更有统计效能",
    }


def fdr_correction(p_values: list[float], alpha: float = 0.05) -> dict[str, Any]:
    """FDR (Benjamini-Hochberg) 校正。"""
    n_comparisons = len(p_values)
    if n_comparisons == 0:
        return {"method": "FDR (Benjamini-Hochberg)", "corrected_pvalues": [], "significant": []}

    indexed_pvalues = sorted(enumerate(p_values), key=lambda item: item[1])
    corrected = [0.0] * n_comparisons

    temp_corrected = []
    for rank, (orig_index, p_value) in enumerate(indexed_pvalues, 1):
        temp_corrected.append((orig_index, min(p_value * n_comparisons / rank, 1.0)))

    min_pvalue = temp_corrected[-1][1] if temp_corrected else 1.0
    for i in range(len(temp_corrected) - 1, -1, -1):
        orig_index, corrected_pvalue = temp_corrected[i]
        min_pvalue = min(min_pvalue, corrected_pvalue)
        corrected[orig_index] = min_pvalue

    significant = [p_value < alpha for p_value in corrected]
    return {
        "method": "FDR (Benjamini-Hochberg)",
        "alpha": alpha,
        "n_comparisons": n_comparisons,
        "original_pvalues": p_values,
        "corrected_pvalues": corrected,
        "significant": significant,
        "description": "控制假发现率，适用于探索性分析",
    }


def multiple_comparison_correction(
    p_values: list[float],
    method: str = "bonferroni",
    alpha: float = 0.05,
) -> dict[str, Any]:
    """多重比较校正的主函数。"""
    normalized_method = method.lower()
    if normalized_method == "bonferroni":
        return bonferroni_correction(p_values, alpha)
    if normalized_method in {"holm", "holm-bonferroni"}:
        return holm_correction(p_values, alpha)
    if normalized_method in {"fdr", "bh", "benjamini-hochberg"}:
        return fdr_correction(p_values, alpha)
    raise ValueError(f"不支持的校正方法: {method}")


def recommend_correction_method(n_comparisons: int, context: str = "exploratory") -> str:
    """基于比较次数与研究场景推荐校正方法。"""
    if n_comparisons <= 1:
        return "none"
    if context == "high_stakes":
        return "bonferroni"
    if context == "confirmatory":
        return "holm"
    if n_comparisons > 10:
        return "fdr"
    return "holm"


def get_correction_recommendation_reason(method: str, context: str = "exploratory") -> str:
    """返回校正方法推荐理由。"""
    reasons = {
        ("bonferroni", "high_stakes"): "高风险场景（如临床试验）应使用最严格的 Bonferroni 校正",
        ("bonferroni", "confirmatory"): "验证性研究建议使用 Bonferroni 或 Holm 方法",
        ("holm", "confirmatory"): "Holm 方法在控制族错误率的同时提供更高的统计效能",
        ("fdr", "exploratory"): "探索性分析建议使用 FDR 控制，以发现更多潜在关联",
        ("holm", "exploratory"): "比较次数较少时，Holm 方法是 FDR 的良好替代",
        ("none", "exploratory"): "单次比较不需要多重校正",
    }
    return reasons.get((method, context), f"基于 {context} 场景推荐 {method} 方法")


class MultipleComparisonCorrectionSkill(Skill):
    """执行多重比较校正。"""

    @property
    def name(self) -> str:
        return "multiple_comparison_correction"

    @property
    def category(self) -> str:
        return "statistics"

    @property
    def expose_to_llm(self) -> bool:
        return True

    @property
    def description(self) -> str:
        return (
            "对多个 p 值进行多重比较校正。支持 Bonferroni（最保守）、"
            "Holm（平衡）、FDR（探索性）三种方法。当进行多次统计检验时，"
            "使用此工具控制族错误率或假发现率。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "p_values": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "p 值列表（例如来自多次 t 检验或相关性分析）",
                },
                "method": {
                    "type": "string",
                    "enum": ["bonferroni", "holm", "fdr"],
                    "description": "校正方法：bonferroni=最保守，holm=平衡，fdr=探索性",
                    "default": "bonferroni",
                },
                "alpha": {
                    "type": "number",
                    "description": "显著性水平",
                    "default": 0.05,
                },
                "context": {
                    "type": "string",
                    "enum": ["exploratory", "confirmatory", "high_stakes"],
                    "description": "研究场景，用于方法推荐",
                    "default": "exploratory",
                },
            },
            "required": ["p_values"],
        }

    async def execute(self, session, **kwargs: Any) -> SkillResult:
        p_values = kwargs["p_values"]
        method = kwargs.get("method", "bonferroni")
        alpha = kwargs.get("alpha", 0.05)
        context = kwargs.get("context", "exploratory")

        if not p_values:
            return SkillResult(success=False, message="p_values 不能为空")
        if not all(0 <= p_value <= 1 for p_value in p_values):
            return SkillResult(success=False, message="所有 p 值必须在 [0, 1] 范围内")

        try:
            result = multiple_comparison_correction(p_values, method, alpha)
            recommended_method = recommend_correction_method(len(p_values), context)
            result["recommended_method"] = recommended_method
            result["recommendation_reason"] = get_correction_recommendation_reason(
                recommended_method, context
            )
            n_significant = sum(result["significant"])
            message = (
                f"{result['method']} 校正完成: "
                f"{n_significant}/{len(p_values)} 个比较显著 "
                f"(α = {alpha})"
            )
            return SkillResult(success=True, data=result, message=message)
        except Exception as exc:
            return SkillResult(success=False, message=f"多重比较校正失败: {exc}")
