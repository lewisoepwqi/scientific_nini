"""Plugin 抽象基类和 DegradationInfo 降级信息模型。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field


class DegradationInfo(BaseModel):
    """插件不可用时的结构化降级信息，供 Agent 提示词和前端 UI 消费。"""

    plugin_name: str
    reason: str  # 不可用原因
    impact: str  # 对用户功能的影响描述
    alternatives: list[str] = Field(default_factory=list)  # 替代建议


class Plugin(ABC):
    """插件抽象基类。

    所有插件必须继承此类并实现 is_available() 和 initialize() 方法。
    插件在应用启动时由 PluginRegistry 统一初始化，关闭时统一清理。
    """

    name: str  # 插件唯一标识名称
    version: str  # 插件版本号
    description: str  # 插件功能描述

    @abstractmethod
    async def is_available(self) -> bool:
        """检测插件是否可用（依赖是否就绪、API key 是否配置等）。"""
        ...

    @abstractmethod
    async def initialize(self) -> None:
        """初始化插件（建立连接、加载资源等）。"""
        ...

    async def shutdown(self) -> None:
        """释放插件资源（默认空操作，子类可覆写）。"""

    def get_degradation_info(self) -> DegradationInfo | None:
        """返回插件不可用时的降级信息（默认返回 None，子类可覆写）。"""
        return None
