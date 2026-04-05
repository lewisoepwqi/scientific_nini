"""Tool 基类和 ToolResult。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from nini.agent.session import Session

if TYPE_CHECKING:
    from nini.tools.manifest import ToolManifest


@dataclass
class ToolResult:
    """工具执行结果。"""

    success: bool = True
    data: Any = None
    message: str = ""
    retryable: bool = False
    # 图表相关
    has_chart: bool = False
    chart_data: Any = None
    # 数据表相关
    has_dataframe: bool = False
    dataframe_preview: Any = None
    # 产物
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    # 扩展元数据
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为可序列化的字典。"""
        result: dict[str, Any] = {
            "success": self.success,
            "message": self.message,
        }
        if self.retryable:
            result["retryable"] = True
        if self.data is not None:
            result["data"] = self.data
        if self.has_chart:
            result["has_chart"] = True
            result["chart_data"] = self.chart_data
        if self.has_dataframe:
            result["has_dataframe"] = True
            result["dataframe_preview"] = self.dataframe_preview
        if self.artifacts:
            result["artifacts"] = self.artifacts
        if self.metadata:
            result["metadata"] = self.metadata
        return result


class ToolError(Exception):
    """工具执行异常基类。"""


class ToolInputError(ToolError):
    """用户输入错误，不可重试。"""


class ToolTimeoutError(ToolError):
    """工具执行超时，可重试。"""


class ToolSystemError(ToolError):
    """系统级故障，通常需要告警。"""


class Tool(ABC):
    """工具基类。所有工具必须实现此接口。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称（用于工具调用）。"""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述（用于 LLM 理解功能）。"""
        ...

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """参数的 JSON Schema。"""
        ...

    @property
    def is_idempotent(self) -> bool:
        """是否幂等（默认否）。"""
        return False

    @property
    def category(self) -> str:
        """工具分类，用于前端分组展示。"""
        return "other"

    @property
    def brief_description(self) -> str:
        """工具简述，用于轻量目录与能力推荐。"""
        first_line = " ".join(str(self.description).split())
        if len(first_line) <= 80:
            return first_line
        return first_line[:77] + "..."

    @property
    def research_domain(self) -> str:
        """工具所属科研领域。"""
        return "general"

    @property
    def difficulty_level(self) -> str:
        """工具使用难度。"""
        return "intermediate"

    @property
    def typical_use_cases(self) -> list[str]:
        """典型使用场景。"""
        return []

    @property
    def output_types(self) -> list[str]:
        """工具常见输出类型。"""
        return []

    @property
    def expose_to_llm(self) -> bool:
        """是否暴露给 LLM 作为可调用工具。设为 False 可减少工具数量。"""
        return True

    @abstractmethod
    async def execute(self, session: Session, **kwargs: Any) -> ToolResult:
        """执行工具。"""
        ...

    def build_input_error(
        self,
        *,
        message: str,
        payload: dict[str, Any],
        retryable: bool = False,
    ) -> ToolResult:
        """构造统一的结构化输入错误结果。"""
        return ToolResult(
            success=False,
            message=message,
            data=payload,
            metadata=payload,
            retryable=retryable,
        )

    def to_manifest(self) -> "ToolManifest":
        """导出为统一工具清单（用于跨平台描述）。"""
        from nini.tools.manifest import ToolManifest

        return ToolManifest(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
            is_idempotent=self.is_idempotent,
            category=self.category,
            brief_description=self.brief_description,
            research_domain=self.research_domain,
            difficulty_level=self.difficulty_level,
            typical_use_cases=self.typical_use_cases,
            output_types=self.output_types,
        )

    def get_tool_definition(self) -> dict[str, Any]:
        """转换为 OpenAI function calling 格式。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def _resolve_dataset_name(
        self,
        session: Session,
        params: dict[str, Any],
    ) -> "str | ToolResult | None":
        """从参数中解析数据集名称，支持多种别名，自动推断单数据集场景。"""
        dataset_name = str(params.get("dataset_name", "")).strip()
        if dataset_name:
            return dataset_name

        for alias in ("dataset", "dataset_id", "input_dataset", "source_dataset"):
            value = params.get(alias)
            if isinstance(value, str) and value.strip():
                return value.strip()

        dataset_names = [
            name for name in session.datasets.keys() if isinstance(name, str) and name.strip()
        ]
        if len(dataset_names) == 1:
            return dataset_names[0]
        if not dataset_names:
            return ToolResult(success=False, message="缺少 dataset_name，且当前会话没有可用数据集")

        preview = ", ".join(dataset_names[:5])
        suffix = "..." if len(dataset_names) > 5 else ""
        return ToolResult(
            success=False,
            message=f"缺少 dataset_name，当前会话存在多个数据集，请明确指定（可选: {preview}{suffix}）",
        )
