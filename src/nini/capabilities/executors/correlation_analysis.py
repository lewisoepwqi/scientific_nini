"""相关性分析能力实现。

执行完整的相关性分析流程：
1. 数据验证与列类型检查
2. 自动选择相关方法（Pearson / Spearman / Kendall）
3. 正态性检验（用于方法选择）
4. 计算相关矩阵与 p 值矩阵
5. 多重比较校正
6. 可视化（热力图）
7. 生成解释性报告
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pandas as pd
from scipy import stats

if TYPE_CHECKING:
    from nini.agent.session import Session
    from nini.tools.base import SkillResult


@dataclass
class CorrelationPair:
    """单个变量对的相关性结果。"""

    var1: str
    var2: str
    coefficient: float
    p_value: float
    p_adjusted: float | None = None
    significant: bool = False
    strength: str = ""  # weak / moderate / strong


@dataclass
class CorrelationAnalysisResult:
    """相关性分析结果。"""

    success: bool = False
    message: str = ""

    # 分析参数
    method: str = ""
    method_reason: str = ""
    n_variables: int = 0
    sample_size: int = 0
    columns: list[str] = field(default_factory=list)

    # 正态性检验
    normality_tests: dict[str, Any] = field(default_factory=dict)

    # 相关矩阵
    correlation_matrix: dict[str, dict[str, float]] = field(default_factory=dict)
    pvalue_matrix: dict[str, dict[str, float]] = field(default_factory=dict)

    # 显著配对（经多重比较校正后）
    significant_pairs: list[CorrelationPair] = field(default_factory=list)
    all_pairs: list[CorrelationPair] = field(default_factory=list)

    # 多重比较校正
    correction_method: str = ""
    alpha: float = 0.05

    # 可视化
    chart_artifact: dict[str, Any] | None = None

    # 解释性报告
    interpretation: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "success": self.success,
            "message": self.message,
            "method": self.method,
            "method_reason": self.method_reason,
            "n_variables": self.n_variables,
            "sample_size": self.sample_size,
            "columns": self.columns,
            "normality_tests": self.normality_tests,
            "correlation_matrix": self.correlation_matrix,
            "pvalue_matrix": self.pvalue_matrix,
            "significant_pairs": [
                {
                    "var1": p.var1,
                    "var2": p.var2,
                    "coefficient": p.coefficient,
                    "p_value": p.p_value,
                    "p_adjusted": p.p_adjusted,
                    "significant": p.significant,
                    "strength": p.strength,
                }
                for p in self.significant_pairs
            ],
            "all_pairs": [
                {
                    "var1": p.var1,
                    "var2": p.var2,
                    "coefficient": p.coefficient,
                    "p_value": p.p_value,
                    "p_adjusted": p.p_adjusted,
                    "significant": p.significant,
                    "strength": p.strength,
                }
                for p in self.all_pairs
            ],
            "correction_method": self.correction_method,
            "alpha": self.alpha,
            "chart_artifact": self.chart_artifact,
            "interpretation": self.interpretation,
        }


class CorrelationAnalysisCapability:
    """
    相关性分析能力。

    自动执行完整的相关性分析流程，包括：
    - 数据验证与列类型检查
    - 正态性检验（决定使用 Pearson 或 Spearman）
    - 计算相关矩阵与 p 值矩阵
    - Bonferroni 多重比较校正
    - 热力图可视化
    - 解释性报告

    使用方法：
        capability = CorrelationAnalysisCapability()
        result = await capability.execute(
            session,
            dataset_name="my_data",
            columns=["var1", "var2", "var3"]
        )
    """

    def __init__(self, registry: Any | None = None) -> None:
        self.name = "correlation_analysis"
        self.display_name = "相关性分析"
        self.description = "探索变量之间的相关关系"
        self.icon = "📈"
        self._registry = registry

    async def execute(
        self,
        session: Session,
        *,
        dataset_name: str,
        columns: list[str] | None = None,
        method: str = "auto",
        alpha: float = 0.05,
        correction: str = "bonferroni",
        **kwargs: Any,
    ) -> CorrelationAnalysisResult:
        """
        执行相关性分析。

        Args:
            session: 会话对象
            dataset_name: 数据集名称
            columns: 要分析的列名列表（None 则自动选择所有数值列）
            method: 相关方法 ("auto", "pearson", "spearman", "kendall")
            alpha: 显著性水平
            correction: 多重比较校正方法 ("bonferroni", "none")
        """
        result = CorrelationAnalysisResult(alpha=alpha, correction_method=correction)

        # Step 1: 数据验证
        df = session.datasets.get(dataset_name)
        if df is None:
            result.message = f"数据集 '{dataset_name}' 不存在"
            return result

        # Step 2: 确定分析列
        if columns is None:
            columns = [col for col in df.columns if pd.api.types.is_numeric_dtype(df[col])]
            if len(columns) < 2:
                result.message = "数据集中数值列不足 2 列，无法进行相关性分析"
                return result

        if not self._validate_columns(df, columns, result):
            return result

        result.columns = columns
        result.n_variables = len(columns)

        # Step 3: 准备干净数据
        clean_data = df[columns].dropna()
        result.sample_size = len(clean_data)
        if result.sample_size < 3:
            result.message = "完整观测值不足 3 个，无法进行相关性分析"
            return result

        # Step 4: 正态性检验 → 选择方法
        if method == "auto":
            normality = self._check_normality(clean_data, columns, alpha)
            result.normality_tests = normality
            selected_method = self._select_method(normality)
            result.method = selected_method
            result.method_reason = self._get_method_reason(selected_method, normality)
        else:
            result.method = method
            result.method_reason = f"用户指定使用 {method.title()} 方法"

        # Step 5: 调用底层工具计算相关矩阵
        corr_result = await self._compute_correlation(session, dataset_name, columns, result.method)
        if corr_result is None:
            result.message = "相关性计算失败"
            return result

        result.correlation_matrix = corr_result.get("correlation_matrix", {})
        result.pvalue_matrix = corr_result.get("pvalue_matrix", {})

        # Step 6: 提取配对并做多重比较校正
        result.all_pairs = self._extract_pairs(
            columns, result.correlation_matrix, result.pvalue_matrix
        )
        n_comparisons = len(result.all_pairs)
        self._apply_correction(result.all_pairs, correction, n_comparisons, alpha)
        result.significant_pairs = [p for p in result.all_pairs if p.significant]

        # Step 7: 可视化（使用已计算的相关矩阵，避免与文本结果不一致）
        chart_result = await self._create_heatmap(
            session, dataset_name, columns, result.method, result.correlation_matrix
        )
        if chart_result is not None:
            if isinstance(chart_result, dict):
                if chart_result.get("success") and chart_result.get("artifacts"):
                    result.chart_artifact = chart_result["artifacts"][0]
            elif hasattr(chart_result, "success") and chart_result.success:
                if chart_result.artifacts:
                    result.chart_artifact = chart_result.artifacts[0]

        # Step 8: 记录富信息到 AnalysisMemory
        self._record_enriched_result(session, dataset_name, result)

        # Step 9: 生成解释
        result.interpretation = self._generate_interpretation(result)
        result.success = True
        result.message = "相关性分析完成"
        return result

    def _validate_columns(
        self,
        df: pd.DataFrame,
        columns: list[str],
        result: CorrelationAnalysisResult,
    ) -> bool:
        """验证列有效性。"""
        if len(columns) < 2:
            result.message = "至少需要 2 个变量进行相关性分析"
            return False

        for col in columns:
            if col not in df.columns:
                result.message = f"列 '{col}' 不存在"
                return False
            if not pd.api.types.is_numeric_dtype(df[col]):
                result.message = f"列 '{col}' 不是数值类型"
                return False
        return True

    def _check_normality(
        self,
        data: pd.DataFrame,
        columns: list[str],
        alpha: float,
    ) -> dict[str, Any]:
        """对每列进行 Shapiro-Wilk 正态性检验。"""
        normality: dict[str, Any] = {}
        for col in columns:
            col_data = data[col].dropna()
            if len(col_data) < 3 or len(col_data) > 5000:
                normality[col] = {
                    "tested": False,
                    "reason": "样本量不在 Shapiro-Wilk 适用范围内",
                }
                continue
            try:
                statistic, p_value = stats.shapiro(col_data)
                normality[col] = {
                    "tested": True,
                    "statistic": float(statistic),
                    "p_value": float(p_value),
                    "normal": bool(p_value > alpha),
                }
            except Exception as exc:
                normality[col] = {
                    "tested": False,
                    "reason": f"正态性检验失败: {exc}",
                }
        return normality

    def _select_method(self, normality: dict[str, Any]) -> str:
        """根据正态性检验结果选择方法。"""
        all_normal = True
        for col, result in normality.items():
            if not isinstance(result, dict):
                continue
            if result.get("tested") is False:
                continue
            if not result.get("normal", True):
                all_normal = False
                break
        return "pearson" if all_normal else "spearman"

    def _get_method_reason(self, method: str, normality: dict[str, Any]) -> str:
        """获取方法选择原因。"""
        non_normal_cols = []
        for col, result in normality.items():
            if isinstance(result, dict) and result.get("tested") and not result.get("normal", True):
                non_normal_cols.append(col)

        if method == "pearson":
            return "所有变量通过正态性检验，使用 Pearson 相关系数"
        elif method == "spearman":
            cols_text = "、".join(non_normal_cols[:3])
            suffix = " 等" if len(non_normal_cols) > 3 else ""
            return f"变量 {cols_text}{suffix} 不符合正态分布，使用 Spearman 秩相关"
        return f"使用 {method.title()} 方法"

    def _get_registry(self) -> Any:
        """获取工具注册中心。"""
        if self._registry is not None:
            return self._registry
        from nini.tools.registry import create_default_tool_registry

        return create_default_tool_registry()

    async def _compute_correlation(
        self,
        session: Session,
        dataset_name: str,
        columns: list[str],
        method: str,
    ) -> dict[str, Any] | None:
        """通过底层工具计算相关矩阵。"""
        registry = self._get_registry()
        try:
            tool_result = await registry.execute(
                "correlation",
                session,
                dataset_name=dataset_name,
                columns=columns,
                method=method,
            )
            if isinstance(tool_result, dict):
                if tool_result.get("success") and tool_result.get("data"):
                    return tool_result["data"]
            elif hasattr(tool_result, "success") and tool_result.success and tool_result.data:
                return tool_result.data
        except Exception:
            pass
        return None

    def _extract_pairs(
        self,
        columns: list[str],
        corr_matrix: dict[str, dict[str, float]],
        pvalue_matrix: dict[str, dict[str, float]],
    ) -> list[CorrelationPair]:
        """提取所有不重复的变量配对。"""
        pairs: list[CorrelationPair] = []
        for i, col1 in enumerate(columns):
            for col2 in columns[i + 1 :]:
                coeff = corr_matrix.get(col1, {}).get(col2, 0.0)
                p_val = pvalue_matrix.get(col1, {}).get(col2, 1.0)
                if not math.isfinite(coeff):
                    coeff = 0.0
                if not math.isfinite(p_val):
                    p_val = 1.0
                pairs.append(
                    CorrelationPair(
                        var1=col1,
                        var2=col2,
                        coefficient=coeff,
                        p_value=p_val,
                        strength=self._classify_strength(coeff),
                    )
                )
        pairs.sort(key=lambda p: abs(p.coefficient), reverse=True)
        return pairs

    @staticmethod
    def _classify_strength(coefficient: float) -> str:
        """根据绝对值分类相关强度。"""
        abs_r = abs(coefficient)
        if abs_r >= 0.7:
            return "strong"
        elif abs_r >= 0.4:
            return "moderate"
        elif abs_r >= 0.2:
            return "weak"
        return "negligible"

    @staticmethod
    def _apply_correction(
        pairs: list[CorrelationPair],
        method: str,
        n_comparisons: int,
        alpha: float,
    ) -> None:
        """对配对 p 值做多重比较校正。"""
        if method == "bonferroni" and n_comparisons > 1:
            adjusted_alpha = alpha / n_comparisons
            for pair in pairs:
                pair.p_adjusted = min(pair.p_value * n_comparisons, 1.0)
                pair.significant = pair.p_value < adjusted_alpha
        else:
            for pair in pairs:
                pair.p_adjusted = pair.p_value
                pair.significant = pair.p_value < alpha

    async def _create_heatmap(
        self,
        session: Session,
        dataset_name: str,
        columns: list[str],
        method: str,
        corr_matrix: dict[str, dict[str, float]] | None = None,
    ) -> Any:
        """创建相关矩阵热力图。

        如果提供了 corr_matrix，先将其写入 session 的临时数据中，
        让 create_chart 使用与文本一致的数据（经过 dropna 的结果）。
        """
        registry = self._get_registry()
        # 如果有预计算矩阵，构建一个 DataFrame 写入会话供图表使用
        if corr_matrix:
            corr_df = pd.DataFrame(corr_matrix)
            corr_df = corr_df.reindex(index=columns, columns=columns)
            temp_name = f"_corr_matrix_{dataset_name}"
            session.datasets[temp_name] = corr_df
            chart_dataset = temp_name
        else:
            chart_dataset = dataset_name
        try:
            result = await registry.execute(
                "create_chart",
                session,
                dataset_name=chart_dataset,
                chart_type="heatmap",
                columns=columns,
                title=f"{method.title()} 相关矩阵",
            )
            return result
        except Exception:
            return None
        finally:
            # 清理临时数据集
            if corr_matrix:
                session.datasets.pop(f"_corr_matrix_{dataset_name}", None)

    @staticmethod
    def _record_enriched_result(
        session: Session,
        dataset_name: str,
        result: CorrelationAnalysisResult,
    ) -> None:
        """将相关性分析富信息记录到 AnalysisMemory。"""
        from nini.tools.statistics.base import _record_stat_result

        # 为每对显著相关记录一条
        for pair in result.significant_pairs:
            _record_stat_result(
                session,
                dataset_name,
                test_name=f"{result.method.title()} 相关性 ({pair.var1} ↔ {pair.var2})",
                message=(
                    f"r = {pair.coefficient:.3f}, p_adj = {pair.p_adjusted:.4f}, "
                    f"强度: {pair.strength}"
                ),
                test_statistic=pair.coefficient,
                p_value=pair.p_value,
                effect_size=abs(pair.coefficient),
                effect_type="r",
                significant=pair.significant,
            )

        # 如果没有显著对，记录一条汇总
        if not result.significant_pairs:
            _record_stat_result(
                session,
                dataset_name,
                test_name=f"{result.method.title()} 相关性分析",
                message=f"分析 {result.n_variables} 个变量，未发现显著相关",
            )

    def _generate_interpretation(self, result: CorrelationAnalysisResult) -> str:
        """生成解释性报告。"""
        parts: list[str] = []

        parts.append("## 分析方法")
        parts.append(f"选择方法: {result.method.title()}")
        parts.append(f"选择理由: {result.method_reason}")
        parts.append(f"变量数: {result.n_variables}, 有效样本量: {result.sample_size}")

        if result.correction_method and result.correction_method != "none":
            parts.append(
                f"多重比较校正: {result.correction_method.title()}"
                f"（{len(result.all_pairs)} 次比较）"
            )

        parts.append("\n## 显著相关")
        if result.significant_pairs:
            for pair in result.significant_pairs:
                direction = "正相关" if pair.coefficient > 0 else "负相关"
                strength_cn = {
                    "strong": "强",
                    "moderate": "中等",
                    "weak": "弱",
                    "negligible": "极弱",
                }.get(pair.strength, "")
                p_display = pair.p_adjusted if pair.p_adjusted is not None else pair.p_value
                parts.append(
                    f"- {pair.var1} ↔ {pair.var2}: "
                    f"r = {pair.coefficient:.3f} ({strength_cn}{direction}), "
                    f"p_adj = {p_display:.4f}"
                )
        else:
            parts.append("未发现显著相关（校正后 p < {:.2f}）。".format(result.alpha))

        parts.append("\n## 结论")
        n_sig = len(result.significant_pairs)
        n_total = len(result.all_pairs)
        if n_sig > 0:
            strong_pairs = [p for p in result.significant_pairs if p.strength == "strong"]
            if strong_pairs:
                names = [f"{p.var1}-{p.var2}" for p in strong_pairs[:3]]
                parts.append(f"发现 {n_sig}/{n_total} 对显著相关，其中强相关: {', '.join(names)}。")
            else:
                parts.append(f"发现 {n_sig}/{n_total} 对显著相关，但均为中等或弱相关。")
        else:
            parts.append(f"在 {n_total} 对变量中未发现显著相关关系。")

        return "\n".join(parts)
