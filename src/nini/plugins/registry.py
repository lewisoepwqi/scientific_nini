"""PluginRegistry：插件注册表，管理插件生命周期。"""

from __future__ import annotations

import asyncio
import logging

from nini.plugins.base import DegradationInfo, Plugin

logger = logging.getLogger(__name__)

# 单插件初始化超时（秒），超时视为不可用
_PLUGIN_INIT_TIMEOUT = 5.0


class PluginRegistry:
    """应用级插件注册表。

    负责插件的注册、查询和生命周期管理（初始化/关闭）。
    与 ToolRegistry 模式一致，作为应用启动时的单例存在。
    """

    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}
        # 记录每个插件的可用性状态（initialize_all 后填充）
        self._available: dict[str, bool] = {}

    def register(self, plugin: Plugin) -> None:
        """注册插件。同名插件后注册者覆盖前者。"""
        self._plugins[plugin.name] = plugin
        logger.debug("插件已注册: %s v%s", plugin.name, plugin.version)

    def get(self, name: str) -> Plugin | None:
        """按名称查询已注册的插件，不存在返回 None。"""
        return self._plugins.get(name)

    def list_available(self) -> list[Plugin]:
        """返回所有已标记为可用的插件列表。"""
        return [p for name, p in self._plugins.items() if self._available.get(name, False)]

    def list_unavailable(self) -> list[tuple[Plugin, DegradationInfo | None]]:
        """返回所有不可用插件及其降级信息。"""
        result: list[tuple[Plugin, DegradationInfo | None]] = []
        for name, plugin in self._plugins.items():
            if not self._available.get(name, False):
                result.append((plugin, plugin.get_degradation_info()))
        return result

    async def initialize_all(self) -> None:
        """初始化所有已注册的插件。

        单个插件的初始化失败（异常或超时）不阻断其他插件和应用启动。
        超时阈值为 5 秒，超时插件被标记为不可用并记录警告日志。
        """
        for name, plugin in self._plugins.items():
            await self._initialize_one(name, plugin)

    async def _initialize_one(self, name: str, plugin: Plugin) -> None:
        """初始化单个插件，含失败隔离和超时保护。"""
        try:
            # 检测可用性
            available = await asyncio.wait_for(plugin.is_available(), timeout=_PLUGIN_INIT_TIMEOUT)
            if not available:
                self._available[name] = False
                info = plugin.get_degradation_info()
                reason = info.reason if info else "插件报告不可用"
                logger.warning("插件不可用，跳过初始化: %s — %s", name, reason)
                return

            # 执行初始化
            await asyncio.wait_for(plugin.initialize(), timeout=_PLUGIN_INIT_TIMEOUT)
            self._available[name] = True
            logger.info("插件已初始化: %s v%s", name, plugin.version)

        except TimeoutError:
            self._available[name] = False
            logger.warning("插件初始化超时（>%.0fs），标记为不可用: %s", _PLUGIN_INIT_TIMEOUT, name)
        except Exception as e:
            self._available[name] = False
            logger.warning("插件初始化异常，标记为不可用: %s — %s", name, e)

    async def shutdown_all(self) -> None:
        """清理所有插件资源。逐个调用 shutdown()，异常不阻断其他插件清理。"""
        for name, plugin in self._plugins.items():
            try:
                await plugin.shutdown()
                logger.debug("插件已关闭: %s", name)
            except Exception as e:
                logger.warning("插件关闭异常: %s — %s", name, e)
