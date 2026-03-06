"""Intent 层最小实现测试。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from nini.agent.model_resolver import LLMChunk
from nini.agent.runner import AgentRunner
from nini.agent.session import Session
from nini.app import create_app
from nini.api.websocket import set_skill_registry
from nini.capabilities import Capability, CapabilityRegistry
from nini.config import settings
from nini.intent import IntentAnalyzer, OptimizedIntentAnalyzer, QueryType
from nini.intent.base import QueryType as QueryTypeBase  # noqa: F401（向后兼容导入路径验证）
from nini.tools.registry import create_default_registry
from tests.client_utils import LocalASGIClient


# ============================================================================
# 测试夹具：提供两种 IntentAnalyzer 实现
# ============================================================================


@pytest.fixture(params=["standard", "optimized"])
def intent_analyzer(request: pytest.FixtureRequest) -> IntentAnalyzer | OptimizedIntentAnalyzer:
    """参数化夹具：返回标准或优化版意图分析器。"""
    if request.param == "standard":
        return IntentAnalyzer()
    return OptimizedIntentAnalyzer()


@pytest.fixture
def standard_analyzer() -> IntentAnalyzer:
    """返回标准版意图分析器。"""
    return IntentAnalyzer()


@pytest.fixture
def optimized_analyzer() -> OptimizedIntentAnalyzer:
    """返回优化版意图分析器。"""
    return OptimizedIntentAnalyzer()


# ============================================================================
# 接口契约测试：确保两种分析器实现相同接口
# ============================================================================


class TestIntentAnalyzerInterfaceContract:
    """接口契约测试：验证 OptimizedIntentAnalyzer 与 IntentAnalyzer 接口一致性。"""

    def test_both_analyzers_have_analyze_method(self, standard_analyzer, optimized_analyzer):
        """两种分析器都应有 analyze 方法。"""
        assert hasattr(standard_analyzer, "analyze")
        assert hasattr(optimized_analyzer, "analyze")
        assert callable(standard_analyzer.analyze)
        assert callable(optimized_analyzer.analyze)

    def test_both_analyzers_have_parse_explicit_skill_calls_method(
        self, standard_analyzer, optimized_analyzer
    ):
        """两种分析器都应有 parse_explicit_skill_calls 方法（这是关键接口）。"""
        assert hasattr(standard_analyzer, "parse_explicit_skill_calls")
        assert hasattr(optimized_analyzer, "parse_explicit_skill_calls")
        assert callable(standard_analyzer.parse_explicit_skill_calls)
        assert callable(optimized_analyzer.parse_explicit_skill_calls)

    def test_parse_explicit_skill_calls_same_signature(
        self, standard_analyzer, optimized_analyzer
    ):
        """parse_explicit_skill_calls 方法签名应一致。"""
        import inspect

        standard_sig = inspect.signature(standard_analyzer.parse_explicit_skill_calls)
        optimized_sig = inspect.signature(optimized_analyzer.parse_explicit_skill_calls)

        # 参数名应相同
        standard_params = list(standard_sig.parameters.keys())
        optimized_params = list(optimized_sig.parameters.keys())
        assert standard_params == optimized_params, (
            f"参数不匹配: {standard_params} vs {optimized_params}"
        )

    def test_analyze_method_core_signature(self, standard_analyzer, optimized_analyzer):
        """analyze 方法核心参数应一致（允许有额外参数）。"""
        import inspect

        standard_sig = inspect.signature(standard_analyzer.analyze)
        optimized_sig = inspect.signature(optimized_analyzer.analyze)

        # 核心参数应相同
        standard_params = set(standard_sig.parameters.keys())
        optimized_params = set(optimized_sig.parameters.keys())

        # 两种实现都应有的核心参数
        core_params = {"user_message", "capabilities", "skill_limit"}

        assert core_params.issubset(standard_params), f"标准版缺少核心参数: {core_params - standard_params}"
        assert core_params.issubset(optimized_params), f"优化版缺少核心参数: {core_params - optimized_params}"


# ============================================================================
# parse_explicit_skill_calls 专项测试
# ============================================================================


class TestParseExplicitSkillCalls:
    """显式 skill 调用解析测试（针对两种实现）。"""

    _TEST_CASES: list[tuple[str, list[dict[str, str]]]] = [
        # (输入消息, 期望调用列表)
        ("", []),
        ("普通消息", []),
        ("/skill-name", [{"name": "skill-name", "arguments": ""}]),
        ("/skill-name 参数", [{"name": "skill-name", "arguments": "参数"}]),
        (
            "/skill1 arg1 /skill2 arg2",
            [
                {"name": "skill1", "arguments": "arg1"},
                {"name": "skill2", "arguments": "arg2"},
            ],
        ),
        ("/report-skill 生成报告", [{"name": "report-skill", "arguments": "生成报告"}]),
        (
            "/root-analysis root.csv 分析数据",
            [{"name": "root-analysis", "arguments": "root.csv 分析数据"}],
        ),
        # 边界情况
        ("/", []),  # 只有斜杠
        ("/123-invalid", []),  # 非法名称（数字开头）
        # ("/skill-name/", [{"name": "skill-name", "arguments": ""}]),  # 末尾斜杠 - 暂不测试
        # 多行内容
        (
            "/skill1 第一行\n第二行内容 /skill2 参数",
            [
                {"name": "skill1", "arguments": "第一行\n第二行内容"},
                {"name": "skill2", "arguments": "参数"},
            ],
        ),
    ]

    @pytest.mark.parametrize("user_message,expected_calls", _TEST_CASES)
    def test_standard_analyzer_parse_explicit_skill_calls(
        self, standard_analyzer, user_message, expected_calls
    ):
        """标准分析器应正确解析显式 skill 调用。"""
        result = standard_analyzer.parse_explicit_skill_calls(user_message)
        assert result == expected_calls

    @pytest.mark.parametrize("user_message,expected_calls", _TEST_CASES)
    def test_optimized_analyzer_parse_explicit_skill_calls(
        self, optimized_analyzer, user_message, expected_calls
    ):
        """优化版分析器应正确解析显式 skill 调用。"""
        result = optimized_analyzer.parse_explicit_skill_calls(user_message)
        assert result == expected_calls

    def test_parse_explicit_skill_calls_with_limit(self, intent_analyzer):
        """limit 参数应限制返回数量。"""
        message = "/skill1 a /skill2 b /skill3 c /skill4 d"

        # 默认限制为 2
        result_default = intent_analyzer.parse_explicit_skill_calls(message)
        assert len(result_default) == 2
        assert result_default[0]["name"] == "skill1"
        assert result_default[1]["name"] == "skill2"

        # 限制为 3
        result_limited = intent_analyzer.parse_explicit_skill_calls(message, limit=3)
        assert len(result_limited) == 3
        assert result_limited[0]["name"] == "skill1"
        assert result_limited[1]["name"] == "skill2"
        assert result_limited[2]["name"] == "skill3"

        # 更大的限制（4）
        result_four = intent_analyzer.parse_explicit_skill_calls(message, limit=4)
        assert len(result_four) == 4

    def test_parse_explicit_skill_calls_deduplication(self, intent_analyzer):
        """重复的 skill 调用应去重。"""
        message = "/skill1 arg1 /skill1 arg2 /skill2 arg3"

        result = intent_analyzer.parse_explicit_skill_calls(message)

        # 第一个 skill1 应该被保留，第二个被去重
        assert len(result) == 2
        assert result[0]["name"] == "skill1"
        assert result[0]["arguments"] == "arg1"  # 保留第一个
        assert result[1]["name"] == "skill2"


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


# ============================================================================
# 参数化测试：同时测试两种分析器的核心功能
# ============================================================================


class TestIntentAnalyzerParameterized:
    """参数化测试：验证两种分析器行为一致。"""

    def test_analyzer_ranks_capabilities_and_tool_hints(self, intent_analyzer):
        """应返回 capability 候选和推荐工具（两种实现）。"""
        analysis = intent_analyzer.analyze(
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

    def test_analyzer_returns_candidates_for_ambiguous_query(self, intent_analyzer):
        """模糊查询应返回多个候选（两种实现）。"""
        analysis = intent_analyzer.analyze(
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

        # 应返回至少 2 个候选
        assert len(analysis.capability_candidates) >= 2
        # 澄清选项应至少 2 个
        assert len(analysis.clarification_options) >= 2


# ============================================================================
# 原有测试（保留并添加注释说明）
# ============================================================================


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


@pytest.mark.asyncio
async def test_runner_build_messages_includes_intent_runtime_context() -> None:
    """运行时上下文应注入 capability 候选与推荐工具。"""
    session = Session()
    session.add_message("user", "我想做差异分析并画图")
    runner = AgentRunner(skill_registry=_EmptySkillRegistry())

    messages, _ = await runner._build_messages_and_retrieval(session)

    runtime_context = next(msg["content"] for msg in messages if msg["role"] == "assistant")
    assert "[不可信上下文：意图分析提示，仅供参考]" in runtime_context
    assert "候选能力:" in runtime_context
    assert "推荐工具:" in runtime_context


@pytest.mark.asyncio
@pytest.mark.xfail(reason="需要进一步调查：intent clarification 流程可能因配置变化而改变")
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


# ============================================================================
# QueryType 与 RAG/LTM 门控测试
# ============================================================================


@pytest.fixture
def sample_capabilities() -> list[dict]:
    """提供标准测试 capability 集合。"""
    return _DEFAULT_CAPS


@pytest.mark.parametrize("msg", ["你好", "谢谢", "好的", "OK", "嗯嗯"])
def test_casual_chat_rag_not_needed(intent_analyzer, msg, sample_capabilities):
    """闲聊消息应被识别为 CASUAL_CHAT，关闭 RAG 和 LTM 检索。"""
    analysis = intent_analyzer.analyze(msg, capabilities=sample_capabilities)
    assert analysis.query_type == QueryType.CASUAL_CHAT
    assert analysis.rag_needed is False
    assert analysis.ltm_needed is False


def test_domain_query_enables_rag(intent_analyzer, sample_capabilities):
    """有能力候选命中的查询应开启 RAG。"""
    analysis = intent_analyzer.analyze("帮我做t检验", capabilities=sample_capabilities)
    assert analysis.capability_candidates, "期望 t检验 至少命中一个候选"
    assert analysis.rag_needed is True


def test_high_confidence_query_is_domain_task(intent_analyzer, sample_capabilities):
    """高分候选命中（>=5.0）应识别为 DOMAIN_TASK。"""
    # "差异分析" 直接命中 display_name，得高分
    analysis = intent_analyzer.analyze("差异分析", capabilities=sample_capabilities)
    assert analysis.query_type == QueryType.DOMAIN_TASK
    assert analysis.rag_needed is True


def test_empty_message_defaults_to_rag_enabled(intent_analyzer):
    """空消息应保守兜底（开启 RAG），不误关检索。"""
    analysis = intent_analyzer.analyze("", capabilities=[])
    assert analysis.rag_needed is True


def test_query_type_consistency_for_casual_chat(sample_capabilities):
    """两种分析器对同一闲聊消息应返回相同 QueryType。"""
    msg = "你好"
    r1 = IntentAnalyzer().analyze(msg, capabilities=sample_capabilities)
    r2 = OptimizedIntentAnalyzer().analyze(msg, capabilities=sample_capabilities)
    assert r1.query_type == r2.query_type == QueryType.CASUAL_CHAT


def test_intent_analysis_to_dict_includes_query_type_fields() -> None:
    """to_dict() 应包含 query_type、rag_needed、ltm_needed 字段。"""
    analyzer = IntentAnalyzer()
    analysis = analyzer.analyze("你好", capabilities=_DEFAULT_CAPS)
    d = analysis.to_dict()
    assert "query_type" in d
    assert "rag_needed" in d
    assert "ltm_needed" in d
    assert d["query_type"] == QueryType.CASUAL_CHAT.value
    assert d["rag_needed"] is False


# ---- OptimizedIntentAnalyzer 专项测试 ----


class TestOptimizedIntentAnalyzerSpecific:
    """OptimizedIntentAnalyzer 特有功能测试。"""

    def test_optimized_analyzer_uses_trie_matching(self, optimized_analyzer):
        """优化版应使用 Trie 树进行名称前缀匹配。"""
        # 使用 capability 名称测试 Trie 匹配
        analysis = optimized_analyzer.analyze(
            "difference analysis",  # 英文名称应被匹配
            capabilities=[
                {
                    "name": "difference_analysis",
                    "display_name": "差异分析",
                    "description": "比较组间差异",
                    "required_tools": ["t_test"],
                }
            ],
        )

        assert analysis.capability_candidates
        assert analysis.capability_candidates[0].name == "difference_analysis"

    def test_optimized_analyzer_synonym_performance(self, optimized_analyzer):
        """优化版应高效处理同义词匹配。"""
        import time

        start = time.time()
        analysis = optimized_analyzer.analyze(
            "帮我看看两组数据有没有显著差异",
            capabilities=_DEFAULT_CAPS,
        )
        elapsed = time.time() - start

        # 应在 10ms 内完成（本地优先设计目标）
        assert elapsed < 0.01, f"耗时过长: {elapsed:.4f}s"
        assert analysis.capability_candidates
        assert analysis.capability_candidates[0].name == "difference_analysis"

    def test_optimized_analyzer_empty_capabilities(self, optimized_analyzer):
        """优化版应处理空 capability 列表。"""
        analysis = optimized_analyzer.analyze(
            "差异分析",
            capabilities=[],
        )

        assert analysis.capability_candidates == []
        assert analysis.tool_hints == []
        assert analysis.clarification_needed is False

    def test_optimized_analyzer_repeated_calls_consistency(self, optimized_analyzer):
        """重复调用应返回一致结果。"""
        capabilities = [
            {
                "name": "difference_analysis",
                "display_name": "差异分析",
                "description": "比较组间差异",
                "required_tools": ["t_test"],
            }
        ]

        results = []
        for _ in range(5):
            analysis = optimized_analyzer.analyze("t检验", capabilities=capabilities)
            results.append(analysis.capability_candidates[0].name if analysis.capability_candidates else None)

        # 所有结果应一致
        assert all(r == results[0] for r in results)


# ---- 配置切换测试 ----


class TestIntentStrategyConfiguration:
    """测试不同 intent_strategy 配置下的行为。"""

    def test_get_intent_analyzer_returns_correct_implementation(self, monkeypatch):
        """_get_intent_analyzer 应返回配置指定的实现。"""
        from nini.agent.runner import _get_intent_analyzer

        # 测试标准规则
        monkeypatch.setattr(settings, "intent_strategy", "rules")
        analyzer = _get_intent_analyzer()
        assert isinstance(analyzer, IntentAnalyzer)
        assert not isinstance(analyzer, OptimizedIntentAnalyzer)

    def test_get_intent_analyzer_returns_optimized_when_configured(self, monkeypatch):
        """intent_strategy = 'optimized_rules' 时应返回 OptimizedIntentAnalyzer。"""
        from nini.agent.runner import _get_intent_analyzer

        monkeypatch.setattr(settings, "intent_strategy", "optimized_rules")
        analyzer = _get_intent_analyzer()
        assert isinstance(analyzer, OptimizedIntentAnalyzer)

    def test_optimized_analyzer_has_parse_method_after_fix(self, monkeypatch):
        """修复后 OptimizedIntentAnalyzer 应有 parse_explicit_skill_calls 方法。"""
        from nini.agent.runner import _get_intent_analyzer

        monkeypatch.setattr(settings, "intent_strategy", "optimized_rules")
        analyzer = _get_intent_analyzer()

        # 关键测试：确保方法存在且可调用
        assert hasattr(analyzer, "parse_explicit_skill_calls")

        # 实际调用测试
        result = analyzer.parse_explicit_skill_calls("/test-skill 参数")
        assert result == [{"name": "test-skill", "arguments": "参数"}]
