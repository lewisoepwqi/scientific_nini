"""样本量计算工具。

支持两组均值比较（t 检验）、多组比较（ANOVA）、比例差异三种设计类型的样本量计算，
基于 statsmodels.stats.power 实现功效分析。
"""

from __future__ import annotations

import math
from typing import Any

from nini.agent.session import Session
from nini.tools.base import Tool, ToolResult


class SampleSizeTool(Tool):
    """样本量计算工具——基于效应量、显著性水平和检验功效估算所需样本量。"""

    @property
    def name(self) -> str:
        return "sample_size"

    @property
    def description(self) -> str:
        return (
            "计算实验所需样本量。支持三种设计：two_sample_ttest（两组均值比较）、"
            "anova（多组均值比较）、proportion（比例差异）。"
            "基于效应量（effect_size）、显著性水平（alpha）和检验功效（power）估算每组所需样本量。"
        )

    @property
    def category(self) -> str:
        return "statistics"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "design_type": {
                    "type": "string",
                    "enum": ["two_sample_ttest", "anova", "proportion"],
                    "description": (
                        "实验设计类型：two_sample_ttest（两组均值比较，Cohen's d 效应量）、"
                        "anova（多组均值比较，Cohen's f 效应量）、"
                        "proportion（两组比例差异，Cohen's h 效应量或直接传入两组比例）"
                    ),
                },
                "effect_size": {
                    "type": "number",
                    "description": (
                        "效应量。two_sample_ttest 使用 Cohen's d（小=0.2, 中=0.5, 大=0.8）；"
                        "anova 使用 Cohen's f（小=0.1, 中=0.25, 大=0.4）；"
                        "proportion 使用 Cohen's h（可由两组比例自动计算，或直接传入）"
                    ),
                },
                "alpha": {
                    "type": "number",
                    "description": "显著性水平（I 类错误率），默认 0.05",
                    "default": 0.05,
                },
                "power": {
                    "type": "number",
                    "description": "检验功效（1 - II 类错误率），默认 0.8",
                    "default": 0.8,
                },
                "groups": {
                    "type": "integer",
                    "description": "组数，仅 anova 设计需要，默认 2",
                    "default": 2,
                },
                "p1": {
                    "type": "number",
                    "description": "第一组比例，仅 proportion 设计使用（与 p2 搭配可自动计算 Cohen's h）",
                },
                "p2": {
                    "type": "number",
                    "description": "第二组比例，仅 proportion 设计使用（与 p1 搭配可自动计算 Cohen's h）",
                },
                "alternative": {
                    "type": "string",
                    "enum": ["two-sided", "one-sided"],
                    "description": "检验方向，默认 two-sided（双侧）",
                    "default": "two-sided",
                },
            },
            "required": ["design_type", "effect_size"],
        }

    @property
    def is_idempotent(self) -> bool:
        return True

    @property
    def research_domain(self) -> str:
        return "experiment_design"

    @property
    def difficulty_level(self) -> str:
        return "intermediate"

    @property
    def typical_use_cases(self) -> list[str]:
        return [
            "实验设计阶段估算所需受试者数量",
            "临床试验样本量计算",
            "功效分析与统计把握度评估",
        ]

    @property
    def output_types(self) -> list[str]:
        return ["sample_size_result"]

    async def execute(self, session: Session, **kwargs: Any) -> ToolResult:
        """执行样本量计算。"""
        design_type: str | None = kwargs.get("design_type")
        effect_size: float | None = kwargs.get("effect_size")
        alpha: float = float(kwargs.get("alpha", 0.05))
        power: float = float(kwargs.get("power", 0.8))
        groups: int = int(kwargs.get("groups", 2))
        p1: float | None = kwargs.get("p1")
        p2: float | None = kwargs.get("p2")
        alternative: str = kwargs.get("alternative", "two-sided")

        # 参数校验
        if not design_type:
            return ToolResult(
                success=False,
                message="缺少必要参数：design_type（实验设计类型）",
            )

        if effect_size is None and not (design_type == "proportion" and p1 is not None and p2 is not None):
            return ToolResult(
                success=False,
                message="缺少必要参数：effect_size（效应量）。"
                "proportion 设计可改为提供 p1 和 p2（两组比例）来自动计算效应量。",
            )

        if not (0 < alpha < 1):
            return ToolResult(success=False, message="alpha 必须在 (0, 1) 范围内")
        if not (0 < power < 1):
            return ToolResult(success=False, message="power 必须在 (0, 1) 范围内")

        try:
            return self._calculate(
                design_type=design_type,
                effect_size=effect_size,
                alpha=alpha,
                power=power,
                groups=groups,
                p1=p1,
                p2=p2,
                alternative=alternative,
            )
        except ImportError:
            return ToolResult(
                success=False,
                message="样本量计算依赖 statsmodels 库，请运行 pip install statsmodels 后重试。",
            )
        except Exception as exc:
            return ToolResult(success=False, message=f"样本量计算失败：{exc}")

    def _calculate(
        self,
        design_type: str,
        effect_size: float | None,
        alpha: float,
        power: float,
        groups: int,
        p1: float | None,
        p2: float | None,
        alternative: str,
    ) -> ToolResult:
        """内部计算逻辑，按设计类型分派。"""
        # statsmodels 的 alternative 使用 'two-sided' / 'larger' / 'smaller'
        # 本工具简化为双侧/单侧，单侧映射为 'larger'
        sm_alternative = "two-sided" if alternative == "two-sided" else "larger"

        if design_type == "two_sample_ttest":
            return self._two_sample_ttest(
                effect_size=float(effect_size),  # type: ignore[arg-type]
                alpha=alpha,
                power=power,
                alternative=sm_alternative,
            )
        elif design_type == "anova":
            return self._anova(
                effect_size=float(effect_size),  # type: ignore[arg-type]
                alpha=alpha,
                power=power,
                groups=groups,
            )
        elif design_type == "proportion":
            return self._proportion(
                effect_size=effect_size,
                alpha=alpha,
                power=power,
                p1=p1,
                p2=p2,
                alternative=sm_alternative,
            )
        else:
            return ToolResult(
                success=False,
                message=f"不支持的设计类型：{design_type}。"
                "请使用 two_sample_ttest、anova 或 proportion。",
            )

    def _two_sample_ttest(
        self, effect_size: float, alpha: float, power: float, alternative: str
    ) -> ToolResult:
        """两组均值比较（独立样本 t 检验）样本量计算。"""
        from statsmodels.stats.power import TTestIndPower

        analysis = TTestIndPower()
        n = analysis.solve_power(
            effect_size=effect_size,
            alpha=alpha,
            power=power,
            alternative=alternative,
        )
        n_ceil = math.ceil(n)

        return ToolResult(
            success=True,
            data={
                "design_type": "two_sample_ttest",
                "n_per_group": n_ceil,
                "total_n": n_ceil * 2,
                "effect_size": effect_size,
                "alpha": alpha,
                "power": power,
                "alternative": alternative,
            },
            message=(
                f"两组 t 检验样本量计算结果：每组 {n_ceil} 例，共 {n_ceil * 2} 例。\n"
                f"参数：效应量（Cohen's d）= {effect_size}，α = {alpha}，功效 = {power}，{alternative}检验。\n"
                "⚠️ 本结果为草稿级（O2），实际样本量需结合研究背景和文献由专业人员确认。"
            ),
        )

    def _anova(
        self, effect_size: float, alpha: float, power: float, groups: int
    ) -> ToolResult:
        """多组均值比较（单因素 ANOVA）样本量计算。"""
        from statsmodels.stats.power import FTestAnovaPower

        if groups < 2:
            return ToolResult(success=False, message="ANOVA 设计需要至少 2 组（groups >= 2）")

        analysis = FTestAnovaPower()
        # solve_power 返回总样本量（Total N），需除以组数得到每组样本量
        n_total = analysis.solve_power(
            effect_size=effect_size,
            alpha=alpha,
            power=power,
            k_groups=groups,
        )
        n_ceil = math.ceil(n_total / groups)
        total = n_ceil * groups

        return ToolResult(
            success=True,
            data={
                "design_type": "anova",
                "n_per_group": n_ceil,
                "total_n": total,
                "groups": groups,
                "effect_size": effect_size,
                "alpha": alpha,
                "power": power,
            },
            message=(
                f"ANOVA 样本量计算结果：每组 {n_ceil} 例，共 {groups} 组，合计 {total} 例。\n"
                f"参数：效应量（Cohen's f）= {effect_size}，α = {alpha}，功效 = {power}，{groups} 组。\n"
                "⚠️ 本结果为草稿级（O2），实际样本量需结合研究背景和文献由专业人员确认。"
            ),
        )

    def _proportion(
        self,
        effect_size: float | None,
        alpha: float,
        power: float,
        p1: float | None,
        p2: float | None,
        alternative: str,
    ) -> ToolResult:
        """两组比例差异（卡方检验）样本量计算。"""
        from statsmodels.stats.power import NormalIndPower
        from statsmodels.stats.proportion import proportion_effectsize

        # 若提供了 p1、p2，则自动计算 Cohen's h
        if p1 is not None and p2 is not None:
            h = float(proportion_effectsize(p1, p2))
            used_effect_size = abs(h)
            effect_size_note = f"由 p1={p1}, p2={p2} 自动计算 Cohen's h = {used_effect_size:.4f}"
        elif effect_size is not None:
            used_effect_size = float(effect_size)
            effect_size_note = f"Cohen's h = {used_effect_size}"
        else:
            return ToolResult(
                success=False,
                message="proportion 设计需提供 effect_size（Cohen's h），或同时提供 p1 和 p2。",
            )

        analysis = NormalIndPower()
        n = analysis.solve_power(
            effect_size=used_effect_size,
            alpha=alpha,
            power=power,
            alternative=alternative,
        )
        n_ceil = math.ceil(n)

        return ToolResult(
            success=True,
            data={
                "design_type": "proportion",
                "n_per_group": n_ceil,
                "total_n": n_ceil * 2,
                "effect_size": used_effect_size,
                "p1": p1,
                "p2": p2,
                "alpha": alpha,
                "power": power,
                "alternative": alternative,
            },
            message=(
                f"比例差异检验样本量计算结果：每组 {n_ceil} 例，共 {n_ceil * 2} 例。\n"
                f"参数：{effect_size_note}，α = {alpha}，功效 = {power}，{alternative}检验。\n"
                "⚠️ 本结果为草稿级（O2），实际样本量需结合研究背景和文献由专业人员确认。"
            ),
        )
