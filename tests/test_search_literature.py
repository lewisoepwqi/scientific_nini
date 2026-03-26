"""search_literature 工具测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from nini.agent.session import Session
from nini.plugins.base import DegradationInfo
from nini.tools.search_literature import SearchLiteratureTool


class _StubPluginRegistry:
    def __init__(self, plugin: object) -> None:
        self._plugin = plugin

    def get(self, name: str) -> object | None:
        if name == "network":
            return self._plugin
        return None


class _StubNetworkPlugin:
    def __init__(self, *, available: bool, client: object | None = None) -> None:
        self._available = available
        self._client = client

    async def is_available(self) -> bool:
        return self._available

    def get_degradation_info(self) -> DegradationInfo:
        return DegradationInfo(
            plugin_name="network",
            reason="测试离线",
            impact="无法进行在线文献检索",
            alternatives=["上传 PDF", "提供参考文献列表"],
        )


def _make_response(payload: dict, *, status_code: int = 200) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


@pytest.mark.asyncio
async def test_search_literature_returns_semantic_scholar_results() -> None:
    client = AsyncMock()
    client.get = AsyncMock(
        return_value=_make_response(
            {
                "data": [
                    {
                        "title": "CRISPR discovery pipeline",
                        "authors": [{"name": "Alice Smith"}, {"name": "Bob Lee"}],
                        "year": 2024,
                        "abstract": "A concise abstract.",
                        "citationCount": 42,
                        "externalIds": {"DOI": "10.1000/crispr.1"},
                    }
                ]
            }
        )
    )
    tool = SearchLiteratureTool(
        plugin_registry=_StubPluginRegistry(
            _StubNetworkPlugin(available=True, client=client),
        )
    )

    result = await tool.execute(Session(), query="CRISPR", max_results=10)

    assert result.success is True
    assert result.data["source"] == "semantic_scholar"
    assert result.data["papers"][0]["title"] == "CRISPR discovery pipeline"
    assert result.data["papers"][0]["authors"] == ["Alice Smith", "Bob Lee"]
    assert result.data["papers"][0]["doi"] == "10.1000/crispr.1"


@pytest.mark.asyncio
async def test_search_literature_falls_back_to_crossref() -> None:
    client = AsyncMock()
    client.get = AsyncMock(
        side_effect=[
            RuntimeError("semantic scholar unavailable"),
            _make_response(
                {
                    "message": {
                        "items": [
                            {
                                "title": ["Machine learning for protein design"],
                                "author": [{"given": "Carol", "family": "Ng"}],
                                "DOI": "10.1000/ml.2",
                                "is-referenced-by-count": 7,
                                "published-print": {"date-parts": [[2023, 5, 1]]},
                            }
                        ]
                    }
                }
            ),
        ]
    )
    tool = SearchLiteratureTool(
        plugin_registry=_StubPluginRegistry(
            _StubNetworkPlugin(available=True, client=client),
        )
    )

    result = await tool.execute(Session(), query="protein design", max_results=5)

    assert result.success is True
    assert result.data["source"] == "crossref"
    assert result.metadata["fallback_from"] == "semantic_scholar"
    assert result.data["papers"][0]["title"] == "Machine learning for protein design"


@pytest.mark.asyncio
async def test_search_literature_enforces_semantic_scholar_rate_limit() -> None:
    client = AsyncMock()
    client.get = AsyncMock(
        return_value=_make_response(
            {
                "data": [
                    {
                        "title": "A paper",
                        "authors": [{"name": "Tester"}],
                        "year": 2024,
                    }
                ]
            }
        )
    )
    tool = SearchLiteratureTool(
        plugin_registry=_StubPluginRegistry(
            _StubNetworkPlugin(available=True, client=client),
        )
    )
    tool._sleep = AsyncMock()  # type: ignore[method-assign]
    timestamps = iter([10.0, 10.0, 11.0])
    tool._monotonic = lambda: next(timestamps)  # type: ignore[method-assign]

    first = await tool.execute(Session(), query="first query")
    second = await tool.execute(Session(), query="second query")

    assert first.success is True
    assert second.success is True
    tool._sleep.assert_awaited_once_with(1.0)


@pytest.mark.asyncio
async def test_search_literature_returns_offline_degradation_without_http_call() -> None:
    client = AsyncMock()
    client.get = AsyncMock(side_effect=AssertionError("离线时不应发起 HTTP 请求"))
    tool = SearchLiteratureTool(
        plugin_registry=_StubPluginRegistry(
            _StubNetworkPlugin(available=False, client=client),
        )
    )

    result = await tool.execute(Session(), query="offline mode")

    assert result.success is False
    assert "离线模式" in result.message
    assert result.data["manual_mode"] is True
    client.get.assert_not_awaited()
