"""插件系统模块。

提供 Plugin 基类、DegradationInfo 模型和 PluginRegistry 注册表，
支持可选功能的可用性检测、生命周期管理和降级通知。
"""

from nini.plugins.base import DegradationInfo, Plugin
from nini.plugins.registry import PluginRegistry

__all__ = ["Plugin", "DegradationInfo", "PluginRegistry"]
