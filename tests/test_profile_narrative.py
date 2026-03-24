"""ProfileNarrativeManager 单元测试。"""

from __future__ import annotations

import pytest

from nini.memory.profile_narrative import (
    KEEP_AGENT_ENTRIES,
    MAX_AGENT_ENTRIES,
    SECTION_AGENT,
    SECTION_AUTO,
    SECTION_USER,
    ProfileNarrativeManager,
)
from nini.models.user_profile import UserProfile


@pytest.fixture()
def manager(tmp_path):
    """返回使用临时目录的管理器实例。"""
    return ProfileNarrativeManager(profiles_dir=tmp_path)


@pytest.fixture()
def sample_profile():
    """返回带常用字段的测试画像。"""
    p = UserProfile(user_id="test")
    p.domain = "medicine"
    p.research_domains = ["medicine", "psychology"]
    p.significance_level = 0.01
    p.confidence_interval = 0.99
    p.preferred_correction = "fdr"
    p.journal_style = "nejm"
    p.report_detail_level = "detailed"
    p.output_language = "zh"
    p.typical_sample_size = "每组 50 个样本"
    p.research_interest = "心血管疾病风险因素研究"
    p.research_notes = "常用配对设计"
    p.total_analyses = 10
    p.recent_datasets = ["blood_pressure.csv", "heart_rate.xlsx"]
    p.favorite_tests = ["t_test", "anova"]
    return p


class TestGenerateAutoContent:
    """测试 AUTO 段内容生成。"""

    def test_includes_domains(self, sample_profile):
        content = ProfileNarrativeManager.generate_auto_content(sample_profile)
        assert "medicine" in content
        assert "psychology" in content

    def test_includes_significance_level(self, sample_profile):
        content = ProfileNarrativeManager.generate_auto_content(sample_profile)
        assert "0.01" in content

    def test_includes_journal_style(self, sample_profile):
        content = ProfileNarrativeManager.generate_auto_content(sample_profile)
        assert "nejm" in content

    def test_includes_typical_sample_size(self, sample_profile):
        content = ProfileNarrativeManager.generate_auto_content(sample_profile)
        assert "每组 50 个样本" in content

    def test_includes_research_interest(self, sample_profile):
        content = ProfileNarrativeManager.generate_auto_content(sample_profile)
        assert "心血管疾病风险因素研究" in content

    def test_includes_history(self, sample_profile):
        content = ProfileNarrativeManager.generate_auto_content(sample_profile)
        assert "10" in content
        assert "blood_pressure.csv" in content

    def test_empty_profile_no_crash(self):
        p = UserProfile(user_id="empty")
        content = ProfileNarrativeManager.generate_auto_content(p)
        assert isinstance(content, str)


class TestRegenerate:
    """测试 regenerate() 方法。"""

    def test_creates_md_file(self, manager, sample_profile, tmp_path):
        manager.regenerate("test", sample_profile)
        md_path = tmp_path / "test_profile.md"
        assert md_path.exists()

    def test_md_contains_all_sections(self, manager, sample_profile, tmp_path):
        manager.regenerate("test", sample_profile)
        content = (tmp_path / "test_profile.md").read_text(encoding="utf-8")
        assert f"## {SECTION_AUTO}" in content
        assert f"## {SECTION_AGENT}" in content
        assert f"## {SECTION_USER}" in content

    def test_user_section_synced_with_research_notes(self, manager, sample_profile, tmp_path):
        manager.regenerate("test", sample_profile)
        sections = manager.read_sections("test")
        assert sections[SECTION_USER] == "常用配对设计"

    def test_agent_section_preserved_on_regen(self, manager, sample_profile):
        """重新生成 AUTO 段时，AGENT 段已有内容不被覆盖。"""
        manager.append_agent_observation("test", "用户习惯先检查正态性")
        manager.regenerate("test", sample_profile)
        sections = manager.read_sections("test")
        assert "用户习惯先检查正态性" in sections[SECTION_AGENT]


class TestAppendAgentObservation:
    """测试 append_agent_observation() 方法。"""

    def test_returns_true_on_success(self, manager):
        ok = manager.append_agent_observation("u1", "用户偏好对数变换")
        assert ok is True

    def test_entry_saved(self, manager):
        manager.append_agent_observation("u1", "用户偏好对数变换")
        sections = manager.read_sections("u1")
        assert "用户偏好对数变换" in sections[SECTION_AGENT]

    def test_entry_has_timestamp(self, manager):
        manager.append_agent_observation("u1", "用户偏好对数变换")
        sections = manager.read_sections("u1")
        # 时间戳格式：[YYYY-MM-DD]
        import re

        assert re.search(r"\[\d{4}-\d{2}-\d{2}\]", sections[SECTION_AGENT])

    def test_multiple_entries_accumulate(self, manager):
        manager.append_agent_observation("u1", "观察 1")
        manager.append_agent_observation("u1", "观察 2")
        manager.append_agent_observation("u1", "观察 3")
        sections = manager.read_sections("u1")
        assert "观察 1" in sections[SECTION_AGENT]
        assert "观察 3" in sections[SECTION_AGENT]

    def test_returns_false_on_empty(self, manager):
        ok = manager.append_agent_observation("u1", "")
        assert ok is False

    def test_archive_when_exceeds_max(self, manager):
        """超过 MAX_AGENT_ENTRIES 时触发归档，保留最新 KEEP_AGENT_ENTRIES 条。"""
        for i in range(MAX_AGENT_ENTRIES + 2):
            manager.append_agent_observation("u1", f"观察 {i:03d}")
        sections = manager.read_sections("u1")
        entries = [ln for ln in sections[SECTION_AGENT].splitlines() if ln.strip()]
        # 归档提示 + 保留条目 + 后续追加条目，总数应显著少于原始总数
        assert len(entries) < MAX_AGENT_ENTRIES + 1
        assert "已归档" in sections[SECTION_AGENT]
        assert f"观察 {(MAX_AGENT_ENTRIES + 1):03d}" in sections[SECTION_AGENT]


class TestParseSections:
    """测试段落解析逻辑。"""

    def test_round_trip(self, manager, sample_profile):
        """regenerate 后再 read_sections，数据应可逆。"""
        manager.regenerate("test", sample_profile)
        sections = manager.read_sections("test")
        assert sections[SECTION_AUTO] != ""
        assert sections[SECTION_USER] == "常用配对设计"

    def test_parse_ignores_comments(self):
        md = "<!-- _auto_generated: 2026-01-01 -->\n## 研究偏好摘要\n内容行"
        sections = ProfileNarrativeManager._parse_sections(md)
        assert "内容行" in sections[SECTION_AUTO]
        assert "auto_generated" not in sections[SECTION_AUTO]


class TestGetNarrativeForContext:
    """测试 LLM context 注入文本裁剪。"""

    def test_returns_empty_when_no_file(self, manager):
        result = manager.get_narrative_for_context("nonexistent")
        assert result == ""

    def test_returns_sections_content(self, manager, sample_profile):
        manager.regenerate("test", sample_profile)
        result = manager.get_narrative_for_context("test")
        assert SECTION_AUTO in result
        assert "nejm" in result

    def test_respects_max_chars(self, manager, sample_profile):
        manager.regenerate("test", sample_profile)
        result = manager.get_narrative_for_context("test", max_chars=50)
        # 截断后 = max_chars(50) + 截断提示("\n…（更多内容已省略）"，11 字符) = 61 字符上限
        assert len(result) <= 50 + 12


class TestUpdateUserNotes:
    """测试 update_user_notes() 方法。"""

    def test_updates_user_section(self, manager, sample_profile):
        manager.regenerate("test", sample_profile)
        manager.update_user_notes("test", "新的备注内容")
        sections = manager.read_sections("test")
        assert sections[SECTION_USER] == "新的备注内容"

    def test_auto_section_preserved(self, manager, sample_profile):
        manager.regenerate("test", sample_profile)
        original_auto = manager.read_sections("test")[SECTION_AUTO]
        manager.update_user_notes("test", "新备注")
        assert manager.read_sections("test")[SECTION_AUTO] == original_auto
