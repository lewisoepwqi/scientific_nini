"""Phase 5：多模型路由与故障转移测试。"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sys
import types
from typing import Any, AsyncGenerator, cast
from unittest.mock import AsyncMock, patch

import httpx
import openai
import pytest

from nini.agent.model_resolver import ModelResolver
from nini.builtin_key_crypto import encrypt_key
from nini.config import settings
from nini.agent.providers import (
    AnthropicClient,
    BaseLLMClient,
    DashScopeClient,
    DeepSeekClient,
    KimiCodingClient,
    LLMChunk,
    MiniMaxClient,
    MoonshotClient,
    OllamaClient,
    ReasoningStreamParser,
    ZhipuClient,
)
from nini.agent.providers.openai_provider import (
    _merge_tool_arguments,
    dump_chat_payload_debug,
    summarize_messages_for_debug,
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


def _make_response(status_code: int) -> httpx.Response:
    """构造带 request 的 HTTP 响应。"""
    request = httpx.Request("POST", "https://example.test/v1/chat/completions")
    return httpx.Response(status_code=status_code, request=request)


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
async def test_model_resolver_emits_fallback_metadata() -> None:
    resolver = ModelResolver(
        clients=[
            FakeClient(
                provider_id="primary",
                model="model-a",
                available=True,
                error=RuntimeError("quota exceeded"),
            ),
            FakeClient(
                provider_id="backup",
                model="model-b",
                available=True,
                chunks=[LLMChunk(text="ok", finish_reason="stop")],
            ),
        ]
    )

    chunks = [chunk async for chunk in resolver.chat([{"role": "user", "content": "hi"}])]
    assert len(chunks) == 1
    first = chunks[0]
    assert first.provider_id == "backup"
    assert first.model == "model-b"
    assert first.fallback_applied is True
    assert first.fallback_from_provider_id == "primary"
    assert first.fallback_from_model == "model-a"
    assert first.fallback_reason == "quota exceeded"
    assert len(first.fallback_chain) == 2


@pytest.mark.asyncio
async def test_model_resolver_rate_limit_error_triggers_fallback() -> None:
    """429 限流错误应触发 fallback 到下一个可用客户端。"""
    resolver = ModelResolver(
        clients=[
            FakeClient(
                provider_id="openai",
                model="gpt-primary",
                available=True,
                error=openai.RateLimitError(
                    "too many requests",
                    response=_make_response(429),
                    body=None,
                ),
            ),
            FakeClient(
                provider_id="backup",
                model="gpt-backup",
                available=True,
                chunks=[LLMChunk(text="fallback-ok", finish_reason="stop")],
            ),
        ]
    )

    chunks = [chunk async for chunk in resolver.chat([{"role": "user", "content": "hi"}])]

    assert len(chunks) == 1
    assert chunks[0].provider_id == "backup"
    assert chunks[0].fallback_applied is True
    assert chunks[0].fallback_reason == "请求过于频繁，请稍后重试"


@pytest.mark.asyncio
async def test_model_resolver_authentication_error_triggers_fallback() -> None:
    """401 认证错误应允许跨 provider 降级。"""
    resolver = ModelResolver(
        clients=[
            FakeClient(
                provider_id="openai",
                model="gpt-primary",
                available=True,
                error=openai.AuthenticationError(
                    "bad key",
                    response=_make_response(401),
                    body=None,
                ),
            ),
            FakeClient(
                provider_id="backup",
                model="gpt-backup",
                available=True,
                chunks=[LLMChunk(text="should-not-run", finish_reason="stop")],
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


@pytest.mark.asyncio
async def test_model_resolver_uses_builtin_fast_for_trial_title_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver = ModelResolver()
    captured: dict[str, str | None] = {}

    def _fake_builtin_client(purpose: str, mode: str | None) -> FakeClient:
        captured["purpose"] = purpose
        captured["mode"] = mode
        return FakeClient(
            provider_id="builtin",
            model="qwen3.5-27b",
            available=True,
            chunks=[LLMChunk(text="trial-title", finish_reason="stop")],
        )

    monkeypatch.setattr(resolver, "_get_builtin_client", _fake_builtin_client)

    with (
        patch("nini.config_manager.is_builtin_exhausted", AsyncMock(return_value=False)),
        patch("nini.config_manager.increment_builtin_usage", AsyncMock()) as increment_usage,
        patch("nini.config_manager.list_user_configured_provider_ids", AsyncMock(return_value=[])),
    ):
        chunks = [
            chunk
            async for chunk in resolver.chat(
                [{"role": "user", "content": "请生成标题"}],
                purpose="title_generation",
            )
        ]

    assert "".join(chunk.text for chunk in chunks) == "trial-title"
    assert captured == {"purpose": "default", "mode": "fast"}
    increment_usage.assert_awaited_once_with("fast")


@pytest.mark.asyncio
async def test_title_generation_invalid_route_falls_back_to_title_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """标题路由无效时，应回退到标题客户端而不是优先级旧供应商。"""

    resolver = ModelResolver(
        clients=[
            FakeClient(
                provider_id="moonshot",
                model="moonshot-v1-8k",
                available=True,
                chunks=[LLMChunk(text="old-provider", finish_reason="stop")],
            ),
            FakeClient(
                provider_id="anthropic",
                model="claude-sonnet",
                available=False,
            ),
        ]
    )
    resolver.set_purpose_route("title_generation", provider_id="anthropic")

    async def _fake_title_client() -> FakeClient:
        return FakeClient(
            provider_id="dashscope",
            model="qwen-turbo",
            available=True,
            chunks=[LLMChunk(text="title-from-active", finish_reason="stop")],
        )

    monkeypatch.setattr(resolver, "_get_title_client", _fake_title_client)

    chunks = [
        chunk
        async for chunk in resolver.chat(
            [{"role": "user", "content": "请生成标题"}],
            purpose="title_generation",
        )
    ]

    assert "".join(chunk.text for chunk in chunks) == "title-from-active"
    assert all(chunk.provider_id != "moonshot" for chunk in chunks)


def test_analysis_and_fast_purposes_inherit_configured_chat_route() -> None:
    """子 Agent 使用的别名 purpose 应回退到用户配置的 chat 路由。"""
    resolver = ModelResolver(clients=[])
    resolver.set_purpose_route("chat", provider_id="zhipu", model="glm-5")
    resolver.set_purpose_route("planning", provider_id="dashscope", model="qwen-plus")

    assert resolver.get_preferred_provider("analysis") == "zhipu"
    assert resolver.get_preferred_provider("fast") == "zhipu"
    assert resolver.get_preferred_provider("deep_reasoning") == "dashscope"


def test_title_generation_and_image_analysis_purposes_inherit_chat_route() -> None:
    """标题生成与图像分析在未配置时应继承 chat 路由。"""
    resolver = ModelResolver(clients=[])
    resolver.set_purpose_route("chat", provider_id="deepseek", model="deepseek-chat")

    assert resolver.get_preferred_provider("title_generation") == "deepseek"
    assert resolver.get_preferred_provider("image_analysis") == "deepseek"


@pytest.mark.asyncio
async def test_get_title_client_uses_provider_pick_model_for_purpose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """标题客户端应通过 provider 接口从当前可用模型中挑选偏好模型。"""

    picked_available_models: list[str] = []

    class _TitleAwareClient(FakeClient):
        def pick_model_for_purpose(self, purpose: str) -> str | None:
            if purpose != "title_generation":
                return None
            available = getattr(self, "_available_models_cache", [])
            picked_available_models.extend(list(available))
            return "qwen-turbo-latest" if "qwen-turbo-latest" in available else None

    resolver = ModelResolver(
        clients=[
            _TitleAwareClient(
                provider_id="dashscope",
                model="qwen-plus",
                available=True,
            ),
        ]
    )
    resolver._active_provider_id = "dashscope"  # noqa: SLF001
    resolver._config_overrides = {  # noqa: SLF001
        "dashscope": {"api_key": "sk-test", "base_url": None, "model": "qwen-plus"}
    }

    async def _fake_list_available_models(*args, **kwargs):  # type: ignore[no-untyped-def]
        return {"models": ["qwen-max", "qwen-turbo-latest", "qwen-plus"], "source": "remote"}

    def _fake_build(provider_id: str, *, model: str | None = None, base_url: str | None = None):  # type: ignore[no-untyped-def]
        return FakeClient(
            provider_id=provider_id,
            model=model or "fallback-model",
            available=True,
        )

    monkeypatch.setattr(
        "nini.agent.model_lister.list_available_models",
        _fake_list_available_models,
    )
    monkeypatch.setattr(resolver, "_build_client_for_provider", _fake_build)

    client = await resolver._get_title_client()  # noqa: SLF001

    assert client is not None
    assert client.provider_id == "dashscope"
    assert client.get_model_name() == "qwen-turbo-latest"
    assert picked_available_models == ["qwen-max", "qwen-turbo-latest", "qwen-plus"]


@pytest.mark.asyncio
async def test_get_title_client_falls_back_to_active_model_when_no_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """动态列表匹配不到标题模型时应回退当前主模型。"""

    class _PassiveTitleClient(FakeClient):
        def pick_model_for_purpose(self, purpose: str) -> str | None:
            return None

    active_client = _PassiveTitleClient(
        provider_id="dashscope",
        model="qwen-plus",
        available=True,
    )
    resolver = ModelResolver(clients=[active_client])
    resolver._active_provider_id = "dashscope"  # noqa: SLF001
    resolver._config_overrides = {  # noqa: SLF001
        "dashscope": {"api_key": "sk-test", "base_url": None, "model": "qwen-plus"}
    }

    async def _fake_list_available_models(*args, **kwargs):  # type: ignore[no-untyped-def]
        return {"models": ["qwen-max"], "source": "remote"}

    monkeypatch.setattr(
        "nini.agent.model_lister.list_available_models",
        _fake_list_available_models,
    )

    client = await resolver._get_title_client()  # noqa: SLF001

    assert client is active_client


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


def test_reload_clients_resets_stale_purpose_routes() -> None:
    """重载客户端时应清空旧的内存态用途路由。"""

    resolver = ModelResolver(
        clients=[
            FakeClient(provider_id="zhipu", model="glm-4", available=True),
        ]
    )
    resolver.set_purpose_route("title_generation", provider_id="anthropic", model="claude-3")

    resolver.reload_clients(
        {
            "dashscope": {
                "api_key": "sk-test",
                "model": "qwen-plus",
                "base_url": None,
            }
        },
        active_provider_id="dashscope",
    )

    route = resolver.get_purpose_routes()["title_generation"]

    assert route["provider_id"] is None
    assert route["model"] is None
    assert route["base_url"] is None


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


def test_model_resolver_reload_clients_respects_priority_order() -> None:
    resolver = ModelResolver()
    resolver.reload_clients(
        config_overrides={},
        priorities={
            "zhipu": 0,
            "openai": 10,
        },
    )

    ordered_providers = [client.provider_id for client in resolver._clients]  # noqa: SLF001
    assert ordered_providers[0] == "zhipu"
    assert ordered_providers.index("openai") > ordered_providers.index("anthropic")


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


def test_anthropic_convert_messages_keeps_tool_data_excerpt() -> None:
    client = AnthropicClient(api_key="anthropic-key", model="claude-test")
    _, converted = client._convert_messages(
        [
            {"role": "user", "content": "执行 /root-analysis"},
            {
                "role": "tool",
                "content": json.dumps(
                    {
                        "success": True,
                        "message": "已读取技能文档",
                        "data_excerpt": "## 关键步骤\n1. validate_data.py\n2. generate_r_project.py",
                    },
                    ensure_ascii=False,
                ),
            },
        ]
    )

    assert converted[1]["role"] == "assistant"
    assert "data_excerpt" in converted[1]["content"]
    assert "validate_data.py" in converted[1]["content"]
    assert "generate_r_project.py" in converted[1]["content"]


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


def test_moonshot_sanitize_tools_moves_type_into_anyof_items() -> None:
    """Moonshot schema 净化：把父级 type 下放到 anyOf 各项内并移除父级 type。

    复现真实工具的 schema 形状（dispatch_agents、code_session.run_script 等），
    验证转换后既满足 Moonshot ``type`` 必须在 anyOf items 内的要求，
    也保留原有 properties / required 等约束。
    """
    tools = [
        {
            "type": "function",
            "function": {
                "name": "dispatch_agents",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agents": {"type": "array"},
                        "tasks": {"type": "array"},
                    },
                    "anyOf": [
                        {"required": ["agents"]},
                        {"required": ["tasks"]},
                    ],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "code_session",
                "parameters": {
                    "type": "object",
                    "oneOf": [
                        {
                            "type": "object",
                            "properties": {"operation": {"const": "run_script"}},
                            "required": ["operation"],
                            "anyOf": [
                                {"required": ["script_id"]},
                                {"required": ["content"]},
                            ],
                        },
                    ],
                },
            },
        },
    ]

    sanitized = MoonshotClient._sanitize_tools_for_moonshot(tools)  # noqa: SLF001
    assert sanitized is not None

    dispatch_params = sanitized[0]["function"]["parameters"]
    # 父级 type 已下放，移除
    assert "type" not in dispatch_params
    # properties 等其它字段保留
    assert "properties" in dispatch_params
    # 每个 anyOf 项都补齐了 type=object 且保留 required
    assert dispatch_params["anyOf"] == [
        {"type": "object", "required": ["agents"]},
        {"type": "object", "required": ["tasks"]},
    ]

    run_script_branch = sanitized[1]["function"]["parameters"]["oneOf"][0]
    # 嵌套节点同样被处理
    assert "type" not in run_script_branch
    assert run_script_branch["required"] == ["operation"]
    assert run_script_branch["anyOf"] == [
        {"type": "object", "required": ["script_id"]},
        {"type": "object", "required": ["content"]},
    ]

    # 不修改原对象
    assert "type" in tools[0]["function"]["parameters"]
    assert tools[0]["function"]["parameters"]["anyOf"][0] == {"required": ["agents"]}


def test_moonshot_sanitize_tools_preserves_explicit_anyof_item_type() -> None:
    """Moonshot schema 净化：anyOf 项已有 type 时不应被父级 type 覆盖。"""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "mixed",
                "parameters": {
                    "type": "object",
                    "anyOf": [
                        {"type": "array", "items": {"type": "string"}},
                        {"required": ["name"]},
                    ],
                },
            },
        }
    ]

    sanitized = MoonshotClient._sanitize_tools_for_moonshot(tools)  # noqa: SLF001
    assert sanitized is not None
    params = sanitized[0]["function"]["parameters"]
    assert "type" not in params
    assert params["anyOf"] == [
        {"type": "array", "items": {"type": "string"}},
        {"type": "object", "required": ["name"]},
    ]


def test_moonshot_sanitize_tools_no_anyof_unchanged() -> None:
    """Moonshot schema 净化：无 anyOf 时不改动 type 字段。"""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "simple",
                "parameters": {
                    "type": "object",
                    "properties": {"x": {"type": "string"}},
                    "required": ["x"],
                },
            },
        }
    ]
    sanitized = MoonshotClient._sanitize_tools_for_moonshot(tools)  # noqa: SLF001
    assert sanitized is not None
    params = sanitized[0]["function"]["parameters"]
    assert params["type"] == "object"
    assert params["required"] == ["x"]


def test_moonshot_sanitize_tools_handles_none_and_empty() -> None:
    """Moonshot schema 净化：None / 空列表保持原值。"""
    assert MoonshotClient._sanitize_tools_for_moonshot(None) is None  # noqa: SLF001
    assert MoonshotClient._sanitize_tools_for_moonshot([]) == []  # noqa: SLF001


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


def test_dashscope_client_uses_settings_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """阿里百炼客户端应尊重 settings 中的自定义 base_url。"""
    monkeypatch.setattr(settings, "dashscope_base_url", "https://coding.dashscope.aliyuncs.com/v1")

    client = DashScopeClient(api_key="sk-dashscope-test", model="qwen-plus")

    assert client._base_url == "https://coding.dashscope.aliyuncs.com/v1"  # noqa: SLF001


def test_dashscope_client_unavailable_without_key() -> None:
    """阿里百炼客户端：无 API Key 时不可用。"""
    client = DashScopeClient(api_key=None, model="qwen-plus")
    client._api_key = None  # noqa: SLF001
    assert client.is_available() is False


def test_model_resolver_includes_domestic_clients() -> None:
    """ModelResolver 默认客户端列表包含当前启用的国产模型。"""
    resolver = ModelResolver()
    client_types = [type(c).__name__ for c in resolver._clients]  # noqa: SLF001
    assert "MoonshotClient" in client_types
    assert "ZhipuClient" in client_types
    assert "DeepSeekClient" in client_types
    assert "DashScopeClient" in client_types
    assert "MiniMaxClient" in client_types
    assert "KimiCodingClient" not in client_types


def test_moonshot_client_normalizes_assistant_tool_calls_for_thinking_mode() -> None:
    """Moonshot 应为 assistant tool_call 历史补 reasoning_content。"""
    client = MoonshotClient(api_key="sk-moonshot-test", model="kimi-k2.5")

    normalized = client._normalize_messages_for_provider(  # noqa: SLF001
        [
            {
                "role": "assistant",
                "content": "",
                "turn_id": "t-1",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "run_code", "arguments": "{}"},
                    }
                ],
            }
        ]
    )

    assert normalized == [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "run_code", "arguments": "{}"},
                }
            ],
            "reasoning_content": "",
        }
    ]


def test_zhipu_client_flattens_tool_history_to_plain_text() -> None:
    """Zhipu 请求体应丢弃历史 tool_calls，只保留 assistant 的文字内容。

    注：之前的实现会注入 [历史工具调用] 格式文本，但这会导致 GLM-5
    通过上下文模仿在下一轮将工具调用输出为纯文本而非真实 function call，
    从而使 ReAct 循环提前退出。修复后只保留文字内容，不注入调用摘要。
    """
    client = ZhipuClient(api_key="zhipu-test-key", model="glm-5")

    normalized = client._normalize_messages_for_provider(  # noqa: SLF001
        [
            {
                "role": "assistant",
                "content": "继续",
                "message_id": "m-1",
                "operation": "complete",
                "effective_model": {"provider_id": "zhipu"},
                "fallback_chain": [{"provider_id": "zhipu", "status": "success"}],
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "task_state", "arguments": "{}"},
                    }
                ],
            }
        ]
    )

    # 只保留文字内容，不注入工具调用摘要；无 user 消息时插入占位 user 保证序列合法
    assert normalized == [
        {"role": "user", "content": "请继续。"},
        {"role": "assistant", "content": "继续"},
    ]


def test_zhipu_client_normalizes_nested_tool_call_fields() -> None:
    """Zhipu 请求体应丢弃历史 tool_calls；content 为 None 时不产生消息。"""
    client = ZhipuClient(api_key="zhipu-test-key", model="glm-5")

    normalized = client._normalize_messages_for_provider(  # noqa: SLF001
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "index": 0,
                        "function": {
                            "name": "task_state",
                            "arguments": {"operation": "update"},
                            "extra": "ignored",
                        },
                        "debug": {"source": "test"},
                    }
                ],
            }
        ]
    )

    # content 为 None，不注入工具调用摘要；序列为空时插入占位 user 保证 GLM-5 序列合法
    assert normalized == [{"role": "user", "content": "请继续。"}]


def test_zhipu_client_flattens_tool_role_to_user_context() -> None:
    """Zhipu 请求体应将 tool 角色转换为 user 消息（工具结果是环境观测值）。

    使用 user 而非 assistant，使 ReAct 轨迹形成合法的 assistant→user 交替结构，
    避免 GLM-5 因全为 assistant 消息而返回 code=1214 错误。
    """
    client = ZhipuClient(api_key="zhipu-test-key", model="glm-5")

    normalized = client._normalize_messages_for_provider(  # noqa: SLF001
        [
            {
                "role": "tool",
                "tool_call_id": "call-1",
                "content": '{"ok": true, "message": "done"}',
            }
        ]
    )

    assert normalized == [
        {
            "role": "user",
            "content": '{"ok": true, "message": "done"}',
        }
    ]


def test_summarize_messages_for_debug_includes_tool_call_shape() -> None:
    """调试摘要应暴露 tool_call 的附加字段形状。"""
    summary = summarize_messages_for_debug(
        [
            {
                "role": "assistant",
                "content": "继续",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "debug": True,
                        "function": {
                            "name": "run_code",
                            "arguments": "{}",
                            "extra": "ignored",
                        },
                    }
                ],
            }
        ]
    )

    assert summary[0]["tool_call_count"] == 1
    assert summary[0]["tool_call_extra_keys"] == [["debug"]]
    assert summary[0]["tool_function_extra_keys"] == [["extra"]]


def test_dump_chat_payload_debug_writes_file(tmp_path: Path) -> None:
    """失败请求 payload 应写入本地调试目录。"""
    dump_path = dump_chat_payload_debug(
        provider_id="zhipu",
        model="glm-5",
        base_url="https://open.bigmodel.cn/api/coding/paas/v4",
        messages=[{"role": "user", "content": "你好"}],
        tools=None,
        temperature=0.3,
        max_tokens=256,
        error=RuntimeError("messages 参数非法"),
        debug_dir=tmp_path,
    )

    assert dump_path.exists() is True
    payload = json.loads(dump_path.read_text(encoding="utf-8"))
    assert payload["provider_id"] == "zhipu"
    assert payload["model"] == "glm-5"
    assert payload["message_count"] == 1
    assert payload["total_content_len"] == 2
    assert payload["messages_summary"][0]["role"] == "user"
    assert payload["error"] == "messages 参数非法"


def test_model_resolver_default_priority_excludes_auto_fallback_blocked_providers() -> None:
    """默认优先级链不应包含被禁用或退出自动降级的 provider。"""
    resolver = ModelResolver(
        clients=[
            FakeClient(provider_id="openai", available=True),
            FakeClient(provider_id="moonshot", available=True),
            FakeClient(provider_id="kimi_coding", available=True),
            FakeClient(provider_id="zhipu", available=True),
            FakeClient(provider_id="dashscope", available=True),
        ]
    )

    ordered = resolver._get_priority_order()  # noqa: SLF001

    assert ordered == ["openai", "zhipu", "dashscope"]
    assert "kimi_coding" not in ordered
    assert "moonshot" not in ordered


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
    for cls in [DeepSeekClient, DashScopeClient, MiniMaxClient]:
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


def test_minimax_client_base_url_and_availability() -> None:
    """MiniMax 客户端：可设置 base_url，且有 API Key 时可用。"""
    client = MiniMaxClient(
        api_key="sk-minimax-test",
        base_url="https://api.minimax.chat/v1",
        model="MiniMax-M2.5",
    )
    assert client.is_available() is True
    assert client._base_url == "https://api.minimax.chat/v1"  # noqa: SLF001
    assert client._model == "MiniMax-M2.5"  # noqa: SLF001


def test_minimax_client_unavailable_without_key() -> None:
    """MiniMax 客户端：无 API Key 时不可用。"""
    client = MiniMaxClient(api_key=None, model="MiniMax-M2.5")
    client._api_key = None  # noqa: SLF001
    assert client.is_available() is False


def test_reasoning_stream_parser_splits_think_tags_across_chunks() -> None:
    """应能跨 chunk 拆分 `<think>` 思考内容。"""
    parser = ReasoningStreamParser(enable_tag_split=True)

    t1, r1, raw1 = parser.consume(raw_piece="<think>先思", explicit_reasoning_piece="")
    t2, r2, raw2 = parser.consume(raw_piece="考后答</think>最终答案", explicit_reasoning_piece="")

    assert t1 == ""
    assert r1 == "先思"
    assert raw1 == "<think>先思"
    assert t2 == "最终答案"
    assert r2 == "考后答"
    assert raw2 == "考后答</think>最终答案"


def test_reasoning_stream_parser_handles_cumulative_reasoning_content() -> None:
    """应兼容累计流（每个 chunk 返回完整 reasoning 前缀）。"""
    parser = ReasoningStreamParser(enable_tag_split=False)

    t1, r1, raw1 = parser.consume(raw_piece="", explicit_reasoning_piece="step-1")
    t2, r2, raw2 = parser.consume(raw_piece="", explicit_reasoning_piece="step-1 + step-2")

    assert t1 == ""
    assert raw1 == ""
    assert r1 == "step-1"

    assert t2 == ""
    assert raw2 == ""
    assert r2 == " + step-2"


def test_reasoning_stream_parser_strips_orphan_think_close_tag_when_reasoning_field_exists() -> (
    None
):
    """当 reasoning 字段已存在时，正文中的孤立 </think> 不应泄漏到 UI。"""
    parser = ReasoningStreamParser(enable_tag_split=True)

    t1, r1, _ = parser.consume(
        raw_piece="",
        explicit_reasoning_piece="先做分析",
    )
    t2, r2, _ = parser.consume(
        raw_piece="结论如下。</think>",
        explicit_reasoning_piece="先做分析",
    )

    assert t1 == ""
    assert r1 == "先做分析"
    assert t2 == "结论如下。"
    assert r2 == ""


def test_merge_tool_arguments_supports_incremental_chunks() -> None:
    merged = _merge_tool_arguments('{"method":"cor', 'relation","dataset_name":"demo"}')
    assert merged == '{"method":"correlation","dataset_name":"demo"}'


def test_merge_tool_arguments_supports_cumulative_chunks() -> None:
    merged = _merge_tool_arguments(
        '{"method":"correlation"',
        '{"method":"correlation","dataset_name":"demo"}',
    )
    assert merged == '{"method":"correlation","dataset_name":"demo"}'


def test_merge_tool_arguments_avoids_duplicate_replay() -> None:
    merged = _merge_tool_arguments(
        '{"method":"correlation","dataset_name":"demo"}',
        ',"dataset_name":"demo"}',
    )
    assert merged == '{"method":"correlation","dataset_name":"demo"}'


def _fake_openai_stream_chunk(text: str = "", finish_reason: str | None = None) -> Any:
    """构造 OpenAI 兼容流式 chunk。"""
    delta = types.SimpleNamespace(content=text, tool_calls=None)
    choice = types.SimpleNamespace(delta=delta, finish_reason=finish_reason)
    return types.SimpleNamespace(choices=[choice], usage=None)


class _FakeOpenAIStream:
    """测试用 OpenAI 兼容异步流。"""

    def __init__(
        self,
        *,
        chunks: list[Any] | None = None,
        error_before_chunks: Exception | None = None,
        error_after_chunks: Exception | None = None,
    ) -> None:
        self._chunks = chunks or []
        self._error_before_chunks = error_before_chunks
        self._error_after_chunks = error_after_chunks

    def __aiter__(self) -> AsyncGenerator[Any, None]:
        return self._iterate()

    async def _iterate(self) -> AsyncGenerator[Any, None]:
        if self._error_before_chunks is not None:
            raise self._error_before_chunks
        for chunk in self._chunks:
            yield chunk
        if self._error_after_chunks is not None:
            raise self._error_after_chunks


class _FakeOpenAICompletions:
    """按顺序返回预设流式响应。"""

    def __init__(self, streams: list[_FakeOpenAIStream]) -> None:
        self._streams = streams
        self.calls = 0

    async def create(self, **kwargs: Any) -> _FakeOpenAIStream:
        self.calls += 1
        return self._streams.pop(0)


@pytest.mark.asyncio
async def test_openai_compatible_client_retries_stream_disconnect_before_any_chunk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """流式读取未产出内容前断开时，应同 provider 重试并只输出成功结果。"""
    monkeypatch.setattr(settings, "llm_stream_retries", 1, raising=False)
    sleep_mock = AsyncMock()
    monkeypatch.setattr("nini.agent.providers.openai_provider.asyncio.sleep", sleep_mock)
    completions = _FakeOpenAICompletions(
        [
            _FakeOpenAIStream(error_before_chunks=httpx.RemoteProtocolError("server disconnected")),
            _FakeOpenAIStream(chunks=[_fake_openai_stream_chunk("ok", finish_reason="stop")]),
        ]
    )
    client = ZhipuClient(api_key="zhipu-test-key", model="glm-5")
    client._client = types.SimpleNamespace(  # noqa: SLF001
        chat=types.SimpleNamespace(completions=completions)
    )

    chunks = [chunk async for chunk in client.chat([{"role": "user", "content": "hi"}])]

    assert completions.calls == 2
    assert [chunk.text for chunk in chunks] == ["ok"]
    sleep_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_openai_compatible_client_does_not_retry_after_emitting_chunk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """流式读取已产出内容后断开时，不应从头重试以免重复输出。"""
    monkeypatch.setattr(settings, "llm_stream_retries", 1, raising=False)
    completions = _FakeOpenAICompletions(
        [
            _FakeOpenAIStream(
                chunks=[_fake_openai_stream_chunk("partial")],
                error_after_chunks=httpx.RemoteProtocolError("server disconnected"),
            ),
            _FakeOpenAIStream(
                chunks=[_fake_openai_stream_chunk("duplicated", finish_reason="stop")]
            ),
        ]
    )
    client = ZhipuClient(api_key="zhipu-test-key", model="glm-5")
    client._client = types.SimpleNamespace(  # noqa: SLF001
        chat=types.SimpleNamespace(completions=completions)
    )

    chunks: list[LLMChunk] = []
    with pytest.raises(httpx.RemoteProtocolError):
        async for chunk in client.chat([{"role": "user", "content": "hi"}]):
            chunks.append(chunk)

    assert completions.calls == 1
    assert [chunk.text for chunk in chunks] == ["partial"]


@pytest.mark.asyncio
async def test_openai_compatible_client_raises_after_stream_retry_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """连续流式断开超过上限后，应抛出最后一次异常。"""
    monkeypatch.setattr(settings, "llm_stream_retries", 2, raising=False)
    sleep_mock = AsyncMock()
    monkeypatch.setattr("nini.agent.providers.openai_provider.asyncio.sleep", sleep_mock)
    completions = _FakeOpenAICompletions(
        [
            _FakeOpenAIStream(error_before_chunks=httpx.ReadError("read failed")),
            _FakeOpenAIStream(error_before_chunks=httpx.ReadError("read failed")),
            _FakeOpenAIStream(error_before_chunks=httpx.ReadError("read failed")),
        ]
    )
    client = ZhipuClient(api_key="zhipu-test-key", model="glm-5")
    client._client = types.SimpleNamespace(  # noqa: SLF001
        chat=types.SimpleNamespace(completions=completions)
    )

    with pytest.raises(httpx.ReadError, match="read failed"):
        _ = [chunk async for chunk in client.chat([{"role": "user", "content": "hi"}])]

    assert completions.calls == 3
    assert sleep_mock.await_count == 2


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
    assert client._client is not None  # noqa: SLF001
    typed_client = cast(Any, client._client)
    assert client._http_client.kwargs["trust_env"] is False  # noqa: SLF001
    assert typed_client.kwargs["http_client"] is client._http_client  # noqa: SLF001
    assert typed_client.kwargs["max_retries"] == 3  # noqa: SLF001

    underlying_client = cast(Any, client._client)  # noqa: SLF001
    await client.aclose()

    assert underlying_client is not None
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


@pytest.mark.asyncio
async def test_openai_compatible_client_dumps_payload_when_create_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """create 抛错时应写入 payload dump 并把路径附到异常对象。"""

    class _FakeCompletions:
        async def create(self, **kwargs: Any) -> Any:
            raise RuntimeError("messages 参数非法")

    class _FakeChat:
        def __init__(self) -> None:
            self.completions = _FakeCompletions()

    client = ZhipuClient(api_key="zhipu-test-key", model="glm-5")
    client._client = types.SimpleNamespace(chat=_FakeChat())  # noqa: SLF001

    monkeypatch.setattr(
        "nini.agent.providers.openai_provider.dump_chat_payload_debug",
        lambda **kwargs: tmp_path / "dump.json",
    )

    with pytest.raises(RuntimeError) as exc_info:
        _ = [chunk async for chunk in client.chat([{"role": "user", "content": "hi"}])]

    assert str(getattr(exc_info.value, "debug_dump_path", "")) == str(tmp_path / "dump.json")


# ---- API 方法覆盖测试 ----


def test_get_active_models_returns_active_model_info() -> None:
    """get_active_models 应返回默认用途的活跃模型信息。"""
    resolver = ModelResolver(
        clients=[
            FakeClient(provider_id="zhipu", model="glm-4", available=True),
            FakeClient(provider_id="openai", model="gpt-4", available=True),
        ]
    )
    resolver.set_preferred_provider("openai")

    active = resolver.get_active_models()

    assert active["provider_id"] == "openai"
    assert active["model"] == "gpt-4"


def test_get_available_models_returns_models_for_provider() -> None:
    """get_available_models 应返回指定提供商的可用模型列表。"""
    resolver = ModelResolver(
        clients=[
            FakeClient(provider_id="zhipu", model="glm-4", available=True),
        ]
    )

    result = resolver.get_available_models("zhipu")

    assert result["provider_id"] == "zhipu"
    assert "glm-4" in result["models"]


def test_get_available_models_returns_empty_for_unknown_provider() -> None:
    """get_available_models 对未知提供商应返回空列表。"""
    resolver = ModelResolver(clients=[])

    result = resolver.get_available_models("unknown")

    assert result["provider_id"] == "unknown"
    assert result["models"] == []


def test_set_priorities_reorders_clients() -> None:
    """set_priorities 应根据优先级重新排序客户端。"""
    resolver = ModelResolver(
        clients=[
            FakeClient(provider_id="openai", available=True),
            FakeClient(provider_id="zhipu", available=True),
            FakeClient(provider_id="deepseek", available=True),
        ]
    )

    resolver.set_priorities({"zhipu": 0, "deepseek": 1, "openai": 2})

    ordered = [c.provider_id for c in resolver._clients]
    assert ordered[0] == "zhipu"
    assert ordered[1] == "deepseek"
    assert ordered[2] == "openai"


def test_get_routing_config_returns_config() -> None:
    """get_routing_config 应返回路由配置。"""
    resolver = ModelResolver(
        clients=[
            FakeClient(provider_id="zhipu", available=True),
        ]
    )
    resolver.set_preferred_provider("zhipu")
    resolver.set_purpose_route("coding", provider_id="deepseek", model="deepseek-coder")

    config = resolver.get_routing_config()

    assert config["preferred_provider"] == "zhipu"
    assert config["purpose_routes"]["coding"]["provider_id"] == "deepseek"
    assert config["purpose_routes"]["coding"]["model"] == "deepseek-coder"


def test_set_routing_config_updates_routes() -> None:
    """set_routing_config 应更新路由配置。"""
    resolver = ModelResolver(clients=[])

    resolver.set_routing_config(
        {
            "preferred_provider": "zhipu",
            "purpose_routes": {
                "coding": {"provider_id": "deepseek", "model": "deepseek-coder", "base_url": None},
                "vision": {"provider_id": "openai", "model": "gpt-4o", "base_url": None},
            },
        }
    )

    assert resolver.get_preferred_provider() == "zhipu"
    assert resolver.get_preferred_provider("coding") == "deepseek"
    assert resolver.get_preferred_provider("vision") == "openai"


@pytest.mark.asyncio
async def test_test_connection_returns_success_for_available() -> None:
    """test_connection 对可用提供商应返回成功。"""
    resolver = ModelResolver(
        clients=[
            FakeClient(provider_id="zhipu", model="glm-4", available=True),
        ]
    )

    result = await resolver.test_connection("zhipu")

    assert result["success"] is True
    assert result["provider"] == "zhipu"


@pytest.mark.asyncio
async def test_test_connection_prefers_remote_available_model_for_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """测试连接在未显式指定模型时，应优先使用远端返回的可用模型。"""
    resolver = ModelResolver(clients=[])

    async def _fake_list_available_models(*args, **kwargs):  # type: ignore[no-untyped-def]
        return {
            "models": ["qwen-coder-plus", "qwen-plus"],
            "source": "remote",
            "supports_remote_listing": True,
        }

    def _fake_build(
        provider_id: str,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ):  # type: ignore[no-untyped-def]
        return FakeClient(
            provider_id=provider_id,
            model=model or "fallback-model",
            available=True,
            chunks=[LLMChunk(text="ok")],
        )

    monkeypatch.setattr(
        "nini.agent.model_lister.list_available_models",
        _fake_list_available_models,
    )
    monkeypatch.setattr(resolver, "_build_client_for_provider", _fake_build)

    result = await resolver.test_connection(
        "dashscope",
        api_key="sk-test",
        base_url="https://coding.dashscope.aliyuncs.com/v1",
    )

    assert result["success"] is True
    assert result["model"] == "qwen-coder-plus"


@pytest.mark.asyncio
async def test_test_connection_falls_back_to_static_available_model_for_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """远端模型列表不可用时，测试连接应回退到静态候选中的首个模型。"""
    resolver = ModelResolver(clients=[])

    async def _fake_list_available_models(*args, **kwargs):  # type: ignore[no-untyped-def]
        return {
            "models": ["qwen3-coder-plus", "qwen3-max-2026-01-23"],
            "source": "static",
            "supports_remote_listing": False,
        }

    def _fake_build(
        provider_id: str,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ):  # type: ignore[no-untyped-def]
        return FakeClient(
            provider_id=provider_id,
            model=model or "fallback-model",
            available=True,
            chunks=[LLMChunk(text="ok")],
        )

    monkeypatch.setattr(
        "nini.agent.model_lister.list_available_models",
        _fake_list_available_models,
    )
    monkeypatch.setattr(resolver, "_build_client_for_provider", _fake_build)

    result = await resolver.test_connection(
        "dashscope",
        api_key="sk-test",
        base_url="https://coding.dashscope.aliyuncs.com/v1",
    )

    assert result["success"] is True
    assert result["model"] == "qwen3-coder-plus"


@pytest.mark.asyncio
async def test_test_connection_does_not_use_static_fallback_when_remote_listing_supported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """支持远端模型列表的服务商，拉取失败时不应再拿静态模型硬试。"""
    resolver = ModelResolver(clients=[])
    captured: dict[str, str | None] = {}

    async def _fake_list_available_models(*args, **kwargs):  # type: ignore[no-untyped-def]
        return {
            "models": ["qwen-plus", "qwen-turbo"],
            "source": "static",
            "supports_remote_listing": True,
        }

    def _fake_build(
        provider_id: str,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ):  # type: ignore[no-untyped-def]
        captured["model"] = model
        return FakeClient(
            provider_id=provider_id,
            model=model or "settings-default-model",
            available=True,
            chunks=[LLMChunk(text="ok")],
        )

    monkeypatch.setattr(
        "nini.agent.model_lister.list_available_models",
        _fake_list_available_models,
    )
    monkeypatch.setattr(resolver, "_build_client_for_provider", _fake_build)

    result = await resolver.test_connection(
        "dashscope",
        api_key="sk-test",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )

    assert result["success"] is True
    assert captured["model"] is None


@pytest.mark.asyncio
async def test_test_connection_returns_failure_for_unavailable() -> None:
    """test_connection 对不可用提供商应返回失败。"""
    resolver = ModelResolver(
        clients=[
            FakeClient(provider_id="zhipu", available=False),
        ]
    )

    result = await resolver.test_connection("zhipu")

    assert result["success"] is False


@pytest.mark.asyncio
async def test_test_connection_returns_failure_for_unknown() -> None:
    """test_connection 对未知提供商应返回失败。"""
    resolver = ModelResolver(clients=[])

    result = await resolver.test_connection("unknown")

    assert result["success"] is False
    assert "unknown" in result["error"]


def test_set_preferred_model_sets_provider_and_model() -> None:
    """set_preferred_model 应同时设置提供商和模型。"""
    resolver = ModelResolver(
        clients=[
            FakeClient(provider_id="zhipu", model="glm-default", available=True),
        ]
    )

    resolver.set_preferred_model("zhipu", "glm-4-flash")

    assert resolver.get_preferred_provider() == "zhipu"
    # 验证路由配置中的模型也被设置
    routes = resolver.get_purpose_routes()
    assert routes["default"]["model"] == "glm-4-flash"


def test_get_preferred_providers_by_purpose_returns_all() -> None:
    """get_preferred_providers_by_purpose 应返回所有用途的首选提供商。"""
    resolver = ModelResolver(clients=[])
    resolver.set_preferred_provider("zhipu")
    resolver.set_preferred_provider("deepseek", purpose="coding")
    resolver.set_preferred_provider("openai", purpose="vision")

    providers = resolver.get_preferred_providers_by_purpose()

    assert providers["default"] == "zhipu"
    assert providers["coding"] == "deepseek"
    assert providers["vision"] == "openai"


def test_get_purpose_routes_returns_copy() -> None:
    """get_purpose_routes 应返回路由配置的副本。"""
    resolver = ModelResolver(clients=[])
    resolver.set_purpose_route("coding", provider_id="deepseek", model="deepseek-coder")

    routes1 = resolver.get_purpose_routes()
    routes2 = resolver.get_purpose_routes()

    # 验证是副本而不是同一对象
    assert routes1 is not routes2
    assert routes1["coding"] == routes2["coding"]


def test_get_active_model_info_uses_purpose_route_model() -> None:
    """get_active_model_info 应优先使用 purpose route 中配置的模型，而非客户端默认模型。"""
    resolver = ModelResolver(
        clients=[
            FakeClient(provider_id="zhipu", model="glm-5", available=True),
        ]
    )
    # 设置 purpose route 使用不同的模型
    resolver.set_purpose_route("chat", provider_id="zhipu", model="glm-4-flash")

    # 获取 chat 用途的模型信息
    info = resolver.get_active_model_info(purpose="chat")

    # 应返回 purpose route 中配置的模型，而不是客户端默认模型
    assert info["provider_id"] == "zhipu"
    assert info["model"] == "glm-4-flash"


def test_get_active_model_info_falls_back_to_client_model() -> None:
    """当 purpose route 没有配置模型时，get_active_model_info 应回退到客户端默认模型。"""
    resolver = ModelResolver(
        clients=[
            FakeClient(provider_id="zhipu", model="glm-5", available=True),
        ]
    )
    # 只设置 provider，不设置 model
    resolver.set_purpose_route("chat", provider_id="zhipu", model=None)

    info = resolver.get_active_model_info(purpose="chat")

    # 应返回客户端默认模型
    assert info["provider_id"] == "zhipu"
    assert info["model"] == "glm-5"


def test_get_active_model_info_inherits_chat_route_for_planning() -> None:
    """planning 未配置时，展示信息应继承 chat 路由。"""
    resolver = ModelResolver(
        clients=[
            FakeClient(provider_id="zhipu", model="glm-5", available=True),
        ]
    )
    resolver.set_purpose_route("chat", provider_id="zhipu", model="glm-5")

    info = resolver.get_active_model_info(purpose="planning")

    assert info["provider_id"] == "zhipu"
    assert info["model"] == "glm-5"


def test_model_resolver_load_builtin_api_key_from_packaged_blob(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """运行时应从已打包模块解密内置 Key，而非依赖 scripts 目录。"""
    encrypted = encrypt_key("sk-builtin-123")
    module = types.ModuleType("nini._builtin_key")
    setattr(module, "ENCRYPTED_BUILTIN_KEY", encrypted)
    monkeypatch.setitem(sys.modules, "nini._builtin_key", module)
    monkeypatch.setattr("nini.agent.model_resolver.settings.builtin_dashscope_api_key", "")
    monkeypatch.setattr("nini.agent.model_resolver.settings.dashscope_api_key", "")

    assert ModelResolver._load_builtin_api_key() == "sk-builtin-123"  # noqa: SLF001


def test_model_resolver_load_trial_api_key_from_packaged_blob(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """运行时应支持从打包模块读取试用密钥。"""
    encrypted = encrypt_key("sk-trial-123")
    module = types.ModuleType("nini._builtin_key")
    setattr(module, "ENCRYPTED_TRIAL_KEY", encrypted)
    monkeypatch.setitem(sys.modules, "nini._builtin_key", module)
    monkeypatch.setattr("nini.agent.model_resolver.settings.trial_api_key", "")

    assert ModelResolver._load_trial_api_key() == "sk-trial-123"  # noqa: SLF001


def test_get_model_context_window_claude():
    """Claude 模型应返回 200K context window。"""
    client = FakeClient(provider_id="anthropic", model="claude-3-5-sonnet-20241022", available=True)
    resolver = ModelResolver(clients=[client])
    resolver._active_provider_id = "anthropic"
    assert resolver.get_model_context_window() == 200_000


def test_get_model_context_window_gpt4o():
    """GPT-4o 模型应返回 128K context window。"""
    client = FakeClient(provider_id="openai", model="gpt-4o-2024-08-06", available=True)
    resolver = ModelResolver(clients=[client])
    resolver._active_provider_id = "openai"
    assert resolver.get_model_context_window() == 128_000


def test_get_model_context_window_deepseek():
    """DeepSeek 模型应返回 64K context window。"""
    client = FakeClient(provider_id="deepseek", model="deepseek-chat", available=True)
    resolver = ModelResolver(clients=[client])
    resolver._active_provider_id = "deepseek"
    assert resolver.get_model_context_window() == 64_000


def test_get_model_context_window_unknown_model():
    """未知模型应返回 None。"""
    client = FakeClient(provider_id="custom", model="my-custom-llm-v1", available=True)
    resolver = ModelResolver(clients=[client])
    resolver._active_provider_id = "custom"
    assert resolver.get_model_context_window() is None


def test_get_model_context_window_no_active_client():
    """无活跃客户端时应返回 None。"""
    resolver = ModelResolver(clients=[])
    assert resolver.get_model_context_window() is None
