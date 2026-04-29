"""试用额度与模型降级策略测试。"""

from __future__ import annotations

from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest

from nini.agent.model_resolver import ModelPreflightResult, ModelResolver
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


@pytest.mark.asyncio
async def test_builtin_fast_exhausted_prompts_switch_to_deep() -> None:
    """快速额度耗尽但深度仍可用时，应提示用户手动切换。"""
    resolver = ModelResolver(clients=[])
    resolver.set_purpose_route("chat", provider_id=BUILTIN_PROVIDER_ID, model="fast")

    async def fake_is_builtin_exhausted(mode: str) -> bool:
        return mode == "fast"

    with (
        patch("nini.config_manager.is_builtin_exhausted", side_effect=fake_is_builtin_exhausted),
        patch.object(
            resolver,
            "_get_user_configured_provider_ids",
            AsyncMock(return_value=[]),
        ),
    ):
        with pytest.raises(
            RuntimeError, match="系统内置「快速」试用额度已用完，请切换到「深度」继续使用。"
        ):
            _ = [
                chunk
                async for chunk in resolver.chat(
                    [{"role": "user", "content": "hi"}], purpose="chat"
                )
            ]


@pytest.mark.asyncio
async def test_builtin_quota_all_exhausted_prompts_user_to_configure_provider() -> None:
    """系统内置全部耗尽且无自配模型时，应提示用户自行配置。"""
    resolver = ModelResolver(clients=[])
    resolver.set_purpose_route("chat", provider_id=BUILTIN_PROVIDER_ID, model="deep")

    with (
        patch("nini.config_manager.is_builtin_exhausted", AsyncMock(return_value=True)),
        patch.object(
            resolver,
            "_get_user_configured_provider_ids",
            AsyncMock(return_value=[]),
        ),
    ):
        with pytest.raises(
            RuntimeError,
            match="系统内置试用额度已全部用完，请在「AI 设置」中配置自己的模型服务商继续使用。",
        ):
            _ = [
                chunk
                async for chunk in resolver.chat(
                    [{"role": "user", "content": "hi"}], purpose="chat"
                )
            ]


@pytest.mark.asyncio
async def test_single_user_provider_does_not_auto_fallback() -> None:
    """仅配置一个用户提供商时，不应自动降级到其他客户端。"""
    primary = FakeClient(
        provider_id="openai",
        model="gpt-test",
        error=RuntimeError("quota exceeded"),
    )
    backup = FakeClient(
        provider_id="deepseek",
        model="deepseek-chat",
        chunks=[LLMChunk(text="should-not-be-used", finish_reason="stop")],
    )
    resolver = ModelResolver(clients=[primary, backup])
    resolver.set_purpose_route("chat", provider_id="openai", model="gpt-test")

    with patch.object(
        resolver,
        "_get_user_configured_provider_ids",
        AsyncMock(return_value=["openai"]),
    ):
        with pytest.raises(RuntimeError, match="所有 LLM 客户端均失败: openai: quota exceeded"):
            _ = [
                chunk
                async for chunk in resolver.chat(
                    [{"role": "user", "content": "hi"}], purpose="chat"
                )
            ]


@pytest.mark.asyncio
async def test_multiple_user_providers_enable_fallback() -> None:
    """仅在用户配置多个提供商时，才允许自动降级。"""
    primary = FakeClient(
        provider_id="openai",
        model="gpt-test",
        error=RuntimeError("quota exceeded"),
    )
    backup = FakeClient(
        provider_id="deepseek",
        model="deepseek-chat",
        chunks=[LLMChunk(text="fallback-ok", finish_reason="stop")],
    )
    resolver = ModelResolver(clients=[primary, backup])
    resolver.set_purpose_route("chat", provider_id="openai", model="gpt-test")

    with patch.object(
        resolver,
        "_get_user_configured_provider_ids",
        AsyncMock(return_value=["openai", "deepseek"]),
    ):
        chunks = [
            chunk
            async for chunk in resolver.chat(
                [{"role": "user", "content": "hi"}],
                purpose="chat",
            )
        ]

    assert len(chunks) == 1
    assert chunks[0].text == "fallback-ok"
    assert chunks[0].provider_id == "deepseek"
    assert chunks[0].fallback_applied is True


@pytest.mark.asyncio
async def test_auto_fallback_skips_moonshot_but_keeps_later_providers() -> None:
    """自动降级链应跳过 Moonshot，避免兼容性问题反复进入兜底路径。"""
    resolver = ModelResolver(
        clients=[
            FakeClient(
                provider_id="openai",
                model="gpt-test",
                error=RuntimeError("openai down"),
            ),
            FakeClient(
                provider_id="moonshot",
                model="moonshot-v1-32k",
                chunks=[LLMChunk(text="should-not-be-used", finish_reason="stop")],
            ),
            FakeClient(
                provider_id="deepseek",
                model="deepseek-chat",
                chunks=[LLMChunk(text="fallback-ok", finish_reason="stop")],
            ),
        ]
    )
    resolver.set_purpose_route("chat", provider_id="openai", model="gpt-test")

    with patch.object(
        resolver,
        "_get_user_configured_provider_ids",
        AsyncMock(return_value=["openai", "moonshot", "deepseek"]),
    ):
        chunks = [
            chunk
            async for chunk in resolver.chat(
                [{"role": "user", "content": "hi"}],
                purpose="chat",
            )
        ]

    assert len(chunks) == 1
    assert chunks[0].text == "fallback-ok"
    assert chunks[0].provider_id == "deepseek"
    assert [item["provider_id"] for item in chunks[0].fallback_chain] == [
        "openai",
        "deepseek",
    ]


@pytest.mark.asyncio
async def test_explicit_moonshot_route_remains_available() -> None:
    """用户显式选择 Moonshot 时，仍应优先调用 Moonshot。"""
    resolver = ModelResolver(
        clients=[
            FakeClient(
                provider_id="openai",
                model="gpt-test",
                chunks=[LLMChunk(text="should-not-be-used", finish_reason="stop")],
            ),
            FakeClient(
                provider_id="moonshot",
                model="moonshot-v1-32k",
                chunks=[LLMChunk(text="moonshot-ok", finish_reason="stop")],
            ),
            FakeClient(
                provider_id="deepseek",
                model="deepseek-chat",
                chunks=[LLMChunk(text="should-not-be-used", finish_reason="stop")],
            ),
        ]
    )
    resolver.set_purpose_route("chat", provider_id="moonshot", model="moonshot-v1-32k")

    with patch.object(
        resolver,
        "_get_user_configured_provider_ids",
        AsyncMock(return_value=["openai", "moonshot", "deepseek"]),
    ):
        chunks = [
            chunk
            async for chunk in resolver.chat(
                [{"role": "user", "content": "hi"}],
                purpose="chat",
            )
        ]

    assert len(chunks) == 1
    assert chunks[0].text == "moonshot-ok"
    assert chunks[0].provider_id == "moonshot"


@pytest.mark.asyncio
async def test_planning_purpose_inherits_chat_route_when_unset() -> None:
    """planning 未单独配置时，应继承 chat 路由而不是回退到内置试用。"""
    primary = FakeClient(
        provider_id="zhipu",
        model="glm-5",
        chunks=[LLMChunk(text="ok", finish_reason="stop")],
    )
    resolver = ModelResolver(clients=[primary])
    resolver.set_purpose_route("chat", provider_id="zhipu", model="glm-5")

    with patch.object(
        resolver,
        "_get_user_configured_provider_ids",
        AsyncMock(return_value=["zhipu"]),
    ):
        chunks = [
            chunk
            async for chunk in resolver.chat(
                [{"role": "user", "content": "hi"}],
                purpose="planning",
            )
        ]

    assert len(chunks) == 1
    assert chunks[0].provider_id == "zhipu"
    assert chunks[0].model == "glm-5"


@pytest.mark.asyncio
async def test_preflight_reports_builtin_fast_quota_exhausted() -> None:
    """预检应在调用前返回配额不足，而不是进入实际 chat。"""
    resolver = ModelResolver(clients=[])
    resolver.set_purpose_route("chat", provider_id=BUILTIN_PROVIDER_ID, model="fast")

    async def fake_is_builtin_exhausted(mode: str) -> bool:
        return mode == "fast"

    with (
        patch("nini.config_manager.is_builtin_exhausted", side_effect=fake_is_builtin_exhausted),
        patch.object(
            resolver,
            "_get_user_configured_provider_ids",
            AsyncMock(return_value=[]),
        ),
    ):
        result = await resolver.preflight(purpose="chat")

    assert isinstance(result, ModelPreflightResult)
    assert result.available is False
    assert "快速" in result.reason


@pytest.mark.asyncio
async def test_preflight_reports_primary_available_client() -> None:
    """预检应返回首选客户端及降级链信息。"""
    resolver = ModelResolver(
        clients=[
            FakeClient(provider_id="openai", model="gpt-test", available=True),
            FakeClient(provider_id="deepseek", model="deepseek-chat", available=True),
        ]
    )
    resolver.set_purpose_route("chat", provider_id="openai", model="gpt-test")

    with patch.object(
        resolver,
        "_get_user_configured_provider_ids",
        AsyncMock(return_value=["openai", "deepseek"]),
    ):
        result = await resolver.preflight(purpose="chat")

    assert result.available is True
    assert result.provider_id == "openai"
    assert result.model == "gpt-test"
    assert [item["provider_id"] for item in result.fallback_chain] == ["openai", "deepseek"]
