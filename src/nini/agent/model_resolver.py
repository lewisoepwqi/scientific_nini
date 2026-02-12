"""多模型路由与故障转移。

统一 LLM 调用协议，支持 OpenAI / Anthropic / Ollama，
按优先级尝试，失败自动降级。
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator

from nini.config import settings

logger = logging.getLogger(__name__)


# ---- 数据结构 ----


@dataclass
class LLMChunk:
    """LLM 流式输出单元。"""

    text: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str | None = None
    usage: dict[str, int] | None = None


@dataclass
class LLMResponse:
    """LLM 完整响应（由流式 chunk 聚合而来）。"""

    text: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)


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

        # 聚合 tool_calls 片段
        pending_tool_calls: dict[int, dict[str, Any]] = {}

        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            finish = chunk.choices[0].finish_reason if chunk.choices else None

            text = ""
            tool_calls_out: list[dict[str, Any]] = []

            if delta:
                text = delta.content or ""

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

            self._client = AsyncAnthropic(api_key=self._api_key)

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
        tool_calls: list[dict[str, Any]] = []
        for block in getattr(response, "content", []) or []:
            b_type = getattr(block, "type", "")
            if b_type == "text":
                text_parts.append(getattr(block, "text", ""))
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
        yield LLMChunk(
            text="".join(text_parts),
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

        if compact is not None:
            text = json.dumps(compact, ensure_ascii=False, default=str)

        if len(text) > 2000:
            text = text[:2000] + "...(截断)"
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


# ---- Model Resolver ----


class ModelResolver:
    """多模型路由器：按优先级尝试可用模型，失败自动降级。

    支持设置首选提供商：当用户选择特定模型时，优先使用该提供商，
    失败后仍按默认优先级降级。
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
            OllamaClient(),
        ]
        # 用户首选的提供商 ID（None 表示使用默认优先级）
        self._preferred_provider: str | None = None

    def set_preferred_provider(self, provider_id: str | None) -> None:
        """设置首选模型提供商。

        Args:
            provider_id: 提供商 ID（如 "openai"、"anthropic"），None 表示恢复默认优先级。
        """
        self._preferred_provider = provider_id
        logger.info("首选模型提供商已设置为: %s", provider_id or "（默认优先级）")

    def get_preferred_provider(self) -> str | None:
        """获取当前首选的提供商 ID。"""
        return self._preferred_provider

    def get_active_model_info(self) -> dict[str, str]:
        """获取当前活跃模型的信息。

        如果设置了首选提供商且可用，返回该提供商信息；
        否则返回默认优先级中第一个可用的提供商信息。

        Returns:
            包含 provider_id、provider_name、model 的字典。
        """
        # 如果有首选提供商，优先检查
        if self._preferred_provider:
            for client in self._clients:
                if client.provider_id == self._preferred_provider and client.is_available():
                    return {
                        "provider_id": client.provider_id,
                        "provider_name": client.provider_name,
                        "model": client.get_model_name(),
                    }

        # 回退到默认优先级
        for client in self._clients:
            if client.is_available():
                return {
                    "provider_id": client.provider_id,
                    "provider_name": client.provider_name,
                    "model": client.get_model_name(),
                }

        return {"provider_id": "", "provider_name": "无可用模型", "model": ""}

    def _get_ordered_clients(self) -> list[BaseLLMClient]:
        """获取按首选提供商优先排序的客户端列表。

        如果设置了首选提供商，将其排在最前面，其余保持原有优先级。
        """
        if not self._preferred_provider:
            return self._clients

        preferred: list[BaseLLMClient] = []
        others: list[BaseLLMClient] = []
        for client in self._clients:
            if client.provider_id == self._preferred_provider:
                preferred.append(client)
            else:
                others.append(client)
        return preferred + others

    def reload_clients(self, config_overrides: dict[str, dict[str, Any]] | None = None) -> None:
        """使用新配置重新初始化所有客户端。

        Args:
            config_overrides: 以 provider 为键的配置字典，
                每个值包含 api_key、model、base_url 等字段。
                DB 配置已合并 .env 后传入。
        """
        overrides = config_overrides or {}

        def _get(provider: str, key: str) -> str | None:
            return overrides.get(provider, {}).get(key)

        self._clients = [
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
            OllamaClient(
                base_url=_get("ollama", "base_url"),
                model=_get("ollama", "model"),
            ),
        ]
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
            "NINI_DEEPSEEK_API_KEY / NINI_DASHSCOPE_API_KEY 或检查 NINI_OLLAMA_BASE_URL。"
        )

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[LLMChunk, None]:
        """带故障转移的流式聊天。

        如果设置了首选提供商，优先使用该提供商；失败后按默认优先级降级。
        """
        temp = temperature if temperature is not None else settings.llm_temperature
        tokens = max_tokens if max_tokens is not None else settings.llm_max_tokens

        last_error: Exception | None = None

        for client in self._get_ordered_clients():
            if not client.is_available():
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
                logger.warning("LLM 客户端 %s 调用失败: %s", type(client).__name__, e)
                last_error = e
                continue

        raise RuntimeError(f"所有 LLM 客户端均失败: {last_error}")

    async def chat_complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """非流式便捷方法：聚合所有 chunk 为完整响应。"""
        response = LLMResponse()
        async for chunk in self.chat(
            messages, tools, temperature=temperature, max_tokens=max_tokens
        ):
            response.text += chunk.text
            if chunk.tool_calls:
                response.tool_calls.extend(chunk.tool_calls)
            if chunk.usage:
                response.usage = chunk.usage
        return response


# 全局单例
model_resolver = ModelResolver()


async def reload_model_resolver() -> None:
    """从数据库加载配置并重新初始化全局 model_resolver 的客户端。"""
    from nini.config_manager import get_all_effective_configs, get_default_provider

    configs = await get_all_effective_configs()
    model_resolver.reload_clients(configs)

    # 加载默认提供商设置
    default_provider = await get_default_provider()
    if default_provider:
        model_resolver.set_preferred_provider(default_provider)
        logger.info("已从数据库加载默认提供商: %s", default_provider)
