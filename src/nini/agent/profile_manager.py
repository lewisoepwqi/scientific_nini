"""用户画像管理器。

负责用户画像的持久化和检索。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from nini.config import settings
from nini.models.user_profile import UserProfile

logger = logging.getLogger(__name__)


class UserProfileManager:
    """用户画像管理器。

    负责用户画像的创建、加载、保存和更新。
    """

    def __init__(self, profiles_dir: Path | None = None):
        """初始化管理器。

        Args:
            profiles_dir: 画像存储目录，默认使用 settings.profiles_dir
        """
        self._profiles_dir = profiles_dir or settings.profiles_dir
        self._profiles_dir.mkdir(parents=True, exist_ok=True)

    def _get_profile_path(self, user_id: str) -> Path:
        """获取用户画像文件路径。"""
        return self._profiles_dir / f"{user_id}.json"

    async def get_or_create(self, user_id: str) -> UserProfile:
        """获取或创建用户画像。

        Args:
            user_id: 用户标识

        Returns:
            UserProfile: 用户画像实例
        """
        existing = await self.load(user_id)
        if existing is not None:
            return existing

        # 创建新画像
        logger.info("创建新用户画像: %s", user_id)
        return UserProfile(user_id=user_id)

    async def load(self, user_id: str) -> UserProfile | None:
        """加载用户画像。

        Args:
            user_id: 用户标识

        Returns:
            UserProfile | None: 用户画像实例，不存在返回 None
        """
        path = self._get_profile_path(user_id)
        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return UserProfile.from_dict(data)
        except Exception as e:
            logger.error("加载用户画像失败 %s: %s", user_id, e)
            return None

    async def save(self, profile: UserProfile) -> None:
        """保存用户画像。

        Args:
            profile: 用户画像实例
        """
        path = self._get_profile_path(profile.user_id)
        try:
            path.write_text(
                json.dumps(profile.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.debug("保存用户画像: %s", profile.user_id)
        except Exception as e:
            logger.error("保存用户画像失败 %s: %s", profile.user_id, e)
            raise

    async def delete(self, user_id: str) -> None:
        """删除用户画像。

        Args:
            user_id: 用户标识
        """
        path = self._get_profile_path(user_id)
        if path.exists():
            path.unlink()
            logger.info("删除用户画像: %s", user_id)

    async def update(
        self,
        user_id: str,
        **updates: Any,
    ) -> UserProfile | None:
        """更新用户画像字段。

        Args:
            user_id: 用户标识
            **updates: 要更新的字段

        Returns:
            UserProfile | None: 更新后的画像，不存在返回 None
        """
        profile = await self.get_or_create(user_id)

        for key, value in updates.items():
            if hasattr(profile, key):
                setattr(profile, key, value)

        await self.save(profile)
        return profile

    async def record_analysis(
        self,
        user_id: str,
        test_method: str,
        journal_style: str | None = None,
    ) -> None:
        """记录分析活动。

        Args:
            user_id: 用户标识
            test_method: 使用的统计方法
            journal_style: 使用的期刊风格（可选）
        """
        profile = await self.get_or_create(user_id)
        profile.increment_analysis_count()
        profile.record_test_usage(test_method)

        if journal_style:
            profile.journal_style = journal_style

        await self.save(profile)

    async def record_dataset_usage(
        self,
        user_id: str,
        dataset_name: str,
    ) -> None:
        """记录数据集使用。

        Args:
            user_id: 用户标识
            dataset_name: 数据集名称
        """
        profile = await self.get_or_create(user_id)
        profile.add_recent_dataset(dataset_name)
        await self.save(profile)

    def get_profile_prompt(self, profile: UserProfile) -> str:
        """获取用于系统提示词的用户画像描述。

        Args:
            profile: 用户画像实例

        Returns:
            str: 适用于系统提示词的描述文本
        """
        parts: list[str] = []

        # 领域信息
        if profile.domain != "general":
            parts.append(f"- 研究领域: {profile.domain}")

        # 统计偏好
        stats_parts = []
        if profile.significance_level != 0.05:
            stats_parts.append(f"显著性水平 α={profile.significance_level}")
        if not profile.auto_check_assumptions:
            stats_parts.append("不自动检查前提假设")
        if not profile.include_effect_size:
            stats_parts.append("不计算效应量")
        if not profile.include_ci:
            stats_parts.append("不计算置信区间")

        if stats_parts:
            parts.append(f"- 统计偏好: {', '.join(stats_parts)}")

        # 可视化偏好
        if profile.journal_style != "nature":
            parts.append(f"- 默认期刊风格: {profile.journal_style}")

        # 常用方法
        if profile.favorite_tests:
            parts.append(f"- 常用方法: {', '.join(profile.favorite_tests[:5])}")

        if not parts:
            return "用户画像: 使用默认设置。"

        return "用户画像:\n" + "\n".join(parts)


# 全局单例
_profile_manager_instance: UserProfileManager | None = None


def get_profile_manager() -> UserProfileManager:
    """获取全局用户画像管理器单例。"""
    global _profile_manager_instance
    if _profile_manager_instance is None:
        _profile_manager_instance = UserProfileManager()
    return _profile_manager_instance


def get_user_profile_prompt(profile: UserProfile) -> str:
    """获取用户画像的提示词描述（便捷函数）。"""
    return get_profile_manager().get_profile_prompt(profile)
