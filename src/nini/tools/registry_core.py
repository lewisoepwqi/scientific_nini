"""Function Tool 注册与执行逻辑。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, cast

from nini.agent.lane_queue import lane_queue
from nini.agent.session import Session
from nini.config import settings
from nini.tools.base import Tool, ToolResult
from nini.tools.diagnostics import DataDiagnostics
from nini.tools.fallback import get_fallback_manager

logger = logging.getLogger(__name__)


class FunctionToolRegistryOps:
    """封装 Function Tool 的注册、目录与执行逻辑。"""

    def __init__(self, owner: Any) -> None:
        self._owner = owner

    def register(self, skill: Tool, *, allow_override: bool = False) -> None:
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

    def get(self, name: str) -> Tool | None:
        """获取工具实例。"""
        return cast(Tool | None, self._owner._skills.get(name))

    def list_skills(self) -> list[str]:
        """列出所有 Function Tool 名称。"""
        return list(self._owner._skills.keys())

    def list_function_skills(self) -> list[dict[str, Any]]:
        """列出 Function Tool 目录。"""
        items: list[dict[str, Any]] = []
        for skill in self._owner._skills.values():
            manifest = skill.to_manifest()
            exposed_to_llm = self._is_exposed_to_llm(skill)
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
                    "expose_to_llm": exposed_to_llm,
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
            if self._is_exposed_to_llm(skill)
        ]

    def _is_exposed_to_llm(self, skill: Tool) -> bool:
        allowlist = getattr(self._owner, "_llm_exposed_function_tools", None)
        if allowlist is not None:
            return skill.name in allowlist
        return skill.expose_to_llm

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

        normalized_kwargs = kwargs
        normalization_meta: dict[str, Any] | None = None
        normalization_error: dict[str, Any] | None = None
        if settings.tool_argument_normalization_enabled:
            normalized_kwargs, normalization_meta, normalization_error = (
                self._normalize_tool_kwargs(
                    skill_name,
                    kwargs,
                )
            )
            if normalization_error is not None:
                return normalization_error

        try:
            result = await lane_queue.execute(
                session.id,
                self._execute_skill_in_thread(
                    skill=skill,
                    session=session,
                    kwargs=normalized_kwargs,
                ),
            )
            result_dict = cast(dict[str, Any], result.to_dict())
            metadata = result_dict.get("metadata")
            result_meta = metadata if isinstance(metadata, dict) else {}
            if normalization_meta:
                result_meta = {**result_meta, **normalization_meta}
                result_dict["metadata"] = result_meta
            error_code = result_meta.get("error_code")
            if isinstance(error_code, str) and error_code.strip():
                result_dict.setdefault("error_code", error_code.strip())
            return result_dict
        except Exception as exc:
            logger.error("技能 %s 执行失败: %s", skill_name, exc, exc_info=True)
            return {"success": False, "message": f"技能执行失败: {exc}"}

    @staticmethod
    def _normalize_tool_kwargs(
        skill_name: str,
        kwargs: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None]:
        if skill_name != "workspace_session":
            return kwargs, None, None

        operation = kwargs.get("operation")
        if isinstance(operation, str) and operation.strip():
            return kwargs, None, None

        list_like_fields = {"query", "kinds", "path_prefix", "limit"}
        provided_fields = {k for k, v in kwargs.items() if k != "operation" and v is not None}
        safe_to_infer_list = not provided_fields or provided_fields.issubset(list_like_fields)
        if safe_to_infer_list:
            normalized_kwargs = dict(kwargs)
            normalized_kwargs["operation"] = "list"
            return (
                normalized_kwargs,
                {
                    "normalized": True,
                    "normalization_reason": "workspace_session_missing_operation_inferred_list",
                    "original_arguments": kwargs,
                },
                None,
            )

        return (
            kwargs,
            {
                "normalized": False,
                "normalization_reason": "workspace_session_missing_operation_unsafe_inference",
                "original_arguments": kwargs,
            },
            {
                "success": False,
                "message": (
                    "workspace_session 缺少 operation，且参数包含非 list 语义字段，"
                    "已拒绝自动纠偏。请显式指定 operation。"
                ),
                "error_code": "WORKSPACE_OPERATION_REQUIRED",
                "expected_operations": [
                    "list",
                    "read",
                    "write",
                    "append",
                    "edit",
                    "organize",
                    "fetch_url",
                ],
                "recovery_hint": (
                    "示例：{'operation':'list'}；"
                    "读取文件请使用 {'operation':'read','file_path':'notes/a.md'}。"
                ),
                "metadata": {
                    "normalized": False,
                    "normalization_reason": "workspace_session_missing_operation_unsafe_inference",
                    "provided_fields": sorted(provided_fields),
                    "error_code": "WORKSPACE_OPERATION_REQUIRED",
                },
            },
        )

    async def execute_with_fallback(
        self,
        skill_name: str,
        session: Session,
        skill_executor: Any,
        enable_fallback: bool = True,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """执行工具，并在需要时触发降级。"""
        original_result = cast(
            dict[str, Any],
            await skill_executor(skill_name, session=session, **kwargs),
        )

        if original_result.get("success") and enable_fallback:
            should_fallback = cast(
                dict[str, Any],
                await self._owner._fallback_manager.should_trigger_fallback(
                    skill_name, session, kwargs
                ),
            )
            if should_fallback["trigger"]:
                return await self._execute_fallback(skill_name, session, kwargs, should_fallback)
            return original_result

        if original_result.get("success"):
            return original_result

        if enable_fallback and bool(self._owner._fallback_manager.has_fallback(skill_name)):
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
        skill: Tool,
        session: Session,
        kwargs: dict[str, Any],
    ) -> ToolResult:
        """在当前事件循环中执行技能协程。"""
        return await skill.execute(session=session, **kwargs)

    @staticmethod
    def _run_skill_coroutine(
        skill: Tool,
        session: Session,
        kwargs: dict[str, Any],
    ) -> ToolResult:
        """为保留历史兼容而保留的同步入口。"""
        return asyncio.run(skill.execute(session=session, **kwargs))

    def ensure_runtime_dependencies(self) -> None:
        """初始化运行期依赖占位。"""
        self._owner._fallback_manager = get_fallback_manager()
        self._owner._diagnostics = DataDiagnostics()
