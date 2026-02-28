"""Capability 基类 - 用户可理解的能力封装。

注意：本模块定义的是用户层面的"能力"(Capability)，区别于：
- Tools: 模型可调用的原子函数（在 tools/ 模块定义）
- Skills: 完整工作流项目（Markdown + 脚本 + 参考文档，在 skills/ 目录）

一个 Capability 通常编排多个 Tools 完成特定业务场景。
Skills 是比 Capability 更重的封装，包含完整的可执行脚本和项目模板。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from nini.agent.session import Session


CapabilityExecutorFactory = Callable[[Any | None], Any]


@dataclass
class Capability:
    """
    Capability 代表用户层面的"能力"，区别于模型层面的 Tools。

    例如：
    - Tool: t_test（模型调用的统计检验函数）
    - Capability: 差异分析（用户理解的完整分析流程）

    一个 Capability 通常编排多个 Tools 完成特定任务。

    Attributes:
        name: 内部标识，如 "difference_analysis"
        display_name: 展示名称，如 "差异分析"
        description: 能力描述
        icon: UI 图标，如 "🔬"
        required_tools: 该能力所需的 Tools 列表
        suggested_workflow: 推荐的工作流步骤（工具名称列表）
        is_executable: 当前版本是否支持直接执行
        execution_message: 不支持直接执行时给前端/API 的提示
    """

    name: str
    display_name: str
    description: str
    icon: str | None = None

    # 该能力所需的 Tools
    required_tools: list[str] = field(default_factory=list)

    # 推荐的工作流步骤（工具名称列表）
    suggested_workflow: list[str] = field(default_factory=list)

    # 当前版本是否支持通过 API 直接执行
    is_executable: bool = False

    # 不支持执行时的提示信息
    execution_message: str = ""

    # 可执行能力的构造器，接收 ToolRegistry 并返回具备 execute() 的执行器
    executor_factory: CapabilityExecutorFactory | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def get_workflow_for_context(self, context: dict[str, Any]) -> list[str]:
        """根据上下文返回定制化的工作流。

        Args:
            context: 当前会话上下文，包含已加载数据集、数据特征等信息

        Returns:
            推荐的工具调用序列
        """
        return self.suggested_workflow

    def get_recommended_tools(self, session: Session) -> list[str]:
        """基于当前会话状态推荐工具。

        Args:
            session: 当前会话对象

        Returns:
            推荐使用的工具名称列表
        """
        # 默认返回所有必需工具
        return self.required_tools

    def to_dict(self) -> dict[str, Any]:
        """转换为字典表示（用于 API 响应）。"""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "icon": self.icon,
            "required_tools": self.required_tools,
            "suggested_workflow": self.suggested_workflow,
            "is_executable": self.supports_direct_execution(),
            "execution_message": self.execution_message,
        }

    def supports_direct_execution(self) -> bool:
        """判断当前能力是否已接入直接执行器。"""
        return self.is_executable and self.executor_factory is not None

    def create_executor(self, registry: Any | None = None) -> Any | None:
        """创建能力执行器。"""
        if self.executor_factory is None:
            return None
        return self.executor_factory(registry)
