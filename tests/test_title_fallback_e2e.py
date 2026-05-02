"""端到端模拟测试：验证 BUILTIN key 失效时的标题生成降级链。

覆盖 openspec 任务 8.3 的自动化模拟场景：
- 8.3.2-8.3.5: BUILTIN 401 → 激活 provider fallback → 标题正常生成
- 8.3.6: 两家都失败 → 规则兜底 _fallback_title → 标题非空
"""

from __future__ import annotations

from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, patch

import openai
import pytest

from nini.agent import title_generator
from nini.agent.model_resolver import BUILTIN_MODE_TITLE, ModelResolver
from nini.agent.providers import BaseLLMClient, LLMChunk, LLMResponse
from nini.config_manager import BUILTIN_PROVIDER_ID


class FakeClient(BaseLLMClient):
    """测试用伪客户端，可配置为成功或抛异常。"""

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

    def get_model_name(self) -> str:
        return self._model

    def pick_model_for_purpose(self, purpose: str) -> str | None:
        return None

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


def _make_response(status_code: int) -> Any:
    """构造带 request 的 HTTP 响应。"""
    import httpx

    request = httpx.Request("POST", "https://api.test/v1/chat/completions")
    return httpx.Response(status_code=status_code, request=request)


# -------------------------------------------------------
# 场景 8.3.2-8.3.5: BUILTIN 401 → 激活 provider 成功
# -------------------------------------------------------


@pytest.mark.asyncio
async def test_builtin_401_fallback_to_active_provider_title_ok() -> None:
    """BUILTIN key 失效(401)时，应降级到激活 provider 生成标题。

    模拟：BUILTIN client 抛 401 → resolver 自动尝试激活 dashscope client →
    dashscope 返回有效标题 → generate_title 返回 LLM 标题（非规则兜底）。
    """
    builtin_client = FakeClient(
        provider_id=BUILTIN_PROVIDER_ID,
        model="builtin-title",
        error=openai.AuthenticationError(
            "Invalid API key",
            response=_make_response(401),
            body=None,
        ),
    )
    active_client = FakeClient(
        provider_id="dashscope",
        model="qwen-plus",
        chunks=[LLMChunk(text="数据探索分析", finish_reason="stop")],
    )

    resolver = ModelResolver(clients=[active_client])
    resolver._active_provider_id = "dashscope"
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
        patch.object(title_generator, "model_resolver", resolver),
    ):
        title = await title_generator.generate_title(
            [{"role": "user", "content": "帮我分析这个数据集"}]
        )

    # 标题来自 LLM（激活 provider），不是规则兜底
    assert title == "数据探索分析"


@pytest.mark.asyncio
async def test_builtin_401_fallback_chain_visible_in_chunks() -> None:
    """BUILTIN 401 降级过程中，streaming chunk 应包含 fallback chain 信息。"""
    builtin_client = FakeClient(
        provider_id=BUILTIN_PROVIDER_ID,
        model="builtin-title",
        error=openai.AuthenticationError(
            "Invalid API key",
            response=_make_response(401),
            body=None,
        ),
    )
    active_client = FakeClient(
        provider_id="dashscope",
        model="qwen-plus",
        chunks=[LLMChunk(text="探索性分析", finish_reason="stop")],
    )

    resolver = ModelResolver(clients=[active_client])
    resolver._active_provider_id = "dashscope"
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
                [{"role": "user", "content": "hi"}],
                purpose="title_generation",
            )
        ]

    # 成功的 chunk 来自激活 provider
    assert len(chunks) == 1
    assert chunks[0].provider_id == "dashscope"
    assert chunks[0].fallback_applied is True
    assert chunks[0].fallback_from_provider_id == BUILTIN_PROVIDER_ID
    assert "API Key" in str(chunks[0].fallback_reason)


# -------------------------------------------------------
# 场景 8.3.6: 两家都失败 → 规则兜底
# -------------------------------------------------------


@pytest.mark.asyncio
async def test_both_providers_fail_fallback_title_nonempty() -> None:
    """BUILTIN 和激活 provider 都失败时，应走规则兜底 _fallback_title。"""
    builtin_client = FakeClient(
        provider_id=BUILTIN_PROVIDER_ID,
        model="builtin-title",
        error=openai.AuthenticationError(
            "Invalid API key",
            response=_make_response(401),
            body=None,
        ),
    )
    active_client = FakeClient(
        provider_id="dashscope",
        model="qwen-plus",
        error=openai.AuthenticationError(
            "Invalid API key",
            response=_make_response(401),
            body=None,
        ),
    )

    resolver = ModelResolver(clients=[active_client])
    resolver._active_provider_id = "dashscope"
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
        patch.object(title_generator, "model_resolver", resolver),
    ):
        title = await title_generator.generate_title(
            [{"role": "user", "content": "帮我分析这个数据集的相关性"}]
        )

    # 规则兜底应生成基于用户消息的标题
    assert title is not None
    assert len(title) > 0


@pytest.mark.asyncio
async def test_all_fail_no_active_provider_uses_fallback_title() -> None:
    """无激活 provider 且 BUILTIN 也失败时，应走规则兜底。"""
    builtin_client = FakeClient(
        provider_id=BUILTIN_PROVIDER_ID,
        model="builtin-title",
        error=RuntimeError("BUILTIN 配额已用尽"),
    )

    resolver = ModelResolver(clients=[])
    resolver.set_purpose_route(
        "title_generation",
        provider_id=BUILTIN_PROVIDER_ID,
        model=BUILTIN_MODE_TITLE,
    )

    # 模拟 BUILTIN 配额耗尽 → _resolve_client_plan 抛错
    # chat_complete(..., optional=True) 应返回 None → generate_title 走 fallback
    with (
        patch.object(
            resolver,
            "chat_complete",
            AsyncMock(return_value=None),
        ),
        patch.object(title_generator, "model_resolver", resolver),
    ):
        title = await title_generator.generate_title(
            [{"role": "user", "content": "请帮我做一个回归分析"}]
        )

    assert title is not None
    assert len(title) > 0


# -------------------------------------------------------
# 辅助验证：主链路不受影响
# -------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_purpose_unaffected_by_title_fallback_mechanism() -> None:
    """普通 chat 用途不受 BUILTIN 标题降级机制影响。"""
    active_client = FakeClient(
        provider_id="dashscope",
        model="qwen-plus",
        chunks=[LLMChunk(text="你好！有什么", finish_reason=None)],
    )

    resolver = ModelResolver(clients=[active_client])
    resolver._active_provider_id = "dashscope"
    resolver.set_purpose_route("chat", provider_id="dashscope", model="qwen-plus")

    with patch.object(
        resolver,
        "_get_user_configured_provider_ids",
        AsyncMock(return_value=["dashscope"]),
    ):
        chunks = [
            chunk
            async for chunk in resolver.chat(
                [{"role": "user", "content": "你好"}],
                purpose="chat",
            )
        ]

    assert len(chunks) == 1
    assert chunks[0].text == "你好！有什么"
    assert chunks[0].fallback_applied is False
