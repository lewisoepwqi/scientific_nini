"""LLM 错误分类与跨 provider 降级测试。"""

from __future__ import annotations

from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, patch

import httpx
import openai
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
    ) -> AsyncGenerator[LLMChunk, None]:
        if self._error is not None:
            raise self._error
        for chunk in self._chunks:
            yield chunk


def _make_response(status_code: int) -> httpx.Response:
    """构造带 request 的 HTTP 响应。"""
    request = httpx.Request("POST", "https://example.test/v1/chat/completions")
    return httpx.Response(status_code=status_code, request=request)


@pytest.mark.asyncio
async def test_auth_error_tries_next_provider() -> None:
    """401 认证错误应允许跨 provider 降级。"""
    resolver = ModelResolver(
        clients=[
            FakeClient(
                provider_id="openai",
                model="gpt-primary",
                error=openai.AuthenticationError(
                    "bad key",
                    response=_make_response(401),
                    body=None,
                ),
            ),
            FakeClient(
                provider_id="backup",
                model="gpt-backup",
                chunks=[LLMChunk(text="fallback-ok", finish_reason="stop")],
            ),
        ]
    )
    resolver.set_purpose_route("chat", provider_id="openai", model="gpt-primary")

    with patch.object(
        resolver,
        "_get_user_configured_provider_ids",
        AsyncMock(return_value=["openai", "backup"]),
    ):
        chunks = [
            chunk
            async for chunk in resolver.chat(
                [{"role": "user", "content": "hi"}],
                purpose="chat",
            )
        ]

    assert len(chunks) == 1
    assert chunks[0].provider_id == "backup"
    assert chunks[0].fallback_applied is True
    assert "API Key 无效" in str(chunks[0].fallback_reason)


@pytest.mark.asyncio
async def test_bad_request_does_not_try_next_provider() -> None:
    """400 请求错误仍应立即停止，避免错误扩散到下一家。"""
    resolver = ModelResolver(
        clients=[
            FakeClient(
                provider_id="openai",
                model="gpt-primary",
                error=httpx.HTTPStatusError(
                    "bad request",
                    request=httpx.Request("POST", "https://example.test"),
                    response=_make_response(400),
                ),
            ),
            FakeClient(
                provider_id="backup",
                model="gpt-backup",
                chunks=[LLMChunk(text="should-not-run", finish_reason="stop")],
            ),
        ]
    )
    resolver.set_purpose_route("chat", provider_id="openai", model="gpt-primary")

    with (
        patch.object(
            resolver,
            "_get_user_configured_provider_ids",
            AsyncMock(return_value=["openai", "backup"]),
        ),
        pytest.raises(RuntimeError, match="请求参数无效"),
    ):
        _ = [
            chunk
            async for chunk in resolver.chat(
                [{"role": "user", "content": "hi"}],
                purpose="chat",
            )
        ]


@pytest.mark.asyncio
async def test_builtin_auth_error_falls_back_to_active_client() -> None:
    """BUILTIN 401 时，应继续尝试已追加的激活 provider。"""
    active_client = FakeClient(
        provider_id="dashscope",
        model="qwen-plus",
        chunks=[LLMChunk(text="title-from-active", finish_reason="stop")],
    )
    builtin_client = FakeClient(
        provider_id=BUILTIN_PROVIDER_ID,
        model="builtin-title",
        error=openai.AuthenticationError(
            "builtin key invalid",
            response=_make_response(401),
            body=None,
        ),
    )
    resolver = ModelResolver(clients=[active_client])
    resolver._active_provider_id = "dashscope"  # noqa: SLF001
    resolver.set_purpose_route(
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
        chunks = [
            chunk
            async for chunk in resolver.chat(
                [{"role": "user", "content": "请生成标题"}],
                purpose="title_generation",
            )
        ]

    assert len(chunks) == 1
    assert chunks[0].provider_id == "dashscope"
    assert chunks[0].text == "title-from-active"


@pytest.mark.asyncio
async def test_single_provider_auth_error_keeps_friendly_message() -> None:
    """单 provider 401 时，仍应保留友好错误提示。"""
    resolver = ModelResolver(
        clients=[
            FakeClient(
                provider_id="openai",
                model="gpt-primary",
                error=openai.AuthenticationError(
                    "bad key",
                    response=_make_response(401),
                    body=None,
                ),
            )
        ]
    )
    resolver.set_purpose_route("chat", provider_id="openai", model="gpt-primary")

    with (
        patch.object(
            resolver,
            "_get_user_configured_provider_ids",
            AsyncMock(return_value=["openai"]),
        ),
        pytest.raises(RuntimeError, match="API Key 无效或已过期，请检查配置"),
    ):
        _ = [
            chunk
            async for chunk in resolver.chat(
                [{"role": "user", "content": "hi"}],
                purpose="chat",
            )
        ]
