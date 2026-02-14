"""技能注册中心。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, cast

from nini.agent.lane_queue import lane_queue
from nini.agent.session import Session
from nini.config import settings
from nini.skills.base import Skill, SkillResult
from nini.skills.clean_data import CleanDataSkill, RecommendCleaningStrategySkill
from nini.skills.code_exec import RunCodeSkill
from nini.skills.data_ops import DataSummarySkill, LoadDatasetSkill, PreviewDataSkill
from nini.skills.data_quality import DataQualitySkill, DataQualityReportSkill
from nini.skills.diagnostics import DataDiagnostics
from nini.skills.export import ExportChartSkill
from nini.skills.fallback import get_fallback_manager
from nini.skills.fetch_url import FetchURLSkill
from nini.skills.organize_workspace import OrganizeWorkspaceSkill
from nini.skills.report import GenerateReportSkill
from nini.skills.statistics import (
    ANOVASkill,
    CorrelationSkill,
    KruskalWallisSkill,
    MannWhitneySkill,
    MultipleComparisonCorrectionSkill,
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


class SkillRegistry:
    """管理所有已注册的技能。"""

    def __init__(self):
        self._skills: dict[str, Skill] = {}
        self._markdown_skills: list[dict[str, Any]] = []
        self._fallback_manager = get_fallback_manager()
        self._diagnostics = DataDiagnostics()

    def register(self, skill: Skill, *, allow_override: bool = False) -> None:
        """注册一个技能。

        Args:
            skill: 要注册的技能实例。
            allow_override: 若为 True，允许覆盖同名技能；否则抛出 ValueError。
        """
        if skill.name in self._skills:
            existing = self._skills[skill.name]
            existing_loc = f"{existing.__class__.__module__}.{existing.__class__.__name__}"
            new_loc = f"{skill.__class__.__module__}.{skill.__class__.__name__}"
            if allow_override:
                logger.warning(
                    "技能 %s 已存在（%s），将被覆盖为 %s", skill.name, existing_loc, new_loc
                )
            else:
                raise ValueError(
                    f"技能名称冲突: '{skill.name}' 已由 {existing_loc} 注册，"
                    f"新注册来源 {new_loc}。如需覆盖请传入 allow_override=True"
                )
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

    def _is_markdown_skill(self, skill_name: str) -> bool:
        """检查给定名称是否为已注册的 Markdown 技能。"""
        return any(m.get("name") == skill_name for m in self._markdown_skills)

    async def execute(
        self,
        skill_name: str,
        session: Session,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """执行技能并返回结果字典。"""
        skill = self._skills.get(skill_name)
        if skill is None:
            if self._is_markdown_skill(skill_name):
                return {
                    "success": False,
                    "message": (
                        f"'{skill_name}' 是提示词类型技能（Markdown Skill），"
                        "不支持直接调用执行。请参考该技能的文档内容来指导后续操作。"
                    ),
                }
            return {"success": False, "message": f"未知技能: {skill_name}"}

        try:
            # 同一会话内串行执行，避免并发读写同一 DataFrame
            result = await lane_queue.execute(
                session.id,
                self._execute_skill_in_thread(skill=skill, session=session, kwargs=kwargs),
            )
            return cast(dict[str, Any], result.to_dict())
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
        # 首先尝试执行原始技能
        original_result = await self.execute(skill_name, session=session, **kwargs)

        # 如果原始技能成功，检查是否需要基于前提条件降级
        if original_result.get("success") and enable_fallback:
            should_fallback = await self._fallback_manager.should_trigger_fallback(
                skill_name, session, kwargs
            )
            if should_fallback["trigger"]:
                return await self._execute_fallback(skill_name, session, kwargs, should_fallback)
            return original_result

        # 原始技能成功但不需要降级
        if original_result.get("success"):
            return original_result

        # 原始技能失败，尝试降级
        if enable_fallback and self._fallback_manager.has_fallback(skill_name):
            return await self._execute_fallback(
                skill_name, session, kwargs, {"reason": "原始技能执行失败"}
            )

        return original_result

    async def _execute_fallback(
        self,
        skill_name: str,
        session: Session,
        kwargs: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """执行降级技能。"""
        result = await self._fallback_manager.execute_fallback(
            skill_name=skill_name,
            session=session,
            kwargs=kwargs.copy(),
            context=context,
            skill_resolver=self.get,
            skill_executor=lambda name, sess, kw: self.execute(name, session=sess, **kw),
        )
        return cast(dict[str, Any], result)

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
        # 使用 DataDiagnostics 进行诊断
        diagnostics = DataDiagnostics(include_quality_score=include_quality_score)
        result = await diagnostics.diagnose(session, dataset_name, target_column)

        # 转换为旧格式以保持向后兼容
        diagnosis: dict[str, Any] = {
            "dataset_name": result.dataset_name,
            "issues": [{"type": i.type, "message": i.message} for i in result.issues],
            "suggestions": [
                {
                    "type": s.type,
                    "severity": s.severity,
                    "message": s.message,
                }
                for s in result.suggestions
            ],
        }

        # 添加质量评分
        if result.quality_score:
            diagnosis["quality_score"] = result.quality_score

        # 添加元数据（保持向后兼容的格式）
        if result.metadata:
            # 将新的 metadata 格式转换为旧的扁平格式
            for key, value in result.metadata.items():
                if isinstance(value, dict) and value:
                    # 取第一个列的数据作为兼容格式
                    first_col = next(iter(value.keys()))
                    diagnosis[key] = {**value[first_col], "column": first_col}

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
    registry.register(MultipleComparisonCorrectionSkill())
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
