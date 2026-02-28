"""默认能力定义。

定义常用的科研分析能力。
"""

from __future__ import annotations

from typing import Any

from nini.capabilities.base import Capability


def _create_difference_analysis_executor(registry: Any | None = None) -> Any:
    """创建差异分析能力执行器。"""
    from nini.capabilities.implementations import DifferenceAnalysisCapability

    return DifferenceAnalysisCapability(registry=registry)


def _create_correlation_analysis_executor(registry: Any | None = None) -> Any:
    """创建相关性分析能力执行器。"""
    from nini.capabilities.implementations import CorrelationAnalysisCapability

    return CorrelationAnalysisCapability(registry=registry)


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
                "evaluate_data_quality",
                "t_test",
                "mann_whitney",
                "anova",
                "kruskal_wallis",
                "create_chart",
            ],
            suggested_workflow=[
                "data_summary",
                "t_test",  # 或根据数据特征自动选择
                "create_chart",
            ],
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
                "correlation",
                "create_chart",
            ],
            suggested_workflow=[
                "data_summary",
                "correlation",
                "create_chart",
            ],
        ),
        Capability(
            name="regression_analysis",
            display_name="回归分析",
            description="建立变量间的回归模型，进行预测和解释",
            icon="📉",
            execution_message="当前版本暂未提供回归分析的直接执行入口，请先通过对话调用相关工具。",
            required_tools=[
                "load_dataset",
                "data_summary",
                "regression",
                "create_chart",
            ],
            suggested_workflow=[
                "data_summary",
                "regression",
                "create_chart",
            ],
        ),
        Capability(
            name="data_exploration",
            display_name="数据探索",
            description="全面了解数据特征：分布、缺失值、异常值等",
            icon="🔍",
            execution_message="当前版本暂未提供数据探索的直接执行入口，请先通过对话调用相关工具。",
            required_tools=[
                "load_dataset",
                "preview_data",
                "data_summary",
                "evaluate_data_quality",
                "create_chart",
            ],
            suggested_workflow=[
                "preview_data",
                "data_summary",
                "evaluate_data_quality",
            ],
        ),
        Capability(
            name="data_cleaning",
            display_name="数据清洗",
            description="处理缺失值、异常值，提升数据质量",
            icon="🧹",
            execution_message="当前版本暂未提供数据清洗的直接执行入口，请先通过对话调用相关工具。",
            required_tools=[
                "load_dataset",
                "data_summary",
                "evaluate_data_quality",
                "clean_data",
                "recommend_cleaning_strategy",
            ],
            suggested_workflow=[
                "evaluate_data_quality",
                "recommend_cleaning_strategy",
                "clean_data",
            ],
        ),
        Capability(
            name="visualization",
            display_name="可视化",
            description="创建各类图表展示数据特征和分析结果",
            icon="📊",
            execution_message="当前版本暂未提供可视化能力的直接执行入口，请先通过对话调用相关工具。",
            required_tools=[
                "load_dataset",
                "create_chart",
                "export_chart",
            ],
            suggested_workflow=[
                "create_chart",
                "export_chart",
            ],
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
                "export_report",
            ],
            suggested_workflow=[
                "generate_report",
                "export_report",
            ],
        ),
    ]
