"""统计结果智能解读模块。

根据统计检验结果自动生成实际意义解读，帮助用户理解统计结果。
"""

from __future__ import annotations

from typing import Any


class ResultInterpreter:
    """统计结果解读器。

    针对不同类型的统计检验结果，生成包含统计意义和实际意义的解读文本。
    """

    @staticmethod
    def interpret_t_test(result: dict[str, Any]) -> str:
        """解读 t 检验结果。

        Args:
            result: t_test 技能返回的 data 字段

        Returns:
            解读文本
        """
        test_type = result.get("test_type", "t 检验")
        p_value = result.get("p_value", 1.0)
        significant = result.get("significant", False)
        t_stat = result.get("t_statistic", 0.0)

        parts = [f"【{test_type}解读】"]

        # 统计显著性解读
        if significant:
            parts.append(f"结果具有统计学显著性 (p = {p_value:.4f} < 0.05)。")
        else:
            parts.append(f"结果不具有统计学显著性 (p = {p_value:.4f} >= 0.05)。")

        # 根据检验类型解读
        if "独立样本" in test_type or "配对样本" in test_type:
            mean1 = result.get("mean1")
            mean2 = result.get("mean2")
            cohens_d = result.get("cohens_d")

            if mean1 is not None and mean2 is not None:
                diff = mean1 - mean2
                direction = "高于" if diff > 0 else "低于"
                parts.append(f"第一组均值 ({mean1:.3f}) {direction}第二组均值 ({mean2:.3f})，差值为 {abs(diff):.3f}。")

            # 效应量解读
            if cohens_d is not None:
                effect_size = ResultInterpreter._interpret_cohens_d(abs(cohens_d))
                parts.append(f"效应量 Cohen's d = {cohens_d:.3f}，属于{effect_size}。")

        elif "单样本" in test_type:
            mean = result.get("mean")
            test_value = result.get("test_value")
            if mean is not None and test_value is not None:
                diff = mean - test_value
                direction = "高于" if diff > 0 else "低于"
                parts.append(f"样本均值 ({mean:.3f}) {direction}检验值 ({test_value:.3f})，差值为 {abs(diff):.3f}。")

        # 实际意义总结
        if significant:
            parts.append("📊 实际意义：两组之间存在统计学差异，该结果不太可能是随机波动导致的。")
        else:
            parts.append("📊 实际意义：未能检测到两组之间的统计学差异。可能原因：1) 确实无差异；2) 样本量不足；3) 效应量较小。")

        return "\n".join(parts)

    @staticmethod
    def interpret_anova(result: dict[str, Any]) -> str:
        """解读 ANOVA 结果。

        Args:
            result: anova 技能返回的 data 字段

        Returns:
            解读文本
        """
        p_value = result.get("p_value", 1.0)
        significant = result.get("significant", False)
        f_stat = result.get("f_statistic", 0.0)
        eta_squared = result.get("eta_squared")
        n_groups = result.get("n_groups", 0)

        parts = ["【单因素方差分析(ANOVA)解读】"]

        # 统计显著性解读
        if significant:
            parts.append(f"结果具有统计学显著性 (F = {f_stat:.3f}, p = {p_value:.4f} < 0.05)。")
            parts.append(f"这表明 {n_groups} 个组的均值中至少有一组与其他组存在显著差异。")
        else:
            parts.append(f"结果不具有统计学显著性 (F = {f_stat:.3f}, p = {p_value:.4f} >= 0.05)。")
            parts.append(f"未能检测到 {n_groups} 个组之间的显著差异。")

        # 效应量解读
        if eta_squared is not None:
            effect_size = ResultInterpreter._interpret_eta_squared(eta_squared)
            parts.append(f"效应量 η² = {eta_squared:.3f}，属于{effect_size}。")

        # 事后检验解读
        post_hoc = result.get("post_hoc", [])
        if post_hoc and significant:
            parts.append("\n【Tukey HSD 事后检验结果】")
            significant_pairs = [p for p in post_hoc if p.get("significant")]
            if significant_pairs:
                parts.append(f"发现 {len(significant_pairs)} 组显著差异：")
                for pair in significant_pairs:
                    g1, g2 = pair.get("group1"), pair.get("group2")
                    diff = pair.get("mean_diff", 0)
                    p = pair.get("p_value", 1.0)
                    parts.append(f"  - {g1} vs {g2}: 均值差 = {diff:.3f}, p = {p:.4f}")
            else:
                parts.append("事后检验未发现具体哪些组之间存在显著差异。")

        # 实际意义总结
        if significant:
            parts.append("\n📊 实际意义：不同组别间存在真实的均值差异。建议结合事后检验结果，确定具体哪些组之间存在差异，并考虑效应量大小判断实际重要性。")
        else:
            parts.append("\n📊 实际意义：各组均值在统计上无显著差异。可能原因：1) 组间确实无差异；2) 组内变异较大；3) 样本量不足。建议检查数据分布或增加样本量。")

        return "\n".join(parts)

    @staticmethod
    def interpret_correlation(result: dict[str, Any]) -> str:
        """解读相关分析结果。

        Args:
            result: correlation 技能返回的 data 字段

        Returns:
            解读文本
        """
        method = result.get("method", "pearson")
        sample_size = result.get("sample_size", 0)
        corr_matrix = result.get("correlation_matrix", {})
        pvalue_matrix = result.get("pvalue_matrix", {})

        parts = [f"【{method.title()} 相关分析解读】"]
        parts.append(f"样本量 n = {sample_size}")

        # 提取所有变量对的相关性
        variables = list(corr_matrix.keys())
        if len(variables) < 2:
            parts.append("变量数量不足，无法计算相关性。")
            return "\n".join(parts)

        parts.append("\n【变量间相关性】")
        interpretations = []

        for i, var1 in enumerate(variables):
            for var2 in variables[i + 1 :]:
                corr = corr_matrix.get(var1, {}).get(var2)
                pval = pvalue_matrix.get(var1, {}).get(var2)

                if corr is not None and pval is not None:
                    sig_text = "显著" if pval < 0.05 else "不显著"
                    strength = ResultInterpreter._interpret_correlation_strength(abs(corr))
                    direction = "正" if corr > 0 else "负"

                    interpretations.append(
                        f"  - {var1} ↔ {var2}: r = {corr:.3f} ({direction}相关, {strength}, p = {pval:.4f}, {sig_text})"
                    )

        parts.extend(interpretations)

        # 找出最强相关
        max_corr = 0
        max_pair = None
        for i, var1 in enumerate(variables):
            for var2 in variables[i + 1 :]:
                corr = abs(corr_matrix.get(var1, {}).get(var2, 0))
                if corr > max_corr:
                    max_corr = corr
                    max_pair = (var1, var2)

        if max_pair and max_corr > 0.3:
            parts.append(f"\n📊 最强相关：{max_pair[0]} 与 {max_pair[1]} (|r| = {max_corr:.3f})")

        # 方法说明
        if method == "pearson":
            parts.append("\n💡 说明：Pearson 相关系数衡量线性关系，取值范围 [-1, 1]。注意：相关性不等于因果性。")
        elif method == "spearman":
            parts.append("\n💡 说明：Spearman 等级相关系数衡量单调关系，对异常值更稳健。注意：相关性不等于因果性。")
        elif method == "kendall":
            parts.append("\n💡 说明：Kendall 等级相关系数衡量一致性，适用于小样本。注意：相关性不等于因果性。")

        return "\n".join(parts)

    @staticmethod
    def interpret_regression(result: dict[str, Any]) -> str:
        """解读回归分析结果。

        Args:
            result: regression 技能返回的 data 字段

        Returns:
            解读文本
        """
        r_squared = result.get("r_squared", 0.0)
        adjusted_r2 = result.get("adjusted_r_squared")
        f_stat = result.get("f_statistic")
        f_pvalue = result.get("f_pvalue")
        coefficients = result.get("coefficients", {})
        n_obs = result.get("n_observations", 0)

        parts = ["【线性回归分析解读】"]
        parts.append(f"样本量 n = {n_obs}")

        # 模型整体显著性
        if f_pvalue is not None:
            if f_pvalue < 0.05:
                parts.append(f"回归模型整体显著 (F = {f_stat:.3f}, p = {f_pvalue:.4f} < 0.05)。")
            else:
                parts.append(f"回归模型整体不显著 (F = {f_stat:.3f}, p = {f_pvalue:.4f} >= 0.05)。")

        # R² 解读
        parts.append(f"R² = {r_squared:.4f}，表示自变量可以解释因变量 {r_squared * 100:.2f}% 的变异。")
        if adjusted_r2 is not None:
            parts.append(f"调整 R² = {adjusted_r2:.4f}（考虑自变量个数后的修正值）。")

        # 效应量解读
        r2_effect = ResultInterpreter._interpret_r_squared(r_squared)
        parts.append(f"模型解释力：{r2_effect}")

        # 系数解读
        parts.append("\n【回归系数解读】")
        for var, coef_info in coefficients.items():
            if var == "const":
                continue
            estimate = coef_info.get("estimate", 0)
            p_value = coef_info.get("p_value", 1.0)
            sig = "显著" if p_value < 0.05 else "不显著"
            direction = "正向" if estimate > 0 else "负向"
            parts.append(f"  - {var}: 系数 = {estimate:.4f} ({direction}影响, {sig}, p = {p_value:.4f})")

        # 实际意义总结
        if f_pvalue is not None and f_pvalue < 0.05:
            parts.append("\n📊 实际意义：模型具有统计学意义，自变量对因变量有预测作用。但需注意：")
            parts.append("  1. 相关不等于因果，需结合研究设计判断因果关系")
            parts.append("  2. 检查残差是否符合正态性和方差齐性假设")
            parts.append("  3. 关注调整 R² 而非原始 R² 以评估模型泛化能力")
        else:
            parts.append("\n📊 实际意义：模型整体不显著，自变量未能有效预测因变量。建议：")
            parts.append("  1. 考虑加入其他潜在预测变量")
            parts.append("  2. 检查是否存在非线性关系")
            parts.append("  3. 确认数据质量和样本量是否充足")

        return "\n".join(parts)

    @staticmethod
    def interpret_mann_whitney(result: dict[str, Any]) -> str:
        """解读 Mann-Whitney U 检验结果。

        Args:
            result: mann_whitney 技能返回的 data 字段

        Returns:
            解读文本
        """
        p_value = result.get("p_value", 1.0)
        significant = result.get("significant", False)
        u_stat = result.get("u_statistic", 0)
        median1 = result.get("median1")
        median2 = result.get("median2")
        effect_size_r = result.get("effect_size_r")

        parts = ["【Mann-Whitney U 检验解读】"]
        parts.append("注：非参数检验，不假设数据服从正态分布。")

        if significant:
            parts.append(f"结果具有统计学显著性 (U = {u_stat:.0f}, p = {p_value:.4f} < 0.05)。")
        else:
            parts.append(f"结果不具有统计学显著性 (U = {u_stat:.0f}, p = {p_value:.4f} >= 0.05)。")

        # 中位数比较
        if median1 is not None and median2 is not None:
            direction = "高于" if median1 > median2 else "低于"
            parts.append(f"第一组中位数 ({median1:.3f}) {direction}第二组中位数 ({median2:.3f})。")

        # 效应量
        if effect_size_r is not None:
            effect = ResultInterpreter._interpret_correlation_strength(effect_size_r)
            parts.append(f"效应量 r = {effect_size_r:.3f}，属于{effect}。")

        if significant:
            parts.append("📊 实际意义：两组分布存在显著差异。由于是非参数检验，结论适用于分布形状而不仅是均值。")
        else:
            parts.append("📊 实际意义：未能检测到两组分布的显著差异。")

        return "\n".join(parts)

    @staticmethod
    def interpret_kruskal_wallis(result: dict[str, Any]) -> str:
        """解读 Kruskal-Wallis H 检验结果。

        Args:
            result: kruskal_wallis 技能返回的 data 字段

        Returns:
            解读文本
        """
        p_value = result.get("p_value", 1.0)
        significant = result.get("significant", False)
        h_stat = result.get("h_statistic", 0)
        df = result.get("df", 0)
        n_groups = result.get("n_groups", 0)
        eta_squared = result.get("eta_squared")

        parts = ["【Kruskal-Wallis H 检验解读】"]
        parts.append("注：非参数检验，不假设数据服从正态分布，适用于多组比较。")

        if significant:
            parts.append(f"结果具有统计学显著性 (H({df}) = {h_stat:.3f}, p = {p_value:.4f} < 0.05)。")
            parts.append(f"{n_groups} 个组的分布中至少有一组与其他组存在显著差异。")
        else:
            parts.append(f"结果不具有统计学显著性 (H({df}) = {h_stat:.3f}, p = {p_value:.4f} >= 0.05)。")
            parts.append(f"未能检测到 {n_groups} 个组之间的显著差异。")

        # 效应量
        if eta_squared is not None:
            effect = ResultInterpreter._interpret_eta_squared(eta_squared)
            parts.append(f"效应量 η² = {eta_squared:.3f}，属于{effect}。")

        # 中位数信息
        group_medians = result.get("group_medians", {})
        if group_medians:
            parts.append("\n【各组中位数】")
            for group, median in group_medians.items():
                parts.append(f"  - {group}: {median:.3f}")

        if significant:
            parts.append("\n📊 实际意义：多组间存在显著差异。建议进行事后检验（如 Dunn 检验）确定具体哪些组之间存在差异。")
        else:
            parts.append("\n📊 实际意义：各组分布在统计上无显著差异。")

        return "\n".join(parts)

    # ---- 辅助方法：效应量解读 ----

    @staticmethod
    def _interpret_cohens_d(d: float) -> str:
        """解读 Cohen's d 效应量。

        参考标准：
        - 0.2: 小效应
        - 0.5: 中等效应
        - 0.8: 大效应
        """
        if d < 0.2:
            return "可忽略效应"
        elif d < 0.5:
            return "小效应"
        elif d < 0.8:
            return "中等效应"
        else:
            return "大效应"

    @staticmethod
    def _interpret_eta_squared(eta2: float) -> str:
        """解读 eta squared 效应量。

        参考标准：
        - 0.01: 小效应
        - 0.06: 中等效应
        - 0.14: 大效应
        """
        if eta2 < 0.01:
            return "可忽略效应"
        elif eta2 < 0.06:
            return "小效应"
        elif eta2 < 0.14:
            return "中等效应"
        else:
            return "大效应"

    @staticmethod
    def _interpret_correlation_strength(r: float) -> str:
        """解读相关系数强度。

        参考标准：
        - 0.1: 弱相关
        - 0.3: 中等相关
        - 0.5: 强相关
        """
        if r < 0.1:
            return "可忽略"
        elif r < 0.3:
            return "弱相关"
        elif r < 0.5:
            return "中等相关"
        elif r < 0.7:
            return "强相关"
        else:
            return "极强相关"

    @staticmethod
    def _interpret_r_squared(r2: float) -> str:
        """解读 R² 效应量。

        参考标准：
        - 0.02: 小效应
        - 0.13: 中等效应
        - 0.26: 大效应
        """
        if r2 < 0.02:
            return "可忽略"
        elif r2 < 0.13:
            return "小效应"
        elif r2 < 0.26:
            return "中等效应"
        else:
            return "大效应"


def interpret_result(test_type: str, result: dict[str, Any]) -> str:
    """根据检验类型自动选择解读方法。

    Args:
        test_type: 检验类型，如 't_test', 'anova', 'correlation' 等
        result: 检验结果数据

    Returns:
        解读文本
    """
    interpreter = ResultInterpreter()

    interpreters = {
        "t_test": interpreter.interpret_t_test,
        "anova": interpreter.interpret_anova,
        "correlation": interpreter.interpret_correlation,
        "regression": interpreter.interpret_regression,
        "mann_whitney": interpreter.interpret_mann_whitney,
        "kruskal_wallis": interpreter.interpret_kruskal_wallis,
    }

    interpret_func = interpreters.get(test_type)
    if interpret_func:
        return interpret_func(result)

    return f"暂不支持 {test_type} 类型的结果解读。"


# ---- Skill 接口 ----

from nini.agent.session import Session
from nini.skills.base import Skill, SkillResult


class InterpretStatisticalResultSkill(Skill):
    """智能解读统计检验结果，生成实际意义解释。"""

    @property
    def name(self) -> str:
        return "interpret_statistical_result"

    @property
    def category(self) -> str:
        return "statistics"

    @property
    def expose_to_llm(self) -> bool:
        return True

    @property
    def description(self) -> str:
        return (
            "智能解读统计检验结果，自动生成包含统计意义和实际意义的解读文本。\n"
            "支持：t检验、ANOVA、相关分析、回归分析、Mann-Whitney U检验、Kruskal-Wallis H检验。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "test_type": {
                    "type": "string",
                    "enum": ["t_test", "anova", "correlation", "regression", "mann_whitney", "kruskal_wallis"],
                    "description": "统计检验类型",
                },
                "result": {
                    "type": "object",
                    "description": "统计检验结果数据（即技能返回的 data 字段）",
                },
            },
            "required": ["test_type", "result"],
        }

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        test_type = kwargs.get("test_type")
        result = kwargs.get("result")

        if not test_type or not result:
            return SkillResult(
                success=False,
                message="请提供 test_type 和 result 参数"
            )

        try:
            interpretation = interpret_result(test_type, result)
            return SkillResult(
                success=True,
                data={"interpretation": interpretation},
                message="统计结果解读完成"
            )
        except Exception as e:
            return SkillResult(
                success=False,
                message=f"解读失败: {e}"
            )
