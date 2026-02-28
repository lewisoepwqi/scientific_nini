"""研究画像记忆。

将既有 ``UserProfile`` 语义提升为 ``ResearchProfile``，
用于承接 Nini 2.0 四层记忆中的研究画像层。
"""

from __future__ import annotations

from pathlib import Path

from nini.agent.profile_manager import UserProfileManager, get_profile_manager
from nini.models.user_profile import UserProfile

DEFAULT_RESEARCH_PROFILE_ID = "default"

# 向后兼容：当前研究画像直接复用既有用户画像模型。
ResearchProfile = UserProfile


class ResearchProfileManager(UserProfileManager):
    """研究画像管理器。

    当前版本直接复用用户画像的持久化格式，并提供同步访问接口，
    以便会话与运行时上下文在不改成异步链路的前提下接入。
    """

    def __init__(self, profiles_dir: Path | None = None):
        super().__init__(profiles_dir=profiles_dir)

    def load_sync(self, profile_id: str) -> ResearchProfile | None:
        """同步加载研究画像。"""
        path = self._get_profile_path(profile_id)
        if not path.exists():
            return None
        try:
            return ResearchProfile.from_dict(self._read_profile_data(path))
        except Exception:
            return None

    def save_sync(self, profile: ResearchProfile) -> None:
        """同步保存研究画像。"""
        path = self._get_profile_path(profile.user_id)
        self._write_profile_data(path, profile.to_dict())

    def get_or_create_sync(self, profile_id: str) -> ResearchProfile:
        """同步获取或创建研究画像。"""
        existing = self.load_sync(profile_id)
        if existing is not None:
            return existing
        profile = ResearchProfile(user_id=profile_id)
        self.save_sync(profile)
        return profile

    def update_sync(self, profile_id: str, **updates: object) -> ResearchProfile:
        """同步更新研究画像字段。"""
        profile = self.get_or_create_sync(profile_id)
        for key, value in updates.items():
            if hasattr(profile, key):
                setattr(profile, key, value)
        self.save_sync(profile)
        return profile

    def record_dataset_usage_sync(self, profile_id: str, dataset_name: str) -> ResearchProfile:
        """同步记录数据集使用。"""
        profile = self.get_or_create_sync(profile_id)
        profile.add_recent_dataset(dataset_name)
        self.save_sync(profile)
        return profile

    def record_analysis_sync(
        self,
        profile_id: str,
        test_method: str,
        journal_style: str | None = None,
    ) -> ResearchProfile:
        """同步记录分析活动。"""
        profile = self.get_or_create_sync(profile_id)
        profile.increment_analysis_count()
        profile.record_test_usage(test_method)
        if journal_style:
            profile.journal_style = journal_style
        self.save_sync(profile)
        return profile

    def get_research_profile_prompt(self, profile: ResearchProfile) -> str:
        """返回研究画像的运行时提示。"""
        parts: list[str] = ["研究画像:"]

        if profile.research_domains:
            parts.append(f"- 研究领域: {', '.join(profile.research_domains)}")
        elif profile.domain and profile.domain != "general":
            parts.append(f"- 研究领域: {profile.domain}")

        if profile.research_interest:
            parts.append(f"- 研究兴趣: {profile.research_interest}")

        if profile.preferred_methods:
            top_methods = sorted(
                profile.preferred_methods.items(), key=lambda x: x[1], reverse=True
            )[:5]
            method_str = ", ".join(f"{m}({w:.0%})" for m, w in top_methods)
            parts.append(f"- 常用方法: {method_str}")
        elif profile.favorite_tests:
            parts.append(f"- 常用方法: {', '.join(profile.favorite_tests[:5])}")

        parts.append(f"- 显著性水平: {profile.significance_level}")
        parts.append(f"- 期刊风格: {profile.journal_style}")
        parts.append(f"- 多重比较校正: {profile.preferred_correction}")

        if profile.report_detail_level != "standard":
            detail_cn = {"brief": "简洁", "detailed": "详细"}.get(
                profile.report_detail_level, profile.report_detail_level
            )
            parts.append(f"- 报告详细程度: {detail_cn}")

        if profile.typical_sample_size:
            parts.append(f"- 典型样本量: {profile.typical_sample_size}")

        if profile.research_notes:
            parts.append(f"- 备注: {profile.research_notes}")

        if profile.total_analyses > 0:
            parts.append(f"- 累计分析: {profile.total_analyses} 次")

        prefs: list[str] = []
        if profile.auto_check_assumptions:
            prefs.append("自动前提检验")
        if profile.include_effect_size:
            prefs.append("包含效应量")
        if profile.include_ci:
            prefs.append("包含置信区间")
        if profile.include_power_analysis:
            prefs.append("包含功效分析")
        if prefs:
            parts.append(f"- 分析偏好: {', '.join(prefs)}")

        return "\n".join(parts)


_research_profile_manager_instance: ResearchProfileManager | None = None


def get_research_profile_manager() -> ResearchProfileManager:
    """获取全局研究画像管理器。"""
    global _research_profile_manager_instance
    if _research_profile_manager_instance is None:
        base_manager = get_profile_manager()
        _research_profile_manager_instance = ResearchProfileManager(
            profiles_dir=base_manager._profiles_dir  # noqa: SLF001
        )
    return _research_profile_manager_instance


def get_research_profile_prompt(profile: ResearchProfile) -> str:
    """获取研究画像提示文本。"""
    return get_research_profile_manager().get_research_profile_prompt(profile)
