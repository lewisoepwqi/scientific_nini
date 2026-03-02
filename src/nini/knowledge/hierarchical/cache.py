"""检索结果缓存模块。

支持 TTL 缓存和查询结果缓存。
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from nini.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    """缓存条目。"""

    key: str
    value: T
    created_at: float
    ttl: int  # 秒

    @property
    def is_expired(self) -> bool:
        """检查是否过期。"""
        # ttl=0 表示立即过期
        if self.ttl <= 0:
            return True
        return time.time() - self.created_at > self.ttl


class RetrievalCache:
    """检索结果缓存。

    基于内存的 TTL 缓存，用于缓存查询结果。
    """

    def __init__(self, ttl: int | None = None) -> None:
        """初始化缓存。

        Args:
            ttl: 缓存生存时间（秒），默认使用配置值
        """
        # 注意：ttl=0 是有效的（立即过期），所以不能用 "or"
        self.ttl = settings.hierarchical_cache_ttl if ttl is None else ttl
        self._cache: dict[str, CacheEntry] = {}
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Any | None:
        """获取缓存值。

        Args:
            key: 缓存键

        Returns:
            缓存值或 None
        """
        entry = self._cache.get(key)

        if entry is None:
            self._misses += 1
            return None

        if entry.is_expired:
            del self._cache[key]
            self._misses += 1
            return None

        self._hits += 1
        return entry.value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """设置缓存值。

        Args:
            key: 缓存键
            value: 缓存值
            ttl: 自定义 TTL（可选）
        """
        # 注意：ttl=0 是有效的（立即过期），所以不能用 "or"
        entry_ttl = self.ttl if ttl is None else ttl
        entry = CacheEntry(
            key=key,
            value=value,
            created_at=time.time(),
            ttl=entry_ttl,
        )
        self._cache[key] = entry

    def invalidate(self, key: str) -> bool:
        """使指定缓存失效。

        Args:
            key: 缓存键

        Returns:
            是否成功删除
        """
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def invalidate_all(self) -> None:
        """清空所有缓存。"""
        self._cache.clear()
        logger.info("检索缓存已清空")

    def cleanup_expired(self) -> int:
        """清理过期缓存。

        Returns:
            清理的条目数
        """
        expired_keys = [
            key for key, entry in self._cache.items() if entry.is_expired
        ]
        for key in expired_keys:
            del self._cache[key]
        return len(expired_keys)

    @staticmethod
    def generate_key(query: str, **params: Any) -> str:
        """生成缓存键。

        Args:
            query: 查询文本
            **params: 其他参数

        Returns:
            缓存键
        """
        key_data = f"{query}:{sorted(params.items())}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:32]

    def get_stats(self) -> dict[str, Any]:
        """获取缓存统计信息。"""
        total_requests = self._hits + self._misses
        hit_rate = self._hits / total_requests if total_requests > 0 else 0

        return {
            "size": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{hit_rate:.2%}",
            "ttl": self.ttl,
        }
