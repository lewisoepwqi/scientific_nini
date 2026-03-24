"""测试 SearchToolsTool 的各种查询场景及工具可见性分层。"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from nini.tools.base import Tool, ToolResult
from nini.tools.search_tools import SearchToolsTool

# ── 测试用 Fixture ──────────────────────────────────────────────────────────


class _FakeTool(Tool):
    """用于测试的最简工具存根。"""

    def __init__(self, name: str, description: str) -> None:
        self._name = name
        self._description = description

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, session: Any, **kwargs: Any) -> ToolResult:
        return ToolResult(success=True)


def _make_registry(*tools: _FakeTool) -> Any:
    """构造一个只实现 list_tools / get 的最小 Mock 注册表。"""
    registry = MagicMock()
    tool_map = {t.name: t for t in tools}
    registry.list_tools.return_value = list(tool_map.keys())
    registry.get.side_effect = lambda name: tool_map.get(name)
    return registry


@pytest.fixture
def sample_registry():
    """包含 3 个测试工具的 Mock 注册表。"""
    return _make_registry(
        _FakeTool("t_test", "执行独立样本 t 检验，比较两组均值差异"),
        _FakeTool("anova", "执行单因素方差分析（ANOVA）"),
        _FakeTool("stat_test", "统一执行 t 检验、Mann-Whitney、ANOVA 等多种检验"),
    )


# ── Task 4.2：select 精确查询 ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_select_single_tool_found(sample_registry):
    """select:name 应返回对应工具的完整 schema。"""
    tool = SearchToolsTool(registry=sample_registry)
    result = await tool.execute(session=None, query="select:t_test")

    assert result.success is True
    assert result.data is not None
    tools = result.data["tools"]
    assert len(tools) == 1
    assert tools[0]["found"] is True
    assert tools[0]["name"] == "t_test"
    # 返回完整 schema，足以直接调用
    schema = tools[0]["schema"]
    assert schema["function"]["name"] == "t_test"
    assert "description" in schema["function"]
    assert "parameters" in schema["function"]


@pytest.mark.asyncio
async def test_select_multiple_tools_found(sample_registry):
    """select:name1,name2 应同时返回两个工具的 schema。"""
    tool = SearchToolsTool(registry=sample_registry)
    result = await tool.execute(session=None, query="select:t_test,anova")

    assert result.success is True
    tools = result.data["tools"]
    assert len(tools) == 2
    assert all(t["found"] for t in tools)
    names = {t["name"] for t in tools}
    assert names == {"t_test", "anova"}


# ── Task 4.2 边界：不存在工具名标注"未找到" ──────────────────────────────────


@pytest.mark.asyncio
async def test_select_nonexistent_tool_not_error(sample_registry):
    """select 不存在的工具名时，应返回 success=True 并标注未找到，不报错。"""
    tool = SearchToolsTool(registry=sample_registry)
    result = await tool.execute(session=None, query="select:nonexistent_tool")

    assert result.success is True
    tools = result.data["tools"]
    assert len(tools) == 1
    assert tools[0]["found"] is False
    assert "nonexistent_tool" in tools[0]["message"]


@pytest.mark.asyncio
async def test_select_mixed_found_and_not_found(sample_registry):
    """select 混合存在/不存在的工具名时，应分别标注各自状态。"""
    tool = SearchToolsTool(registry=sample_registry)
    result = await tool.execute(session=None, query="select:t_test,ghost_tool")

    assert result.success is True
    by_name = {t["name"]: t for t in result.data["tools"]}
    assert by_name["t_test"]["found"] is True
    assert by_name["ghost_tool"]["found"] is False


# ── Task 4.3：关键词搜索 ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_keyword_search_matches_name(sample_registry):
    """关键词匹配工具名称时应返回结果。"""
    tool = SearchToolsTool(registry=sample_registry)
    result = await tool.execute(session=None, query="anova")

    assert result.success is True
    names = [t["name"] for t in result.data["tools"]]
    assert "anova" in names


@pytest.mark.asyncio
async def test_keyword_search_matches_description(sample_registry):
    """关键词匹配工具 description 时应返回结果。"""
    tool = SearchToolsTool(registry=sample_registry)
    # "方差分析" 只在 anova 的 description 中
    result = await tool.execute(session=None, query="方差分析")

    assert result.success is True
    names = [t["name"] for t in result.data["tools"]]
    assert "anova" in names


@pytest.mark.asyncio
async def test_keyword_search_case_insensitive(sample_registry):
    """关键词搜索应大小写不敏感。"""
    tool = SearchToolsTool(registry=sample_registry)
    result_lower = await tool.execute(session=None, query="t_test")
    result_upper = await tool.execute(session=None, query="T_TEST")

    assert result_lower.success is True
    assert result_upper.success is True
    assert [t["name"] for t in result_lower.data["tools"]] == [
        t["name"] for t in result_upper.data["tools"]
    ]


@pytest.mark.asyncio
async def test_keyword_search_result_contains_schema(sample_registry):
    """关键词搜索结果中每条应包含 name、description 和完整 schema。"""
    tool = SearchToolsTool(registry=sample_registry)
    result = await tool.execute(session=None, query="检验")

    assert result.success is True
    for item in result.data["tools"]:
        assert "name" in item
        assert "description" in item
        assert "schema" in item
        assert "function" in item["schema"]


# ── Task 4.4：无匹配时返回空列表 ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_keyword_search_no_match(sample_registry):
    """关键词无匹配时，tools 应为空列表，success 仍为 True。"""
    tool = SearchToolsTool(registry=sample_registry)
    result = await tool.execute(session=None, query="不存在的工具描述xyz123")

    assert result.success is True
    assert result.data["tools"] == []


# ── Task 4.3 限流：最多返回 5 个 ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_keyword_search_max_5_results():
    """关键词匹配超过 5 个工具时，只返回前 5 个。"""
    # 创建 8 个名称都含"test"的工具
    registry = _make_registry(
        *[_FakeTool(f"test_tool_{i}", f"这是第 {i} 个测试工具") for i in range(8)]
    )
    tool = SearchToolsTool(registry=registry)
    result = await tool.execute(session=None, query="test")

    assert result.success is True
    assert len(result.data["tools"]) == 5


# ── Tasks 4.5 + 4.6：与真实注册表的集成测试 ──────────────────────────────────


def test_llm_visible_tools_reduced():
    """get_tool_definitions() 返回的工具中不应包含已隐藏的低频工具。"""
    from nini.tools.registry import create_default_tool_registry

    registry = create_default_tool_registry()
    definitions = registry.get_tool_definitions()
    visible_names = {d["function"]["name"] for d in definitions}

    # 这些工具应已被隐藏
    hidden_tools = {
        "t_test",
        "mann_whitney",
        "anova",
        "kruskal_wallis",
        "correlation_analysis",
        "regression_analysis",
        "export_chart",
        "export_document",
        "export_report",
        "analysis_memory",
        "search_memory_archive",
        "update_profile_notes",
        "fetch_url",
    }
    for name in hidden_tools:
        assert name not in visible_names, f"工具 '{name}' 应已隐藏，但仍出现在 LLM 工具列表中"


def test_hidden_tools_discoverable_via_search():
    """隐藏工具应仍可通过 search_tools 发现。"""
    from nini.tools.registry import create_default_tool_registry

    registry = create_default_tool_registry()
    search = registry.get("search_tools")
    assert search is not None, "search_tools 必须已注册"

    # 通过 _registry 引用直接调用内部方法验证隐藏工具可被发现
    # （等同于 LLM 调用 search_tools(query="select:t_test")）
    result = search._select_by_names("t_test")
    assert result.success is True
    tools = result.data["tools"]
    assert len(tools) == 1
    assert tools[0]["found"] is True
    assert tools[0]["schema"]["function"]["name"] == "t_test"


def test_search_tools_visible_to_llm():
    """search_tools 自身必须出现在 LLM 工具列表中。"""
    from nini.tools.registry import create_default_tool_registry

    registry = create_default_tool_registry()
    definitions = registry.get_tool_definitions()
    visible_names = {d["function"]["name"] for d in definitions}
    assert "search_tools" in visible_names
