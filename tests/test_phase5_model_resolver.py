"""Phase 5：多模型路由与故障转移测试。"""

from __future__ import annotations

from dataclasses import dataclass
import json
import sys
import types
from typing import Any, AsyncGenerator

import pytest

from nini.agent.model_resolver import (
    AnthropicClient,
    BaseLLMClient,
    DashScopeClient,
    DeepSeekClient,
    KimiCodingClient,
    LLMChunk,
    ModelResolver,
    MoonshotClient,
    OllamaClient,
    ZhipuClient,
)


class FakeClient(BaseLLMClient):
    """测试用伪客户端。"""

    def __init__(
        self,
        *,
        provider_id: str = "fake",
        model: str = "fake-model",
        available: bool,
        chunks: list[LLMChunk] | None = None,
        error: Exception | None = None,
    ):
        self.provider_id = provider_id
        self.provider_name = provider_id
        self._model = model
        self.available = available
        self.chunks = chunks or []
        self.error = error

    def is_available(self) -> bool:
        return self.available

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[LLMChunk, None]:
        if self.error is not None:
            raise self.error
        for chunk in self.chunks:
            yield chunk


@pytest.mark.asyncio
async def test_model_resolver_fallback_to_next_available_client() -> None:
    resolver = ModelResolver(
        clients=[
            FakeClient(available=True, error=RuntimeError("openai failed")),
            FakeClient(available=False),
            FakeClient(
                available=True,
                chunks=[LLMChunk(text="ok-from-fallback", finish_reason="stop")],
            ),
        ]
    )

    chunks = [chunk async for chunk in resolver.chat([{"role": "user", "content": "hi"}])]
    assert "".join(c.text for c in chunks) == "ok-from-fallback"


@pytest.mark.asyncio
async def test_model_resolver_all_clients_failed_raises_runtime_error() -> None:
    resolver = ModelResolver(
        clients=[
            FakeClient(available=True, error=RuntimeError("a failed")),
            FakeClient(available=True, error=RuntimeError("b failed")),
        ]
    )

    with pytest.raises(RuntimeError) as exc:
        _ = [chunk async for chunk in resolver.chat([{"role": "user", "content": "hi"}])]
    assert "所有 LLM 客户端均失败" in str(exc.value)


@pytest.mark.asyncio
async def test_model_resolver_supports_purpose_routing() -> None:
    resolver = ModelResolver(
        clients=[
            FakeClient(
                provider_id="openai",
                available=True,
                chunks=[LLMChunk(text="from-openai", finish_reason="stop")],
            ),
            FakeClient(
                provider_id="zhipu",
                available=True,
                chunks=[LLMChunk(text="from-zhipu", finish_reason="stop")],
            ),
        ]
    )
    resolver.set_preferred_provider("openai")
    resolver.set_preferred_provider("zhipu", purpose="title_generation")

    default_chunks = [chunk async for chunk in resolver.chat([{"role": "user", "content": "hi"}])]
    title_chunks = [
        chunk
        async for chunk in resolver.chat(
            [{"role": "user", "content": "hi"}],
            purpose="title_generation",
        )
    ]

    assert "".join(c.text for c in default_chunks) == "from-openai"
    assert "".join(c.text for c in title_chunks) == "from-zhipu"
    assert resolver.get_preferred_provider() == "openai"
    assert resolver.get_preferred_provider(purpose="title_generation") == "zhipu"


def test_model_resolver_get_active_model_info_by_purpose() -> None:
    resolver = ModelResolver(
        clients=[
            FakeClient(provider_id="openai", model="gpt-4o", available=True),
            FakeClient(provider_id="zhipu", model="glm-4", available=True),
        ]
    )
    resolver.set_preferred_provider("openai")
    resolver.set_preferred_provider("zhipu", purpose="image_analysis")

    chat_info = resolver.get_active_model_info()
    image_info = resolver.get_active_model_info(purpose="image_analysis")

    assert chat_info["provider_id"] == "openai"
    assert image_info["provider_id"] == "zhipu"
    assert image_info["model"] == "glm-4"


def test_model_resolver_builds_purpose_model_override_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver = ModelResolver(
        clients=[
            FakeClient(provider_id="zhipu", model="glm-default", available=True),
        ]
    )
    resolver.set_purpose_route(
        "title_generation",
        provider_id="zhipu",
        model="glm-4.7-flash",
    )

    captured: dict[str, str | None] = {}

    def _fake_build(provider_id: str, *, model: str | None = None, base_url: str | None = None):  # type: ignore[no-untyped-def]
        captured["provider_id"] = provider_id
        captured["model"] = model
        captured["base_url"] = base_url
        return FakeClient(
            provider_id=provider_id,
            model=model or "fallback-model",
            available=True,
            chunks=[LLMChunk(text="from-purpose-override", finish_reason="stop")],
        )

    monkeypatch.setattr(resolver, "_build_client_for_provider", _fake_build)

    ordered = resolver._get_ordered_clients(purpose="title_generation")  # noqa: SLF001

    assert captured["provider_id"] == "zhipu"
    assert captured["model"] == "glm-4.7-flash"
    assert ordered[0].provider_id == "zhipu"
    assert ordered[0].get_model_name() == "glm-4.7-flash"


def test_model_resolver_get_active_client() -> None:
    resolver = ModelResolver(
        clients=[
            FakeClient(available=False),
            FakeClient(available=True),
            FakeClient(available=True),
        ]
    )
    active = resolver.get_active_client()
    assert isinstance(active, FakeClient)
    assert active.is_available() is True


def test_ollama_client_openai_compat_base_url() -> None:
    client = OllamaClient(base_url="http://localhost:11434", model="qwen2.5:7b")
    assert client.is_available() is True
    assert client._base_url == "http://localhost:11434/v1"  # noqa: SLF001


@dataclass
class _FakeAnthropicBlockText:
    type: str
    text: str


@dataclass
class _FakeAnthropicBlockToolUse:
    type: str
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class _FakeAnthropicUsage:
    input_tokens: int
    output_tokens: int


@dataclass
class _FakeAnthropicResponse:
    content: list[Any]
    usage: _FakeAnthropicUsage
    stop_reason: str


class _FakeAnthropicMessagesApi:
    async def create(self, **kwargs: Any) -> _FakeAnthropicResponse:
        assert kwargs["model"] == "claude-test"
        return _FakeAnthropicResponse(
            content=[
                _FakeAnthropicBlockText(type="text", text="先看结果。"),
                _FakeAnthropicBlockToolUse(
                    type="tool_use",
                    id="toolu_1",
                    name="run_code",
                    input={"code": "result = 1"},
                ),
            ],
            usage=_FakeAnthropicUsage(input_tokens=12, output_tokens=8),
            stop_reason="tool_use",
        )


class _FakeAnthropicClient:
    def __init__(self):
        self.messages = _FakeAnthropicMessagesApi()


@pytest.mark.asyncio
async def test_anthropic_client_parses_text_and_tool_calls() -> None:
    client = AnthropicClient(api_key="anthropic-key", model="claude-test")
    client._client = _FakeAnthropicClient()  # type: ignore[attr-defined]

    tools = [
        {
            "type": "function",
            "function": {
                "name": "run_code",
                "description": "run python",
                "parameters": {"type": "object", "properties": {"code": {"type": "string"}}},
            },
        }
    ]

    chunks = [
        c
        async for c in client.chat(
            [
                {"role": "system", "content": "你是科研助手"},
                {"role": "user", "content": "帮我执行代码"},
            ],
            tools=tools,
        )
    ]

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.text == "先看结果。"
    assert len(chunk.tool_calls) == 1
    assert chunk.tool_calls[0]["function"]["name"] == "run_code"
    assert json.loads(chunk.tool_calls[0]["function"]["arguments"]) == {"code": "result = 1"}
    assert chunk.usage == {"input_tokens": 12, "output_tokens": 8}


def test_anthropic_convert_messages_maps_tool_to_assistant_summary() -> None:
    client = AnthropicClient(api_key="anthropic-key", model="claude-test")
    system_prompt, converted = client._convert_messages(
        [
            {"role": "system", "content": "你是科研助手"},
            {"role": "user", "content": "帮我分析"},
            {
                "role": "tool",
                "content": json.dumps(
                    {
                        "success": True,
                        "message": "图表已生成",
                        "has_chart": True,
                        "chart_data": {"data": [1, 2, 3]},
                        "data": {"chart_type": "box", "dataset_name": "exp.csv"},
                    },
                    ensure_ascii=False,
                ),
            },
        ]
    )

    assert system_prompt == "你是科研助手"
    assert converted[0] == {"role": "user", "content": "帮我分析"}
    assert converted[1]["role"] == "assistant"
    assert "[工具结果]" in converted[1]["content"]
    assert '"message": "图表已生成"' in converted[1]["content"]
    assert "chart_data" not in converted[1]["content"]


# ---- 国产模型适配器测试 ----


def test_moonshot_client_base_url_and_availability() -> None:
    """Moonshot 客户端：正确设置 base_url，有 API Key 时可用。"""
    client = MoonshotClient(api_key="sk-moonshot-test", model="moonshot-v1-8k")
    assert client.is_available() is True
    assert client._base_url == "https://api.moonshot.cn/v1"  # noqa: SLF001
    assert client._model == "moonshot-v1-8k"  # noqa: SLF001


def test_moonshot_client_unavailable_without_key() -> None:
    """Moonshot 客户端：无 API Key 时不可用。"""
    client = MoonshotClient(api_key=None, model="moonshot-v1-8k")
    # 由于 settings 中默认 moonshot_api_key 为 None，直接传 None
    client._api_key = None  # noqa: SLF001
    assert client.is_available() is False


def test_kimi_coding_client_base_url_and_availability() -> None:
    """Kimi Coding 客户端：正确设置 base_url，有 API Key 时可用。"""
    client = KimiCodingClient(api_key="sk-kimi-test", model="kimi-for-coding")
    assert client.is_available() is True
    assert client._base_url == "https://api.kimi.com/coding/v1"  # noqa: SLF001
    assert client._model == "kimi-for-coding"  # noqa: SLF001


def test_zhipu_client_base_url_and_availability() -> None:
    """智谱 AI 客户端：默认使用 Coding Plan 端点，有 API Key 时可用。"""
    client = ZhipuClient(api_key="zhipu-test-key", model="glm-4")
    assert client.is_available() is True
    assert client._base_url == "https://open.bigmodel.cn/api/coding/paas/v4"  # noqa: SLF001
    assert client._model == "glm-4"  # noqa: SLF001


def test_zhipu_client_supports_custom_base_url() -> None:
    """智谱 AI 客户端：支持自定义 base_url（如 Coding Plan 端点）。"""
    client = ZhipuClient(
        api_key="zhipu-test-key",
        base_url="https://open.bigmodel.cn/api/coding/paas/v4",
        model="glm-4.7",
    )
    assert client.is_available() is True
    assert client._base_url == "https://open.bigmodel.cn/api/coding/paas/v4"  # noqa: SLF001
    assert client._model == "glm-4.7"  # noqa: SLF001


def test_zhipu_client_unavailable_without_key() -> None:
    """智谱 AI 客户端：无 API Key 时不可用。"""
    client = ZhipuClient(api_key=None, model="glm-4")
    client._api_key = None  # noqa: SLF001
    assert client.is_available() is False


def test_deepseek_client_base_url_and_availability() -> None:
    """DeepSeek 客户端：正确设置 base_url，有 API Key 时可用。"""
    client = DeepSeekClient(api_key="sk-deepseek-test", model="deepseek-chat")
    assert client.is_available() is True
    assert client._base_url == "https://api.deepseek.com/v1"  # noqa: SLF001
    assert client._model == "deepseek-chat"  # noqa: SLF001


def test_deepseek_client_unavailable_without_key() -> None:
    """DeepSeek 客户端：无 API Key 时不可用。"""
    client = DeepSeekClient(api_key=None, model="deepseek-chat")
    client._api_key = None  # noqa: SLF001
    assert client.is_available() is False


def test_dashscope_client_base_url_and_availability() -> None:
    """阿里百炼客户端：正确设置 base_url，有 API Key 时可用。"""
    client = DashScopeClient(api_key="sk-dashscope-test", model="qwen-plus")
    assert client.is_available() is True
    assert client._base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"  # noqa: SLF001
    assert client._model == "qwen-plus"  # noqa: SLF001


def test_dashscope_client_unavailable_without_key() -> None:
    """阿里百炼客户端：无 API Key 时不可用。"""
    client = DashScopeClient(api_key=None, model="qwen-plus")
    client._api_key = None  # noqa: SLF001
    assert client.is_available() is False


def test_model_resolver_includes_domestic_clients() -> None:
    """ModelResolver 默认客户端列表包含国产模型。"""
    resolver = ModelResolver()
    client_types = [type(c).__name__ for c in resolver._clients]  # noqa: SLF001
    assert "MoonshotClient" in client_types
    assert "ZhipuClient" in client_types
    assert "DeepSeekClient" in client_types
    assert "DashScopeClient" in client_types


@pytest.mark.asyncio
async def test_domestic_client_fallback_in_resolver() -> None:
    """国产模型客户端参与故障转移链。"""
    # 模拟：OpenAI 失败 → Moonshot 不可用 → DeepSeek 成功
    resolver = ModelResolver(
        clients=[
            FakeClient(available=True, error=RuntimeError("openai down")),
            FakeClient(available=False),  # 模拟 Moonshot 未配置
            FakeClient(
                available=True,
                chunks=[LLMChunk(text="deepseek-ok", finish_reason="stop")],
            ),
        ]
    )
    chunks = [chunk async for chunk in resolver.chat([{"role": "user", "content": "hi"}])]
    assert "".join(c.text for c in chunks) == "deepseek-ok"


def test_all_domestic_clients_support_stream_usage() -> None:
    """国产模型客户端 stream_options.include_usage 支持情况。"""
    # 支持 stream_options 的提供商
    for cls in [DeepSeekClient, DashScopeClient]:
        client = cls(api_key="test-key", model="test-model")
        assert client._supports_stream_usage() is True  # noqa: SLF001

    # 不支持 stream_options 的提供商
    for cls, kwargs in [  # type: ignore[assignment]
        (MoonshotClient, {"api_key": "test-key", "model": "test-model"}),
        (KimiCodingClient, {"api_key": "test-key", "model": "kimi-for-coding"}),
        (ZhipuClient, {"api_key": "test-key", "model": "test-model"}),
    ]:
        client = cls(**kwargs)
        assert client._supports_stream_usage() is False  # noqa: SLF001


@pytest.mark.asyncio
async def test_openai_compatible_client_uses_default_http_client_and_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OpenAI 兼容客户端应显式注入并关闭 httpx 客户端。"""

    class _FakeHttpClient:
        def __init__(self, **kwargs: Any):
            self.closed = False
            self.kwargs = kwargs

        async def aclose(self) -> None:
            self.closed = True

    class _FakeAsyncOpenAI:
        def __init__(self, **kwargs: Any):
            self.kwargs = kwargs
            self.closed = False

        async def close(self) -> None:
            self.closed = True

    fake_module = types.SimpleNamespace(
        AsyncOpenAI=_FakeAsyncOpenAI,
        DefaultAsyncHttpxClient=_FakeHttpClient,
    )
    monkeypatch.setitem(sys.modules, "openai", fake_module)

    client = ZhipuClient(api_key="zhipu-test-key", model="glm-4")
    client._ensure_client()  # noqa: SLF001

    assert isinstance(client._http_client, _FakeHttpClient)  # noqa: SLF001
    assert client._http_client.kwargs["trust_env"] is False  # noqa: SLF001
    assert client._client.kwargs["http_client"] is client._http_client  # noqa: SLF001
    assert client._client.kwargs["max_retries"] == 3  # noqa: SLF001

    underlying_client = client._client  # noqa: SLF001
    await client.aclose()

    assert underlying_client.closed is True
    assert client._client is None  # noqa: SLF001
    assert client._http_client is None  # noqa: SLF001


@pytest.mark.asyncio
async def test_openai_compatible_client_aclose_ignores_mounts_attribute_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """当底层关闭触发 _mounts 兼容性异常时应被吞掉。"""

    class _FakeHttpClient:
        def __init__(self, **kwargs: Any):
            self.kwargs = kwargs

        async def aclose(self) -> None:
            return

    class _FakeAsyncOpenAI:
        def __init__(self, **kwargs: Any):
            self.kwargs = kwargs

        async def close(self) -> None:
            raise AttributeError("'AsyncHttpxClientWrapper' object has no attribute '_mounts'")

    fake_module = types.SimpleNamespace(
        AsyncOpenAI=_FakeAsyncOpenAI,
        DefaultAsyncHttpxClient=_FakeHttpClient,
    )
    monkeypatch.setitem(sys.modules, "openai", fake_module)

    client = ZhipuClient(api_key="zhipu-test-key", model="glm-4")
    client._ensure_client()  # noqa: SLF001

    await client.aclose()
    assert client._client is None  # noqa: SLF001
    assert client._http_client is None  # noqa: SLF001
