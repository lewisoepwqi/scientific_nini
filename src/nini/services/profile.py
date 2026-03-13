"""用户画像服务。

为 API 路由提供用户画像业务逻辑层。
"""

from __future__ import annotations

import logging
from typing import Any

from nini.agent.profile_manager import get_profile_manager, UserProfileManager
from nini.models.user_profile import UserProfile

logger = logging.getLogger(__name__)


class ProfileService:
    """用户画像服务。

    封装用户画像的业务逻辑，为 API 路由提供简洁接口。
    """

    def __init__(self, manager: Any | None = None):
        """初始化服务。

        Args:
            manager: 用户画像管理器实例，默认使用全局单例
        """
        self._manager = manager or get_profile_manager()

    async def get_profile(self, user_id: str = "default") -> dict[str, Any]:
        """获取用户画像。

        Args:
            user_id: 用户标识，默认为 "default"

        Returns:
            dict: 用户画像数据
        """
        try:
            profile = await self._manager.get_or_create(user_id)
            return profile.to_dict()
        except Exception as e:
            logger.error("获取用户画像失败: %s", e)
            # 返回默认画像
            return UserProfile(user_id=user_id).to_dict()

    async def update_profile(
        self, updates: dict[str, Any], user_id: str = "default"
    ) -> dict[str, Any]:
        """更新用户画像，并同步更新 Markdown 叙述层。

        Args:
            updates: 要更新的字段
            user_id: 用户标识，默认为 "default"

        Returns:
            dict: 更新后的画像数据
        """
        try:
            profile = await self._manager.update(user_id, **updates)
            if profile:
                # 触发叙述层 AUTO 段重新生成
                try:
                    from nini.memory.profile_narrative import get_profile_narrative_manager

                    get_profile_narrative_manager().regenerate(profile.user_id, profile)
                except Exception:
                    logger.warning("画像叙述层更新失败", exc_info=True)
                return profile.to_dict()
        except Exception as e:
            logger.error("更新用户画像失败: %s", e)

        # 失败时返回当前画像
        return await self.get_profile(user_id)

    async def get_profile_prompt(self, user_id: str = "default") -> str:
        """获取研究画像的系统提示词。

        Args:
            user_id: 用户标识，默认为 "default"

        Returns:
            str: 系统提示词描述
        """
        try:
            profile = await self._manager.get_or_create(user_id)
            return self._manager.get_profile_prompt(profile)
        except Exception as e:
            logger.error("获取画像提示词失败: %s", e)
            return "用户画像: 使用默认设置。"

    async def record_analysis(
        self, method: str, dataset_size: int = 0, user_id: str = "default"
    ) -> None:
        """记录分析历史到画像。

        Args:
            method: 使用的统计方法
            dataset_size: 数据集大小
            user_id: 用户标识，默认为 "default"
        """
        try:
            await self._manager.record_analysis(user_id, method)
        except Exception as e:
            logger.error("记录分析历史失败: %s", e)
