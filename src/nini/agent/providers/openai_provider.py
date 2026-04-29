"""OpenAI Compatible Provider.

OpenAI API adapter and compatible providers.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
from typing import Any, AsyncGenerator

import httpx
import openai

from nini.config import settings

from .base import BaseLLMClient, LLMChunk, ReasoningStreamParser, match_first_model

logger = logging.getLogger(__name__)


def _merge_tool_arguments(existing: str, incoming: str) -> str:
    """聚合 tool arguments 片段，兼容增量与累计两种流式实现。"""
    if not incoming:
        return existing
    if not existing:
        return incoming
    if incoming == existing:
        return existing
    # 累计片段：新值已包含旧值，直接替换避免重复拼接。
    if incoming.startswith(existing) or existing in incoming:
        return incoming
    # 重复回放：旧值尾部已包含较长新片段，不重复追加。
    # 单字符分片可能是合法增量，例如工具参数里的 `n = len(...)`，
    # 不能仅因历史文本也以 `n` 结尾就吞掉。
    if len(incoming) > 1 and existing.endswith(incoming):
        return existing
    # 增量片段：正常追加。
    return existing + incoming


def _sanitize_debug_filename(value: str, *, fallback: str) -> str:
    """将调试文件名收紧到安全字符集合。"""
    normalized = re.sub(r"[^0-9A-Za-z._-]+", "-", value.strip())
    normalized = normalized.strip("-._")
    return normalized or fallback


def _normalize_tool_call_for_provider(tool_call: Any) -> dict[str, Any] | None:
    """仅保留 tool_call 的协议字段，丢弃兼容提供商不接受的附加元数据。"""
    if not isinstance(tool_call, dict):
        return None

    function_raw = tool_call.get("function")
    if not isinstance(function_raw, dict):
        return None

    name = str(function_raw.get("name") or "").strip()
    if not name:
        return None

    arguments = function_raw.get("arguments")
    if arguments is None:
        arguments_text = ""
    elif isinstance(arguments, str):
        arguments_text = arguments
    else:
        arguments_text = json.dumps(arguments, ensure_ascii=False, default=str)

    normalized: dict[str, Any] = {
        "type": "function",
        "function": {
            "name": name,
            "arguments": arguments_text,
        },
    }

    tool_call_id = str(tool_call.get("id") or "").strip()
    if tool_call_id:
        normalized["id"] = tool_call_id

    return normalized


def summarize_messages_for_debug(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """生成消息结构摘要，避免在日志中直接输出大段正文。"""
    summary: list[dict[str, Any]] = []
    for index, message in enumerate(messages, start=1):
        item: dict[str, Any] = {
            "index": index,
            "role": str(message.get("role") or "").strip(),
            "keys": sorted(str(key) for key in message.keys()),
            "content_len": len(
                "" if message.get("content") is None else str(message.get("content"))
            ),
        }

        tool_calls_raw = message.get("tool_calls")
        if isinstance(tool_calls_raw, list) and tool_calls_raw:
            item["tool_call_count"] = len(tool_calls_raw)
            item["tool_call_ids"] = [
                str(tool_call.get("id") or "").strip()
                for tool_call in tool_calls_raw
                if isinstance(tool_call, dict)
            ]
            item["tool_call_names"] = [
                str((tool_call.get("function") or {}).get("name") or "").strip()
                for tool_call in tool_calls_raw
                if isinstance(tool_call, dict) and isinstance(tool_call.get("function"), dict)
            ]
            item["tool_call_extra_keys"] = [
                sorted(key for key in tool_call.keys() if key not in {"id", "type", "function"})
                for tool_call in tool_calls_raw
                if isinstance(tool_call, dict)
            ]
            item["tool_function_extra_keys"] = [
                sorted(
                    key for key in tool_call["function"].keys() if key not in {"name", "arguments"}
                )
                for tool_call in tool_calls_raw
                if isinstance(tool_call, dict) and isinstance(tool_call.get("function"), dict)
            ]

        tool_call_id = str(message.get("tool_call_id") or "").strip()
        if tool_call_id:
            item["tool_call_id"] = tool_call_id

        summary.append(item)
    return summary


def total_message_content_length(messages: list[dict[str, Any]]) -> int:
    """统计消息正文总字符数。"""
    return sum(
        len("" if message.get("content") is None else str(message.get("content")))
        for message in messages
    )


def dump_chat_payload_debug(
    *,
    provider_id: str,
    model: str | None,
    base_url: str | None,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    temperature: float,
    max_tokens: int,
    error: Exception,
    debug_dir: Path | None = None,
) -> Path:
    """将失败请求写入本地调试文件，便于离线复盘。"""
    timestamp = datetime.now(timezone.utc)
    target_dir = debug_dir or (settings.data_dir / "debug" / "llm")
    target_dir.mkdir(parents=True, exist_ok=True)

    provider_part = _sanitize_debug_filename(provider_id, fallback="provider")
    model_part = _sanitize_debug_filename(model or "unknown", fallback="model")
    file_name = f"{timestamp.strftime('%Y%m%dT%H%M%S.%fZ')}_{provider_part}_{model_part}.json"
    file_path = target_dir / file_name

    payload = {
        "timestamp": timestamp.isoformat(),
        "provider_id": provider_id,
        "model": model,
        "base_url": base_url,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "tools_count": len(tools or []),
        "message_count": len(messages),
        "total_content_len": total_message_content_length(messages),
        "messages_summary": summarize_messages_for_debug(messages),
        "messages": messages,
        "tools": tools or [],
        "error_type": type(error).__name__,
        "error": str(error),
    }
    file_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return file_path


def _is_retryable_stream_error(exc: Exception) -> bool:
    """判断 OpenAI 兼容流式调用是否属于可重试的瞬态错误。"""
    if isinstance(
        exc,
        (
            httpx.RemoteProtocolError,
            httpx.ReadError,
            httpx.WriteError,
            openai.APIConnectionError,
        ),
    ):
        return True
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if isinstance(status_code, int):
        return status_code in {502, 504}
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {502, 504}
    return False


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
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._client: Any | None = None
        self._http_client: Any | None = None

    def _ensure_client(self) -> None:
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

    def _normalize_messages_for_provider(
        self,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """在发请求前收紧消息字段，避免兼容提供商拒绝非协议字段。"""
        normalized: list[dict[str, Any]] = []
        for message in messages:
            role = str(message.get("role") or "").strip()
            if role not in {"system", "user", "assistant", "tool"}:
                continue

            if role == "assistant":
                item: dict[str, Any] = {
                    "role": "assistant",
                    "content": (
                        "" if message.get("content") is None else str(message.get("content"))
                    ),
                }
                tool_calls = message.get("tool_calls")
                if tool_calls:
                    normalized_tool_calls = [
                        normalized_tool_call
                        for tool_call in tool_calls
                        if (normalized_tool_call := _normalize_tool_call_for_provider(tool_call))
                        is not None
                    ]
                    if normalized_tool_calls:
                        item["tool_calls"] = normalized_tool_calls
                        # DeepSeek thinking 模式要求带 tool_calls 的 assistant 历史
                        # 必须回传上一轮的 reasoning_content；其它 OpenAI 兼容
                        # 提供商通常忽略未知字段，因此在基类透传是安全的。
                        reasoning_content = message.get("reasoning_content")
                        if reasoning_content:
                            item["reasoning_content"] = str(reasoning_content)
                normalized.append(item)
                continue

            item = {
                "role": role,
                "content": "" if message.get("content") is None else str(message.get("content")),
            }
            if role == "tool" and message.get("tool_call_id"):
                item["tool_call_id"] = str(message.get("tool_call_id"))
            normalized.append(item)
        return normalized

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

        normalized_messages = self._normalize_messages_for_provider(messages)
        message_summary = summarize_messages_for_debug(normalized_messages)
        logger.debug(
            "准备调用 LLM provider=%s model=%s base_url=%s tools=%d temperature=%s max_tokens=%d messages=%s",
            self.provider_id,
            self._model,
            self._base_url,
            len(tools or []),
            temperature,
            max_tokens,
            json.dumps(message_summary, ensure_ascii=False),
        )

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": normalized_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if self._supports_stream_usage():
            kwargs["stream_options"] = {"include_usage": True}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        max_stream_retries = max(0, int(settings.llm_stream_retries))
        for attempt in range(max_stream_retries + 1):
            chunks_emitted = 0
            parser = ReasoningStreamParser(enable_tag_split=self._supports_reasoning_tags())
            pending_tool_calls: dict[int, dict[str, Any]] = {}

            try:
                stream = await self._client.chat.completions.create(**kwargs)

                async for chunk in stream:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    finish = chunk.choices[0].finish_reason if chunk.choices else None

                    text = ""
                    reasoning = ""
                    raw_text = ""
                    tool_calls_out: list[dict[str, Any]] = []

                    if delta:
                        raw_piece = getattr(delta, "content", "") or ""
                        explicit_reasoning = ReasoningStreamParser.extract_reasoning_from_delta(
                            delta
                        )
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
                                        entry["function"]["arguments"] = _merge_tool_arguments(
                                            str(entry["function"]["arguments"]),
                                            str(tc.function.arguments),
                                        )

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

                    chunks_emitted += 1
                    yield LLMChunk(
                        text=text,
                        reasoning=reasoning,
                        raw_text=raw_text,
                        tool_calls=tool_calls_out,
                        finish_reason=finish,
                        usage=usage,
                    )
                return
            except Exception as exc:
                can_retry = (
                    chunks_emitted == 0
                    and attempt < max_stream_retries
                    and _is_retryable_stream_error(exc)
                )
                if can_retry:
                    delay = min(0.5 * (2**attempt), 4.0)
                    logger.warning(
                        "LLM 流式读取失败，准备同 provider 重试: provider=%s model=%s attempt=%d delay=%.1fs reason=%s",
                        self.provider_id,
                        self._model,
                        attempt + 1,
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)
                    continue

                if chunks_emitted == 0:
                    dump_path = dump_chat_payload_debug(
                        provider_id=self.provider_id,
                        model=self._model,
                        base_url=self._base_url,
                        messages=normalized_messages,
                        tools=tools,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        error=exc,
                    )
                    setattr(exc, "debug_dump_path", str(dump_path))
                    logger.warning(
                        "LLM 请求失败，已写入调试 payload: provider=%s model=%s dump=%s reason=%s",
                        self.provider_id,
                        self._model,
                        dump_path,
                        exc,
                    )
                raise

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

    def pick_model_for_purpose(self, purpose: str) -> str | None:
        if purpose != "title_generation":
            return None
        return match_first_model(
            list(getattr(self, "_available_models_cache", [])),
            [("mini",), ("gpt-4.1",), ("gpt-4o",)],
        )
