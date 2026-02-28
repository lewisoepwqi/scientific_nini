"""Intent 层最小实现测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from nini.agent.model_resolver import LLMChunk
from nini.agent.runner import AgentRunner
from nini.agent.session import Session
from nini.app import create_app
from nini.api.websocket import set_skill_registry
from nini.capabilities import Capability, CapabilityRegistry
from nini.config import settings
from nini.intent import IntentAnalyzer
from nini.tools.registry import create_default_registry
from tests.client_utils import LocalASGIClient


class _EmptySkillRegistry:
    def get_tool_definitions(self) -> list[dict]:
        return []

    def list_markdown_skills(self) -> list[dict]:
        return []

    def get_semantic_catalog(self, skill_type: str | None = None) -> list[dict]:
        return []


class _StaticTextResolver:
    def __init__(self) -> None:
        self.last_messages = None

    async def chat(self, messages, tools=None, purpose=None):  # noqa: ANN001
        self.last_messages = messages
        yield LLMChunk(text="已继续执行。")


def test_intent_analyzer_ranks_capabilities_and_tool_hints() -> None:
    """应返回 capability 候选和推荐工具。"""
    analyzer = IntentAnalyzer()
    analysis = analyzer.analyze(
        "我想做差异分析并画图",
        capabilities=[
            {
                "name": "difference_analysis",
                "display_name": "差异分析",
                "description": "比较两组或多组数据差异并生成图表",
                "required_tools": ["t_test", "create_chart"],
            },
            {
                "name": "report_generation",
                "display_name": "报告生成",
                "description": "生成分析报告",
                "required_tools": ["generate_report"],
            },
        ],
    )

    assert analysis.capability_candidates
    assert analysis.capability_candidates[0].name == "difference_analysis"
    assert "t_test" in analysis.tool_hints
    assert analysis.clarification_needed is False


def test_intent_analyzer_requests_clarification_for_ambiguous_query() -> None:
    """多个能力分数接近时应要求澄清。"""
    analyzer = IntentAnalyzer()
    analysis = analyzer.analyze(
        "帮我比较差异和相关性",
        capabilities=[
            {
                "name": "difference_analysis",
                "display_name": "差异分析",
                "description": "分析组间差异",
                "required_tools": ["t_test"],
            },
            {
                "name": "correlation_analysis",
                "display_name": "相关性分析",
                "description": "分析变量关系",
                "required_tools": ["correlation"],
            },
        ],
    )

    assert analysis.clarification_needed is True
    assert analysis.clarification_question
    assert len(analysis.clarification_options) >= 2


def test_intent_analyzer_matches_semantic_skills() -> None:
    """应基于语义目录匹配 Markdown skill。"""
    analyzer = IntentAnalyzer()
    matches = analyzer.rank_semantic_skills(
        "请帮我做根长分析",
        [
            {
                "name": "root-analysis",
                "enabled": True,
                "disable_model_invocation": False,
                "aliases": ["根长分析"],
                "tags": ["anova"],
            },
            {
                "name": "blocked-skill",
                "enabled": True,
                "disable_model_invocation": True,
                "aliases": ["根长分析"],
            },
        ],
        limit=2,
    )

    assert len(matches) == 1
    assert matches[0].name == "root-analysis"


def test_intent_analyzer_selects_explicit_skills_before_auto_match() -> None:
    """显式 `/skill` 应覆盖自动匹配。"""
    analyzer = IntentAnalyzer()
    selected = analyzer.select_active_skills(
        "/report-skill 并且顺带提一下根长分析",
        [
            {
                "name": "report-skill",
                "enabled": True,
                "user_invocable": True,
                "aliases": ["报告润色"],
            },
            {
                "name": "root-analysis",
                "enabled": True,
                "aliases": ["根长分析"],
            },
        ],
        explicit_limit=2,
        auto_limit=1,
    )

    assert [item["name"] for item in selected] == ["report-skill"]


def test_intent_analyzer_skips_non_invocable_explicit_skill() -> None:
    """显式 skill 若 user_invocable=false 应被跳过。"""
    analyzer = IntentAnalyzer()
    selected = analyzer.select_active_skills(
        "/internal-skill",
        [
            {
                "name": "internal-skill",
                "enabled": True,
                "metadata": {"user_invocable": False},
            }
        ],
    )

    assert selected == []


def test_intent_analyzer_collects_allowed_tools_from_selected_skills() -> None:
    """应能汇总多个 skill 的 allowed_tools。"""
    analyzer = IntentAnalyzer()
    allowed, sources = analyzer.collect_allowed_tools(
        [
            {
                "name": "skill-a",
                "metadata": {"allowed_tools": ["run_code", "create_chart"]},
            },
            {
                "name": "skill-b",
                "allowed_tools": ["create_chart", "export_report"],
            },
        ]
    )

    assert allowed == {"run_code", "create_chart", "export_report"}
    assert sources == ["skill-a", "skill-b"]


@pytest.fixture
def intent_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """创建 intent API 测试客户端。"""
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "root-analysis"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: root-analysis\n"
        "description: 根长分析工作流\n"
        "category: statistics\n"
        "aliases: [根长分析]\n"
        "tags: [anova, root-length]\n"
        "---\n\n"
        "## 步骤\n"
        "1. 比较不同处理的根长差异\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(settings, "skills_dir_path", skills_dir)
    app = create_app()
    set_skill_registry(create_default_registry())
    with LocalASGIClient(app) as client:
        yield client


def test_capability_registry_analyze_intent_returns_structured_result() -> None:
    """CapabilityRegistry 应返回结构化意图分析。"""
    registry = CapabilityRegistry()
    registry.register(
        Capability(
            name="difference_analysis",
            display_name="差异分析",
            description="比较组间差异",
            required_tools=["t_test", "create_chart"],
        )
    )

    analysis = registry.analyze_intent("差异分析")

    assert analysis.capability_candidates
    assert analysis.capability_candidates[0].name == "difference_analysis"
    assert "t_test" in analysis.tool_hints


def test_capabilities_suggest_api_exposes_intent_metadata(intent_client: LocalASGIClient) -> None:
    """能力推荐 API 应返回意图层附加信息。"""
    resp = intent_client.post("/api/capabilities/suggest", params={"user_message": "差异分析"})
    assert resp.status_code == 200

    payload = resp.json()["data"]
    assert payload["suggestions"]
    assert "tool_hints" in payload
    assert "clarification_needed" in payload
    assert payload["analysis_method"] == "rule_based_v2"


def test_intent_analyze_api_returns_capabilities_and_skills(intent_client: LocalASGIClient) -> None:
    """Intent API 应同时返回 capability 与 skill 候选。"""
    resp = intent_client.post(
        "/api/intent/analyze",
        params={"user_message": "/root-analysis root.csv 我想做差异分析，并参考根长分析 workflow"},
    )
    assert resp.status_code == 200

    payload = resp.json()["data"]
    assert payload["capability_candidates"]
    assert payload["skill_candidates"]
    assert payload["skill_candidates"][0]["name"] == "root-analysis"
    assert payload["explicit_skill_calls"] == [
        {"name": "root-analysis", "arguments": "root.csv 我想做差异分析，并参考根长分析 workflow"}
    ]
    assert payload["active_skills"]
    assert payload["active_skills"][0]["name"] == "root-analysis"
    assert "allowed_tools" in payload
    assert "allowed_tool_sources" in payload
    assert "clarification_options" in payload


def test_runner_build_messages_includes_intent_runtime_context() -> None:
    """运行时上下文应注入 capability 候选与推荐工具。"""
    session = Session()
    session.add_message("user", "我想做差异分析并画图")
    runner = AgentRunner(skill_registry=_EmptySkillRegistry())

    messages, _ = runner._build_messages_and_retrieval(session)

    runtime_context = next(msg["content"] for msg in messages if msg["role"] == "assistant")
    assert "[不可信上下文：意图分析提示，仅供参考]" in runtime_context
    assert "候选能力:" in runtime_context
    assert "推荐工具:" in runtime_context


@pytest.mark.asyncio
async def test_runner_requests_intent_clarification_before_llm() -> None:
    """存在歧义且通道支持时，应先触发 ask_user_question 再调用 LLM。"""
    session = Session()
    resolver = _StaticTextResolver()

    async def ask_handler(session_obj, tool_call_id, payload):  # noqa: ANN001
        assert session_obj is session
        assert tool_call_id.startswith("intent-ask-")
        assert payload["questions"][0]["question"]
        return {payload["questions"][0]["question"]: "差异分析"}

    runner = AgentRunner(
        resolver=resolver,
        skill_registry=_EmptySkillRegistry(),
        ask_user_question_handler=ask_handler,
    )

    events = []
    async for event in runner.run(session, "帮我比较差异和相关性"):
        events.append(event)

    event_types = [event.type.value for event in events]
    assert event_types[:4] == [
        "tool_call",
        "ask_user_question",
        "tool_result",
        "iteration_start",
    ]
    assert "text" in event_types
    assert "done" in event_types

    tool_messages = [msg for msg in session.messages if msg.get("role") == "tool"]
    assert tool_messages
    assert tool_messages[-1]["tool_name"] == "ask_user_question"
    assert tool_messages[-1]["intent"] == "intent_clarification"

    resolver_messages = resolver.last_messages
    assert resolver_messages is not None
    assert any(
        msg.get("role") == "assistant"
        and any(
            call.get("function", {}).get("name") == "ask_user_question"
            for call in msg.get("tool_calls", [])
        )
        for msg in resolver_messages
    )
    assert any(msg.get("role") == "tool" for msg in resolver_messages)


# ---- v2 同义词扩展测试 ----

_DEFAULT_CAPS = [
    {
        "name": "difference_analysis",
        "display_name": "差异分析",
        "description": "比较两组或多组数据差异",
        "required_tools": ["t_test", "create_chart"],
        "is_executable": True,
    },
    {
        "name": "correlation_analysis",
        "display_name": "相关性分析",
        "description": "探索变量之间的相关关系",
        "required_tools": ["correlation", "create_chart"],
        "is_executable": True,
    },
    {
        "name": "regression_analysis",
        "display_name": "回归分析",
        "description": "建立变量间的回归模型",
        "required_tools": ["regression"],
    },
    {
        "name": "data_exploration",
        "display_name": "数据探索",
        "description": "全面了解数据特征",
        "required_tools": ["data_summary", "preview_data"],
    },
]


def test_synonym_match_natural_language_correlation() -> None:
    """自然语言描述"有没有联系"应匹配到 correlation_analysis。"""
    analyzer = IntentAnalyzer()
    analysis = analyzer.analyze(
        "帮我看看这些变量之间有没有联系",
        capabilities=_DEFAULT_CAPS,
    )
    assert analysis.capability_candidates
    assert analysis.capability_candidates[0].name == "correlation_analysis"


def test_synonym_match_t_test_keyword() -> None:
    """提到 t检验 应匹配到 difference_analysis。"""
    analyzer = IntentAnalyzer()
    analysis = analyzer.analyze(
        "能不能跑一个t检验看看两组有没有显著差别",
        capabilities=_DEFAULT_CAPS,
    )
    assert analysis.capability_candidates
    assert analysis.capability_candidates[0].name == "difference_analysis"


def test_synonym_match_prediction() -> None:
    """提到"预测"应匹配到 regression_analysis。"""
    analyzer = IntentAnalyzer()
    analysis = analyzer.analyze(
        "我想建立一个预测模型",
        capabilities=_DEFAULT_CAPS,
    )
    assert analysis.capability_candidates
    assert analysis.capability_candidates[0].name == "regression_analysis"


def test_synonym_match_data_overview() -> None:
    """提到"看看数据"应匹配到 data_exploration。"""
    analyzer = IntentAnalyzer()
    analysis = analyzer.analyze(
        "先看看数据的分布情况",
        capabilities=_DEFAULT_CAPS,
    )
    assert analysis.capability_candidates
    assert analysis.capability_candidates[0].name == "data_exploration"


def test_executable_capability_bonus() -> None:
    """可执行能力在同等匹配下应获得加分。"""
    analyzer = IntentAnalyzer()
    analysis = analyzer.analyze(
        "相关性分析",
        capabilities=_DEFAULT_CAPS,
    )
    assert analysis.capability_candidates
    top = analysis.capability_candidates[0]
    assert top.name == "correlation_analysis"
    assert "可直接执行" in top.reason


def test_synonym_no_false_positive() -> None:
    """完全不相关的查询不应产生候选。"""
    analyzer = IntentAnalyzer()
    analysis = analyzer.analyze(
        "今天天气怎么样",
        capabilities=_DEFAULT_CAPS,
    )
    assert len(analysis.capability_candidates) == 0
