"""Function Tool 注册与执行逻辑。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, cast

from nini.agent.lane_queue import lane_queue
from nini.agent.session import Session
from nini.tools.base import Skill, SkillResult
from nini.tools.diagnostics import DataDiagnostics
from nini.tools.fallback import get_fallback_manager

logger = logging.getLogger(__name__)


class FunctionToolRegistryOps:
    """封装 Function Tool 的注册、目录与执行逻辑。"""

    def __init__(self, owner: Any) -> None:
        self._owner = owner

    def register(self, skill: Skill, *, allow_override: bool = False) -> None:
        """注册一个工具。"""
        if skill.name in self._owner._skills:
            existing = self._owner._skills[skill.name]
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
        self._owner._skills[skill.name] = skill
        logger.info("注册工具: %s", skill.name)

    def unregister(self, name: str) -> None:
        """注销一个工具。"""
        self._owner._skills.pop(name, None)

    def get(self, name: str) -> Skill | None:
        """获取工具实例。"""
        return self._owner._skills.get(name)

    def list_skills(self) -> list[str]:
        """列出所有 Function Tool 名称。"""
        return list(self._owner._skills.keys())

    def list_function_skills(self) -> list[dict[str, Any]]:
        """列出 Function Tool 目录。"""
        items: list[dict[str, Any]] = []
        for skill in self._owner._skills.values():
            manifest = skill.to_manifest()
            items.append(
                {
                    "type": "function",
                    "name": skill.name,
                    "description": skill.description,
                    "category": skill.category,
                    "brief_description": manifest.brief_description,
                    "research_domain": manifest.research_domain,
                    "difficulty_level": manifest.difficulty_level,
                    "typical_use_cases": manifest.typical_use_cases,
                    "location": f"{skill.__class__.__module__}.{skill.__class__.__name__}",
                    "enabled": True,
                    "expose_to_llm": skill.expose_to_llm,
                    "metadata": {
                        "parameters": skill.parameters,
                        "is_idempotent": skill.is_idempotent,
                        "brief_description": manifest.brief_description,
                        "research_domain": manifest.research_domain,
                        "difficulty_level": manifest.difficulty_level,
                        "typical_use_cases": manifest.typical_use_cases,
                        "output_types": manifest.output_types,
                    },
                }
            )
        return items

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """获取暴露给 LLM 的工具定义。"""
        return [
            skill.get_tool_definition()
            for skill in self._owner._skills.values()
            if skill.expose_to_llm
        ]

    async def execute(
        self,
        skill_name: str,
        session: Session,
        markdown_skill_checker: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """执行 Function Tool。"""
        skill = self._owner._skills.get(skill_name)
        if skill is None:
            if markdown_skill_checker(skill_name):
                return {
                    "success": False,
                    "message": (
                        f"'{skill_name}' 是提示词类型技能（Markdown Skill），"
                        "不支持直接调用执行。请参考该技能的文档内容来指导后续操作。"
                    ),
                }
            return {"success": False, "message": f"未知技能: {skill_name}"}

        try:
            result = await lane_queue.execute(
                session.id,
                self._execute_skill_in_thread(skill=skill, session=session, kwargs=kwargs),
            )
            return cast(dict[str, Any], result.to_dict())
        except Exception as exc:
            logger.error("技能 %s 执行失败: %s", skill_name, exc, exc_info=True)
            return {"success": False, "message": f"技能执行失败: {exc}"}

    async def execute_with_fallback(
        self,
        skill_name: str,
        session: Session,
        skill_executor: Any,
        enable_fallback: bool = True,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """执行工具，并在需要时触发降级。"""
        original_result = await skill_executor(skill_name, session=session, **kwargs)

        if original_result.get("success") and enable_fallback:
            should_fallback = await self._owner._fallback_manager.should_trigger_fallback(
                skill_name, session, kwargs
            )
            if should_fallback["trigger"]:
                return await self._execute_fallback(skill_name, session, kwargs, should_fallback)
            return original_result

        if original_result.get("success"):
            return original_result

        if enable_fallback and self._owner._fallback_manager.has_fallback(skill_name):
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
        """执行降级工具。"""
        result = await self._owner._fallback_manager.execute_fallback(
            skill_name=skill_name,
            session=session,
            kwargs=kwargs.copy(),
            context=context,
            skill_resolver=self.get,
            skill_executor=lambda name, sess, kw: self.execute(
                name,
                session=sess,
                markdown_skill_checker=self._owner._markdown_ops.is_markdown_skill,
                **kw,
            ),
        )
        return cast(dict[str, Any], result)

    async def diagnose_data_problem(
        self,
        session: Session,
        dataset_name: str,
        target_column: str | None = None,
        include_quality_score: bool = True,
    ) -> dict[str, Any]:
        """诊断数据问题并输出兼容格式。"""
        diagnostics = DataDiagnostics(include_quality_score=include_quality_score)
        result = await diagnostics.diagnose(session, dataset_name, target_column)

        diagnosis: dict[str, Any] = {
            "dataset_name": result.dataset_name,
            "issues": [{"type": issue.type, "message": issue.message} for issue in result.issues],
            "suggestions": [
                {
                    "type": suggestion.type,
                    "severity": suggestion.severity,
                    "message": suggestion.message,
                }
                for suggestion in result.suggestions
            ],
        }
        if result.quality_score:
            diagnosis["quality_score"] = result.quality_score

        if result.metadata:
            for key, value in result.metadata.items():
                if isinstance(value, dict) and value:
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
        """为保留历史兼容而保留的同步入口。"""
        return asyncio.run(skill.execute(session=session, **kwargs))

    def ensure_runtime_dependencies(self) -> None:
        """初始化运行期依赖占位。"""
        self._owner._fallback_manager = get_fallback_manager()
        self._owner._diagnostics = DataDiagnostics()
