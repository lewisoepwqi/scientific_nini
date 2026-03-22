"""技能注册中心。"""

from __future__ import annotations

import logging
from typing import Any

from nini.agent.session import Session
from nini.config import settings
from nini.sandbox.r_router import detect_r_backend
from nini.tools.chart_session import ChartSessionTool
from nini.tools.code_session import CodeSessionTool
from nini.tools.code_exec import RunCodeTool
from nini.tools.dataset_catalog import DatasetCatalogTool
from nini.tools.data_ops import DataSummaryTool, LoadDatasetTool
from nini.tools.dataset_transform import DatasetTransformTool
from nini.tools.edit_file import EditFile
from nini.tools.export import ExportChartTool
from nini.tools.export_document import ExportDocumentTool
from nini.tools.export_report import ExportReportTool
from nini.tools.fetch_url import FetchURLTool
from nini.tools.organize_workspace import OrganizeWorkspaceTool
from nini.tools.r_code_exec import RunRCodeTool
from nini.tools.registry_catalog import ToolCatalogOps
from nini.tools.registry_core import FunctionToolRegistryOps
from nini.tools.registry_markdown import MarkdownSkillRegistryOps
from nini.tools.report import GenerateReportTool
from nini.tools.report_session import ReportSessionTool
from nini.tools.statistics import (
    ANOVATool,
    KruskalWallisTool,
    MannWhitneyTool,
    TTestTool,
)
from nini.tools.stat_interpret import StatInterpretTool
from nini.tools.stat_model import StatModelTool
from nini.tools.stat_test import StatTestTool
from nini.tools.task_write import TaskWriteTool
from nini.tools.task_state import TaskStateTool
from nini.tools.templates import (
    CompleteANOVATool,
    CompleteComparisonTool,
    CorrelationAnalysisTool,
    RegressionAnalysisTool,
)
from nini.tools.analysis_memory_tool import AnalysisMemoryTool
from nini.tools.dispatch_agents import DispatchAgentsTool
from nini.tools.profile_notes import UpdateProfileNotesTool
from nini.tools.workspace_session import WorkspaceSessionTool

logger = logging.getLogger(__name__)

LLM_EXPOSED_BASE_TOOL_NAMES = {
    "task_state",
    "dataset_catalog",
    "dataset_transform",
    "stat_test",
    "stat_model",
    "stat_interpret",
    "chart_session",
    "report_session",
    "workspace_session",
    "code_session",
    "analysis_memory",
}


class ToolRegistry:
    """管理所有已注册的工具(Tools)。

    注意：本类管理的是模型可调用的原子函数(Tools)，区别于：
    - Skills：完整工作流项目(Markdown + 脚本 + 参考文档，在 skills/ 目录)
    - Capabilities：用户层面的能力元数据(在 capabilities/ 模块定义)
    """

    def __init__(self) -> None:
        self._skills: dict[str, Any] = {}
        self._markdown_skills: list[dict[str, Any]] = []
        self._markdown_enabled_overrides: dict[str, bool] = {}
        self._fallback_manager: Any = None
        self._diagnostics: Any = None
        self._llm_exposed_function_tools = set(LLM_EXPOSED_BASE_TOOL_NAMES)

        self._function_ops = FunctionToolRegistryOps(self)
        self._markdown_ops = MarkdownSkillRegistryOps(self)
        self._catalog_ops = ToolCatalogOps(self)

        self._function_ops.ensure_runtime_dependencies()
        self._markdown_enabled_overrides = self._markdown_ops.load_enabled_overrides()

    def register(self, skill: Any, *, allow_override: bool = False) -> None:
        self._function_ops.register(skill, allow_override=allow_override)

    def unregister(self, name: str) -> None:
        self._function_ops.unregister(name)

    def get(self, name: str) -> Any | None:
        return self._function_ops.get(name)

    def list_skills(self) -> list[str]:
        return self._function_ops.list_skills()

    def list_function_skills(self) -> list[dict[str, Any]]:
        return self._function_ops.list_function_skills()

    def list_markdown_skills(self) -> list[dict[str, Any]]:
        return self._markdown_ops.list_markdown_skills()

    def get_markdown_skill(self, name: str) -> dict[str, Any] | None:
        return self._markdown_ops.get_markdown_skill(name)

    def get_skill_index(self, name: str) -> dict[str, Any] | None:
        return self._catalog_ops.get_skill_index(name)

    def get_skill_instruction(self, name: str) -> dict[str, Any] | None:
        return self._markdown_ops.get_skill_instruction(name)

    def get_runtime_resources(self, name: str) -> dict[str, Any] | None:
        return self._markdown_ops.get_runtime_resources(name)

    def get_semantic_catalog(self, skill_type: str | None = None) -> list[dict[str, Any]]:
        return self._catalog_ops.get_semantic_catalog(skill_type=skill_type)

    def list_skill_catalog(self, skill_type: str | None = None) -> list[dict[str, Any]]:
        return self._catalog_ops.list_skill_catalog(skill_type=skill_type)

    def list_tools_catalog(self) -> list[dict[str, Any]]:
        return self._catalog_ops.list_tools_catalog()

    def list_markdown_skill_catalog(self) -> list[dict[str, Any]]:
        return self._catalog_ops.list_markdown_skill_catalog()

    def reload_markdown_skills(self) -> list[dict[str, Any]]:
        return self._markdown_ops.reload_markdown_skills(set(self._skills.keys()))

    def set_markdown_skill_enabled(self, name: str, enabled: bool) -> dict[str, Any] | None:
        return self._markdown_ops.set_markdown_skill_enabled(name, enabled)

    def remove_markdown_skill_override(self, name: str) -> None:
        self._markdown_ops.remove_markdown_skill_override(name)

    def write_skills_snapshot(self) -> None:
        self._catalog_ops.write_skills_snapshot()

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return self._function_ops.get_tool_definitions()

    def _is_markdown_skill(self, skill_name: str) -> bool:
        return self._markdown_ops.is_markdown_skill(skill_name)

    async def execute(
        self,
        skill_name: str,
        session: Session,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return await self._function_ops.execute(
            skill_name,
            session,
            markdown_skill_checker=self._markdown_ops.is_markdown_skill,
            **kwargs,
        )

    async def execute_with_fallback(
        self,
        skill_name: str,
        session: Session,
        enable_fallback: bool = True,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return await self._function_ops.execute_with_fallback(
            skill_name,
            session,
            skill_executor=self.execute,
            enable_fallback=enable_fallback,
            **kwargs,
        )

    def create_subset(self, allowed_tool_names: list[str]) -> "ToolRegistry":
        """构造仅包含指定工具的受限注册表实例。

        不存在的工具名记录 WARNING 并跳过，不抛出异常。
        原注册表不受影响。

        Args:
            allowed_tool_names: 允许包含的工具名列表

        Returns:
            新的 ToolRegistry 实例，仅含指定工具
        """
        subset = ToolRegistry()
        # 清空新实例的默认注册工具（空白基础，只放入指定工具）
        subset._skills.clear()
        subset._llm_exposed_function_tools = set()

        for name in allowed_tool_names:
            skill = self._skills.get(name)
            if skill is None:
                logger.warning("create_subset: 工具 '%s' 不存在，已跳过", name)
                continue
            subset._skills[name] = skill
            subset._llm_exposed_function_tools.add(name)

        return subset

    async def diagnose_data_problem(
        self,
        session: Session,
        dataset_name: str,
        target_column: str | None = None,
        include_quality_score: bool = True,
    ) -> dict[str, Any]:
        return await self._function_ops.diagnose_data_problem(
            session,
            dataset_name,
            target_column=target_column,
            include_quality_score=include_quality_score,
        )

    async def _execute_skill_in_thread(
        self, *, skill: Any, session: Session, kwargs: dict[str, Any]
    ):
        return await self._function_ops._execute_skill_in_thread(
            skill=skill,
            session=session,
            kwargs=kwargs,
        )

    @staticmethod
    def _run_skill_coroutine(skill: Any, session: Session, kwargs: dict[str, Any]):
        return FunctionToolRegistryOps._run_skill_coroutine(skill, session, kwargs)


def create_default_tool_registry() -> ToolRegistry:
    """创建并注册默认工具集(Tools)。"""
    registry = ToolRegistry()
    registry.register(TaskWriteTool())
    registry.register(TaskStateTool())
    registry.register(LoadDatasetTool())
    registry.register(DataSummaryTool())
    registry.register(DatasetCatalogTool())
    registry.register(DatasetTransformTool())
    # 保留原子统计工具：被 fallback.py 和 planner.py 硬编码引用
    registry.register(TTestTool())
    registry.register(MannWhitneyTool())
    registry.register(ANOVATool())
    registry.register(KruskalWallisTool())
    registry.register(StatTestTool())
    registry.register(StatModelTool())
    registry.register(StatInterpretTool())
    registry.register(CodeSessionTool())
    registry.register(RunCodeTool())
    if settings.r_enabled:
        backend = detect_r_backend()
        if backend["available"]:
            registry.register(RunRCodeTool())
            logger.info("run_r_code 已注册（%s）", backend["message"])
        else:
            logger.warning(
                "R 环境不可用，跳过 run_r_code 注册: %s。"
                "请运行 pip install webr 或安装本地 R 环境。",
                backend["message"],
            )
    registry.register(ChartSessionTool())
    registry.register(ExportChartTool())
    registry.register(ExportDocumentTool())
    registry.register(GenerateReportTool())
    registry.register(ReportSessionTool())
    registry.register(ExportReportTool())
    registry.register(OrganizeWorkspaceTool())
    registry.register(FetchURLTool())
    registry.register(CompleteComparisonTool())
    registry.register(CompleteANOVATool())
    registry.register(CorrelationAnalysisTool())
    registry.register(RegressionAnalysisTool())
    registry.register(EditFile())
    registry.register(WorkspaceSessionTool())
    registry.register(AnalysisMemoryTool())
    registry.register(UpdateProfileNotesTool())

    # 注册 dispatch_agents 工具（不加入 LLM_EXPOSED_BASE_TOOL_NAMES，仅主 Agent 可用）
    from nini.agent.registry import AgentRegistry
    from nini.agent.spawner import SubAgentSpawner
    from nini.agent.fusion import ResultFusionEngine
    from nini.agent.router import TaskRouter
    from nini.agent.model_resolver import model_resolver as _model_resolver

    _agent_registry = AgentRegistry(tool_registry=registry)
    _spawner = SubAgentSpawner(registry=_agent_registry, tool_registry=registry)
    _fusion_engine = ResultFusionEngine(model_resolver=_model_resolver)
    _task_router = TaskRouter(
        model_resolver=_model_resolver,
        enable_llm_fallback=False,
    )
    registry.register(
        DispatchAgentsTool(
            agent_registry=_agent_registry,
            spawner=_spawner,
            fusion_engine=_fusion_engine,
            task_router=_task_router,
        )
    )

    registry.reload_markdown_skills()
    registry.write_skills_snapshot()
    return registry


import warnings as _warnings


def __getattr__(name: str):
    """弃用别名的延迟访问，触发 DeprecationWarning。"""
    _aliases = {
        "SkillRegistry": ToolRegistry,
        "create_default_registry": create_default_tool_registry,
    }
    if name in _aliases:
        _warnings.warn(
            f"{name} 已弃用，请使用 {'ToolRegistry' if name == 'SkillRegistry' else 'create_default_tool_registry'}",
            DeprecationWarning,
            stacklevel=2,
        )
        return _aliases[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
