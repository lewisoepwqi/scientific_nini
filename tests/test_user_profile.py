"""测试用户画像系统。

TDD 方式：先写测试，再写实现。
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

import pytest


class TestUserProfile:
    """测试 UserProfile 数据类。"""

    def test_user_profile_default_values(self):
        """测试用户画像默认值。"""
        from nini.models.user_profile import UserProfile

        profile = UserProfile(user_id="test_user")

        assert profile.user_id == "test_user"
        assert profile.domain == "general"
        assert profile.significance_level == 0.05
        assert profile.journal_style == "nature"
        assert profile.auto_check_assumptions is True
        assert profile.include_effect_size is True
        assert profile.include_ci is True

    def test_user_profile_custom_values(self):
        """测试自定义用户画像值。"""
        from nini.models.user_profile import UserProfile

        profile = UserProfile(
            user_id="bio_researcher",
            domain="biology",
            significance_level=0.01,
            journal_style="cell",
            color_palette="viridis",
            auto_check_assumptions=True,
            include_effect_size=True,
            include_ci=True,
        )

        assert profile.domain == "biology"
        assert profile.significance_level == 0.01
        assert profile.journal_style == "cell"

    def test_user_profile_serialization(self):
        """测试用户画像序列化。"""
        from nini.models.user_profile import UserProfile

        profile = UserProfile(
            user_id="test_user",
            domain="psychology",
            favorite_tests=["t_test", "anova"],
        )

        # 转换为字典
        profile_dict = asdict(profile)
        assert profile_dict["user_id"] == "test_user"
        assert profile_dict["domain"] == "psychology"
        assert "t_test" in profile_dict["favorite_tests"]

    def test_user_profile_favorite_tests_tracking(self):
        """测试常用检验方法追踪。"""
        from nini.models.user_profile import UserProfile

        profile = UserProfile(user_id="test_user")

        # 初始状态
        assert len(profile.favorite_tests) == 0

        # 记录使用
        profile.record_test_usage("t_test")
        profile.record_test_usage("anova")
        profile.record_test_usage("t_test")  # 重复使用

        # 应该按使用次数排序
        assert "t_test" in profile.favorite_tests
        assert "anova" in profile.favorite_tests

    def test_user_profile_update_statistics(self):
        """测试统计信息更新。"""
        from nini.models.user_profile import UserProfile

        profile = UserProfile(user_id="test_user")

        assert profile.total_analyses == 0

        profile.increment_analysis_count()
        assert profile.total_analyses == 1

        profile.increment_analysis_count()
        assert profile.total_analyses == 2

    def test_test_usage_counter_survives_round_trip(self):
        """测试 _test_usage_counter 在序列化/反序列化后正确恢复。"""
        from nini.models.user_profile import UserProfile

        profile = UserProfile(user_id="test_user")
        profile.record_test_usage("t_test")
        profile.record_test_usage("t_test")
        profile.record_test_usage("anova")

        # 序列化再反序列化
        data = profile.to_dict()
        restored = UserProfile.from_dict(data)

        # 内部计数器应恢复
        assert restored._test_usage_counter == {"t_test": 2, "anova": 1}
        assert restored.preferred_methods["t_test"] > restored.preferred_methods["anova"]

        # 继续记录应该基于恢复后的计数器，不会重置
        restored.record_test_usage("anova")
        assert restored._test_usage_counter == {"t_test": 2, "anova": 2}
        # 权重应该相等
        assert abs(restored.preferred_methods["t_test"] - restored.preferred_methods["anova"]) < 0.01


class TestUserProfileManager:
    """测试 UserProfileManager 类。"""

    @pytest.mark.asyncio
    async def test_create_new_profile(self):
        """测试创建新用户画像。"""
        from nini.agent.profile_manager import UserProfileManager

        manager = UserProfileManager()

        profile = await manager.get_or_create("new_user")

        assert profile.user_id == "new_user"
        assert profile.domain == "general"

    @pytest.mark.asyncio
    async def test_load_existing_profile(self):
        """测试加载已存在的用户画像。"""
        from nini.agent.profile_manager import UserProfileManager
        from nini.models.user_profile import UserProfile

        manager = UserProfileManager()

        # 创建并保存
        profile = UserProfile(
            user_id="existing_user",
            domain="medicine",
            journal_style="lancet",
        )
        await manager.save(profile)

        # 加载
        loaded = await manager.get_or_create("existing_user")

        assert loaded.user_id == "existing_user"
        assert loaded.domain == "medicine"
        assert loaded.journal_style == "lancet"

    @pytest.mark.asyncio
    async def test_update_profile(self):
        """测试更新用户画像。"""
        from nini.agent.profile_manager import UserProfileManager
        from nini.models.user_profile import UserProfile

        manager = UserProfileManager()

        profile = await manager.get_or_create("user_to_update")

        # 更新偏好
        profile.domain = "biology"
        profile.significance_level = 0.01

        await manager.save(profile)

        # 重新加载
        updated = await manager.get_or_create("user_to_update")

        assert updated.domain == "biology"
        assert updated.significance_level == 0.01

    @pytest.mark.asyncio
    async def test_delete_profile(self):
        """测试删除用户画像。"""
        from nini.agent.profile_manager import UserProfileManager

        manager = UserProfileManager()

        # 创建
        await manager.get_or_create("user_to_delete")

        # 删除
        await manager.delete("user_to_delete")

        # 应该创建新的默认画像
        new_profile = await manager.get_or_create("user_to_delete")
        assert new_profile.domain == "general"

    @pytest.mark.asyncio
    async def test_record_analysis_activity(self):
        """测试记录分析活动。"""
        from nini.agent.profile_manager import UserProfileManager

        manager = UserProfileManager()

        # 记录活动
        await manager.record_analysis(
            user_id="active_user",
            test_method="t_test",
            journal_style="nature",
        )

        # 加载并检查
        profile = await manager.get_or_create("active_user")

        assert profile.total_analyses > 0
        assert "t_test" in profile.favorite_tests

    @pytest.mark.asyncio
    async def test_get_profile_for_prompt(self):
        """测试获取用于 Prompt 的画像描述。"""
        from nini.agent.profile_manager import UserProfileManager

        manager = UserProfileManager()

        profile = await manager.get_or_create("prompt_user")
        profile.domain = "psychology"
        profile.journal_style = "apa"

        prompt_text = manager.get_profile_prompt(profile)

        assert "psychology" in prompt_text
        assert "apa" in prompt_text or "APA" in prompt_text


class TestUserProfileIntegration:
    """测试用户画像系统集成。"""

    @pytest.mark.asyncio
    async def test_profile_injected_to_system_prompt(self):
        """测试用户画像注入到系统提示词。"""
        from nini.agent.profile_manager import UserProfileManager, get_user_profile_prompt
        from nini.agent.session import Session

        session = Session(id="test_session")
        manager = UserProfileManager()

        # 设置会话用户
        profile = await manager.get_or_create("session_user")
        profile.domain = "biology"
        profile.journal_style = "cell"  # 使用非默认值

        # 获取提示词片段
        prompt_fragment = get_user_profile_prompt(profile)

        assert "biology" in prompt_fragment.lower()
        # cell 风格应该显示
        assert "cell" in prompt_fragment.lower()

    @pytest.mark.asyncio
    async def test_profile_persists_across_sessions(self):
        """测试画像在会话间持久化。"""
        from nini.agent.profile_manager import UserProfileManager

        manager = UserProfileManager()

        # 会话 1：创建画像
        profile1 = await manager.get_or_create("persistent_user")
        profile1.domain = "medicine"
        profile1.favorite_tests = ["t_test", "anova"]
        await manager.save(profile1)

        # 会话 2：加载画像
        profile2 = await manager.get_or_create("persistent_user")

        assert profile2.domain == "medicine"
        assert "t_test" in profile2.favorite_tests
