"""Skill 基类和 SkillResult。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from nini.agent.session import Session

if TYPE_CHECKING:
    from nini.tools.manifest import SkillManifest


@dataclass
class SkillResult:
    """技能执行结果。"""

    success: bool = True
    data: Any = None
    message: str = ""
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


class Skill(ABC):
    """技能基类。所有技能必须实现此接口。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """技能名称（用于工具调用）。"""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """技能描述（用于 LLM 理解功能）。"""
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
        """技能分类，用于前端分组展示。"""
        return "other"

    @property
    def brief_description(self) -> str:
        """技能简述，用于轻量目录与能力推荐。"""
        first_line = " ".join(str(self.description).split())
        if len(first_line) <= 80:
            return first_line
        return first_line[:77] + "..."

    @property
    def research_domain(self) -> str:
        """技能所属科研领域。"""
        return "general"

    @property
    def difficulty_level(self) -> str:
        """技能使用难度。"""
        return "intermediate"

    @property
    def typical_use_cases(self) -> list[str]:
        """典型使用场景。"""
        return []

    @property
    def output_types(self) -> list[str]:
        """技能常见输出类型。"""
        return []

    @property
    def expose_to_llm(self) -> bool:
        """是否暴露给 LLM 作为可调用工具。设为 False 可减少工具数量。"""
        return True

    @abstractmethod
    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        """执行技能。"""
        ...

    def to_manifest(self) -> "SkillManifest":
        """导出为统一技能清单（用于跨平台技能描述）。"""
        from nini.tools.manifest import SkillManifest

        return SkillManifest(
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
