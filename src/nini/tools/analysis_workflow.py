"""内部分析编排层。"""

from __future__ import annotations

from typing import Any

import pandas as pd
from scipy import stats

from nini.agent.session import Session
from nini.tools.base import SkillResult


class AnalysisWorkflowEngine:
    """组合基础工具完成复合分析。"""

    def __init__(self) -> None:
        from nini.tools.chart_session import ChartSessionSkill
        from nini.tools.dataset_catalog import DatasetCatalogSkill
        from nini.tools.stat_interpret import StatInterpretSkill
        from nini.tools.stat_model import StatModelSkill
        from nini.tools.stat_test import StatTestSkill

        self._catalog = DatasetCatalogSkill()
        self._chart = ChartSessionSkill()
        self._stat_test = StatTestSkill()
        self._stat_model = StatModelSkill()
        self._interpret = StatInterpretSkill()

    async def complete_comparison(
        self,
        session: Session,
        *,
        dataset_name: str,
        value_column: str,
        group_column: str,
        journal_style: str = "nature",
        paired: bool = False,
    ) -> SkillResult:
        profile = await self._catalog.execute(
            session,
            operation="profile",
            dataset_name=dataset_name,
            view="full",
            n_rows=10,
        )
        if not profile.success:
            return profile

        df = session.datasets.get(dataset_name)
        if df is None:
            return SkillResult(success=False, message=f"数据集 '{dataset_name}' 不存在")
        if value_column not in df.columns:
            return SkillResult(success=False, message=f"列 '{value_column}' 不存在")
        if group_column not in df.columns:
            return SkillResult(success=False, message=f"分组列 '{group_column}' 不存在")

        clean_df = df[[value_column, group_column]].dropna()
        groups = clean_df[group_column].unique()
        if len(groups) != 2:
            return SkillResult(
                success=False,
                message=f"此技能适用于恰好 2 个分组，当前有 {len(groups)} 个分组。",
            )

        assumptions = self._compare_assumptions(clean_df, value_column, group_column)
        method = "paired_t" if paired else "independent_t"
        test_type = "t_test"
        if assumptions["use_non_parametric"]:
            method = "mann_whitney"
            test_type = "mann_whitney"

        stat_result = await self._stat_test.execute(
            session,
            method=method,
            dataset_name=dataset_name,
            value_column=value_column,
            group_column=group_column,
        )
        if not stat_result.success:
            return stat_result

        interpret = await self._interpret.execute(
            session,
            test_type=test_type,
            result=stat_result.data,
        )
        chart = await self._chart.execute(
            session,
            operation="create",
            dataset_name=dataset_name,
            chart_type="box",
            x_column=group_column,
            y_column=value_column,
            title=f"{value_column} 按 {group_column} 分组比较",
            journal_style=journal_style,
        )
        report_summary = interpret.data.get("interpretation", "") if isinstance(interpret.data, dict) else ""
        return SkillResult(
            success=True,
            message=report_summary or stat_result.message,
            data={
                "workflow": "complete_comparison",
                "data_quality": profile.data.get("quality", {}) if isinstance(profile.data, dict) else {},
                "profile": profile.data,
                "assumptions": assumptions,
                "test_result": stat_result.data,
                "effect_size": self._comparison_effect_size(stat_result.data),
                "report": {"summary": report_summary or interpret.message},
                "chart_resource_id": self._resource_id(chart.data),
                "selected_method": method,
            },
            has_chart=chart.has_chart,
            chart_data=chart.chart_data,
            artifacts=chart.artifacts,
        )

    async def complete_anova(
        self,
        session: Session,
        *,
        dataset_name: str,
        value_column: str,
        group_column: str,
        journal_style: str = "nature",
    ) -> SkillResult:
        profile = await self._catalog.execute(
            session,
            operation="profile",
            dataset_name=dataset_name,
            view="full",
            n_rows=10,
        )
        if not profile.success:
            return profile

        df = session.datasets.get(dataset_name)
        if df is None:
            return SkillResult(success=False, message=f"数据集 '{dataset_name}' 不存在")
        clean_df = df[[value_column, group_column]].dropna()
        groups = clean_df[group_column].unique()
        if len(groups) < 2:
            return SkillResult(success=False, message="至少需要 2 个分组进行 ANOVA 分析")

        assumptions = self._anova_assumptions(clean_df, value_column, group_column)
        method = "kruskal_wallis" if assumptions["use_non_parametric"] else "one_way_anova"
        test_type = "kruskal_wallis" if method == "kruskal_wallis" else "anova"
        stat_result = await self._stat_test.execute(
            session,
            method=method,
            dataset_name=dataset_name,
            value_column=value_column,
            group_column=group_column,
        )
        if not stat_result.success:
            return stat_result

        interpret = await self._interpret.execute(
            session,
            test_type=test_type,
            result=stat_result.data,
        )
        chart = await self._chart.execute(
            session,
            operation="create",
            dataset_name=dataset_name,
            chart_type="box",
            x_column=group_column,
            y_column=value_column,
            title=f"{value_column} 按 {group_column} 的多组比较",
            journal_style=journal_style,
        )
        report_summary = interpret.data.get("interpretation", "") if isinstance(interpret.data, dict) else ""
        return SkillResult(
            success=True,
            message=report_summary or stat_result.message,
            data={
                "workflow": "complete_anova",
                "data_quality": profile.data.get("quality", {}) if isinstance(profile.data, dict) else {},
                "profile": profile.data,
                "assumptions": assumptions,
                "anova": stat_result.data,
                "post_hoc": stat_result.data.get("post_hoc", []) if isinstance(stat_result.data, dict) else [],
                "effect_size": self._anova_effect_size(stat_result.data),
                "report": {"summary": report_summary or interpret.message},
                "chart_resource_id": self._resource_id(chart.data),
                "selected_method": method,
            },
            has_chart=chart.has_chart,
            chart_data=chart.chart_data,
            artifacts=chart.artifacts,
        )

    async def correlation_analysis(
        self,
        session: Session,
        *,
        dataset_name: str,
        columns: list[str],
        method: str = "pearson",
        journal_style: str = "nature",
    ) -> SkillResult:
        profile = await self._catalog.execute(
            session,
            operation="profile",
            dataset_name=dataset_name,
            view="full",
            n_rows=10,
        )
        if not profile.success:
            return profile

        stat_result = await self._stat_model.execute(
            session,
            method="correlation",
            dataset_name=dataset_name,
            columns=columns,
            correlation_method=method,
        )
        if not stat_result.success:
            return stat_result

        interpret = await self._interpret.execute(
            session,
            test_type="correlation",
            result=stat_result.data,
        )
        chart = await self._chart.execute(
            session,
            operation="create",
            dataset_name=dataset_name,
            chart_type="heatmap",
            columns=columns,
            title=f"{method.title()} 相关矩阵",
            journal_style=journal_style,
        )
        report_summary = interpret.data.get("interpretation", "") if isinstance(interpret.data, dict) else ""
        return SkillResult(
            success=True,
            message=report_summary or stat_result.message,
            data={
                "workflow": "correlation_analysis",
                "profile": profile.data,
                **(stat_result.data if isinstance(stat_result.data, dict) else {}),
                "report": {"summary": report_summary or interpret.message},
                "chart_resource_id": self._resource_id(chart.data),
            },
            has_chart=chart.has_chart,
            chart_data=chart.chart_data,
            artifacts=chart.artifacts,
        )

    async def regression_analysis(
        self,
        session: Session,
        *,
        dataset_name: str,
        dependent_var: str,
        independent_vars: list[str],
        journal_style: str = "nature",
    ) -> SkillResult:
        profile = await self._catalog.execute(
            session,
            operation="profile",
            dataset_name=dataset_name,
            view="full",
            n_rows=10,
        )
        if not profile.success:
            return profile

        method = "multiple_regression" if len(independent_vars) > 1 else "linear_regression"
        stat_result = await self._stat_model.execute(
            session,
            method=method,
            dataset_name=dataset_name,
            dependent_var=dependent_var,
            independent_vars=independent_vars,
        )
        if not stat_result.success:
            return stat_result

        interpret = await self._interpret.execute(
            session,
            test_type="regression",
            result=stat_result.data,
        )
        chart = await self._chart.execute(
            session,
            operation="create",
            dataset_name=dataset_name,
            chart_type="scatter",
            x_column=independent_vars[0],
            y_column=dependent_var,
            title=f"{dependent_var} 与 {independent_vars[0]} 的回归关系",
            journal_style=journal_style,
        )
        report_summary = interpret.data.get("interpretation", "") if isinstance(interpret.data, dict) else ""
        return SkillResult(
            success=True,
            message=report_summary or stat_result.message,
            data={
                "workflow": "regression_analysis",
                "profile": profile.data,
                "quality_report": profile.data.get("quality", {}) if isinstance(profile.data, dict) else {},
                "regression": stat_result.data,
                "report": {"summary": report_summary or interpret.message},
                "chart_resource_id": self._resource_id(chart.data),
                "selected_method": method,
            },
            has_chart=chart.has_chart,
            chart_data=chart.chart_data,
            artifacts=chart.artifacts,
        )

    def _compare_assumptions(
        self,
        df: pd.DataFrame,
        value_column: str,
        group_column: str,
    ) -> dict[str, Any]:
        groups = df[group_column].dropna().unique()
        data1 = df[df[group_column] == groups[0]][value_column].dropna()
        data2 = df[df[group_column] == groups[1]][value_column].dropna()
        normality1 = self._normality_payload(data1)
        normality2 = self._normality_payload(data2)
        levene_stat, levene_p = stats.levene(data1, data2)
        use_non_parametric = not normality1["normal"] or not normality2["normal"]
        reason = "满足正态性假设"
        if use_non_parametric:
            reason = "至少一组不满足正态性假设"
        return {
            "normality_test1": normality1,
            "normality_test2": normality2,
            "variance_test": {
                "statistic": float(levene_stat),
                "p_value": float(levene_p),
                "equal_variance": bool(levene_p > 0.05),
            },
            "use_non_parametric": use_non_parametric,
            "reason": reason,
        }

    def _anova_assumptions(
        self,
        df: pd.DataFrame,
        value_column: str,
        group_column: str,
    ) -> dict[str, Any]:
        normality: dict[str, Any] = {}
        non_normal = False
        for group in df[group_column].dropna().unique():
            sample = df[df[group_column] == group][value_column].dropna()
            payload = self._normality_payload(sample)
            normality[str(group)] = payload
            if not payload["normal"]:
                non_normal = True
        return {
            "normality": normality,
            "use_non_parametric": non_normal,
            "reason": "至少一组不满足正态性假设" if non_normal else "满足正态性假设",
        }

    def _normality_payload(self, series: pd.Series) -> dict[str, Any]:
        if len(series) < 3 or len(series) > 5000:
            return {"normal": True, "note": "样本量超出 Shapiro-Wilk 建议范围，默认不触发降级"}
        stat, p_value = stats.shapiro(series)
        return {
            "statistic": float(stat),
            "p_value": float(p_value),
            "normal": bool(p_value > 0.05),
        }

    def _comparison_effect_size(self, result: Any) -> dict[str, Any]:
        if not isinstance(result, dict):
            return {}
        if "cohens_d" in result:
            return {"type": "cohens_d", "value": result.get("cohens_d")}
        if "effect_size_r" in result:
            return {"type": "r", "value": result.get("effect_size_r")}
        return {}

    def _anova_effect_size(self, result: Any) -> dict[str, Any]:
        if not isinstance(result, dict):
            return {}
        if "eta_squared" in result:
            return {"type": "eta_squared", "value": result.get("eta_squared")}
        return {}

    def _resource_id(self, data: Any) -> str | None:
        if isinstance(data, dict):
            value = data.get("resource_id")
            return str(value) if value else None
        return None
