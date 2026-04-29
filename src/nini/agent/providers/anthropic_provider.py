"""Anthropic Provider.

Anthropic Claude API adapter.
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncGenerator

from nini.config import settings

from .base import BaseLLMClient, LLMChunk, match_first_model

logger = logging.getLogger(__name__)


class AnthropicClient(BaseLLMClient):
    """Anthropic Claude 适配器。"""

    provider_id = "anthropic"
    provider_name = "Anthropic Claude"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ):
        self._api_key = api_key or settings.anthropic_api_key
        self._model = model or settings.anthropic_model
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            from anthropic import AsyncAnthropic

            self._client = AsyncAnthropic(
                api_key=self._api_key,
                timeout=max(1, int(settings.llm_timeout)),
            )

    def is_available(self) -> bool:
        return bool(self._api_key and self._model)

    def pick_model_for_purpose(self, purpose: str) -> str | None:
        if purpose != "title_generation":
            return None
        return match_first_model(
            list(getattr(self, "_available_models_cache", [])),
            [("haiku",), ("sonnet",)],
        )

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

        system_prompt, anthropic_messages = self._convert_messages(messages)
        anthropic_tools = self._convert_tools(tools)

        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": anthropic_messages,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools

        response = await self._client.messages.create(**kwargs)

        text_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for block in getattr(response, "content", []) or []:
            b_type = getattr(block, "type", "")
            if b_type == "text":
                text_parts.append(getattr(block, "text", ""))
            elif b_type in {"thinking", "reasoning"}:
                reasoning_text = (
                    getattr(block, "thinking", None)
                    or getattr(block, "text", None)
                    or getattr(block, "content", None)
                )
                if isinstance(reasoning_text, str) and reasoning_text:
                    reasoning_parts.append(reasoning_text)
            elif b_type == "tool_use":
                tool_calls.append(
                    {
                        "id": getattr(block, "id", ""),
                        "type": "function",
                        "function": {
                            "name": getattr(block, "name", ""),
                            "arguments": json.dumps(
                                getattr(block, "input", {}) or {},
                                ensure_ascii=False,
                            ),
                        },
                    }
                )

        usage_obj = getattr(response, "usage", None)
        usage = None
        if usage_obj is not None:
            usage = {
                "input_tokens": int(getattr(usage_obj, "input_tokens", 0) or 0),
                "output_tokens": int(getattr(usage_obj, "output_tokens", 0) or 0),
            }

        finish_reason = getattr(response, "stop_reason", None)
        text = "".join(text_parts)
        yield LLMChunk(
            text=text,
            reasoning="".join(reasoning_parts),
            raw_text=text,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
        )

    async def aclose(self) -> None:
        """关闭底层 AsyncAnthropic 客户端。"""
        if self._client is not None:
            await self._client.close()
            self._client = None

    def _convert_messages(self, messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
        """将 OpenAI 消息格式转换为 Anthropic 消息格式。"""
        system_parts: list[str] = []
        out: list[dict[str, Any]] = []

        for msg in messages:
            role = str(msg.get("role", "user"))
            if role == "system":
                content = msg.get("content")
                if content:
                    system_parts.append(str(content))
                continue

            if role == "tool":
                # Anthropic 不支持 tool 角色：转为 assistant 摘要消息，
                # 保持对话的 user/assistant 合法交替结构（tool 结果紧跟 user 之后）。
                out.append(
                    {
                        "role": "assistant",
                        "content": self._summarize_tool_context(msg.get("content")),
                    }
                )
                continue

            if role not in {"user", "assistant"}:
                # 其他未知角色降级为 user 文本上下文
                role = "user"

            content = msg.get("content")
            if content is None:
                # assistant tool_calls 场景，转为简化文本上下文
                tc = msg.get("tool_calls")
                if tc:
                    content = json.dumps(tc, ensure_ascii=False)
                else:
                    content = ""

            out.append(
                {
                    "role": role,
                    "content": str(content),
                }
            )

        if not out:
            out = [{"role": "user", "content": "你好"}]
        return "\n\n".join(system_parts), out

    @staticmethod
    def _summarize_tool_context(content: Any) -> str:
        """将 tool 输出压缩为简短上下文，避免注入大体积 JSON。"""
        text = "" if content is None else str(content)
        compact: dict[str, Any] | None = None
        has_reference_excerpt = False

        if isinstance(content, dict):
            payload = content
        elif isinstance(content, str):
            stripped = content.strip()
            if stripped.startswith("{") and stripped.endswith("}"):
                try:
                    payload = json.loads(stripped)
                except json.JSONDecodeError:
                    payload = None
            else:
                payload = None
        else:
            payload = None

        if isinstance(payload, dict):
            compact = {}
            for key in ("success", "message", "error", "status"):
                if key in payload:
                    compact[key] = payload[key]
            for key in ("has_chart", "has_dataframe"):
                if key in payload:
                    compact[key] = bool(payload.get(key))

            data_obj = payload.get("data")
            if isinstance(data_obj, dict):
                compact["data_keys"] = list(data_obj.keys())[:8]
                excerpt = data_obj.get("content")
                if isinstance(excerpt, str) and excerpt.strip():
                    compact["data_excerpt"] = excerpt.strip()[:6000]
                    has_reference_excerpt = True

            direct_excerpt = payload.get("data_excerpt")
            if isinstance(direct_excerpt, str) and direct_excerpt.strip():
                compact["data_excerpt"] = direct_excerpt.strip()[:6000]
                has_reference_excerpt = True

        if compact is not None:
            text = json.dumps(compact, ensure_ascii=False, default=str)

        max_chars = 12000 if has_reference_excerpt else 2000
        if len(text) > max_chars:
            text = text[:max_chars] + "...(截断)"
        return "[工具结果]\n" + text

    def _convert_tools(self, tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
        """将 OpenAI tools 转换为 Anthropic tools。"""
        if not tools:
            return None
        converted: list[dict[str, Any]] = []
        for tool in tools:
            func = tool.get("function", {})
            name = func.get("name")
            if not name:
                continue
            converted.append(
                {
                    "name": name,
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {"type": "object"}),
                }
            )
        return converted or None
