"""chat_complete optional 语义测试。"""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest

from nini.agent.model_resolver import ModelResolver
from nini.agent.providers import BaseLLMClient, LLMChunk, LLMResponse


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
async def test_chat_complete_returns_none_when_optional_and_all_clients_fail(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """optional=True 时，全链失败应返回 None 并记录警告。"""
    resolver = ModelResolver(
        clients=[
            FakeClient(provider_id="openai", model="gpt-a", error=RuntimeError("quota exceeded")),
            FakeClient(provider_id="backup", model="gpt-b", error=RuntimeError("timeout")),
        ]
    )
    resolver.set_purpose_route("chat", provider_id="openai", model="gpt-a")

    with (
        patch.object(
            resolver,
            "_get_user_configured_provider_ids",
            AsyncMock(return_value=["openai", "backup"]),
        ),
        caplog.at_level(logging.WARNING),
    ):
        result = await resolver.chat_complete(
            [{"role": "user", "content": "hi"}],
            purpose="chat",
            optional=True,
        )

    assert result is None
    assert any("optional" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_chat_complete_raises_summary_when_optional_false() -> None:
    """optional=False 时，仍应抛出带 fallback 摘要的错误。"""
    resolver = ModelResolver(
        clients=[
            FakeClient(provider_id="openai", model="gpt-a", error=RuntimeError("quota exceeded")),
            FakeClient(provider_id="backup", model="gpt-b", error=RuntimeError("timeout")),
        ]
    )
    resolver.set_purpose_route("chat", provider_id="openai", model="gpt-a")

    with (
        patch.object(
            resolver,
            "_get_user_configured_provider_ids",
            AsyncMock(return_value=["openai", "backup"]),
        ),
        pytest.raises(RuntimeError, match="openai: quota exceeded \\| backup: timeout"),
    ):
        await resolver.chat_complete(
            [{"role": "user", "content": "hi"}],
            purpose="chat",
            optional=False,
        )


@pytest.mark.asyncio
async def test_chat_complete_returns_response_without_warning_when_optional_and_success(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """optional=True 但首家成功时，应正常返回响应且不记告警。"""
    resolver = ModelResolver(
        clients=[
            FakeClient(
                provider_id="openai",
                model="gpt-a",
                chunks=[LLMChunk(text="ok", finish_reason="stop")],
            )
        ]
    )
    resolver.set_purpose_route("chat", provider_id="openai", model="gpt-a")

    with (
        patch.object(
            resolver,
            "_get_user_configured_provider_ids",
            AsyncMock(return_value=["openai"]),
        ),
        caplog.at_level(logging.WARNING),
    ):
        result = await resolver.chat_complete(
            [{"role": "user", "content": "hi"}],
            purpose="chat",
            optional=True,
        )

    assert isinstance(result, LLMResponse)
    assert result.text == "ok"
    assert not any("optional" in record.message for record in caplog.records)
