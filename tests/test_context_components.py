"""拆分后的上下文组件测试。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from nini.agent.components.context_dataset import build_dataset_context
from nini.agent.components.context_knowledge import fallback_knowledge_load, inject_knowledge
from nini.agent.components.context_memory import (
    build_analysis_memory_context,
    build_research_profile_context,
)
from nini.agent.components.context_tools import (
    build_explicit_tool_context,
    build_intent_runtime_context,
    build_tool_runtime_resources_note,
    match_tools_by_context,
)
from nini.agent.session import Session


def test_build_dataset_context_includes_columns_and_row_count() -> None:
    """数据集上下文应包含行数、列名和 dtype。"""
    session = Session()
    session.datasets["demo.csv"] = pd.DataFrame({"value": [1, 2], "group": ["a", "b"]})

    context, columns = build_dataset_context(session)

    assert "demo.csv" in context
    assert "2 行" in context
    assert "value(int64)" in context
    assert columns == ["value", "group"]


def test_build_skill_runtime_resources_note_lists_preview_files() -> None:
    """运行时资源提示应列出前几个文件。"""
    registry = SimpleNamespace(
        get_runtime_resources=lambda name: {
            "name": name,
            "resources": [
                {"type": "file", "path": "scripts/run.py"},
                {"type": "file", "path": "references/guide.md"},
            ],
        }
    )

    note = build_tool_runtime_resources_note(registry, "guide")

    assert "scripts/run.py" in note
    assert "references/guide.md" in note


def test_build_explicit_skill_context_replaces_arguments_and_includes_tools() -> None:
    """显式技能上下文应替换参数占位符并带上首选工具。"""

    class _Analyzer:
        def parse_explicit_skill_calls(self, user_message: str, limit: int):
            return [{"name": "guide", "arguments": "demo.csv score"}]

    registry = SimpleNamespace(
        list_markdown_tools=lambda: [
            {
                "name": "guide",
                "enabled": True,
                "metadata": {"allowed_tools": ["read_file", "run_tests"]},
            }
        ],
        get_tool_instruction=lambda name: {
            "instruction": "读取 $1 并分析 $2\n工具: $ARGUMENTS",
            "location": "/tmp/guide/SKILL.md",
        },
    )

    context = build_explicit_tool_context(
        "/guide demo.csv score",
        registry,
        context_intent_analyzer=lambda: _Analyzer(),
        runtime_resources_builder=lambda _: "- 运行时资源: scripts/run.py。\n",
    )

    assert "demo.csv" in context
    assert "score" in context
    assert "read_file, run_tests" in context
    assert "scripts/run.py" in context


def test_match_skills_by_context_returns_payloads() -> None:
    """上下文匹配应返回候选 payload 列表。"""

    class _Candidate:
        def __init__(self, payload):
            self.payload = payload

    class _Analyzer:
        def rank_semantic_skills(self, user_message: str, markdown_items, limit: int):
            return [_Candidate(markdown_items[0])]

    registry = SimpleNamespace(
        get_semantic_catalog=lambda skill_type=None: [
            {"name": "guide", "description": "说明文档", "aliases": ["实验技能"]}
        ]
    )

    matched = match_tools_by_context(
        "请参考实验技能",
        registry,
        context_intent_analyzer=lambda: _Analyzer(),
    )

    assert matched == [{"name": "guide", "description": "说明文档", "aliases": ["实验技能"]}]


def test_build_intent_runtime_context_formats_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    """意图分析上下文应格式化候选能力、技能与工具。"""

    class _Candidate:
        def __init__(self, name: str, reason: str, payload: dict):
            self.name = name
            self.reason = reason
            self.payload = payload

    class _Analysis:
        capability_candidates = [
            _Candidate("difference_analysis", "提到差异", {"display_name": "差异分析"})
        ]
        skill_candidates = [_Candidate("root-analysis", "命中领域词", {})]
        tool_hints = ["t_test", "create_chart"]
        active_skills = [{"name": "root-analysis"}]

    class _Analyzer:
        def analyze(self, *args, **kwargs):
            return _Analysis()

    monkeypatch.setattr(
        "nini.agent.components.context_tools.create_default_capabilities",
        lambda: [SimpleNamespace(to_dict=lambda: {"name": "difference_analysis"})],
    )
    registry = SimpleNamespace(get_semantic_catalog=lambda skill_type=None: [])

    context = build_intent_runtime_context(
        "帮我做差异分析",
        registry,
        intent_analyzer=lambda: _Analyzer(),
    )

    assert "候选能力: 差异分析(提到差异)" in context
    assert "候选技能: root-analysis(命中领域词)" in context
    assert "推荐工具: t_test, create_chart" in context
    assert "激活技能: root-analysis" in context


def test_fallback_knowledge_load_uses_legacy_loader() -> None:
    """旧知识加载器回退路径应写入知识块并返回命中信息。"""

    class _Loader:
        vector_available = True

        def select_with_hits(self, *args, **kwargs):
            return "相关背景知识", [{"source": "guide", "score": 0.8, "snippet": "摘要"}]

    context_parts: list[str] = []
    event = fallback_knowledge_load(_Loader(), "怎么做 t 检验", ["value"], context_parts)

    assert event is not None
    assert event["query"] == "怎么做 t 检验"
    assert event["mode"] == "hybrid"
    assert event["results"][0]["source"] == "guide"
    assert event["results"][0]["source_id"].startswith("source:")
    assert event["results"][0]["acquisition_method"] == "unknown"
    assert "相关背景知识" in context_parts[0]


@pytest.mark.asyncio
async def test_inject_knowledge_falls_back_when_new_pipeline_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """新知识注入失败时应自动回退到旧加载器。"""

    class _Loader:
        def select_with_hits(self, *args, **kwargs):
            return "回退知识", [{"source": "legacy", "score": 0.5, "snippet": "回退摘要"}]

    monkeypatch.setattr(
        "nini.knowledge.context_injector.inject_knowledge_to_prompt",
        AsyncMock(side_effect=RuntimeError("boom")),
    )

    session = Session()
    context_parts: list[str] = []
    event = await inject_knowledge(_Loader(), session, "分析方法", ["value"], context_parts)

    assert event is not None
    assert event["query"] == "分析方法"
    assert event["mode"] == "keyword"
    assert event["results"][0]["source"] == "legacy"
    assert event["results"][0]["source_id"].startswith("source:")
    assert event["results"][0]["acquisition_method"] == "unknown"
    assert "回退知识" in context_parts[0]


def test_build_analysis_memory_context_formats_each_memory() -> None:
    """分析记忆上下文应按数据集分块渲染（条目较少时使用完整模式）。"""

    class _Memory:
        def __init__(self, dataset_name: str, prompt: str):
            self.dataset_name = dataset_name
            self._prompt = prompt
            # 条目数 ≤ 8 时应使用完整模式
            self.statistics: list = []
            self.findings: list = []

        def get_context_prompt(self) -> str:
            return self._prompt

    context = build_analysis_memory_context(
        "session-1",
        list_memories=lambda session_id: [_Memory("demo.csv", "使用过稳健统计")],
    )

    assert "### 数据集: demo.csv" in context
    assert "使用过稳健统计" in context


def test_build_analysis_memory_context_uses_summary_mode_when_many_entries() -> None:
    """当总条目数 > 8 时，应切换为摘要模式并引导调用 analysis_memory 工具。"""

    class _Stat:
        pass

    class _Memory:
        def __init__(self, dataset_name: str):
            self.dataset_name = dataset_name
            self.statistics = [_Stat()] * 5
            self.findings = [_Stat()] * 5
            self.decisions: list = []

        def get_context_prompt(self) -> str:
            return "不应出现在摘要模式中"

    context = build_analysis_memory_context(
        "session-1",
        list_memories=lambda session_id: [_Memory("demo.csv")],
    )

    assert "analysis_memory" in context
    assert "不应出现在摘要模式中" not in context
    assert "demo.csv" in context


def test_build_research_profile_context_uses_default_profile_id() -> None:
    """研究画像上下文应使用默认 profile id 并渲染偏好提示。"""

    class _Profile:
        domain = "biology"

    class _ProfileManager:
        def __init__(self):
            self.seen_profile_ids: list[str] = []

        def get_or_create_sync(self, profile_id: str):
            self.seen_profile_ids.append(profile_id)
            return _Profile()

        def get_research_profile_prompt(self, profile: _Profile) -> str:
            return "偏好先做稳健统计。"

    manager = _ProfileManager()
    session = Session()
    session.research_profile_id = ""

    context = build_research_profile_context(
        session,
        default_profile_id="default-profile",
        get_profile_manager=lambda: manager,
    )

    assert manager.seen_profile_ids == ["default-profile"]
    assert "偏好先做稳健统计。" in context
