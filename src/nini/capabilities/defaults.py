"""默认能力定义。

定义常用的科研分析能力。
"""

from __future__ import annotations

from typing import Any

from nini.capabilities.base import Capability
from nini.capabilities.executors import (
    CorrelationAnalysisCapability,
    DataCleaningCapability,
    DataExplorationCapability,
    DifferenceAnalysisCapability,
    RegressionAnalysisCapability,
    VisualizationCapability,
)
from nini.models.risk import OutputLevel, ResearchPhase, RiskLevel


def _create_difference_analysis_executor(registry: Any | None = None) -> Any:
    """创建差异分析能力执行器。"""
    return DifferenceAnalysisCapability(registry=registry)


def _create_correlation_analysis_executor(registry: Any | None = None) -> Any:
    """创建相关性分析能力执行器。"""
    return CorrelationAnalysisCapability(registry=registry)


def _create_regression_analysis_executor(registry: Any | None = None) -> Any:
    """创建回归分析能力执行器。"""
    return RegressionAnalysisCapability(registry=registry)


def _create_data_exploration_executor(registry: Any | None = None) -> Any:
    """创建数据探索能力执行器。"""
    return DataExplorationCapability(registry=registry)


def _create_data_cleaning_executor(registry: Any | None = None) -> Any:
    """创建数据清洗能力执行器。"""
    return DataCleaningCapability(registry=registry)


def _create_visualization_executor(registry: Any | None = None) -> Any:
    """创建可视化能力执行器。"""
    return VisualizationCapability(registry=registry)


def create_default_capabilities() -> list[Capability]:
    """创建默认能力集。

    Returns:
        能力实例列表
    """
    return [
        Capability(
            name="difference_analysis",
            display_name="差异分析",
            description="比较两组或多组数据的差异，自动选择合适的统计检验方法",
            icon="🔬",
            is_executable=True,
            executor_factory=_create_difference_analysis_executor,
            required_tools=[
                "load_dataset",
                "data_summary",
                "dataset_catalog",
                "t_test",
                "mann_whitney",
                "anova",
                "kruskal_wallis",
                "chart_session",
            ],
            suggested_workflow=[
                "data_summary",
                "t_test",  # 或根据数据特征自动选择
                "chart_session",
            ],
            phase=ResearchPhase.DATA_ANALYSIS,
            risk_level=RiskLevel.MEDIUM,
            max_output_level=OutputLevel.O4,
        ),
        Capability(
            name="correlation_analysis",
            display_name="相关性分析",
            description="探索变量之间的相关关系，计算相关系数矩阵",
            icon="📈",
            is_executable=True,
            executor_factory=_create_correlation_analysis_executor,
            required_tools=[
                "load_dataset",
                "data_summary",
                "stat_model",
                "chart_session",
            ],
            suggested_workflow=[
                "data_summary",
                "stat_model",
                "chart_session",
            ],
            phase=ResearchPhase.DATA_ANALYSIS,
            risk_level=RiskLevel.MEDIUM,
            max_output_level=OutputLevel.O4,
        ),
        Capability(
            name="regression_analysis",
            display_name="回归分析",
            description="建立变量间的回归模型，进行预测和解释",
            icon="📉",
            is_executable=True,
            executor_factory=_create_regression_analysis_executor,
            required_tools=[
                "load_dataset",
                "data_summary",
                "stat_model",
                "chart_session",
            ],
            suggested_workflow=[
                "data_summary",
                "stat_model",
                "chart_session",
            ],
            phase=ResearchPhase.DATA_ANALYSIS,
            risk_level=RiskLevel.MEDIUM,
            max_output_level=OutputLevel.O4,
        ),
        Capability(
            name="data_exploration",
            display_name="数据探索",
            description="全面了解数据特征：分布、缺失值、异常值等",
            icon="🔍",
            is_executable=False,
            execution_message="请在对话中告知你要探索的数据集，Agent 将调用数据探索工具为你生成分布、缺失值和异常值分析。",
            executor_factory=_create_data_exploration_executor,
            required_tools=[
                "load_dataset",
                "dataset_catalog",
                "data_summary",
                "chart_session",
            ],
            suggested_workflow=[
                "dataset_catalog",
                "data_summary",
            ],
            phase=ResearchPhase.DATA_ANALYSIS,
            risk_level=RiskLevel.LOW,
            max_output_level=OutputLevel.O3,
        ),
        Capability(
            name="data_cleaning",
            display_name="数据清洗",
            description="处理缺失值、异常值，提升数据质量",
            icon="🧹",
            is_executable=True,
            executor_factory=_create_data_cleaning_executor,
            required_tools=[
                "load_dataset",
                "data_summary",
                "dataset_catalog",
                "dataset_transform",
            ],
            suggested_workflow=[
                "dataset_catalog",
                "dataset_transform",
            ],
            phase=ResearchPhase.DATA_ANALYSIS,
            risk_level=RiskLevel.LOW,
            max_output_level=OutputLevel.O3,
        ),
        Capability(
            name="visualization",
            display_name="可视化",
            description="创建各类图表展示数据特征和分析结果",
            icon="📊",
            is_executable=True,
            executor_factory=_create_visualization_executor,
            required_tools=[
                "load_dataset",
                "chart_session",
                "export_chart",
            ],
            suggested_workflow=[
                "chart_session",
                "export_chart",
            ],
            phase=None,  # 通用，不限阶段
            risk_level=RiskLevel.LOW,
            max_output_level=OutputLevel.O4,
        ),
        Capability(
            name="report_generation",
            display_name="报告生成",
            description="生成完整的分析报告，包含统计结果和可视化",
            icon="📄",
            execution_message="当前版本暂未提供报告生成能力的直接执行入口，请先通过对话调用相关工具。",
            required_tools=[
                "load_dataset",
                "generate_report",
                "export_document",
                "export_report",
            ],
            suggested_workflow=[
                "generate_report",
                "export_document",
            ],
            phase=ResearchPhase.DATA_ANALYSIS,
            risk_level=RiskLevel.MEDIUM,
            max_output_level=OutputLevel.O4,
        ),
        Capability(
            name="article_draft",
            display_name="科研文章初稿",
            description="根据数据分析结果，自动编排多个分析工具逐章生成结构完整的科研论文初稿（摘要/方法/结果/讨论等章节）",
            icon="📝",
            is_executable=False,
            execution_message="请在对话中描述你的研究背景和数据，Agent 将调用 article_draft 技能为你逐章生成论文初稿。",
            required_tools=[
                "data_summary",
                "stat_interpret",
                "chart_session",
                "workspace_session",
                "edit_file",
                "generate_report",
                "export_document",
                "export_report",
            ],
            suggested_workflow=[
                "data_summary",
                "stat_interpret",
                "chart_session",
                "workspace_session",
                "edit_file",
                "export_document",
            ],
            phase=ResearchPhase.PAPER_WRITING,
            risk_level=RiskLevel.HIGH,
            max_output_level=OutputLevel.O2,
        ),
        Capability(
            name="citation_management",
            display_name="引用管理",
            description="参考文献格式化、引用规范转换（APA/MLA/GB/T）",
            icon="📚",
            is_executable=False,
            execution_message="请在对话中描述需要整理的参考文献和目标格式，Agent 将调用 citation_manager 为你处理。",
            phase=ResearchPhase.PAPER_WRITING,
            risk_level=RiskLevel.MEDIUM,
            max_output_level=OutputLevel.O3,
        ),
        Capability(
            name="peer_review",
            display_name="同行评审辅助",
            description="整理审稿意见、生成回复信件",
            icon="📋",
            is_executable=False,
            execution_message="请在对话中粘贴审稿意见，Agent 将调用 review_assistant 帮你整理回复思路和草拟回信。",
            phase=ResearchPhase.PAPER_WRITING,
            risk_level=RiskLevel.HIGH,
            max_output_level=OutputLevel.O2,
        ),
        Capability(
            name="research_planning",
            display_name="研究规划",
            description="研究设计、实验方案制定、样本量计算",
            icon="🗺️",
            is_executable=False,
            execution_message="请在对话中描述你的研究目标和约束条件，Agent 将调用 research_planner 帮你制定实验方案。",
            phase=ResearchPhase.EXPERIMENT_DESIGN,
            risk_level=RiskLevel.HIGH,
            max_output_level=OutputLevel.O2,
        ),
    ]
