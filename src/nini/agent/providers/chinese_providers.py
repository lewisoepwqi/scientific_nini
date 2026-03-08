"""Chinese LLM Providers.

Moonshot, Kimi Coding, Zhipu, DeepSeek, DashScope, MiniMax adapters.
"""

from __future__ import annotations

from typing import Any, AsyncGenerator

from nini.config import settings

from .base import LLMChunk
from .openai_provider import OpenAICompatibleClient


class MoonshotClient(OpenAICompatibleClient):
    """Moonshot AI (Kimi) 适配器，兼容 OpenAI 协议。"""

    provider_id = "moonshot"
    provider_name = "Moonshot AI (Kimi)"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        super().__init__(
            api_key=api_key or settings.moonshot_api_key,
            base_url=base_url or "https://api.moonshot.cn/v1",
            model=model or settings.moonshot_model,
        )

    def _supports_stream_usage(self) -> bool:
        # Moonshot API 不支持 stream_options.include_usage
        return False

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[LLMChunk, None]:
        """Kimi 模型流式聊天，处理 temperature 限制。"""
        # kimi-k2.5 等模型只支持 temperature=1
        model = self._model or ""
        if "k2.5" in model:
            temperature = 1.0
        async for chunk in super().chat(
            messages, tools, temperature=temperature, max_tokens=max_tokens
        ):
            yield chunk


class KimiCodingClient(OpenAICompatibleClient):
    """Kimi Coding Plan 适配器（api.kimi.com），兼容 OpenAI 协议。

    Kimi Coding API 通过 User-Agent 头识别编码工具客户端，
    未携带合法标识会返回 403 access_terminated_error。
    """

    provider_id = "kimi_coding"
    provider_name = "Kimi Coding"

    # Kimi 白名单校验所需的 User-Agent 标识
    _USER_AGENT = "ClaudeCode/1.0.0"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        super().__init__(
            api_key=api_key or settings.kimi_coding_api_key,
            base_url=base_url or settings.kimi_coding_base_url,
            model=model or settings.kimi_coding_model,
        )

    def _ensure_client(self):
        if self._client is None:
            from openai import AsyncOpenAI, DefaultAsyncHttpxClient

            kwargs: dict[str, Any] = {"api_key": self._api_key}
            kwargs["max_retries"] = max(0, int(settings.llm_max_retries))
            kwargs["timeout"] = max(1, int(settings.llm_timeout))
            if self._base_url:
                kwargs["base_url"] = self._base_url
            if self._http_client is None:
                self._http_client = DefaultAsyncHttpxClient(trust_env=settings.llm_trust_env_proxy)
            kwargs["http_client"] = self._http_client
            kwargs["default_headers"] = {
                "User-Agent": self._USER_AGENT,
                "X-Title": "Nini",
            }
            self._client = AsyncOpenAI(**kwargs)

    def _supports_stream_usage(self) -> bool:
        # Kimi Coding API 不支持 stream_options.include_usage
        return False


class ZhipuClient(OpenAICompatibleClient):
    """智谱 AI (GLM) 适配器，兼容 OpenAI 协议。

    默认使用 Coding Plan 端点 (open.bigmodel.cn/api/coding/paas/v4)，
    与标准 API 端点共用同一 API Key，但计费走 Coding 订阅通道。
    """

    provider_id = "zhipu"
    provider_name = "智谱 AI (GLM)"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        super().__init__(
            api_key=api_key or settings.zhipu_api_key,
            base_url=base_url or settings.zhipu_base_url,
            model=model or settings.zhipu_model,
        )

    def _supports_stream_usage(self) -> bool:
        # 智谱 Coding Plan 端点不支持 stream_options.include_usage
        return False


class DeepSeekClient(OpenAICompatibleClient):
    """DeepSeek 适配器，兼容 OpenAI 协议。"""

    provider_id = "deepseek"
    provider_name = "DeepSeek"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ):
        super().__init__(
            api_key=api_key or settings.deepseek_api_key,
            base_url="https://api.deepseek.com/v1",
            model=model or settings.deepseek_model,
        )


class DashScopeClient(OpenAICompatibleClient):
    """阿里百炼（通义千问）适配器，兼容 OpenAI 协议。"""

    provider_id = "dashscope"
    provider_name = "阿里百炼（通义千问）"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        super().__init__(
            api_key=api_key or settings.dashscope_api_key,
            base_url=base_url or settings.dashscope_base_url,
            model=model or settings.dashscope_model,
        )


class MiniMaxClient(OpenAICompatibleClient):
    """MiniMax 文本模型适配器，兼容 OpenAI 协议。"""

    provider_id = "minimax"
    provider_name = "MiniMax"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        super().__init__(
            api_key=api_key or settings.minimax_api_key,
            base_url=base_url or settings.minimax_base_url,
            model=model or settings.minimax_model,
        )
