"""Capability 注册表。

管理用户层面的能力（Capabilities）。

区别于：
- ToolRegistry: 管理模型可调用的原子工具
- Skill 目录: 完整工作流项目（含脚本、模板、文档）
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from nini.capabilities.base import Capability
from nini.intent import IntentAnalysis, default_intent_analyzer

if TYPE_CHECKING:
    from nini.agent.session import Session

logger = logging.getLogger(__name__)


class CapabilityExecutionError(RuntimeError):
    """Capability 执行异常基类。"""


class CapabilityNotExecutableError(CapabilityExecutionError):
    """Capability 未接入直接执行器。"""


class CapabilityExecutorNotConfiguredError(CapabilityExecutionError):
    """Capability 声明可执行，但未配置执行器。"""


class CapabilityRegistry:
    """管理用户层面的能力（Capabilities）。

    区别于 ToolRegistry：
    - ToolRegistry 管理模型可调用的原子工具
    - CapabilityRegistry 管理用户可理解的能力封装
    """

    def __init__(self):
        self._capabilities: dict[str, Capability] = {}

    def register(self, capability: Capability) -> None:
        """注册一个能力。

        Args:
            capability: 要注册的能力实例
        """
        if capability.name in self._capabilities:
            logger.warning("能力 %s 已存在，将被覆盖", capability.name)
        self._capabilities[capability.name] = capability
        logger.info("注册能力: %s", capability.name)

    def get(self, name: str) -> Capability | None:
        """获取能力。

        Args:
            name: 能力名称

        Returns:
            能力实例，如果不存在则返回 None
        """
        return self._capabilities.get(name)

    def list_capabilities(self) -> list[Capability]:
        """列出所有能力。

        Returns:
            能力实例列表
        """
        return list(self._capabilities.values())

    def list_capability_names(self) -> list[str]:
        """列出所有能力名称。

        Returns:
            能力名称列表
        """
        return list(self._capabilities.keys())

    def suggest_for_intent(self, user_message: str) -> list[Capability]:
        """基于用户意图推荐能力。

        当前实现：简单的关键词匹配
        未来改进：使用 Embedding 相似度

        Args:
            user_message: 用户输入消息

        Returns:
            推荐的能力列表（按相关性排序）
        """
        analysis = self.analyze_intent(user_message)
        suggested: list[Capability] = []
        for candidate in analysis.capability_candidates:
            cap = self._capabilities.get(candidate.name)
            if cap is not None:
                suggested.append(cap)
        return suggested

    def analyze_intent(self, user_message: str) -> IntentAnalysis:
        """分析用户意图并返回结构化结果。"""
        capability_items = [cap.to_dict() for cap in self._capabilities.values()]
        return default_intent_analyzer.analyze(
            user_message,
            capabilities=capability_items,
        )

    def get_tools_for_capability(self, name: str) -> list[str]:
        """获取特定能力所需的工具列表。

        Args:
            name: 能力名称

        Returns:
            工具名称列表，如果能力不存在则返回空列表
        """
        cap = self._capabilities.get(name)
        if cap:
            return cap.required_tools
        return []

    def create_executor(self, name: str, tool_registry: Any | None = None) -> Any | None:
        """为指定能力创建执行器。"""
        cap = self._capabilities.get(name)
        if cap is None:
            return None
        return cap.create_executor(tool_registry)

    async def execute(
        self,
        name: str,
        session: Session,
        params: dict[str, Any],
        *,
        tool_registry: Any | None = None,
    ) -> Any:
        """通过统一注册契约执行能力。"""
        cap = self._capabilities.get(name)
        if cap is None:
            raise KeyError(name)
        if not cap.is_executable:
            message = cap.execution_message or f"能力 '{name}' 暂不支持直接执行"
            raise CapabilityNotExecutableError(message)

        executor = cap.create_executor(tool_registry)
        if executor is None or not hasattr(executor, "execute"):
            raise CapabilityExecutorNotConfiguredError(
                f"能力 '{name}' 已标记为可执行，但尚未接入执行器"
            )

        return await executor.execute(session, **params)

    def to_catalog(self) -> list[dict[str, Any]]:
        """生成能力目录（用于 API 响应）。

        Returns:
            能力字典列表
        """
        return [cap.to_dict() for cap in self._capabilities.values()]
