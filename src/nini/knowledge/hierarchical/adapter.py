"""向后兼容适配器。

为现有的 KnowledgeLoader 提供适配层，支持配置切换。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from nini.config import settings
from nini.knowledge.hierarchical.unified_retriever import UnifiedRetriever

logger = logging.getLogger(__name__)


class HierarchicalKnowledgeAdapter:
    """层次化知识检索适配器。

    提供与现有 KnowledgeLoader 兼容的接口，
    同时支持通过配置切换到新的层次化检索。
    """

    def __init__(
        self,
        knowledge_dir: Path | None = None,
        storage_dir: Path | None = None,
    ) -> None:
        """初始化适配器。

        Args:
            knowledge_dir: 知识库目录
            storage_dir: 索引存储目录
        """
        self._knowledge_dir = knowledge_dir or settings.knowledge_dir
        self._storage_dir = storage_dir

        # 根据配置决定是否启用层次化检索
        self._use_hierarchical = settings.enable_hierarchical_index
        self._unified_retriever: UnifiedRetriever | None = None

        # 保留旧版检索器引用（用于回退）
        self._legacy_loader: Any = None

    async def initialize(self) -> bool:
        """异步初始化适配器。

        Returns:
            是否成功初始化
        """
        if self._use_hierarchical:
            try:
                self._unified_retriever = UnifiedRetriever(
                    self._knowledge_dir,
                    self._storage_dir,
                )
                result = await self._unified_retriever.initialize()
                if result:
                    logger.info("层次化检索适配器初始化成功")
                    return True
                else:
                    logger.warning("层次化检索初始化失败，回退到传统检索")
                    self._use_hierarchical = False
            except Exception as e:
                logger.warning(f"层次化检索初始化异常: {e}，回退到传统检索")
                self._use_hierarchical = False

        # 初始化传统检索器
        return await self._init_legacy_loader()

    async def _init_legacy_loader(self) -> bool:
        """初始化传统检索器。"""
        try:
            from nini.knowledge.loader import KnowledgeLoader

            self._legacy_loader = KnowledgeLoader(self._knowledge_dir)
            logger.info("传统知识检索器初始化成功")
            return True
        except Exception as e:
            logger.error(f"传统检索器初始化失败: {e}")
            return False

    async def select(
        self,
        user_message: str,
        *,
        dataset_columns: list[str] | None = None,
        max_entries: int = 3,
        max_total_chars: int = 3000,
    ) -> str:
        """选择相关知识（兼容旧接口）。

        Args:
            user_message: 用户消息
            dataset_columns: 数据集列名（可选）
            max_entries: 最大条目数
            max_total_chars: 最大字符数

        Returns:
            相关知识文本
        """
        if self._use_hierarchical and self._unified_retriever:
            try:
                result = await self._unified_retriever.search(
                    user_message,
                    top_k=max_entries,
                )
                # 限制返回长度
                content = result.content
                if len(content) > max_total_chars:
                    content = content[:max_total_chars] + "\n..."
                return content
            except Exception as e:
                logger.warning(f"层次化检索失败: {e}，回退到传统检索")

        # 回退到传统检索
        if self._legacy_loader:
            return self._legacy_loader.select(
                user_message,
                dataset_columns=dataset_columns,
                max_entries=max_entries,
                max_total_chars=max_total_chars,
            )

        return ""

    async def select_with_hits(
        self,
        user_message: str,
        *,
        dataset_columns: list[str] | None = None,
        max_entries: int = 3,
        max_total_chars: int = 3000,
    ) -> tuple[str, list[dict[str, Any]]]:
        """选择相关知识并返回命中详情（兼容旧接口）。

        Returns:
            (知识文本, 命中详情列表)
        """
        if self._use_hierarchical and self._unified_retriever:
            try:
                result = await self._unified_retriever.search(
                    user_message,
                    top_k=max_entries,
                )
                content = result.content
                if len(content) > max_total_chars:
                    content = content[:max_total_chars] + "\n..."
                return content, result.hits
            except Exception as e:
                logger.warning(f"层次化检索失败: {e}，回退到传统检索")

        # 回退到传统检索
        if self._legacy_loader:
            return self._legacy_loader.select_with_hits(
                user_message,
                dataset_columns=dataset_columns,
                max_entries=max_entries,
                max_total_chars=max_total_chars,
            )

        return "", []

    def get_stats(self) -> dict[str, Any]:
        """获取检索统计信息。"""
        stats = {
            "use_hierarchical": self._use_hierarchical,
        }

        if self._unified_retriever:
            stats.update(self._unified_retriever.get_stats())

        return stats


async def create_knowledge_adapter(
    knowledge_dir: Path | None = None,
) -> HierarchicalKnowledgeAdapter:
    """创建知识检索适配器。

    工厂函数，自动初始化并返回配置好的适配器。

    Args:
        knowledge_dir: 知识库目录

    Returns:
        初始化后的适配器实例
    """
    adapter = HierarchicalKnowledgeAdapter(knowledge_dir)
    await adapter.initialize()
    return adapter
