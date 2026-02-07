"""技能注册中心。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from nini.agent.lane_queue import lane_queue
from nini.agent.session import Session
from nini.skills.base import Skill, SkillResult
from nini.skills.clean_data import CleanDataSkill
from nini.skills.code_exec import RunCodeSkill
from nini.skills.data_ops import DataSummarySkill, LoadDatasetSkill, PreviewDataSkill
from nini.skills.export import ExportChartSkill
from nini.skills.report import GenerateReportSkill
from nini.skills.statistics import ANOVASkill, CorrelationSkill, RegressionSkill, TTestSkill
from nini.skills.visualization import CreateChartSkill
from nini.skills.workflow_skill import ApplyWorkflowSkill, ListWorkflowsSkill, SaveWorkflowSkill

logger = logging.getLogger(__name__)


class SkillRegistry:
    """管理所有已注册的技能。"""

    def __init__(self):
        self._skills: dict[str, Skill] = {}

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

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """获取所有技能的 LLM 工具定义。"""
        return [s.get_tool_definition() for s in self._skills.values()]

    async def execute(self, name: str, session: Session, **kwargs: Any) -> dict[str, Any]:
        """执行技能并返回结果字典。"""
        skill = self._skills.get(name)
        if skill is None:
            return {"success": False, "message": f"未知技能: {name}"}

        try:
            # 同一会话内串行执行，避免并发读写同一 DataFrame
            result = await lane_queue.execute(
                session.id,
                self._execute_skill_in_thread(skill=skill, session=session, kwargs=kwargs),
            )
            return result.to_dict()
        except Exception as e:
            logger.error("技能 %s 执行失败: %s", name, e, exc_info=True)
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
    return registry
