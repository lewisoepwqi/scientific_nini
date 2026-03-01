"""OpenAI Compatible Provider.

OpenAI API adapter and compatible providers.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator

from nini.config import settings

from .base import BaseLLMClient, LLMChunk, ReasoningStreamParser

logger = logging.getLogger(__name__)


class OpenAICompatibleClient(BaseLLMClient):
    """OpenAI 兼容 API 适配器基类（OpenAI / Ollama 共用）。"""

    provider_id: str = "openai_compatible"
    provider_name: str = "OpenAI Compatible"

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str | None,
        model: str | None,
    ):
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._client = None
        self._http_client = None

    def _ensure_client(self):
        if self._client is None:
            from openai import AsyncOpenAI, DefaultAsyncHttpxClient

            kwargs: dict[str, Any] = {"api_key": self._api_key}
            kwargs["max_retries"] = max(0, int(settings.llm_max_retries))
            kwargs["timeout"] = max(1, int(settings.llm_timeout))
            if self._base_url:
                kwargs["base_url"] = self._base_url
            # 显式传入默认 httpx 客户端，避免 SDK 内部 wrapper 在 GC 时
            # 触发 `AsyncHttpxClientWrapper._mounts` 兼容性异常。
            if self._http_client is None:
                # 默认不读取系统代理环境变量，避免 ALL_PROXY/HTTPS_PROXY
                # 意外注入导致的 socksio 依赖报错。
                self._http_client = DefaultAsyncHttpxClient(trust_env=settings.llm_trust_env_proxy)
            kwargs["http_client"] = self._http_client
            self._client = AsyncOpenAI(**kwargs)

    def is_available(self) -> bool:
        return bool(self._api_key and self._model)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[LLMChunk, None]:
        self._ensure_client()
        assert self._client is not None

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if self._supports_stream_usage():
            kwargs["stream_options"] = {"include_usage": True}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        stream = await self._client.chat.completions.create(**kwargs)
        parser = ReasoningStreamParser(enable_tag_split=self._supports_reasoning_tags())

        # 聚合 tool_calls 片段
        pending_tool_calls: dict[int, dict[str, Any]] = {}

        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            finish = chunk.choices[0].finish_reason if chunk.choices else None

            text = ""
            reasoning = ""
            raw_text = ""
            tool_calls_out: list[dict[str, Any]] = []

            if delta:
                raw_piece = getattr(delta, "content", "") or ""
                explicit_reasoning = ReasoningStreamParser.extract_reasoning_from_delta(delta)
                text, reasoning, raw_text = parser.consume(
                    raw_piece=str(raw_piece),
                    explicit_reasoning_piece=explicit_reasoning,
                )

                # 聚合 tool_calls 的分段
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in pending_tool_calls:
                            pending_tool_calls[idx] = {
                                "id": tc.id or "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            }
                        entry = pending_tool_calls[idx]
                        if tc.id:
                            entry["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                entry["function"]["name"] = tc.function.name
                            if tc.function.arguments:
                                entry["function"]["arguments"] += tc.function.arguments

            # 当 finish_reason 为 tool_calls 时，输出完整的 tool_calls
            if finish == "tool_calls":
                tool_calls_out = list(pending_tool_calls.values())
                pending_tool_calls.clear()

            usage = None
            if chunk.usage:
                usage = {
                    "input_tokens": chunk.usage.prompt_tokens or 0,
                    "output_tokens": chunk.usage.completion_tokens or 0,
                }

            yield LLMChunk(
                text=text,
                reasoning=reasoning,
                raw_text=raw_text,
                tool_calls=tool_calls_out,
                finish_reason=finish,
                usage=usage,
            )

    async def aclose(self) -> None:
        """关闭底层 AsyncOpenAI 客户端，避免 GC 时 _mounts 属性缺失错误。"""
        try:
            if self._client is not None:
                await self._client.close()
            elif self._http_client is not None:
                await self._http_client.aclose()
        except AttributeError as e:
            # 兼容某些 SDK/httpx 组合下的析构噪音，不影响主流程。
            if "_mounts" not in str(e):
                raise
            logger.warning("关闭 %s 客户端时忽略 _mounts 兼容性异常: %s", self.provider_id, e)
        finally:
            self._client = None
            self._http_client = None

    def _supports_stream_usage(self) -> bool:
        """是否支持 stream_options.include_usage。"""
        return True

    def _supports_reasoning_tags(self) -> bool:
        """是否启用 `<think>` 等标签解析（用于兼容国产推理模型）。"""
        model = (self._model or "").lower()
        if any(
            key in model
            for key in (
                "qwen",
                "qwq",
                "deepseek",
                "r1",
                "reasoner",
                "kimi",
                "moonshot",
                "glm",
                "chatglm",
                "minimax",
                "m1",
                "m2",
                "think",
            )
        ):
            return True
        return self.provider_id in {
            "moonshot",
            "kimi_coding",
            "zhipu",
            "deepseek",
            "dashscope",
            "minimax",
            "ollama",
        }


class OpenAIClient(OpenAICompatibleClient):
    """OpenAI API 适配器。"""

    provider_id = "openai"
    provider_name = "OpenAI"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        super().__init__(
            api_key=api_key or settings.openai_api_key,
            base_url=base_url or settings.openai_base_url,
            model=model or settings.openai_model,
        )
