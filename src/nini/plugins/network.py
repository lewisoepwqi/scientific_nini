"""NetworkPlugin：网络请求能力插件骨架。

封装网络可用性检测逻辑，为后续文献检索（C7）等联网功能提供基础。
网络不可用时提供结构化降级信息，告知用户离线替代方案。
"""

from __future__ import annotations

import logging

from nini.plugins.base import DegradationInfo, Plugin

logger = logging.getLogger(__name__)

_SEMANTIC_SCHOLAR_PROBE_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
_SEMANTIC_SCHOLAR_PROBE_PARAMS: dict[str, str | int] = {
    "query": "test",
    "limit": 1,
    "fields": "title",
}

# 尝试在模块级导入 httpx，不影响无 httpx 环境的模块加载
try:
    import httpx as httpx

    _HTTPX_AVAILABLE = True
except ImportError:
    httpx = None  # type: ignore[assignment]
    _HTTPX_AVAILABLE = False


class NetworkPlugin(Plugin):
    """网络请求能力插件。

    启动时检测网络连通性，不可用时优雅降级并提供替代建议。
    具体联网功能（如文献检索）由 C7 等后续插件扩展实现。
    """

    name = "network"
    version = "1.0"
    description = "提供网络请求能力，支持文献检索等联网功能"

    def __init__(self) -> None:
        self._client: object | None = None

    async def is_available(self) -> bool:
        """检测网络连通性。

        先探测通用网络连通性，再检测 Semantic Scholar API 端点可达性。
        任一环节失败都返回 False。
        """
        if not _HTTPX_AVAILABLE or httpx is None:
            logger.warning("httpx 未安装，NetworkPlugin 不可用")
            return False

        from nini.config import settings

        try:
            proxy = settings.network_proxy
            timeout = settings.network_timeout

            client = (
                httpx.AsyncClient(proxy=proxy, timeout=timeout)
                if proxy
                else httpx.AsyncClient(timeout=timeout)
            )
            async with client:
                response = await client.head(settings.network_probe_url)
                if response.status_code >= 500:
                    return False

                semantic_response = await client.get(
                    _SEMANTIC_SCHOLAR_PROBE_URL,
                    params=_SEMANTIC_SCHOLAR_PROBE_PARAMS,
                )
                return semantic_response.status_code < 500
        except Exception as e:
            logger.debug("网络可用性检测失败: %s", e)
            return False

    async def initialize(self) -> None:
        """初始化 HTTP 客户端。"""
        if not _HTTPX_AVAILABLE or httpx is None:
            logger.warning("httpx 未安装，NetworkPlugin 初始化跳过")
            return

        from nini.config import settings

        proxy = settings.network_proxy
        # 保存长连接客户端供后续工具使用
        self._client = (
            httpx.AsyncClient(proxy=proxy, timeout=settings.network_timeout)
            if proxy
            else httpx.AsyncClient(timeout=settings.network_timeout)
        )
        logger.info("NetworkPlugin HTTP 客户端已初始化（代理: %s）", proxy or "无")

    async def shutdown(self) -> None:
        """释放 HTTP 客户端资源。"""
        if self._client is not None and httpx is not None:
            try:
                if isinstance(self._client, httpx.AsyncClient):
                    await self._client.aclose()
                    logger.debug("NetworkPlugin HTTP 客户端已关闭")
            except Exception as e:
                logger.warning("NetworkPlugin 关闭 HTTP 客户端异常: %s", e)
            finally:
                self._client = None

    def get_degradation_info(self) -> DegradationInfo:
        """返回网络不可用时的降级信息。"""
        return DegradationInfo(
            plugin_name=self.name,
            reason="网络不可用或网络连接超时",
            impact="无法进行在线文献检索、URL 内容抓取等联网操作",
            alternatives=[
                "手动下载论文 PDF 后上传至 Nini 进行本地分析",
                "将文献摘要或全文复制粘贴到对话中",
                "检查网络连接后重启 Nini 以重新激活网络功能",
            ],
        )
