"""差异分析能力实现。

执行完整的差异分析流程：
1. 数据质量检查
2. 正态性检验
3. 方差齐性检验（多组时）
4. 自动选择合适的统计检验
5. 效应量计算
6. 事后检验（如需要）
7. 可视化
8. 生成解释性报告
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

from scipy import stats
from nini.tools.base import SkillResult

if TYPE_CHECKING:
    from nini.agent.session import Session


@dataclass
class DifferenceAnalysisResult:
    """差异分析结果。"""

    success: bool = False
    message: str = ""

    # 数据特征
    n_groups: int = 0
    group_sizes: dict[str, int] = field(default_factory=dict)
    group_means: dict[str, float] = field(default_factory=dict)

    # 前提检验
    normality_tests: dict[str, Any] = field(default_factory=dict)
    equal_variance_test: dict[str, Any] | None = None

    # 选择的统计方法
    selected_method: str = ""
    method_reason: str = ""

    # 统计结果
    test_statistic: float | None = None
    p_value: float | None = None
    degrees_of_freedom: int | None = None
    effect_size: float | None = None
    effect_type: str = ""
    significant: bool = False

    # 事后检验（多组时）
    post_hoc: list[dict[str, Any]] | None = None

    # 可视化
    chart_artifact: dict[str, Any] | None = None

    # 解释性报告
    interpretation: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "success": self.success,
            "message": self.message,
            "n_groups": self.n_groups,
            "group_sizes": self.group_sizes,
            "group_means": self.group_means,
            "normality_tests": self.normality_tests,
            "equal_variance_test": self.equal_variance_test,
            "selected_method": self.selected_method,
            "method_reason": self.method_reason,
            "test_statistic": self.test_statistic,
            "p_value": self.p_value,
            "degrees_of_freedom": self.degrees_of_freedom,
            "effect_size": self.effect_size,
            "effect_type": self.effect_type,
            "significant": self.significant,
            "post_hoc": self.post_hoc,
            "chart_artifact": self.chart_artifact,
            "interpretation": self.interpretation,
        }


class DifferenceAnalysisCapability:
    """
    差异分析能力。

    自动执行完整的差异分析流程，包括：
    - 数据质量检查
    - 正态性检验（Shapiro-Wilk）
    - 方差齐性检验（Levene）
    - 自动选择统计方法
    - 效应量计算
    - 可视化
    - 解释性报告

    使用方法：
        capability = DifferenceAnalysisCapability()
        result = await capability.execute(
            session,
            dataset_name="my_data",
            value_column="score",
            group_column="group"
        )
    """

    def __init__(self, registry: Any | None = None) -> None:
        """初始化差异分析能力。

        Args:
            registry: ToolRegistry 实例，如果为 None 则尝试获取全局 registry
        """
        self.name = "difference_analysis"
        self.display_name = "差异分析"
        self.description = "比较两组或多组数据的差异"
        self.icon = "🔬"
        self._registry = registry

    async def execute(
        self,
        session: Session,
        *,
        dataset_name: str,
        value_column: str,
        group_column: str | None = None,
        test_value: float | None = None,
        alpha: float = 0.05,
        auto_select_method: bool = True,
        **kwargs: Any,
    ) -> DifferenceAnalysisResult:
        """
        执行差异分析。

        Args:
            session: 会话对象
            dataset_name: 数据集名称
            value_column: 数值列名
            group_column: 分组列名（两组或多组比较时使用）
            test_value: 检验值（单样本检验时使用）
            alpha: 显著性水平（默认 0.05）
            auto_select_method: 是否自动选择统计方法

        Returns:
            差异分析结果
        """
        result = DifferenceAnalysisResult()

        # Step 1: 数据验证
        if not await self._validate_data(
            session, dataset_name, value_column, group_column, test_value, result
        ):
            return result

        # Step 2: 获取数据特征
        df = session.datasets.get(dataset_name)
        if df is None:
            result.message = f"数据集不存在: {dataset_name}"
            return result
        if group_column:
            groups_data = self._extract_groups(df, value_column, group_column)
            result.n_groups = len(groups_data)
            result.group_sizes = {name: len(data) for name, data in groups_data.items()}
            result.group_means = {name: float(data.mean()) for name, data in groups_data.items()}
        else:
            # 单样本检验
            data = df[value_column].dropna()
            result.n_groups = 1
            result.group_sizes = {"sample": len(data)}
            result.group_means = {"sample": float(data.mean())}

        # Step 3: 前提检验
        if auto_select_method:
            assumptions = await self._check_assumptions(
                session, dataset_name, value_column, group_column, alpha
            )
            result.normality_tests = assumptions.get("normality", {})
            result.equal_variance_test = assumptions.get("equal_variance")

            # Step 4: 自动选择统计方法
            selected_method = self._select_statistical_method(
                result.n_groups,
                assumptions,
                auto_select_method,
            )
            result.selected_method = selected_method
            result.method_reason = self._get_method_reason(selected_method, assumptions)
        else:
            # 使用默认方法
            if result.n_groups == 1:
                result.selected_method = "t_test"
            elif result.n_groups == 2:
                result.selected_method = "t_test"
            else:
                result.selected_method = "anova"
            result.method_reason = "使用默认方法（未启用自动选择）"

        # Step 5: 执行统计检验
        stat_result = await self._execute_statistical_test(
            session,
            dataset_name,
            value_column,
            group_column,
            test_value,
            result.selected_method,
            **kwargs,
        )

        # Note: registry.execute returns a dict, not SkillResult
        if isinstance(stat_result, dict):
            if not stat_result.get("success"):
                result.message = f"统计检验失败: {stat_result.get('message', '未知错误')}"
                return result
        elif hasattr(stat_result, "success") and not stat_result.success:
            result.message = f"统计检验失败: {stat_result.message}"
            return result

        # 提取统计结果
        self._extract_statistical_results(result, stat_result)

        # Step 6: 可视化
        chart_result = await self._create_visualization(
            session, dataset_name, value_column, group_column, result.selected_method
        )
        # 处理 dict 或 SkillResult 类型
        if isinstance(chart_result, dict):
            if chart_result.get("success") and chart_result.get("artifacts"):
                artifacts = chart_result["artifacts"]
                result.chart_artifact = artifacts[0] if artifacts else None
        elif chart_result.success and chart_result.artifacts:
            result.chart_artifact = chart_result.artifacts[0] if chart_result.artifacts else None

        # Step 7: 生成解释
        result.interpretation = self._generate_interpretation(result)
        result.success = True
        result.message = "差异分析完成"

        return result

    async def _validate_data(
        self,
        session: Session,
        dataset_name: str,
        value_column: str,
        group_column: str | None,
        test_value: float | None,
        result: DifferenceAnalysisResult,
    ) -> bool:
        """验证数据有效性。"""
        df = session.datasets.get(dataset_name)
        if df is None:
            result.message = f"数据集 '{dataset_name}' 不存在"
            return False

        if value_column not in df.columns:
            result.message = f"列 '{value_column}' 不存在"
            return False

        if group_column and group_column not in df.columns:
            result.message = f"分组列 '{group_column}' 不存在"
            return False

        if group_column is None and test_value is None:
            result.message = "请指定 group_column（组间比较）或 test_value（单样本检验）"
            return False

        return True

    def _extract_groups(self, df, value_column: str, group_column: str) -> dict[str, Any]:
        """提取各组数据。"""
        groups = {}
        for group_name in df[group_column].dropna().unique():
            group_data = df[df[group_column] == group_name][value_column].dropna()
            if len(group_data) > 0:
                groups[str(group_name)] = group_data
        return groups

    async def _check_assumptions(
        self,
        session: Session,
        dataset_name: str,
        value_column: str,
        group_column: str | None,
        alpha: float,
    ) -> dict[str, Any]:
        """检查统计前提假设。"""
        normality_results: dict[str, dict[str, Any]] = {}
        assumptions: dict[str, Any] = {"normality": normality_results, "equal_variance": None}

        df = session.datasets.get(dataset_name)
        if df is None:
            return assumptions

        if group_column:
            groups_data = self._extract_groups(df, value_column, group_column)
        else:
            groups_data = {"sample": df[value_column].dropna()}

        # 直接在 Capability 内部完成最小前提检验，避免依赖不存在的 Tool 协议。
        for group_name, group_data in groups_data.items():
            if len(group_data) < 3 or len(group_data) > 5000:
                normality_results[group_name] = {
                    "tested": False,
                    "reason": "样本量不在 Shapiro-Wilk 适用范围内",
                }
                continue
            try:
                normality_stat_raw, normality_p_raw = stats.shapiro(group_data)
                normality_results[group_name] = {
                    "tested": True,
                    "statistic": float(normality_stat_raw),
                    "p_value": float(normality_p_raw),
                    "normal": bool(float(normality_p_raw) > alpha),
                }
            except Exception as exc:
                normality_results[group_name] = {
                    "tested": False,
                    "reason": f"正态性检验失败: {exc}",
                }

        if len(groups_data) >= 2:
            try:
                levene_stat_raw, levene_p_raw = stats.levene(*groups_data.values())
                assumptions["equal_variance"] = {
                    "tested": True,
                    "statistic": float(levene_stat_raw),
                    "p_value": float(levene_p_raw),
                    "equal_variance": bool(float(levene_p_raw) > alpha),
                }
            except Exception as exc:
                assumptions["equal_variance"] = {
                    "tested": False,
                    "reason": f"方差齐性检验失败: {exc}",
                }

        return assumptions

    def _select_statistical_method(
        self,
        n_groups: int,
        assumptions: dict[str, Any],
        auto_select: bool,
    ) -> str:
        """根据前提检验结果选择统计方法。"""
        if not auto_select:
            if n_groups == 1:
                return "t_test"
            elif n_groups == 2:
                return "t_test"
            else:
                return "anova"

        # 检查正态性
        normality = assumptions.get("normality", {})
        is_normal = True
        if normality:
            # 如果所有组的 p 值都 > 0.05，认为符合正态性
            for col, result in normality.items():
                if not isinstance(result, dict):
                    continue
                if result.get("tested") is False:
                    continue
                if result.get("p_value", 1) < 0.05:
                    is_normal = False
                    break

        # 选择方法
        if n_groups == 1:
            return "t_test" if is_normal else "not_supported"  # 单样本非参暂未实现
        elif n_groups == 2:
            return "t_test" if is_normal else "mann_whitney"
        else:
            # 多组
            equal_variance = assumptions.get("equal_variance")
            if (
                isinstance(equal_variance, dict)
                and equal_variance.get("tested") is not False
                and equal_variance.get("p_value", 1) < 0.05
            ):
                # 方差不齐
                return "kruskal_wallis"
            return "anova" if is_normal else "kruskal_wallis"

    def _get_method_reason(self, method: str, assumptions: dict[str, Any]) -> str:
        """获取方法选择的原因说明。"""
        reasons = {
            "t_test": "数据符合正态分布假设，使用 t 检验",
            "mann_whitney": "数据不符合正态分布，使用 Mann-Whitney U 检验（非参数方法）",
            "anova": "数据符合正态分布假设，使用方差分析（ANOVA）",
            "kruskal_wallis": "数据不符合正态分布，使用 Kruskal-Wallis H 检验（非参数方法）",
            "not_supported": "当前方法暂不支持",
        }
        return reasons.get(method, "使用默认方法")

    def _get_registry(self) -> Any:
        """获取工具注册中心。"""
        if self._registry is not None:
            return self._registry
        # 延迟导入避免循环依赖
        from nini.tools.registry import create_default_tool_registry

        return create_default_tool_registry()

    async def _execute_statistical_test(
        self,
        session: Session,
        dataset_name: str,
        value_column: str,
        group_column: str | None,
        test_value: float | None,
        method: str,
        **kwargs: Any,
    ) -> SkillResult | dict[str, Any]:
        """执行统计检验。"""
        registry = self._get_registry()

        if method == "t_test":
            if test_value is not None:
                # 单样本 t 检验
                return cast(
                    SkillResult | dict[str, Any],
                    await registry.execute(
                        "t_test",
                        session,
                        dataset_name=dataset_name,
                        value_column=value_column,
                        test_value=test_value,
                        **kwargs,
                    ),
                )
            else:
                # 独立样本 t 检验
                return cast(
                    SkillResult | dict[str, Any],
                    await registry.execute(
                        "t_test",
                        session,
                        dataset_name=dataset_name,
                        value_column=value_column,
                        group_column=group_column,
                        **kwargs,
                    ),
                )
        elif method == "mann_whitney":
            return cast(
                SkillResult | dict[str, Any],
                await registry.execute(
                    "mann_whitney",
                    session,
                    dataset_name=dataset_name,
                    value_column=value_column,
                    group_column=group_column,
                    **kwargs,
                ),
            )
        elif method == "anova":
            return cast(
                SkillResult | dict[str, Any],
                await registry.execute(
                    "anova",
                    session,
                    dataset_name=dataset_name,
                    value_column=value_column,
                    group_column=group_column,
                    **kwargs,
                ),
            )
        elif method == "kruskal_wallis":
            return cast(
                SkillResult | dict[str, Any],
                await registry.execute(
                    "kruskal_wallis",
                    session,
                    dataset_name=dataset_name,
                    value_column=value_column,
                    group_column=group_column,
                    **kwargs,
                ),
            )
        else:
            return SkillResult(success=False, message=f"不支持的方法: {method}")

    def _extract_statistical_results(
        self, result: DifferenceAnalysisResult, stat_result: SkillResult | dict[str, Any]
    ) -> None:
        """从统计结果中提取关键信息。"""
        # 处理 dict 类型结果（ToolRegistry.execute 返回 dict）
        if isinstance(stat_result, dict):
            if not stat_result.get("success") or not stat_result.get("data"):
                return
            data = stat_result["data"]
        else:
            if not stat_result.success or not stat_result.data:
                return
            data = stat_result.data
        result.test_statistic = (
            data.get("t_statistic")
            or data.get("f_statistic")
            or data.get("u_statistic")
            or data.get("h_statistic")
        )
        result.p_value = data.get("p_value")
        result.degrees_of_freedom = data.get("df") or data.get("df_between")
        result.effect_size = data.get("cohens_d") or data.get("eta_squared") or data.get("r")
        result.effect_type = (
            "cohens_d"
            if "cohens_d" in data
            else "eta_squared" if "eta_squared" in data else "r" if "r" in data else ""
        )
        result.significant = data.get("significant", False)
        result.post_hoc = data.get("post_hoc")

    async def _create_visualization(
        self,
        session: Session,
        dataset_name: str,
        value_column: str,
        group_column: str | None,
        method: str,
    ) -> SkillResult | dict[str, Any]:
        """创建可视化图表。"""
        registry = self._get_registry()

        # 选择图表类型
        if group_column:
            if method in ["anova", "kruskal_wallis"]:
                chart_type = "box"
            else:
                chart_type = "box"
        else:
            chart_type = "histogram"

        return cast(
            SkillResult | dict[str, Any],
            await registry.execute(
                "create_chart",
                session,
                dataset_name=dataset_name,
                chart_type=chart_type,
                x_column=group_column,
                y_column=value_column,
                title=f"{self.display_name} - {value_column}",
            ),
        )

    def _generate_interpretation(self, result: DifferenceAnalysisResult) -> str:
        """生成解释性报告。"""
        parts = []

        # 方法说明
        parts.append(f"## 分析方法")
        parts.append(f"选择方法: {result.selected_method}")
        parts.append(f"选择理由: {result.method_reason}")

        # 统计结果
        parts.append(f"\n## 统计结果")
        if result.n_groups == 2:
            parts.append(f"比较两组数据差异")
        elif result.n_groups > 2:
            parts.append(f"比较 {result.n_groups} 组数据差异")

        if result.test_statistic is not None:
            parts.append(f"检验统计量: {result.test_statistic:.3f}")
        if result.p_value is not None:
            parts.append(f"p 值: {result.p_value:.4f}")
        if result.effect_size is not None:
            parts.append(f"效应量 ({result.effect_type}): {result.effect_size:.3f}")

        # 结论
        parts.append(f"\n## 结论")
        if result.significant:
            parts.append(f"结果显著 (p < 0.05)，拒绝原假设，认为各组间存在显著差异。")
            # 效应量解释
            if result.effect_size is not None:
                if result.effect_type == "cohens_d":
                    if abs(result.effect_size) < 0.2:
                        parts.append("效应量较小 (Cohen's d < 0.2)。")
                    elif abs(result.effect_size) < 0.5:
                        parts.append("效应量中等 (Cohen's d = 0.2-0.5)。")
                    elif abs(result.effect_size) < 0.8:
                        parts.append("效应量较大 (Cohen's d = 0.5-0.8)。")
                    else:
                        parts.append("效应量很大 (Cohen's d > 0.8)。")
        else:
            parts.append(
                f"结果不显著 (p = {result.p_value:.4f} >= 0.05)，无法拒绝原假设，未发现各组间存在显著差异。"
            )

        # 事后检验
        if result.post_hoc:
            parts.append(f"\n## 事后检验 (Tukey HSD)")
            for comp in result.post_hoc[:5]:  # 最多显示 5 个
                g1, g2 = comp.get("group1"), comp.get("group2")
                p = comp.get("p_value")
                sig = "显著" if comp.get("significant") else "不显著"
                parts.append(f"- {g1} vs {g2}: p = {p:.4f} ({sig})")

        return "\n".join(parts)
