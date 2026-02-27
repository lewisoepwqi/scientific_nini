"""多模型路由与故障转移。

统一 LLM 调用协议，支持 OpenAI / Anthropic / 国产与本地模型，
按优先级尝试，失败自动降级。
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, TypedDict

from nini.config import settings

logger = logging.getLogger(__name__)


# ---- 数据结构 ----


@dataclass
class LLMChunk:
    """LLM 流式输出单元。"""

    text: str = ""
    reasoning: str = ""
    # 保留供应商原始输出文本（可能包含 <think> 标签），用于工具调用上下文回放
    raw_text: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str | None = None
    usage: dict[str, int] | None = None


@dataclass
class LLMResponse:
    """LLM 完整响应（由流式 chunk 聚合而来）。"""

    text: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    # 记录流式聚合后的终止原因，便于上层诊断空输出/截断等问题
    finish_reason: str | None = None
    finish_reasons: list[str] = field(default_factory=list)


class PurposeRoute(TypedDict):
    """用途路由配置。"""

    provider_id: str | None
    model: str | None
    base_url: str | None


class ReasoningStreamParser:
    """统一解析各供应商“思考内容”输出并处理流式累计片段。"""

    _TAG_PAIRS: tuple[tuple[str, str], ...] = (
        ("<think>", "</think>"),
        ("<thinking>", "</thinking>"),
        ("◁think▷", "◁/think▷"),
    )

    def __init__(self, *, enable_tag_split: bool = False):
        self._enable_tag_split = enable_tag_split
        self._raw_snapshot = ""
        self._text_snapshot = ""
        self._reasoning_snapshot = ""
        self._pending = ""
        self._tag_state: tuple[str, str] | None = None

    @staticmethod
    def _normalize_stream_piece(piece: str, snapshot: str) -> tuple[str, str]:
        """兼容增量流和累计流两种分片格式。"""
        if not piece:
            return "", snapshot

        # 累计片段：当前值是历史完整前缀，返回增量部分
        if snapshot and piece.startswith(snapshot):
            return piece[len(snapshot) :], piece

        # 默认按“增量分片”处理
        return piece, snapshot + piece

    @staticmethod
    def _to_text(value: Any) -> str:
        """将 reasoning 相关字段统一转成文本。"""
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, (int, float, bool)):
            return str(value)
        if isinstance(value, dict):
            for key in ("text", "content", "reasoning_content", "reasoning"):
                nested = value.get(key)
                if isinstance(nested, str) and nested:
                    return nested
            try:
                return json.dumps(value, ensure_ascii=False)
            except Exception:
                return str(value)
        if isinstance(value, list):
            parts = [ReasoningStreamParser._to_text(item) for item in value]
            return "".join(part for part in parts if part)
        return str(value)

    @classmethod
    def extract_reasoning_from_delta(cls, delta: Any) -> str:
        """从 OpenAI 兼容 delta 中提取 reasoning 相关字段。"""
        parts: list[str] = []

        reasoning_content = getattr(delta, "reasoning_content", None)
        if reasoning_content:
            parts.append(cls._to_text(reasoning_content))

        reasoning = getattr(delta, "reasoning", None)
        if reasoning:
            parts.append(cls._to_text(reasoning))

        details = getattr(delta, "reasoning_details", None)
        if details:
            if isinstance(details, list):
                detail_parts: list[str] = []
                for item in details:
                    if isinstance(item, dict):
                        text = item.get("text")
                        if isinstance(text, str) and text:
                            detail_parts.append(text)
                            continue
                    text = getattr(item, "text", None)
                    if isinstance(text, str) and text:
                        detail_parts.append(text)
                        continue
                    detail_parts.append(cls._to_text(item))
                parts.append("".join(detail_parts))
            else:
                parts.append(cls._to_text(details))

        return "".join(part for part in parts if part)

    @classmethod
    def _pending_prefix_len(cls, text: str) -> int:
        """识别结尾是否是标签前缀，避免跨 chunk 标签被截断。"""
        if not text:
            return 0

        candidates = [token for pair in cls._TAG_PAIRS for token in pair]
        max_len = 0
        for token in candidates:
            max_check = min(len(token) - 1, len(text))
            for i in range(1, max_check + 1):
                if text.endswith(token[:i]):
                    max_len = max(max_len, i)
        return max_len

    @classmethod
    def _find_next_tag(cls, text: str) -> tuple[int, tuple[str, str]] | None:
        best_index: int | None = None
        best_pair: tuple[str, str] | None = None
        for pair in cls._TAG_PAIRS:
            idx = text.find(pair[0])
            if idx < 0:
                continue
            if best_index is None or idx < best_index:
                best_index = idx
                best_pair = pair
        if best_index is None or best_pair is None:
            return None
        return best_index, best_pair

    @classmethod
    def strip_reasoning_markers(cls, text: str) -> str:
        """移除思考标签标记，仅保留可展示正文。"""
        cleaned = text
        for open_tag, close_tag in cls._TAG_PAIRS:
            cleaned = cleaned.replace(open_tag, "")
            cleaned = cleaned.replace(close_tag, "")
        return cleaned

    def _split_reasoning_tags(self, raw_piece: str) -> tuple[str, str]:
        """从 content 中拆分思考标签和正式回答。"""
        if not raw_piece:
            return "", ""

        text_out: list[str] = []
        reasoning_out: list[str] = []
        cursor = self._pending + raw_piece
        self._pending = ""

        while cursor:
            if self._tag_state is None:
                tag_hit = self._find_next_tag(cursor)
                if tag_hit is None:
                    hold = self._pending_prefix_len(cursor)
                    if hold > 0:
                        text_out.append(cursor[:-hold])
                        self._pending = cursor[-hold:]
                    else:
                        text_out.append(cursor)
                    break

                open_idx, pair = tag_hit
                if open_idx > 0:
                    text_out.append(cursor[:open_idx])
                cursor = cursor[open_idx + len(pair[0]) :]
                self._tag_state = pair
                continue

            _, close_tag = self._tag_state
            close_idx = cursor.find(close_tag)
            if close_idx < 0:
                hold = self._pending_prefix_len(cursor)
                if hold > 0:
                    reasoning_out.append(cursor[:-hold])
                    self._pending = cursor[-hold:]
                else:
                    reasoning_out.append(cursor)
                break

            if close_idx > 0:
                reasoning_out.append(cursor[:close_idx])
            cursor = cursor[close_idx + len(close_tag) :]
            self._tag_state = None

        return "".join(text_out), "".join(reasoning_out)

    def consume(
        self, *, raw_piece: str, explicit_reasoning_piece: str = ""
    ) -> tuple[str, str, str]:
        """消费一次 chunk，返回（text_delta, reasoning_delta, raw_delta）。"""
        raw_delta, self._raw_snapshot = self._normalize_stream_piece(raw_piece, self._raw_snapshot)
        explicit_reasoning_delta, self._reasoning_snapshot = self._normalize_stream_piece(
            explicit_reasoning_piece,
            self._reasoning_snapshot,
        )

        text_candidate = raw_delta
        tagged_reasoning = ""
        if self._enable_tag_split and raw_delta:
            text_candidate, tagged_reasoning = self._split_reasoning_tags(raw_delta)
            if tagged_reasoning and self._reasoning_snapshot:
                tagged_reasoning = self.strip_reasoning_markers(tagged_reasoning)

        if self._reasoning_snapshot:
            # 当供应商已返回 reasoning 字段时，content 中出现的 think 标记属于冗余噪音
            text_candidate = self.strip_reasoning_markers(text_candidate)

        reasoning_candidate = explicit_reasoning_delta or tagged_reasoning
        text_delta, self._text_snapshot = self._normalize_stream_piece(
            text_candidate,
            self._text_snapshot,
        )
        if explicit_reasoning_delta and tagged_reasoning:
            # 少数模型会同时返回 reasoning_content + 带标签 content，此时避免重复叠加
            tagged_reasoning = ""
        if tagged_reasoning:
            reasoning_candidate = tagged_reasoning
        reasoning_delta = reasoning_candidate
        if explicit_reasoning_delta and tagged_reasoning:
            reasoning_delta = explicit_reasoning_delta
        return text_delta, reasoning_delta, raw_delta


# ---- 抽象客户端 ----


class BaseLLMClient(ABC):
    """统一 LLM 客户端协议。"""

    # 子类应覆盖此属性以标识提供商
    provider_id: str = ""
    provider_name: str = ""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[LLMChunk, None]:
        """流式聊天接口。"""
        ...  # pragma: no cover
        # 确保类型检查器知道这是个 async generator
        yield LLMChunk()  # type: ignore[misc]

    @abstractmethod
    def is_available(self) -> bool:
        """检查客户端是否可用（API Key 是否配置等）。"""
        ...

    def get_model_name(self) -> str:
        """获取当前使用的模型名称。"""
        return getattr(self, "_model", "") or ""

    async def aclose(self) -> None:
        """关闭底层 HTTP 客户端，释放连接资源。

        子类应覆盖此方法以关闭各自的 SDK 客户端。
        不调用此方法不会导致功能异常，但可能产生 GC 阶段的
        'AsyncHttpxClientWrapper' 属性缺失警告。
        """


# ---- OpenAI 兼容客户端基类 ----


class OpenAICompatibleClient(BaseLLMClient):
    """OpenAI 兼容 API 适配器基类（OpenAI / Ollama 共用）。"""

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


# ---- OpenAI 客户端 ----


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


# ---- Anthropic 客户端 ----


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
                # Anthropic 不支持 tool 角色：转为 assistant 摘要，避免误判为用户输入。
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


# ---- Ollama 客户端 ----


class OllamaClient(OpenAICompatibleClient):
    """Ollama OpenAI 兼容接口适配器。"""

    provider_id = "ollama"
    provider_name = "Ollama（本地）"

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
    ):
        resolved_base = (base_url or settings.ollama_base_url or "").rstrip("/")
        openai_compat_base = f"{resolved_base}/v1" if resolved_base else None
        super().__init__(
            api_key="ollama",
            base_url=openai_compat_base,
            model=model or settings.ollama_model,
        )

    def is_available(self) -> bool:
        return bool(self._base_url and self._model)

    def _supports_stream_usage(self) -> bool:
        # Ollama OpenAI 兼容端通常不返回 usage
        return False


# ---- Moonshot AI (Kimi) 客户端 ----


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


# ---- Kimi Coding 客户端 ----


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


# ---- 智谱 AI (GLM) 客户端 ----


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


# ---- DeepSeek 客户端 ----


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


# ---- 阿里百炼（通义千问）客户端 ----


class DashScopeClient(OpenAICompatibleClient):
    """阿里百炼（通义千问）适配器，兼容 OpenAI 协议。"""

    provider_id = "dashscope"
    provider_name = "阿里百炼（通义千问）"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ):
        super().__init__(
            api_key=api_key or settings.dashscope_api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            model=model or settings.dashscope_model,
        )


# ---- MiniMax 客户端 ----


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


# ---- Model Resolver ----


class ModelResolver:
    """多模型路由器：按优先级尝试可用模型，失败自动降级。

    支持全局首选与用途级首选：
    - 全局首选：所有用途共享
    - 用途首选：仅作用于特定用途（如 title_generation/image_analysis）
    路由优先级：用途首选 > 全局首选 > 默认优先级。
    """

    def __init__(self, clients: list[BaseLLMClient] | None = None):
        # 按优先级排列的客户端
        self._clients: list[BaseLLMClient] = clients or [
            OpenAIClient(),
            AnthropicClient(),
            MoonshotClient(),
            KimiCodingClient(),
            ZhipuClient(),
            DeepSeekClient(),
            DashScopeClient(),
            MiniMaxClient(),
            OllamaClient(),
        ]
        # 用户首选的提供商 ID（None 表示使用默认优先级）
        self._preferred_provider: str | None = None
        # 用途级路由配置：purpose -> {provider_id, model, base_url}
        self._purpose_routes: dict[str, PurposeRoute] = {}
        # 最近一次客户端重载时的有效配置（用于构造用途专用客户端）
        self._config_overrides: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _empty_purpose_route() -> PurposeRoute:
        return {"provider_id": None, "model": None, "base_url": None}

    def set_purpose_route(
        self,
        purpose: str,
        *,
        provider_id: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        """设置用途级路由配置。"""
        if not purpose:
            return
        normalized_provider = provider_id.strip() if isinstance(provider_id, str) else ""
        normalized_model = model.strip() if isinstance(model, str) else ""
        normalized_base_url = base_url.strip() if isinstance(base_url, str) else ""
        if not normalized_provider:
            self._purpose_routes.pop(purpose, None)
            logger.info("用途模型路由已清除: purpose=%s", purpose)
            return
        route: PurposeRoute = {
            "provider_id": normalized_provider,
            "model": normalized_model or None,
            "base_url": normalized_base_url or None,
        }
        self._purpose_routes[purpose] = route
        logger.info(
            "用途模型路由已设置: purpose=%s provider=%s model=%s base_url=%s",
            purpose,
            route["provider_id"],
            route["model"] or "",
            route["base_url"] or "",
        )

    def get_purpose_route(self, purpose: str) -> PurposeRoute:
        """获取用途级路由配置。"""
        route = self._purpose_routes.get(purpose)
        if route is None:
            return self._empty_purpose_route()
        return {
            "provider_id": route.get("provider_id"),
            "model": route.get("model"),
            "base_url": route.get("base_url"),
        }

    def get_purpose_routes(self) -> dict[str, PurposeRoute]:
        """获取全部用途级路由配置。"""
        return {
            purpose: {
                "provider_id": route.get("provider_id"),
                "model": route.get("model"),
                "base_url": route.get("base_url"),
            }
            for purpose, route in self._purpose_routes.items()
        }

    def set_preferred_provider(
        self,
        provider_id: str | None,
        *,
        purpose: str | None = None,
    ) -> None:
        """设置首选模型提供商。

        Args:
            provider_id: 提供商 ID（如 "openai"、"anthropic"），None 表示恢复默认优先级。
            purpose: 用途标识；None 表示全局首选，非 None 表示用途级首选。
        """
        if purpose:
            self.set_purpose_route(purpose, provider_id=provider_id)
            return

        self._preferred_provider = provider_id
        logger.info("全局首选模型提供商已设置为: %s", provider_id or "（默认优先级）")

    def get_preferred_provider(self, *, purpose: str | None = None) -> str | None:
        """获取当前首选的提供商 ID。"""
        if purpose:
            return self.get_purpose_route(purpose).get("provider_id")
        return self._preferred_provider

    def get_preferred_providers_by_purpose(self) -> dict[str, str]:
        """获取所有用途级首选提供商。"""
        result: dict[str, str] = {}
        for purpose, route in self._purpose_routes.items():
            provider = route.get("provider_id")
            if provider:
                result[purpose] = provider
        return result

    def get_active_model_info(self, *, purpose: str | None = None) -> dict[str, str]:
        """获取当前活跃模型的信息。

        如果设置了用途首选且可用，优先返回用途首选；
        否则回退到全局首选；最后使用默认优先级中第一个可用提供商。

        Returns:
            包含 provider_id、provider_name、model 的字典。
        """
        for client in self._get_ordered_clients(purpose=purpose):
            if client.is_available():
                return {
                    "provider_id": client.provider_id,
                    "provider_name": client.provider_name,
                    "model": client.get_model_name(),
                }

        return {"provider_id": "", "provider_name": "无可用模型", "model": ""}

    def _get_ordered_clients(self, *, purpose: str | None = None) -> list[BaseLLMClient]:
        """获取按首选提供商优先排序的客户端列表。

        如果设置了用途模型覆盖，先插入用途专用客户端；
        再按用途首选/全局首选将同提供商客户端排在前面。
        """
        ordered = list(self._clients)
        route = self.get_purpose_route(purpose) if purpose else self._empty_purpose_route()
        route_provider = route.get("provider_id")
        route_model = route.get("model")
        route_base_url = route.get("base_url")
        if route_provider and (route_model or route_base_url):
            specialized = self._build_client_for_provider(
                route_provider,
                model=route_model,
                base_url=route_base_url,
            )
            if specialized is not None:
                ordered = [specialized] + ordered

        preferred_provider = route_provider or self._preferred_provider
        if not preferred_provider:
            return ordered

        preferred: list[BaseLLMClient] = []
        others: list[BaseLLMClient] = []
        for client in ordered:
            if client.provider_id == preferred_provider:
                preferred.append(client)
            else:
                others.append(client)
        return preferred + others

    def _build_client_for_provider(
        self,
        provider_id: str,
        *,
        model: str | None = None,
        base_url: str | None = None,
    ) -> BaseLLMClient | None:
        """按 provider 构造临时客户端（支持用途级 model/base_url 覆盖）。"""
        cfg = self._config_overrides.get(provider_id, {})
        api_key = cfg.get("api_key")
        cfg_model = cfg.get("model")
        cfg_base_url = cfg.get("base_url")
        effective_model = model or cfg_model
        effective_base_url = base_url or cfg_base_url

        if provider_id == "openai":
            return OpenAIClient(api_key=api_key, base_url=effective_base_url, model=effective_model)
        if provider_id == "anthropic":
            return AnthropicClient(api_key=api_key, model=effective_model)
        if provider_id == "moonshot":
            return MoonshotClient(
                api_key=api_key,
                base_url=effective_base_url,
                model=effective_model,
            )
        if provider_id == "kimi_coding":
            return KimiCodingClient(
                api_key=api_key,
                base_url=effective_base_url,
                model=effective_model,
            )
        if provider_id == "zhipu":
            return ZhipuClient(
                api_key=api_key,
                base_url=effective_base_url,
                model=effective_model,
            )
        if provider_id == "deepseek":
            return DeepSeekClient(api_key=api_key, model=effective_model)
        if provider_id == "dashscope":
            return DashScopeClient(api_key=api_key, model=effective_model)
        if provider_id == "minimax":
            return MiniMaxClient(
                api_key=api_key,
                base_url=effective_base_url,
                model=effective_model,
            )
        if provider_id == "ollama":
            return OllamaClient(base_url=effective_base_url, model=effective_model)
        return None

    def _is_temporary_client(self, client: BaseLLMClient) -> bool:
        """判断是否为临时用途客户端。"""
        return all(client is not base for base in self._clients)

    def reload_clients(
        self,
        config_overrides: dict[str, dict[str, Any]] | None = None,
        priorities: dict[str, int] | None = None,
    ) -> None:
        """使用新配置重新初始化所有客户端。

        Args:
            config_overrides: 以 provider 为键的配置字典，
                每个值包含 api_key、model、base_url 等字段。
                DB 配置已合并 .env 后传入。
            priorities: provider -> priority 映射，值越小优先级越高。
        """
        overrides = config_overrides or {}
        self._config_overrides = overrides

        def _get(provider: str, key: str) -> str | None:
            return overrides.get(provider, {}).get(key)

        clients = [
            OpenAIClient(
                api_key=_get("openai", "api_key"),
                base_url=_get("openai", "base_url"),
                model=_get("openai", "model"),
            ),
            AnthropicClient(
                api_key=_get("anthropic", "api_key"),
                model=_get("anthropic", "model"),
            ),
            MoonshotClient(
                api_key=_get("moonshot", "api_key"),
                base_url=_get("moonshot", "base_url"),
                model=_get("moonshot", "model"),
            ),
            KimiCodingClient(
                api_key=_get("kimi_coding", "api_key"),
                base_url=_get("kimi_coding", "base_url"),
                model=_get("kimi_coding", "model"),
            ),
            ZhipuClient(
                api_key=_get("zhipu", "api_key"),
                base_url=_get("zhipu", "base_url"),
                model=_get("zhipu", "model"),
            ),
            DeepSeekClient(
                api_key=_get("deepseek", "api_key"),
                model=_get("deepseek", "model"),
            ),
            DashScopeClient(
                api_key=_get("dashscope", "api_key"),
                model=_get("dashscope", "model"),
            ),
            MiniMaxClient(
                api_key=_get("minimax", "api_key"),
                base_url=_get("minimax", "base_url"),
                model=_get("minimax", "model"),
            ),
            OllamaClient(
                base_url=_get("ollama", "base_url"),
                model=_get("ollama", "model"),
            ),
        ]
        default_order = {client.provider_id: idx for idx, client in enumerate(clients)}
        priority_map = priorities or {}
        clients.sort(
            key=lambda client: (
                int(
                    priority_map.get(client.provider_id, default_order.get(client.provider_id, 999))
                ),
                default_order.get(client.provider_id, 999),
            )
        )
        self._clients = clients
        logger.info(
            "模型客户端已重新加载，可用客户端: %s",
            [type(c).__name__ for c in self._clients if c.is_available()],
        )

    def get_active_client(self) -> BaseLLMClient:
        """获取第一个可用的客户端。"""
        for client in self._clients:
            if client.is_available():
                return client
        raise RuntimeError(
            "没有可用的 LLM 客户端。请配置 NINI_OPENAI_API_KEY / NINI_ANTHROPIC_API_KEY / "
            "NINI_MOONSHOT_API_KEY / NINI_KIMI_CODING_API_KEY / NINI_ZHIPU_API_KEY / "
            "NINI_DEEPSEEK_API_KEY / NINI_DASHSCOPE_API_KEY / NINI_MINIMAX_API_KEY "
            "或检查 NINI_OLLAMA_BASE_URL。"
        )

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        purpose: str | None = None,
    ) -> AsyncGenerator[LLMChunk, None]:
        """带故障转移的流式聊天。

        路由优先级：用途首选 > 全局首选 > 默认优先级。
        """
        temp = temperature if temperature is not None else settings.llm_temperature
        tokens = max_tokens if max_tokens is not None else settings.llm_max_tokens

        last_error: Exception | None = None

        for client in self._get_ordered_clients(purpose=purpose):
            is_temp = self._is_temporary_client(client)
            if not client.is_available():
                if is_temp:
                    with suppress(Exception):
                        await client.aclose()
                continue
            try:
                async for chunk in client.chat(
                    messages, tools, temperature=temp, max_tokens=tokens
                ):
                    yield chunk
                return  # 成功完成
            except NotImplementedError:
                continue
            except Exception as e:
                logger.warning(
                    "LLM 客户端 %s 调用失败: purpose=%s err=%s",
                    type(client).__name__,
                    purpose or "default",
                    e,
                )
                last_error = e
                continue
            finally:
                if is_temp:
                    with suppress(Exception):
                        await client.aclose()

        raise RuntimeError(f"所有 LLM 客户端均失败: {last_error}")

    async def chat_complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        purpose: str | None = None,
    ) -> LLMResponse:
        """非流式便捷方法：聚合所有 chunk 为完整响应。"""
        response = LLMResponse()
        async for chunk in self.chat(
            messages,
            tools,
            temperature=temperature,
            max_tokens=max_tokens,
            purpose=purpose,
        ):
            response.text += chunk.text
            if chunk.finish_reason:
                response.finish_reason = chunk.finish_reason
                if chunk.finish_reason not in response.finish_reasons:
                    response.finish_reasons.append(chunk.finish_reason)
            if chunk.tool_calls:
                response.tool_calls.extend(chunk.tool_calls)
            if chunk.usage:
                response.usage = chunk.usage
        return response


# 全局单例
model_resolver = ModelResolver()


async def reload_model_resolver() -> None:
    """从数据库加载配置并重新初始化全局 model_resolver 的客户端。"""
    from nini.config_manager import (
        get_all_effective_configs,
        get_default_provider,
        get_model_priorities,
        get_model_purpose_routes,
    )

    configs = await get_all_effective_configs()
    priorities = await get_model_priorities()
    model_resolver.reload_clients(configs, priorities=priorities)

    # 加载默认提供商设置
    default_provider = await get_default_provider()
    if default_provider:
        model_resolver.set_preferred_provider(default_provider)
        logger.info("已从数据库加载默认提供商: %s", default_provider)
    else:
        model_resolver.set_preferred_provider(None)

    purpose_routes = await get_model_purpose_routes()
    for purpose, route in purpose_routes.items():
        model_resolver.set_purpose_route(
            purpose,
            provider_id=route.get("provider_id"),
            model=route.get("model"),
            base_url=route.get("base_url"),
        )
    logger.info("已从数据库加载用途模型路由: %s", purpose_routes)
