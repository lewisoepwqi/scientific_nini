"""Capabilities 模块 - 用户层面的能力封装。

本模块提供用户可理解的"能力"(Capability)，区别于模型层面的 Tools：
- Capability: 用户理解的完整功能（如"差异分析"）
- Tool: 模型可调用的原子函数（如 t_test, create_chart）

一个 Capability 通常编排多个 Tools 完成特定业务场景。

示例用法:
    >>> from nini.capabilities import CapabilityRegistry, create_default_capabilities
    >>> registry = CapabilityRegistry()
    >>> for cap in create_default_capabilities():
    ...     registry.register(cap)
    >>> caps = registry.suggest_for_intent("比较两组数据的差异")
"""

from __future__ import annotations

from nini.capabilities.base import Capability
from nini.capabilities.defaults import create_default_capabilities
from nini.capabilities.registry import (
    CapabilityExecutionError,
    CapabilityExecutorNotConfiguredError,
    CapabilityNotExecutableError,
    CapabilityRegistry,
)

__all__ = [
    "Capability",
    "CapabilityExecutionError",
    "CapabilityExecutorNotConfiguredError",
    "CapabilityNotExecutableError",
    "CapabilityRegistry",
    "create_default_capabilities",
]
