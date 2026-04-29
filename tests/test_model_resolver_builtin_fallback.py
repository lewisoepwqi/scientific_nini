"""BUILTIN 候选链追加激活 provider 的测试。"""

from __future__ import annotations

from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest

from nini.agent.model_resolver import BUILTIN_MODE_TITLE, ModelResolver
from nini.agent.providers import BaseLLMClient, LLMChunk
from nini.config_manager import BUILTIN_PROVIDER_ID


class FakeClient(BaseLLMClient):
    """测试用伪客户端。"""

    def __init__(
        self,
        *,
        provider_id: str,
        model: str,
        available: bool = True,
        chunks: list[LLMChunk] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.provider_id = provider_id
        self.provider_name = provider_id
        self._model = model
        self._available = available
        self._chunks = chunks or []
        self._error = error

    def is_available(self) -> bool:
        return self._available

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        reasoning_effort: str | None = None,
    ) -> AsyncGenerator[LLMChunk, None]:
        if self._error is not None:
            raise self._error
        for chunk in self._chunks:
            yield chunk


@pytest.mark.asyncio
async def test_resolve_client_plan_appends_active_client_after_builtin() -> None:
    """BUILTIN 路由命中时，应在候选链后追加激活 provider。"""
    active_client = FakeClient(provider_id="dashscope", model="qwen-plus")
    builtin_client = FakeClient(provider_id=BUILTIN_PROVIDER_ID, model="builtin-title")
    resolver = ModelResolver(clients=[active_client])
    resolver._active_provider_id = "dashscope"  # noqa: SLF001
    resolver.set_purpose_route(  # noqa: SLF001
        "title_generation",
        provider_id=BUILTIN_PROVIDER_ID,
        model=BUILTIN_MODE_TITLE,
    )

    with (
        patch.object(resolver, "_get_builtin_client", return_value=builtin_client),
        patch.object(
            resolver,
            "_get_user_configured_provider_ids",
            AsyncMock(return_value=["dashscope"]),
        ),
    ):
        plan = await resolver._resolve_client_plan("title_generation")  # noqa: SLF001

    assert [client.provider_id for client in plan.clients] == [BUILTIN_PROVIDER_ID, "dashscope"]
    assert plan.builtin_mode_to_count is None


@pytest.mark.asyncio
async def test_resolve_client_plan_keeps_single_builtin_when_no_active_client() -> None:
    """无激活 provider 时，BUILTIN 候选链应保持单元素。"""
    builtin_client = FakeClient(provider_id=BUILTIN_PROVIDER_ID, model="builtin-title")
    resolver = ModelResolver(clients=[])
    resolver.set_purpose_route(
        "title_generation",
        provider_id=BUILTIN_PROVIDER_ID,
        model=BUILTIN_MODE_TITLE,
    )

    with patch.object(resolver, "_get_builtin_client", return_value=builtin_client):
        plan = await resolver._resolve_client_plan("title_generation")  # noqa: SLF001

    assert [client.provider_id for client in plan.clients] == [BUILTIN_PROVIDER_ID]
    assert plan.builtin_mode_to_count is None


@pytest.mark.asyncio
async def test_resolve_client_plan_does_not_duplicate_same_active_client() -> None:
    """若激活 client 与 BUILTIN client 为同一对象，不应重复追加。"""
    builtin_client = FakeClient(provider_id=BUILTIN_PROVIDER_ID, model="builtin-title")
    resolver = ModelResolver(clients=[])
    resolver._active_provider_id = BUILTIN_PROVIDER_ID  # noqa: SLF001
    resolver.set_purpose_route(
        "title_generation",
        provider_id=BUILTIN_PROVIDER_ID,
        model=BUILTIN_MODE_TITLE,
    )

    with (
        patch.object(resolver, "_get_builtin_client", return_value=builtin_client),
        patch.object(resolver, "_get_single_active_client", return_value=builtin_client),
        patch.object(
            resolver,
            "_get_user_configured_provider_ids",
            AsyncMock(return_value=[BUILTIN_PROVIDER_ID]),
        ),
    ):
        plan = await resolver._resolve_client_plan("title_generation")  # noqa: SLF001

    assert plan.clients == [builtin_client]
