"""技能注册中心。"""

from __future__ import annotations

import logging
from typing import Any

from nini.agent.session import Session
from nini.config import settings
from nini.sandbox.r_router import detect_r_backend
from nini.tools.clean_data import CleanDataSkill, RecommendCleaningStrategySkill
from nini.tools.chart_session import ChartSessionSkill
from nini.tools.code_session import CodeSessionSkill
from nini.tools.code_exec import RunCodeSkill
from nini.tools.dataset_catalog import DatasetCatalogSkill
from nini.tools.data_ops import DataSummarySkill, LoadDatasetSkill, PreviewDataSkill
from nini.tools.data_quality import DataQualitySkill
from nini.tools.dataset_transform import DatasetTransformSkill
from nini.tools.edit_file import EditFile
from nini.tools.export import ExportChartSkill
from nini.tools.export_document import ExportDocumentSkill
from nini.tools.export_report import ExportReportSkill
from nini.tools.fetch_url import FetchURLSkill
from nini.tools.interpretation import InterpretStatisticalResultSkill
from nini.tools.organize_workspace import OrganizeWorkspaceSkill
from nini.tools.r_code_exec import RunRCodeSkill
from nini.tools.registry_catalog import ToolCatalogOps
from nini.tools.registry_core import FunctionToolRegistryOps
from nini.tools.registry_markdown import MarkdownSkillRegistryOps
from nini.tools.report import GenerateReportSkill
from nini.tools.report_session import ReportSessionSkill
from nini.tools.statistics import (
    ANOVASkill,
    CorrelationSkill,
    KruskalWallisSkill,
    MannWhitneySkill,
    MultipleComparisonCorrectionSkill,
    RegressionSkill,
    TTestSkill,
)
from nini.tools.stat_interpret import StatInterpretSkill
from nini.tools.stat_model import StatModelSkill
from nini.tools.stat_test import StatTestSkill
from nini.tools.task_write import TaskWriteSkill
from nini.tools.task_state import TaskStateSkill
from nini.tools.templates import (
    CompleteANOVASkill,
    CompleteComparisonSkill,
    CorrelationAnalysisSkill,
    RegressionAnalysisSkill,
)
from nini.tools.visualization import CreateChartSkill
from nini.tools.workspace_files import ListWorkspaceFilesSkill
from nini.tools.workspace_session import WorkspaceSessionSkill

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
    registry.register(TaskWriteSkill())
    registry.register(TaskStateSkill())
    registry.register(LoadDatasetSkill())
    registry.register(PreviewDataSkill())
    registry.register(DataSummarySkill())
    registry.register(DatasetCatalogSkill())
    registry.register(DatasetTransformSkill())
    registry.register(TTestSkill())
    registry.register(MannWhitneySkill())
    registry.register(ANOVASkill())
    registry.register(KruskalWallisSkill())
    registry.register(CorrelationSkill())
    registry.register(RegressionSkill())
    registry.register(MultipleComparisonCorrectionSkill())
    registry.register(StatTestSkill())
    registry.register(StatModelSkill())
    registry.register(StatInterpretSkill())
    registry.register(CodeSessionSkill())
    registry.register(RunCodeSkill())
    if settings.r_enabled:
        backend = detect_r_backend()
        if backend["available"]:
            registry.register(RunRCodeSkill())
            logger.info("run_r_code 已注册（%s）", backend["message"])
        else:
            logger.warning(
                "R 环境不可用，跳过 run_r_code 注册: %s。"
                "请运行 pip install webr 或安装本地 R 环境。",
                backend["message"],
            )
    registry.register(CreateChartSkill())
    registry.register(ChartSessionSkill())
    registry.register(ExportChartSkill())
    registry.register(ExportDocumentSkill())
    registry.register(CleanDataSkill())
    registry.register(RecommendCleaningStrategySkill())
    registry.register(DataQualitySkill())
    registry.register(GenerateReportSkill())
    registry.register(ReportSessionSkill())
    registry.register(ExportReportSkill())
    registry.register(OrganizeWorkspaceSkill())
    registry.register(FetchURLSkill())
    registry.register(CompleteComparisonSkill())
    registry.register(CompleteANOVASkill())
    registry.register(CorrelationAnalysisSkill())
    registry.register(RegressionAnalysisSkill())
    registry.register(InterpretStatisticalResultSkill())
    registry.register(EditFile())
    registry.register(ListWorkspaceFilesSkill())
    registry.register(WorkspaceSessionSkill())
    registry.reload_markdown_skills()
    registry.write_skills_snapshot()
    return registry


SkillRegistry = ToolRegistry
create_default_registry = create_default_tool_registry
