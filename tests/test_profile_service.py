"""ProfileService 回归测试。"""

from __future__ import annotations

import pytest

from nini.models.user_profile import UserProfile
from nini.services.profile import ProfileService


class _FakeProfileManager:
    def __init__(self) -> None:
        self.recorded: tuple[str, str, str | None] | None = None

    async def get_or_create(self, user_id: str) -> UserProfile:
        return UserProfile(user_id=user_id)

    async def update(self, user_id: str, **updates):
        profile = UserProfile(user_id=user_id)
        for key, value in updates.items():
            if hasattr(profile, key):
                setattr(profile, key, value)
        return profile

    async def record_analysis(
        self, user_id: str, test_method: str, journal_style: str | None = None
    ) -> None:
        self.recorded = (user_id, test_method, journal_style)

    def get_profile_prompt(self, profile: UserProfile) -> str:
        return f"用户画像: {profile.user_id}"


@pytest.mark.asyncio
async def test_profile_service_methods_work_in_async_context() -> None:
    manager = _FakeProfileManager()
    service = ProfileService(manager=manager)

    profile = await service.get_profile("u_async")
    assert profile["user_id"] == "u_async"

    updated = await service.update_profile({"domain": "biology"}, user_id="u_async")
    assert updated["domain"] == "biology"

    prompt = await service.get_profile_prompt("u_async")
    assert "u_async" in prompt

    await service.record_analysis("t_test", user_id="u_async")
    assert manager.recorded == ("u_async", "t_test", None)
