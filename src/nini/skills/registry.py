"""技能注册中心。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from nini.agent.lane_queue import lane_queue
from nini.agent.session import Session
from nini.config import settings
from nini.skills.base import Skill, SkillResult
from nini.skills.clean_data import CleanDataSkill
from nini.skills.code_exec import RunCodeSkill
from nini.skills.data_ops import DataSummarySkill, LoadDatasetSkill, PreviewDataSkill
from nini.skills.export import ExportChartSkill
from nini.skills.fetch_url import FetchURLSkill
from nini.skills.organize_workspace import OrganizeWorkspaceSkill
from nini.skills.report import GenerateReportSkill
from nini.skills.statistics import ANOVASkill, CorrelationSkill, RegressionSkill, TTestSkill
from nini.skills.visualization import CreateChartSkill
from nini.skills.workflow_skill import ApplyWorkflowSkill, ListWorkflowsSkill, SaveWorkflowSkill
from nini.skills.markdown_scanner import render_skills_snapshot, scan_markdown_skills
# 复合技能模板
from nini.skills.templates import CompleteANOVASkill, CompleteComparisonSkill, CorrelationAnalysisSkill

logger = logging.getLogger(__name__)


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
                    "location": f"{skill.__class__.__module__}.{skill.__class__.__name__}",
                    "enabled": True,
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
        """获取所有技能的 LLM 工具定义。"""
        return [s.get_tool_definition() for s in self._skills.values()]

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

    async def _execute_skill_in_thread(
        self,
        *,
        skill: Skill,
        session: Session,
        kwargs: dict[str, Any],
    ) -> SkillResult:
        """在线程中运行技能协程，避免主事件循环被 CPU 密集逻辑阻塞。"""
        return await asyncio.to_thread(
            self._run_skill_coroutine,
            skill,
            session,
            kwargs,
        )

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
    registry.register(ANOVASkill())
    registry.register(CorrelationSkill())
    registry.register(RegressionSkill())
    registry.register(CreateChartSkill())
    registry.register(ExportChartSkill())
    registry.register(CleanDataSkill())
    registry.register(GenerateReportSkill())
    registry.register(RunCodeSkill())
    registry.register(SaveWorkflowSkill())
    registry.register(ListWorkflowsSkill())
    registry.register(ApplyWorkflowSkill())
    registry.register(OrganizeWorkspaceSkill())
    registry.register(FetchURLSkill())
    # 复合技能模板（P0 优化）
    registry.register(CompleteComparisonSkill())
    registry.register(CompleteANOVASkill())
    registry.register(CorrelationAnalysisSkill())
    registry.reload_markdown_skills()
    registry.write_skills_snapshot()
    return registry
