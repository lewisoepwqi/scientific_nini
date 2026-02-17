"""AnalysisMemory 集成测试。

覆盖：
- compressed_context 上限截断
- _record_stat_result 记录到 AnalysisMemory
- AnalysisMemory 注入到 LLM messages
- KnowledgeMemory 被统计 Skill 写入
"""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from nini.agent.session import Session
from nini.memory.compression import (
    AnalysisMemory,
    StatisticResult,
    clear_session_analysis_memories,
    get_analysis_memory,
    list_session_analysis_memories,
)
from nini.tools.statistics import _record_stat_result

# ---- compressed_context 上限截断 ----


class TestCompressedContextTruncation:
    """测试 set_compressed_context 上限截断逻辑。"""

    def test_single_summary_within_limit(self) -> None:
        session = Session(id="test_trunc_1")
        session.set_compressed_context("短摘要")
        assert session.compressed_context == "短摘要"
        assert session.compressed_rounds == 1

    def test_multiple_summaries_within_limit(self) -> None:
        session = Session(id="test_trunc_2")
        session.set_compressed_context("第一段")
        session.set_compressed_context("第二段")
        assert "第一段" in session.compressed_context
        assert "第二段" in session.compressed_context
        assert session.compressed_rounds == 2

    @patch("nini.agent.session.settings")
    def test_truncate_oldest_segment(self, mock_settings: object) -> None:
        """超过上限时应丢弃最旧段。"""
        # 设置一个很小的上限
        mock_settings.compressed_context_max_chars = 50  # type: ignore[attr-defined]
        mock_settings.sessions_dir = Session.__dataclass_fields__["id"].default_factory  # type: ignore[attr-defined]
        mock_settings.memory_auto_compress = False  # type: ignore[attr-defined]

        session = Session(id="test_trunc_3")
        session.set_compressed_context("A" * 20)  # 20 chars
        session.set_compressed_context("B" * 20)  # 合并后 20 + sep + 20 > 50
        session.set_compressed_context("C" * 20)  # 第三段

        # 最旧段应该被丢弃
        assert "C" * 20 in session.compressed_context
        assert len(session.compressed_context) <= 50

    def test_empty_summary_ignored(self) -> None:
        session = Session(id="test_trunc_4")
        session.set_compressed_context("")
        session.set_compressed_context("   ")
        assert session.compressed_context == ""
        assert session.compressed_rounds == 0


# ---- _record_stat_result ----


class TestRecordStatResult:
    """测试 _record_stat_result 辅助函数。"""

    def setup_method(self) -> None:
        self.session = Session(id="test_record_stat")
        self.session.datasets["demo"] = pd.DataFrame({"x": [1, 2, 3]})
        # 确保清理
        clear_session_analysis_memories(self.session.id)

    def teardown_method(self) -> None:
        clear_session_analysis_memories(self.session.id)

    def test_records_to_analysis_memory(self) -> None:
        _record_stat_result(
            self.session,
            "demo",
            test_name="t 检验",
            message="t(10) = 2.5, p = 0.03",
            test_statistic=2.5,
            p_value=0.03,
            degrees_of_freedom=10,
            effect_size=0.8,
            effect_type="cohens_d",
            significant=True,
        )

        mem = get_analysis_memory(self.session.id, "demo")
        assert len(mem.statistics) == 1
        stat = mem.statistics[0]
        assert stat.test_name == "t 检验"
        assert stat.p_value == 0.03
        assert stat.significant is True

    def test_records_to_knowledge_memory(self) -> None:
        _record_stat_result(
            self.session,
            "demo",
            test_name="ANOVA",
            message="F(2, 30) = 5.0, p = 0.01",
        )

        content = self.session.knowledge_memory.read()
        assert "ANOVA" in content
        assert "F(2, 30)" in content


# ---- AnalysisMemory 注入到 messages ----


class TestAnalysisMemoryInjection:
    """测试 AnalysisMemory 上下文注入到 LLM messages。"""

    def setup_method(self) -> None:
        self.session = Session(id="test_inject")
        clear_session_analysis_memories(self.session.id)

    def teardown_method(self) -> None:
        clear_session_analysis_memories(self.session.id)

    def test_no_injection_when_empty(self) -> None:
        """没有分析记忆时不应注入。"""
        from nini.agent.runner import AgentRunner

        runner = AgentRunner()
        messages, _ = runner._build_messages_and_retrieval(self.session)
        # 只有 system message
        for msg in messages:
            if msg["role"] == "assistant":
                assert "分析记忆" not in msg["content"]

    def test_injection_when_has_memories(self) -> None:
        """有分析记忆时应注入到上下文中。"""
        from nini.agent.runner import AgentRunner

        mem = get_analysis_memory(self.session.id, "test_data")
        mem.add_statistic(
            StatisticResult(
                test_name="t 检验",
                p_value=0.01,
                significant=True,
            )
        )

        runner = AgentRunner()
        messages, _ = runner._build_messages_and_retrieval(self.session)

        # 查找包含分析记忆的 assistant 消息
        found = False
        for msg in messages:
            if msg["role"] == "assistant" and "分析记忆" in msg.get("content", ""):
                found = True
                assert "test_data" in msg["content"]
                assert "t 检验" in msg["content"]
                break
        assert found, "应该注入分析记忆到 LLM messages"


# ---- list_session_analysis_memories ----


class TestListSessionAnalysisMemories:
    """测试 list_session_analysis_memories 函数。"""

    def setup_method(self) -> None:
        clear_session_analysis_memories("test_list")

    def teardown_method(self) -> None:
        clear_session_analysis_memories("test_list")

    def test_empty_session(self) -> None:
        result = list_session_analysis_memories("test_list")
        assert result == []

    def test_returns_non_empty_memories_only(self) -> None:
        # 创建一个空的和一个有内容的
        get_analysis_memory("test_list", "empty_data")
        mem = get_analysis_memory("test_list", "has_data")
        mem.add_statistic(StatisticResult(test_name="test", p_value=0.05, significant=False))

        result = list_session_analysis_memories("test_list")
        assert len(result) == 1
        assert result[0].dataset_name == "has_data"


# ---- 统计 Skill 实际执行后写入 KnowledgeMemory ----


class TestStatSkillWritesKnowledge:
    """测试统计 Skill 执行后写入 KnowledgeMemory。"""

    def setup_method(self) -> None:
        self.session = Session(id="test_skill_km")
        self.df = pd.DataFrame(
            {
                "value": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
                "group": ["A"] * 5 + ["B"] * 5,
            }
        )
        self.session.datasets["mydata"] = self.df
        clear_session_analysis_memories(self.session.id)

    def teardown_method(self) -> None:
        clear_session_analysis_memories(self.session.id)

    @pytest.mark.asyncio
    async def test_ttest_writes_knowledge(self) -> None:
        from nini.tools.statistics import TTestSkill

        skill = TTestSkill()
        result = await skill.execute(
            self.session,
            dataset_name="mydata",
            value_column="value",
            group_column="group",
        )
        assert result.success
        content = self.session.knowledge_memory.read()
        assert "t 检验" in content

    @pytest.mark.asyncio
    async def test_mann_whitney_writes_knowledge(self) -> None:
        from nini.tools.statistics import MannWhitneySkill

        skill = MannWhitneySkill()
        result = await skill.execute(
            self.session,
            dataset_name="mydata",
            value_column="value",
            group_column="group",
        )
        assert result.success
        content = self.session.knowledge_memory.read()
        assert "Mann-Whitney" in content
