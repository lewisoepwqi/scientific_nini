"""多模型路由与故障转移。

统一 LLM 调用协议，支持 OpenAI / Anthropic / 国产与本地模型，
按优先级尝试，失败自动降级。
"""

from __future__ import annotations

import logging
from contextlib import suppress
from typing import Any, AsyncGenerator

from nini.config import settings

from .providers import (
    AnthropicClient,
    BaseLLMClient,
    DashScopeClient,
    DeepSeekClient,
    KimiCodingClient,
    LLMChunk,
    LLMResponse,
    MiniMaxClient,
    MoonshotClient,
    OllamaClient,
    OpenAIClient,
    PurposeRoute,
    ZhipuClient,
)

logger = logging.getLogger(__name__)

# ---- 标题生成廉价模型偏好顺序 ----
# 按 provider_id 映射到廉价模型名称列表（优先级从高到低）
# None 表示使用用户选择的主模型（如 Ollama）
TITLE_MODEL_PREFERENCE: dict[str, list[str] | None] = {
    "deepseek":  ["deepseek-chat"],
    "zhipu":     ["glm-4-flash", "glm-4-air", "glm-4"],
    "dashscope": ["qwen-turbo", "qwen-plus"],
    "ollama":    None,
}

# ---- 用途路由映射 ----

# 内置默认路由，可通过配置覆盖
DEFAULT_PURPOSE_ROUTES: dict[str, PurposeRoute] = {
    "default": {
        "provider_id": None,
        "model": None,
        "base_url": None,
    },
    "coding": {
        "provider_id": None,
        "model": None,
        "base_url": None,
    },
    "analysis": {
        "provider_id": None,
        "model": None,
        "base_url": None,
    },
    "vision": {
        "provider_id": None,
        "model": None,
        "base_url": None,
    },
    "embedding": {
        "provider_id": None,
        "model": None,
        "base_url": None,
    },
}


def _load_purpose_routes_from_settings() -> dict[str, PurposeRoute]:
    """从 settings 加载用途路由配置。"""
    routes: dict[str, PurposeRoute] = {}
    for key in DEFAULT_PURPOSE_ROUTES:
        provider = getattr(settings, f"purpose_{key}_provider", None)
        model = getattr(settings, f"purpose_{key}_model", None)
        base_url = getattr(settings, f"purpose_{key}_base_url", None)
        routes[key] = {
            "provider_id": provider,
            "model": model,
            "base_url": base_url,
        }
    return routes


# ---- 模型解析器 ----


class ModelResolver:
    """多模型路由与故障转移管理器。

    支持按用途选择模型，并在失败时自动降级到下一个可用提供商。
    """

    def __init__(self, clients: list[BaseLLMClient] | None = None) -> None:
        self._clients: list[BaseLLMClient] = []
        self._client_map: dict[str, BaseLLMClient] = {}
        self._purpose_routes = _load_purpose_routes_from_settings()
        self._config_overrides: dict[str, dict[str, Any]] = {}
        # 单一激活供应商 ID（None 表示使用试用模式）
        self._active_provider_id: str | None = None
        # 试用模式客户端（使用内嵌密钥构造）
        self._trial_client: BaseLLMClient | None = None
        if clients is not None:
            # 测试注入模式
            self._clients = clients
            self._client_map = {c.provider_id: c for c in self._clients}
        else:
            self._init_clients()

    def _init_clients(self) -> None:
        """初始化所有提供商客户端。"""
        self._clients = [
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
        self._client_map = {c.provider_id: c for c in self._clients}

    def _get_priority_order(self, purpose: str = "default") -> list[str]:
        """获取指定用途的提供商优先级顺序。"""
        route = self._purpose_routes.get(purpose, self._purpose_routes["default"])
        provider_id = route.get("provider_id")

        # 如果配置了特定用途的提供商，优先使用
        priority: list[str] = []
        if provider_id and provider_id in self._client_map:
            priority.append(provider_id)

        # 默认优先级（成本与效果平衡）
        default_priority = [c.provider_id for c in self._clients]

        # 添加未包含的提供商
        for p in default_priority:
            if p not in priority:
                priority.append(p)

        # 过滤掉不可用的
        return [p for p in priority if p in self._client_map and self._client_map[p].is_available()]

    @staticmethod
    def _compact_error_message(error: Exception) -> str:
        """压缩错误信息，避免把长 traceback 直接暴露到前端。"""
        text = str(error or "").strip()
        if not text:
            return error.__class__.__name__
        first_line = text.splitlines()[0].strip()
        if len(first_line) > 240:
            return first_line[:240].rstrip() + "..."
        return first_line

    def _get_single_active_client(self) -> BaseLLMClient | None:
        """获取单一激活供应商的客户端。

        Returns:
            激活的客户端，若无激活供应商则返回 None
        """
        if not self._active_provider_id:
            return None
        client = self._client_map.get(self._active_provider_id)
        if client and client.is_available():
            return client
        return None

    def _get_title_client(self) -> BaseLLMClient | None:
        """获取用于标题生成的廉价模型客户端。

        按 TITLE_MODEL_PREFERENCE 偏好从激活供应商中选取廉价模型。
        若无偏好配置或 Ollama，则使用激活供应商的主模型。

        Returns:
            适合标题生成的客户端，若无激活供应商则返回 None
        """
        if not self._active_provider_id:
            return self._trial_client  # 试用模式直接用试用客户端

        preferred = TITLE_MODEL_PREFERENCE.get(self._active_provider_id)
        if preferred is None:
            # Ollama 或无偏好：使用主模型
            return self._get_single_active_client()

        # 选取偏好列表中的第一个模型构建临时客户端
        title_model = preferred[0]
        built = self._build_client_for_provider(self._active_provider_id, model=title_model)
        if built and built.is_available():
            return built
        # 构建失败则回退主模型
        return self._get_single_active_client()

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        purpose: str = "default",
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[LLMChunk, None]:
        """流式聊天（单一激活供应商模式）。

        Args:
            messages: OpenAI 格式的消息列表
            tools: 可选的工具定义
            purpose: 用途标识（title_generation 时自动使用廉价模型）
            temperature: 采样温度
            max_tokens: 最大生成 token 数

        Yields:
            LLMChunk: 流式输出块
        """
        # 单一激活模式：
        # 1) 有激活供应商时，仅使用该供应商（title_generation 走廉价模型偏好）
        # 2) 无激活供应商但有试用客户端时，仅使用试用客户端
        # 3) 其余场景（主要是测试注入）保留多客户端故障转移能力
        clients: list[BaseLLMClient] = []
        if self._active_provider_id:
            if purpose == "title_generation":
                title_client = self._get_title_client()
                if title_client:
                    clients = [title_client]
            else:
                active_client = self._get_single_active_client()
                if active_client:
                    clients = [active_client]
        elif self._trial_client:
            clients = [self._trial_client]
        else:
            clients = self._get_ordered_clients(purpose)

        if not clients:
            raise RuntimeError("未配置 AI 服务，请先在「AI 设置」中配置供应商密钥")
        fallback_chain: list[dict[str, Any]] = []
        last_error: Exception | None = None

        for attempt, client in enumerate(clients, start=1):
            provider_id = getattr(client, "provider_id", "") or ""
            provider_name = getattr(client, "provider_name", provider_id) or provider_id
            model_name = client.get_model_name() or "unknown"
            success_entry = {
                "provider_id": provider_id,
                "provider_name": provider_name,
                "model": model_name,
                "attempt": attempt,
                "status": "success",
                "error": None,
            }
            first_failed = next((item for item in fallback_chain if item.get("status") == "failed"), None)

            try:
                async for chunk in client.chat(
                    messages=messages,
                    tools=tools,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ):
                    chunk_text = chunk.text if hasattr(chunk, "text") else ""
                    chunk_reasoning = chunk.reasoning if hasattr(chunk, "reasoning") else ""
                    yield LLMChunk(
                        text=chunk_text,
                        reasoning=chunk_reasoning,
                        raw_text=getattr(chunk, "raw_text", chunk_text),
                        tool_calls=getattr(chunk, "tool_calls", []),
                        finish_reason=getattr(chunk, "finish_reason", None),
                        usage=getattr(chunk, "usage", None),
                        provider_id=provider_id,
                        provider_name=provider_name,
                        model=model_name,
                        attempt=attempt,
                        fallback_applied=attempt > 1,
                        fallback_from_provider_id=first_failed.get("provider_id") if first_failed else None,
                        fallback_from_model=first_failed.get("model") if first_failed else None,
                        fallback_reason=first_failed.get("error") if first_failed else None,
                        fallback_chain=[*fallback_chain, success_entry],
                    )
                return
            except Exception as e:
                last_error = e
                compact_error = self._compact_error_message(e)
                fallback_chain.append(
                    {
                        "provider_id": provider_id,
                        "provider_name": provider_name,
                        "model": model_name,
                        "attempt": attempt,
                        "status": "failed",
                        "error": compact_error,
                    }
                )
                logger.warning(
                    "LLM 客户端调用失败，尝试下一个提供商: provider=%s model=%s reason=%s",
                    provider_id,
                    model_name,
                    compact_error,
                )

        if last_error is not None:
            summary = " | ".join(
                f"{item.get('provider_id', 'unknown')}: {item.get('error', 'unknown error')}"
                for item in fallback_chain
            )
            raise RuntimeError(f"所有 LLM 客户端均失败: {summary}") from last_error

        raise RuntimeError("LLM 调用未返回结果")

    async def chat_complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        purpose: str = "default",
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """非流式聊天，聚合所有 chunk 返回完整响应。

        Args:
            messages: OpenAI 格式的消息列表
            tools: 可选的工具定义
            purpose: 用途标识
            temperature: 采样温度
            max_tokens: 最大生成 token 数

        Returns:
            LLMResponse: 完整响应
        """
        text_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        usage: dict[str, int] = {}
        finish_reasons: list[str] = []

        async for chunk in self.chat(
            messages=messages,
            tools=tools,
            purpose=purpose,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            if chunk.text:
                text_parts.append(chunk.text)
            if chunk.reasoning:
                reasoning_parts.append(chunk.reasoning)
            if chunk.tool_calls:
                tool_calls.extend(chunk.tool_calls)
            if chunk.usage:
                usage["input_tokens"] = usage.get("input_tokens", 0) + chunk.usage.get("input_tokens", 0)
                usage["output_tokens"] = usage.get("output_tokens", 0) + chunk.usage.get("output_tokens", 0)
            if chunk.finish_reason:
                finish_reasons.append(chunk.finish_reason)

        finish_reason = finish_reasons[-1] if finish_reasons else None

        return LLMResponse(
            text="".join(text_parts),
            tool_calls=tool_calls,
            usage=usage,
            finish_reason=finish_reason,
            finish_reasons=finish_reasons,
        )

    def get_provider_info(self) -> dict[str, dict[str, Any]]:
        """获取所有提供商状态信息。"""
        return {
            client.provider_id: {
                "name": client.provider_name,
                "available": client.is_available(),
                "model": client.get_model_name(),
            }
            for client in self._clients
        }

    def _build_client_for_provider(
        self,
        provider_id: str,
        *,
        model: str | None = None,
        base_url: str | None = None,
    ) -> BaseLLMClient | None:
        """为指定提供商构建新的客户端实例（用于用途路由覆盖）。

        Args:
            provider_id: 提供商 ID
            model: 可选的模型名称覆盖
            base_url: 可选的 base URL 覆盖

        Returns:
            新的客户端实例，如果提供商未知则返回 None
        """
        from nini.agent.providers import (
            AnthropicClient,
            DashScopeClient,
            DeepSeekClient,
            KimiCodingClient,
            MiniMaxClient,
            MoonshotClient,
            OllamaClient,
            OpenAIClient,
            ZhipuClient,
        )

        # 获取配置覆盖
        override = self._config_overrides.get(provider_id, {})
        api_key = override.get("api_key")
        default_model = override.get("model")
        default_base_url = override.get("base_url")

        # 使用传入的参数或配置覆盖
        final_model = model or default_model
        final_base_url = base_url or default_base_url

        client_map: dict[str, type[BaseLLMClient]] = {
            "openai": OpenAIClient,
            "anthropic": AnthropicClient,
            "moonshot": MoonshotClient,
            "kimi_coding": KimiCodingClient,
            "zhipu": ZhipuClient,
            "deepseek": DeepSeekClient,
            "dashscope": DashScopeClient,
            "minimax": MiniMaxClient,
            "ollama": OllamaClient,
        }

        client_cls = client_map.get(provider_id)
        if not client_cls:
            return None

        kwargs: dict[str, Any] = {}
        if api_key:
            kwargs["api_key"] = api_key
        if final_model:
            kwargs["model"] = final_model
        if final_base_url:
            kwargs["base_url"] = final_base_url

        return client_cls(**kwargs)

    def _get_ordered_clients(self, purpose: str = "default") -> list[BaseLLMClient]:
        """获取按优先级排序的客户端列表（考虑用途路由覆盖）。

        Args:
            purpose: 用途标识

        Returns:
            按优先级排序的客户端列表
        """
        priority = self._get_priority_order(purpose)
        clients: list[BaseLLMClient] = []

        # 检查是否有用途特定的模型覆盖
        route = self._purpose_routes.get(purpose, {})
        purpose_provider = route.get("provider_id")
        purpose_model = route.get("model")

        for provider_id in priority:
            client: BaseLLMClient | None = None
            # 如果是用途指定的提供商且有模型覆盖，尝试构建临时客户端
            if purpose_provider and provider_id == purpose_provider and purpose_model:
                built_client = self._build_client_for_provider(
                    provider_id,
                    model=purpose_model,
                    base_url=route.get("base_url"),
                )
                # 如果构建的客户端可用，使用它；否则回退到 _client_map 中的客户端
                if built_client and built_client.is_available():
                    client = built_client
                else:
                    client = self._client_map.get(provider_id)
            else:
                # 否则使用现有客户端
                client = self._client_map.get(provider_id)

            if client and client.is_available():
                clients.append(client)

        return clients

    def get_active_model_info(self, purpose: str = "default") -> dict[str, Any]:
        """获取指定用途的活跃模型信息。

        Args:
            purpose: 用途标识，如 "default", "chat", "coding", "analysis", "vision"

        Returns:
            包含 provider_id, provider_name, model, preferred_provider 的字典
        """
        # 获取按用途排序的客户端列表
        ordered = self._get_ordered_clients(purpose)

        # 检查 purpose route 中是否配置了特定模型
        route = self._purpose_routes.get(purpose, self._purpose_routes.get("default", {}))
        route_model = route.get("model") if route else None
        route_provider = route.get("provider_id") if route else None

        for client in ordered:
            if client.is_available():
                # 优先使用 purpose route 中配置的模型，否则使用客户端默认模型
                model_name = route_model or client.get_model_name() or "unknown"
                return {
                    "provider_id": client.provider_id,
                    "provider_name": client.provider_name,
                    "model": model_name,
                    "preferred_provider": route_provider or client.provider_id,
                    "purpose_preferred_providers": self.get_preferred_providers_by_purpose(),
                }
        # 没有可用客户端时返回空值
        return {
            "provider_id": "",
            "provider_name": "",
            "model": "",
            "preferred_provider": route_provider,
            "purpose_preferred_providers": self.get_preferred_providers_by_purpose(),
        }

    def get_preferred_provider(self, purpose: str = "default") -> str | None:
        """获取指定用途的首选提供商 ID。

        Args:
            purpose: 用途标识，默认为 "default"

        Returns:
            提供商 ID 或 None
        """
        route = self._purpose_routes.get(purpose, {})
        return route.get("provider_id")

    def get_preferred_providers_by_purpose(self) -> dict[str, str | None]:
        """获取各用途的首选提供商。"""
        return {
            purpose: route.get("provider_id")
            for purpose, route in self._purpose_routes.items()
        }

    def get_purpose_routes(self) -> dict[str, dict[str, Any]]:
        """获取用途路由配置。"""
        return self._purpose_routes.copy()

    def set_preferred_provider(
        self, provider_id: str | None, purpose: str = "default"
    ) -> None:
        """设置指定用途的首选提供商。

        Args:
            provider_id: 提供商 ID
            purpose: 用途标识，默认为 "default"
        """
        if purpose not in self._purpose_routes:
            self._purpose_routes[purpose] = {
                "provider_id": None,
                "model": None,
                "base_url": None,
            }
        self._purpose_routes[purpose]["provider_id"] = provider_id

    def set_purpose_route(
        self,
        purpose: str,
        provider_id: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        """设置指定用途的路由配置。"""
        if purpose not in self._purpose_routes:
            self._purpose_routes[purpose] = {
                "provider_id": None,
                "model": None,
                "base_url": None,
            }
        self._purpose_routes[purpose]["provider_id"] = provider_id
        if model is not None:
            self._purpose_routes[purpose]["model"] = model
        if base_url is not None:
            self._purpose_routes[purpose]["base_url"] = base_url

    def get_active_models(self) -> dict[str, Any]:
        """获取当前活动的模型信息（兼容旧API）。

        Returns:
            包含活跃模型信息的字典
        """
        return self.get_active_model_info(purpose="default")

    def get_available_models(self, provider_id: str) -> dict[str, Any]:
        """获取指定提供商的可用模型列表。

        Args:
            provider_id: 提供商 ID

        Returns:
            包含提供商 ID 和模型列表的字典
        """
        client = self._client_map.get(provider_id)
        if client:
            return {
                "provider_id": provider_id,
                "models": [client.get_model_name()] if client.get_model_name() else [],
            }
        return {"provider_id": provider_id, "models": []}

    def set_priorities(self, priorities: dict[str, int]) -> None:
        """设置模型优先级。

        Args:
            priorities: provider_id -> priority 映射，值越小优先级越高
        """
        # 根据优先级重新排序客户端列表；未配置项沿用当前顺序对应的默认优先级
        default_priorities = {client.provider_id: idx for idx, client in enumerate(self._clients)}

        def get_priority(client: BaseLLMClient) -> int:
            return priorities.get(client.provider_id, default_priorities.get(client.provider_id, 999))

        self._clients.sort(key=get_priority)
        # 重新构建客户端映射
        self._client_map = {c.provider_id: c for c in self._clients}

    def get_routing_config(self) -> dict[str, Any]:
        """获取模型路由配置。

        Returns:
            包含路由配置的字典
        """
        return {
            "purpose_routes": self._purpose_routes.copy(),
            "preferred_provider": self.get_preferred_provider(),
        }

    def set_routing_config(self, config: dict[str, Any]) -> None:
        """设置模型路由配置。

        Args:
            config: 路由配置字典
        """
        if "purpose_routes" in config:
            for purpose, route in config["purpose_routes"].items():
                self.set_purpose_route(
                    purpose=purpose,
                    provider_id=route.get("provider_id"),
                    model=route.get("model"),
                    base_url=route.get("base_url"),
                )
        if "preferred_provider" in config:
            self.set_preferred_provider(config["preferred_provider"])

    async def test_connection(self, provider_id: str) -> dict[str, Any]:
        """测试指定提供商的连接。

        Args:
            provider_id: 提供商 ID

        Returns:
            包含测试结果的字典
        """
        client = self._client_map.get(provider_id)
        if not client:
            return {"success": False, "error": f"未知的提供商: {provider_id}"}
        if not client.is_available():
            return {"success": False, "error": "提供商未配置或不可用（请检查 API Key）"}
        try:
            # 发送一个简单的测试请求验证连接
            test_messages = [{"role": "user", "content": "Hi"}]
            response_text = ""

            async for chunk in client.chat(
                messages=test_messages,
                temperature=0.3,
                max_tokens=5,  # 只需要少量 token 验证连接
            ):
                if chunk.text:
                    response_text += chunk.text
                # 收到第一个 chunk 就说明连接成功
                if response_text:
                    break

            return {
                "success": True,
                "provider": provider_id,
                "model": client.get_model_name(),
                "message": "连接成功",
            }
        except Exception as e:
            error_msg = str(e)
            # 常见错误友好提示
            if "authentication" in error_msg.lower() or "api key" in error_msg.lower():
                error_msg = "API Key 无效或已过期"
            elif "rate limit" in error_msg.lower():
                error_msg = "请求过于频繁，请稍后重试"
            elif "timeout" in error_msg.lower():
                error_msg = "连接超时，请检查网络或 Base URL"
            elif "connection" in error_msg.lower():
                error_msg = "无法连接到服务器，请检查网络或 Base URL"
            return {"success": False, "error": error_msg}

    def set_preferred_model(self, provider: str | None, model: str | None) -> None:
        """设置首选模型。

        Args:
            provider: 提供商 ID
            model: 模型名称
        """
        self.set_preferred_provider(provider)
        if provider and model:
            self.set_purpose_route(
                purpose="default",
                provider_id=provider,
                model=model,
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

    async def aclose(self) -> None:
        """关闭所有客户端连接。"""
        for client in self._clients:
            with suppress(Exception):
                if hasattr(client, "aclose"):
                    await client.aclose()

    def reload_clients(
        self,
        config_overrides: dict[str, dict[str, Any]] | None = None,
        priorities: dict[str, int] | None = None,
        active_provider_id: str | None = None,
        trial_api_key: str | None = None,
    ) -> None:
        """使用新配置重新初始化所有客户端。

        Args:
            config_overrides: 以 provider 为键的配置字典，
                每个值包含 api_key、model、base_url 等字段。
                DB 配置已合并 .env 后传入。
            priorities: provider -> priority 映射，值越小优先级越高（保留兼容，已不影响路由）。
            active_provider_id: 当前激活的单一供应商 ID。
            trial_api_key: 内嵌试用密钥（用于构造试用 DeepSeek 客户端）。
        """
        overrides = config_overrides or {}
        self._config_overrides = overrides

        # 更新单一激活供应商
        self._active_provider_id = active_provider_id

        # 构建试用客户端（仅当有内嵌密钥时）
        if trial_api_key:
            self._trial_client = DeepSeekClient(api_key=trial_api_key, model="deepseek-chat")
        else:
            self._trial_client = None

        def _get(provider: str, key: str) -> str | None:
            return overrides.get(provider, {}).get(key)

        clients: list[BaseLLMClient] = [
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
        self._clients = clients
        self._client_map = {c.provider_id: c for c in self._clients}
        if priorities:
            self.set_priorities(priorities)
        logger.info(
            "模型客户端已重新加载，激活供应商: %s，试用模式: %s",
            active_provider_id or "无",
            "启用" if self._trial_client else "禁用",
        )


# ---- 全局单例 ----

_resolver: ModelResolver | None = None


def get_model_resolver() -> ModelResolver:
    """获取全局 ModelResolver 单例。"""
    global _resolver
    if _resolver is None:
        _resolver = ModelResolver()
    return _resolver


def reset_model_resolver() -> None:
    """重置全局 ModelResolver 单例（主要用于测试）。"""
    global _resolver
    _resolver = None


async def reload_model_resolver() -> None:
    """从数据库加载配置并重新初始化全局 model_resolver 的客户端。"""
    from nini.config import settings
    from nini.config_manager import (
        get_active_provider_id,
        get_all_effective_configs,
        get_model_priorities,
        get_model_purpose_routes,
    )

    configs = await get_all_effective_configs()
    priorities = await get_model_priorities()
    purpose_routes = await get_model_purpose_routes()
    active_provider_id = await get_active_provider_id()
    trial_api_key = settings.trial_api_key or None

    resolver = get_model_resolver()
    resolver.reload_clients(
        configs,
        priorities=priorities,
        active_provider_id=active_provider_id,
        trial_api_key=trial_api_key,
    )

    # 兼容保留 purpose_routes 配置（后端保留，不影响新路由逻辑）
    for purpose, route in purpose_routes.items():
        if route.get("provider_id"):
            resolver.set_purpose_route(
                purpose=purpose,
                provider_id=route.get("provider_id"),
                model=route.get("model"),
                base_url=route.get("base_url"),
            )


# Module-level singleton for convenient access
model_resolver = get_model_resolver()
