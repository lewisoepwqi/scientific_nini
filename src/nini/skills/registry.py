"""技能注册中心。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from nini.agent.lane_queue import lane_queue
from nini.agent.session import Session
from nini.config import settings
from nini.skills.base import Skill, SkillResult
from nini.skills.clean_data import CleanDataSkill, RecommendCleaningStrategySkill
from nini.skills.code_exec import RunCodeSkill
from nini.skills.data_ops import DataSummarySkill, LoadDatasetSkill, PreviewDataSkill
from nini.skills.data_quality import DataQualitySkill, DataQualityReportSkill
from nini.skills.export import ExportChartSkill
from nini.skills.fetch_url import FetchURLSkill
from nini.skills.organize_workspace import OrganizeWorkspaceSkill
from nini.skills.report import GenerateReportSkill
from nini.skills.statistics import (
    ANOVASkill,
    CorrelationSkill,
    KruskalWallisSkill,
    MannWhitneySkill,
    RegressionSkill,
    TTestSkill,
)
from nini.skills.interpretation import InterpretStatisticalResultSkill
from nini.skills.visualization import CreateChartSkill
from nini.skills.workflow_skill import ApplyWorkflowSkill, ListWorkflowsSkill, SaveWorkflowSkill
from nini.skills.markdown_scanner import render_skills_snapshot, scan_markdown_skills

# 复合技能模板
from nini.skills.templates import (
    CompleteANOVASkill,
    CompleteComparisonSkill,
    CorrelationAnalysisSkill,
)

logger = logging.getLogger(__name__)


# 统计方法的降级映射
_FALLBACK_MAP: dict[str, list[dict[str, Any]]] = {
    "t_test": [
        {
            "fallback_skill": "mann_whitney",
            "condition": "non_normal",
            "reason": "数据不符合正态性假设，改用非参数检验",
        },
    ],
    "anova": [
        {
            "fallback_skill": "kruskal_wallis",
            "condition": "non_normal_or_variance_hetero",
            "reason": "数据不符合正态性或方差齐性假设，改用非参数检验",
        },
    ],
}


class SkillRegistry:
    """管理所有已注册的技能。"""

    def __init__(self):
        self._skills: dict[str, Skill] = {}
        self._markdown_skills: list[dict[str, Any]] = []

    def register(self, skill: Skill) -> None:
        """注册一个技能。"""
        if skill.name in self._skills:
            logger.warning("技能 %s 已存在，将被覆盖", skill.name)
        self._skills[skill.name] = skill
        logger.info("注册技能: %s", skill.name)

    def unregister(self, name: str) -> None:
        """注销一个技能。"""
        self._skills.pop(name, None)

    def get(self, name: str) -> Skill | None:
        """获取技能。"""
        return self._skills.get(name)

    def list_skills(self) -> list[str]:
        """列出所有技能名称。"""
        return list(self._skills.keys())

    def list_function_skills(self) -> list[dict[str, Any]]:
        """列出 Function Skill 元数据。"""
        items: list[dict[str, Any]] = []
        for skill in self._skills.values():
            items.append(
                {
                    "type": "function",
                    "name": skill.name,
                    "description": skill.description,
                    "category": skill.category,
                    "location": f"{skill.__class__.__module__}.{skill.__class__.__name__}",
                    "enabled": True,
                    "expose_to_llm": skill.expose_to_llm,
                    "metadata": {
                        "parameters": skill.parameters,
                        "is_idempotent": skill.is_idempotent,
                    },
                }
            )
        return items

    def list_markdown_skills(self) -> list[dict[str, Any]]:
        return list(self._markdown_skills)

    def list_skill_catalog(self, skill_type: str | None = None) -> list[dict[str, Any]]:
        """返回聚合技能目录。"""
        all_items = self.list_function_skills() + self.list_markdown_skills()
        if skill_type:
            skill_type = skill_type.strip().lower()
            if skill_type in {"function", "markdown"}:
                return [item for item in all_items if item.get("type") == skill_type]
        return all_items

    def reload_markdown_skills(self) -> list[dict[str, Any]]:
        """重新扫描 Markdown 技能并应用冲突策略。"""
        markdown_skills = scan_markdown_skills(settings.skills_dir)
        function_names = set(self._skills.keys())
        items: list[dict[str, Any]] = []
        for skill in markdown_skills:
            item = skill.to_dict()
            if skill.name in function_names:
                item["enabled"] = False
                metadata = dict(item.get("metadata") or {})
                metadata["conflict_with"] = "function"
                item["metadata"] = metadata
                logger.warning("Markdown 技能与 Function Skill 同名，已禁用: %s", skill.name)
            items.append(item)
        self._markdown_skills = items
        return self.list_markdown_skills()

    def write_skills_snapshot(self) -> None:
        """将聚合技能目录写入快照文件。"""
        catalog = self.list_skill_catalog()
        content = render_skills_snapshot(catalog)
        settings.skills_snapshot_path.write_text(content, encoding="utf-8")

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """获取暴露给 LLM 的技能工具定义（过滤 expose_to_llm=False）。"""
        return [s.get_tool_definition() for s in self._skills.values() if s.expose_to_llm]

    async def execute(
        self,
        skill_name: str,
        session: Session,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """执行技能并返回结果字典。"""
        skill = self._skills.get(skill_name)
        if skill is None:
            return {"success": False, "message": f"未知技能: {skill_name}"}

        try:
            # 同一会话内串行执行，避免并发读写同一 DataFrame
            result = await lane_queue.execute(
                session.id,
                self._execute_skill_in_thread(skill=skill, session=session, kwargs=kwargs),
            )
            return result.to_dict()
        except Exception as e:
            logger.error("技能 %s 执行失败: %s", skill_name, e, exc_info=True)
            return {"success": False, "message": f"技能执行失败: {e}"}

    async def execute_with_fallback(
        self,
        skill_name: str,
        session: Session,
        enable_fallback: bool = True,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """执行技能，在失败时尝试降级策略。

        Args:
            skill_name: 要执行的技能名称
            session: 会话对象
            enable_fallback: 是否启用降级策略
            **kwargs: 技能参数

        Returns:
            包含执行结果和降级信息的字典
        """
        result: dict[str, Any] = {
            "success": False,
            "original_skill": skill_name,
            "fallback": False,
        }

        # 首先尝试执行原始技能
        original_result = await self.execute(skill_name, session=session, **kwargs)

        # 如果原始技能成功，直接返回
        if original_result.get("success") and enable_fallback:
            # 检查是否需要基于前提条件降级
            should_fallback = await self._should_trigger_fallback(
                skill_name, session, kwargs, original_result
            )
            if should_fallback["trigger"]:
                # 执行降级
                return await self._execute_fallback(skill_name, session, kwargs, should_fallback)
            return original_result
        elif original_result.get("success"):
            return original_result

        # 原始技能失败，尝试降级
        if enable_fallback and skill_name in _FALLBACK_MAP:
            return await self._execute_fallback(
                skill_name, session, kwargs, {"reason": "原始技能执行失败"}
            )

        return original_result

    async def _should_trigger_fallback(
        self,
        skill_name: str,
        session: Session,
        kwargs: dict[str, Any],
        result: dict[str, Any],
    ) -> dict[str, Any]:
        """判断是否应该触发降级。"""
        trigger = False
        reason = ""

        # 检查数据前提条件
        if skill_name in ["t_test", "anova"]:
            dataset_name = kwargs.get("dataset_name")
            value_column = kwargs.get("value_column")
            group_column = kwargs.get("group_column")

            if dataset_name and value_column and group_column:
                df = session.datasets.get(dataset_name)
                if df is not None:
                    groups = df[group_column].dropna().unique()

                    # 检查正态性
                    non_normal_groups = []
                    for group in groups:
                        group_data = df[df[group_column] == group][value_column].dropna()
                        if len(group_data) >= 3 and len(group_data) <= 5000:
                            try:
                                stat, p = stats.shapiro(group_data)
                                if p < 0.05:
                                    non_normal_groups.append(str(group))
                            except Exception:
                                pass

                    if non_normal_groups:
                        trigger = True
                        reason = f"以下组不符合正态性假设: {', '.join(non_normal_groups)}"

        return {"trigger": trigger, "reason": reason}

    async def _execute_fallback(
        self,
        skill_name: str,
        session: Session,
        kwargs: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """执行降级技能。"""
        fallbacks = _FALLBACK_MAP.get(skill_name, [])
        for fallback_config in fallbacks:
            fallback_skill = fallback_config["fallback_skill"]

            # 检查降级技能是否存在
            if fallback_skill not in self._skills:
                continue

            # 特殊处理：mann_whitney 使用 t_test 的参数
            fallback_kwargs = kwargs.copy()
            if fallback_skill == "mann_whitney":
                # Mann-Whitney 使用与 t_test 相同的参数
                pass
            elif fallback_skill == "kruskal_wallis":
                # Kruskal-Wallis 使用与 anova 相同的参数
                pass

            # 执行降级技能
            fallback_result = await self.execute(fallback_skill, session=session, **fallback_kwargs)

            if fallback_result.get("success"):
                return {
                    **fallback_result,
                    "original_skill": skill_name,
                    "fallback_skill": fallback_skill,
                    "fallback": True,
                    "fallback_reason": fallback_config["reason"],
                }

        # 所有降级都失败
        return {
            "success": False,
            "message": f"技能 {skill_name} 及其降级策略均失败",
            "original_skill": skill_name,
            "fallback": False,
        }

    async def diagnose_data_problem(
        self,
        session: Session,
        dataset_name: str,
        target_column: str | None = None,
        include_quality_score: bool = True,
    ) -> dict[str, Any]:
        """诊断数据问题并提供修复建议。

        Args:
            session: 会话对象
            dataset_name: 数据集名称
            target_column: 目标列名（可选）
            include_quality_score: 是否包含质量评分（默认 True）

        Returns:
            诊断结果字典
        """
        from nini.skills.data_quality import evaluate_data_quality

        diagnosis: dict[str, Any] = {
            "dataset_name": dataset_name,
            "issues": [],
            "suggestions": [],
        }

        df = session.datasets.get(dataset_name)
        if df is None:
            diagnosis["issues"].append({"type": "dataset_not_found", "message": "数据集不存在"})
            return diagnosis

        # 集成质量评分
        if include_quality_score:
            try:
                quality_report = evaluate_data_quality(df, dataset_name)
                diagnosis["quality_score"] = {
                    "overall_score": round(quality_report.overall_score, 2),
                    "grade": quality_report.summary.get("grade", "未知"),
                    "dimension_scores": {
                        ds.dimension.value: round(ds.score, 2)
                        for ds in quality_report.dimension_scores
                    },
                }
                # 将质量问题的建议添加到诊断建议中
                for ds in quality_report.dimension_scores:
                    for suggestion in ds.suggestions:
                        diagnosis["suggestions"].append(
                            {
                                "type": f"quality_{ds.dimension.value}",
                                "severity": "medium" if ds.score >= 70 else "high",
                                "message": suggestion,
                            }
                        )
            except Exception as e:
                logger.warning("质量评分计算失败: %s", e)

        # 分析列
        columns_to_analyze = [target_column] if target_column else df.columns.tolist()

        for col in columns_to_analyze:
            if col not in df.columns:
                continue

            col_data = df[col]

            # 检查缺失值
            missing_count = col_data.isna().sum()
            if missing_count > 0:
                missing_ratio = missing_count / len(col_data)
                diagnosis["missing_values"] = {
                    "column": col,
                    "count": int(missing_count),
                    "ratio": float(missing_ratio),
                }
                if missing_ratio > 0.5:
                    diagnosis["suggestions"].append(
                        {
                            "type": "missing_values",
                            "severity": "high",
                            "message": f"列 '{col}' 缺失值超过 50%，建议删除该列或使用插补方法",
                        }
                    )
                elif missing_ratio > 0.1:
                    diagnosis["suggestions"].append(
                        {
                            "type": "missing_values",
                            "severity": "medium",
                            "message": f"列 '{col}' 有 {missing_count} 个缺失值，考虑使用均值/中位数填充",
                        }
                    )

            # 检查数据类型（仅对数值列）
            if pd.api.types.is_numeric_dtype(col_data):
                # 检查异常值（使用 IQR 方法）
                clean_data = col_data.dropna()
                if len(clean_data) >= 4:
                    Q1 = clean_data.quantile(0.25)
                    Q3 = clean_data.quantile(0.75)
                    IQR = Q3 - Q1
                    lower_bound = Q1 - 1.5 * IQR
                    upper_bound = Q3 + 1.5 * IQR

                    outliers = clean_data[(clean_data < lower_bound) | (clean_data > upper_bound)]
                    if len(outliers) > 0:
                        diagnosis["outliers"] = {
                            "column": col,
                            "count": len(outliers),
                            "values": outliers.tolist()[:10],  # 最多返回 10 个
                        }
                        if len(outliers) > len(clean_data) * 0.05:
                            diagnosis["suggestions"].append(
                                {
                                    "type": "outliers",
                                    "severity": "medium",
                                    "message": f"列 '{col}' 有 {len(outliers)} 个异常值，建议检查数据质量",
                                }
                            )

                # 检查样本量
                if len(clean_data) < 30:
                    diagnosis["sample_size"] = {
                        "column": col,
                        "count": len(clean_data),
                        "warning": True,
                    }
                    if len(clean_data) < 10:
                        diagnosis["suggestions"].append(
                            {
                                "type": "sample_size",
                                "severity": "high",
                                "message": f"列 '{col}' 样本量过小（n={len(clean_data)}），统计结果可能不可靠",
                            }
                        )

            else:
                # 检查是否可以转换为数值
                try:
                    pd.to_numeric(col_data, errors="coerce")
                    diagnosis["type_conversion"] = {
                        "column": col,
                        "current_type": str(col_data.dtype),
                        "suggested_type": "numeric",
                        "can_convert": True,
                    }
                    diagnosis["suggestions"].append(
                        {
                            "type": "type_conversion",
                            "severity": "low",
                            "message": f"列 '{col}' 可以转换为数值类型以进行数值分析",
                        }
                    )
                except Exception:
                    pass

        return diagnosis

    async def _execute_skill_in_thread(
        self,
        *,
        skill: Skill,
        session: Session,
        kwargs: dict[str, Any],
    ) -> SkillResult:
        """在当前事件循环中执行技能协程。"""
        return await skill.execute(session=session, **kwargs)

    @staticmethod
    def _run_skill_coroutine(
        skill: Skill,
        session: Session,
        kwargs: dict[str, Any],
    ) -> SkillResult:
        return asyncio.run(skill.execute(session=session, **kwargs))


def create_default_registry() -> SkillRegistry:
    """创建并注册默认技能集。"""
    registry = SkillRegistry()
    registry.register(LoadDatasetSkill())
    registry.register(PreviewDataSkill())
    registry.register(DataSummarySkill())
    registry.register(TTestSkill())
    registry.register(MannWhitneySkill())
    registry.register(ANOVASkill())
    registry.register(KruskalWallisSkill())
    registry.register(CorrelationSkill())
    registry.register(RegressionSkill())
    registry.register(RunCodeSkill())
    registry.register(CreateChartSkill())
    registry.register(ExportChartSkill())
    registry.register(CleanDataSkill())
    registry.register(RecommendCleaningStrategySkill())
    registry.register(DataQualitySkill())
    registry.register(DataQualityReportSkill())
    registry.register(GenerateReportSkill())
    registry.register(SaveWorkflowSkill())
    registry.register(ListWorkflowsSkill())
    registry.register(ApplyWorkflowSkill())
    registry.register(OrganizeWorkspaceSkill())
    registry.register(FetchURLSkill())
    # 复合技能模板（P0 优化）
    registry.register(CompleteComparisonSkill())
    registry.register(CompleteANOVASkill())
    registry.register(CorrelationAnalysisSkill())
    registry.register(InterpretStatisticalResultSkill())
    registry.reload_markdown_skills()
    registry.write_skills_snapshot()
    return registry
