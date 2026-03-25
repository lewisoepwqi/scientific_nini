"""多模型路由与故障转移。

统一 LLM 调用协议，支持 OpenAI / Anthropic / 国产与本地模型，
按优先级尝试，失败自动降级。
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from contextlib import suppress
from typing import Any, AsyncGenerator

import anthropic
import httpx
import openai

from nini.config import settings
from nini.builtin_key_crypto import decrypt_key
from nini.config_manager import BUILTIN_PROVIDER_ID

from .providers import (
    AnthropicClient,
    BaseLLMClient,
    DashScopeClient,
    DeepSeekClient,
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

BUILTIN_PROVIDER_NAME = "系统内置"
BUILTIN_MODE_FAST = "fast"
BUILTIN_MODE_DEEP = "deep"
BUILTIN_MODE_TITLE = "title"
DISABLED_PROVIDER_IDS: frozenset[str] = frozenset({"kimi_coding"})

# ---- 标题生成动态选模规则 ----
# 每个 provider 配置一组关键词偏好，按顺序从可用模型列表中动态匹配。
# 空列表表示不切换标题专用模型，直接复用当前主模型。
TITLE_MODEL_MATCHERS: dict[str, list[tuple[str, ...]]] = {
    "deepseek": [("chat",), ("coder",)],
    "zhipu": [("flash",), ("air",), ("glm-4",), ("glm-5",)],
    "dashscope": [("turbo",), ("plus",)],
    "moonshot": [("8k",), ("32k",), ("kimi", "chat")],
    "anthropic": [("haiku",), ("sonnet",)],
    "openai": [("mini",), ("gpt-4.1",), ("gpt-4o",)],
    "minimax": [("abab",), ("m2.1",), ("m2.5",)],
    "ollama": [],
}

# ---- 模型上下文窗口映射 ----
# 按模型名称前缀/关键词匹配，返回 context window 大小（token 数）。
# 列表按优先级排序：更具体的模式在前。
_MODEL_CONTEXT_WINDOWS: list[tuple[tuple[str, ...], int]] = [
    (("claude-3-5",), 200_000),
    (("claude-3",), 200_000),
    (("claude-4",), 200_000),
    (("claude",), 200_000),
    (("gpt-4.1",), 1_047_576),
    (("gpt-4o",), 128_000),
    (("gpt-4-turbo",), 128_000),
    (("gpt-4",), 8_192),
    (("gpt-3.5",), 16_385),
    (("o1",), 200_000),
    (("o3",), 200_000),
    (("o4",), 200_000),
    (("deepseek",), 64_000),
    (("glm-5",), 128_000),
    (("glm-4",), 128_000),
    (("glm-3",), 8_192),
    (("moonshot", "128k"), 128_000),
    (("moonshot", "32k"), 32_000),
    (("moonshot", "8k"), 8_000),
    (("kimi",), 128_000),
    (("qwen-max",), 32_000),
    (("qwen-plus",), 131_072),
    (("qwen-turbo",), 131_072),
    (("qwen",), 32_000),
    (("abab",), 245_760),
    (("minimax",), 245_760),
]


def _match_context_window(model_name: str) -> int | None:
    """根据模型名称匹配 context window 大小。"""
    lower = model_name.lower()
    for keywords, window_size in _MODEL_CONTEXT_WINDOWS:
        if all(kw in lower for kw in keywords):
            return window_size
    return None


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
    # 以下两个 key 复用默认路由（None），预留给后续专项配置
    "planning": {
        "provider_id": None,
        "model": None,
        "base_url": None,
    },
    "verification": {
        "provider_id": None,
        "model": None,
        "base_url": None,
    },
}

PURPOSE_ROUTE_FALLBACKS: dict[str, str] = {
    "planning": "chat",
    "verification": "chat",
}


@dataclass(frozen=True)
class _LLMErrorDisposition:
    """LLM 调用错误的统一判定结果。"""

    message: str
    should_fallback: bool
    log_level: int


def _extract_http_status_code(exc: Exception) -> int | None:
    """从 provider/httpx 异常中提取 HTTP 状态码。"""
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if isinstance(status_code, int):
        return status_code
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code
    return None


def _blank_purpose_route() -> PurposeRoute:
    """返回空用途路由占位。"""
    return {
        "provider_id": None,
        "model": None,
        "base_url": None,
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


def _empty_purpose_routes() -> dict[str, PurposeRoute]:
    """返回一份新的用途路由默认值，避免重载时复用旧内存态。"""
    routes: dict[str, PurposeRoute] = {
        key: {
            "provider_id": value.get("provider_id"),
            "model": value.get("model"),
            "base_url": value.get("base_url"),
        }
        for key, value in _load_purpose_routes_from_settings().items()
    }
    for purpose in ("chat", "title_generation", "image_analysis"):
        routes.setdefault(
            purpose,
            {
                "provider_id": None,
                "model": None,
                "base_url": None,
            },
        )
    return routes


# ---- 模型解析器 ----


class ModelResolver:
    """多模型路由与故障转移管理器。

    支持按用途选择模型，并在失败时自动降级到下一个可用提供商。
    """

    def __init__(self, clients: list[BaseLLMClient] | None = None) -> None:
        self._clients: list[BaseLLMClient] = []
        self._client_map: dict[str, BaseLLMClient] = {}
        self._purpose_routes = _empty_purpose_routes()
        self._config_overrides: dict[str, dict[str, Any]] = {}
        # 单一激活供应商 ID（None 表示使用试用模式）
        self._active_provider_id: str | None = None
        # 试用模式客户端（使用内嵌密钥构造）
        self._trial_client: BaseLLMClient | None = None
        # 测试注入标志：构造时传入 clients 则跳过系统内置优先逻辑
        self._injected_clients: bool = clients is not None
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
            ZhipuClient(),
            DeepSeekClient(),
            DashScopeClient(),
            MiniMaxClient(),
            OllamaClient(),
        ]
        self._client_map = {c.provider_id: c for c in self._clients}

    def _normalize_builtin_mode(self, purpose: str, mode: str | None) -> str:
        """归一化系统内置模式标识。"""
        normalized = (mode or "").strip().lower()
        if purpose == "title_generation":
            return BUILTIN_MODE_TITLE
        if normalized == BUILTIN_MODE_DEEP:
            return BUILTIN_MODE_DEEP
        return BUILTIN_MODE_FAST

    def _get_builtin_display_name(self, purpose: str, mode: str | None) -> str:
        """获取系统内置模式的展示名称。"""
        normalized = self._normalize_builtin_mode(purpose, mode)
        if normalized == BUILTIN_MODE_DEEP:
            return "深度"
        if normalized == BUILTIN_MODE_TITLE:
            return "标题生成"
        return "快速"

    def _get_builtin_model_name(self, purpose: str, mode: str | None) -> str | None:
        """将系统内置模式映射到实际模型名称。"""
        normalized = self._normalize_builtin_mode(purpose, mode)
        if purpose == "title_generation":
            return settings.builtin_title_model
        if purpose == "image_analysis":
            return (
                settings.builtin_image_deep_model
                if normalized == BUILTIN_MODE_DEEP
                else settings.builtin_image_fast_model
            )
        return (
            settings.builtin_chat_deep_model
            if normalized == BUILTIN_MODE_DEEP
            else settings.builtin_chat_fast_model
        )

    async def _get_user_configured_provider_ids(self) -> list[str]:
        """获取用户已配置且可参与路由的提供商列表。"""
        if self._injected_clients:
            return [
                client.provider_id
                for client in self._clients
                if client.provider_id and client.is_available()
            ]

        from nini.config_manager import list_user_configured_provider_ids

        return await list_user_configured_provider_ids()

    async def _build_builtin_quota_error(self, exhausted_mode: str) -> RuntimeError:
        """根据内置模式耗尽情况构造分场景提示。"""
        from nini.config_manager import is_builtin_exhausted

        configured_provider_ids = await self._get_user_configured_provider_ids()
        has_user_provider = len(configured_provider_ids) > 0

        normalized = exhausted_mode if exhausted_mode == BUILTIN_MODE_DEEP else BUILTIN_MODE_FAST
        exhausted_label = "深度" if normalized == BUILTIN_MODE_DEEP else "快速"
        switch_mode = BUILTIN_MODE_FAST if normalized == BUILTIN_MODE_DEEP else BUILTIN_MODE_DEEP
        switch_label = "快速" if switch_mode == BUILTIN_MODE_FAST else "深度"
        switch_available = not await is_builtin_exhausted(switch_mode)

        if switch_available:
            if has_user_provider:
                return RuntimeError(
                    f"系统内置「{exhausted_label}」试用额度已用完，请切换到「{switch_label}」或你已配置的模型继续使用。"
                )
            return RuntimeError(
                f"系统内置「{exhausted_label}」试用额度已用完，请切换到「{switch_label}」继续使用。"
            )

        if has_user_provider:
            return RuntimeError("系统内置试用额度已全部用完，请切换到你已配置的模型继续使用。")

        return RuntimeError(
            "系统内置试用额度已全部用完，请在「AI 设置」中配置自己的模型服务商继续使用。"
        )

    def _get_specific_client_for_route(
        self,
        provider_id: str,
        *,
        model: str | None = None,
        base_url: str | None = None,
    ) -> BaseLLMClient | None:
        """按指定 provider 精确获取单个客户端，不启用自动降级。"""
        built_client = None
        if model or base_url:
            built_client = self._build_client_for_provider(
                provider_id,
                model=model,
                base_url=base_url,
            )
        if built_client and built_client.is_available():
            return built_client

        client = self._client_map.get(provider_id)
        if client and client.is_available():
            return client
        return None

    @staticmethod
    def _route_is_configured(route: PurposeRoute | None) -> bool:
        """判断用途路由是否包含显式配置。"""
        if route is None:
            return False
        return any(route.get(field) for field in ("provider_id", "model", "base_url"))

    def _get_effective_purpose_route(self, purpose: str) -> PurposeRoute:
        """获取指定用途的有效路由，必要时继承 chat 路由。"""
        default_route = self._purpose_routes.get("default") or _blank_purpose_route()
        route = self._purpose_routes.get(purpose) or default_route
        if self._route_is_configured(route):
            return route

        fallback_purpose = PURPOSE_ROUTE_FALLBACKS.get(purpose)
        if fallback_purpose:
            fallback_route = self._purpose_routes.get(fallback_purpose)
            if fallback_route is not None and self._route_is_configured(fallback_route):
                return fallback_route

        return route

    @staticmethod
    def _load_encrypted_packaged_secret(name: str) -> str | None:
        """从打包阶段生成的模块中读取并解密密钥。"""
        try:
            from nini import _builtin_key  # type: ignore[attr-defined, import-not-found]

            value = getattr(_builtin_key, name, None)
            if isinstance(value, str) and value:
                return decrypt_key(value) or None
        except ImportError:
            pass
        return None

    @staticmethod
    def _load_builtin_api_key() -> str | None:
        """加载内置 API Key。

        优先读取 settings.builtin_dashscope_api_key（.env 开发模式），
        若为空则尝试从构建时生成的 _builtin_key.py 解密读取。
        """
        # 开发模式：直接使用 .env 中配置的明文 Key
        if settings.builtin_dashscope_api_key:
            return settings.builtin_dashscope_api_key
        # 打包模式：从加密模块解密
        packaged_key = ModelResolver._load_encrypted_packaged_secret("ENCRYPTED_BUILTIN_KEY")
        if packaged_key:
            return packaged_key
        # 最终回退：用用户自己的 dashscope key
        return settings.dashscope_api_key

    @staticmethod
    def _load_trial_api_key() -> str | None:
        """加载试用模式 API Key。"""
        if settings.trial_api_key:
            return settings.trial_api_key
        return ModelResolver._load_encrypted_packaged_secret("ENCRYPTED_TRIAL_KEY")

    @staticmethod
    def _has_builtin_client_available() -> bool:
        """检查当前环境是否存在可用的系统内置客户端配置。"""
        return bool(ModelResolver._load_builtin_api_key())

    def _get_builtin_client(self, purpose: str, mode: str | None) -> BaseLLMClient | None:
        """构造系统内置客户端。"""
        model_name = self._get_builtin_model_name(purpose, mode)
        api_key = self._load_builtin_api_key()
        base_url = settings.builtin_dashscope_base_url
        if not model_name:
            return None
        client = DashScopeClient(api_key=api_key, base_url=base_url, model=model_name)
        if client.is_available():
            return client
        return None

    def _should_use_builtin_fast_for_trial_title(self, purpose: str) -> bool:
        """判断试用模式的标题生成是否应改走内置快速模型。"""
        return (
            purpose == "title_generation"
            and not self._active_provider_id
            and not self._injected_clients
        )

    def _get_priority_order(self, purpose: str = "default") -> list[str]:
        """获取指定用途的提供商优先级顺序。"""
        route = self._get_effective_purpose_route(purpose)
        provider_id = route.get("provider_id")

        # 如果配置了特定用途的提供商，优先使用
        priority: list[str] = []
        if (
            provider_id
            and provider_id not in DISABLED_PROVIDER_IDS
            and provider_id in self._client_map
        ):
            priority.append(provider_id)

        # 默认优先级（成本与效果平衡）
        default_priority = [
            c.provider_id
            for c in self._clients
            if c.provider_id and c.provider_id not in DISABLED_PROVIDER_IDS
        ]

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

    @staticmethod
    def _select_title_model_from_available(
        provider_id: str,
        available_models: list[str],
    ) -> str | None:
        """从当前可用模型列表中动态挑选适合标题生成的模型。"""
        matchers = TITLE_MODEL_MATCHERS.get(provider_id, [])
        if not matchers:
            return None

        normalized_models = [
            (model, model.strip().lower()) for model in available_models if str(model).strip()
        ]
        for matcher in matchers:
            for original, normalized in normalized_models:
                if all(keyword in normalized for keyword in matcher):
                    return original
        return None

    async def _get_title_client(self) -> BaseLLMClient | None:
        """获取用于标题生成的客户端。

        优先基于当前服务商的可用模型列表动态选取更轻量的标题模型，
        匹配失败时回退到当前激活供应商的主模型。
        """
        if not self._active_provider_id:
            return self._trial_client  # 试用模式直接用试用客户端

        active_client = self._get_single_active_client()
        if active_client is None:
            return None

        from nini.agent.model_lister import list_available_models

        override = self._config_overrides.get(self._active_provider_id, {})
        api_key = override.get("api_key")
        base_url = override.get("base_url")
        model_source = "fallback_active_model"
        try:
            result = await list_available_models(
                provider_id=self._active_provider_id,
                api_key=api_key,
                base_url=base_url,
            )
            model_source = str(result.get("source") or "unknown")
            title_model = self._select_title_model_from_available(
                self._active_provider_id,
                result.get("models", []),
            )
        except Exception as exc:
            logger.debug(
                "动态选择标题模型失败，回退主模型: provider=%s err=%s",
                self._active_provider_id,
                exc,
            )
            title_model = None

        if not title_model:
            logger.info(
                "标题生成模型已确定: provider=%s model=%s source=%s",
                self._active_provider_id,
                active_client.get_model_name() or "unknown",
                "fallback_active_model",
            )
            return active_client

        if title_model == active_client.get_model_name():
            logger.info(
                "标题生成模型已确定: provider=%s model=%s source=%s",
                self._active_provider_id,
                active_client.get_model_name() or "unknown",
                model_source,
            )
            return active_client

        built = self._build_client_for_provider(self._active_provider_id, model=title_model)
        if built and built.is_available():
            logger.info(
                "标题生成模型已确定: provider=%s model=%s source=%s",
                self._active_provider_id,
                title_model,
                model_source,
            )
            return built

        logger.info(
            "标题生成模型已确定: provider=%s model=%s source=%s",
            self._active_provider_id,
            active_client.get_model_name() or "unknown",
            "fallback_active_model",
        )
        return active_client

    def get_model_context_window(self) -> int | None:
        """获取当前活跃模型的 context window 大小（token 数）。"""
        client = self._get_single_active_client() or self._trial_client
        if client is None:
            return None
        model_name = client.get_model_name()
        if not model_name:
            return None
        return _match_context_window(model_name)

    def _classify_llm_error(self, exc: Exception) -> _LLMErrorDisposition:
        """将 LLM/HTTP 异常映射为重试策略与用户友好提示。"""
        status_code = _extract_http_status_code(exc)

        if isinstance(exc, (openai.AuthenticationError, anthropic.AuthenticationError)):
            return _LLMErrorDisposition(
                message="API Key 无效或已过期，请检查配置",
                should_fallback=False,
                log_level=logging.ERROR,
            )
        if status_code in {401, 403}:
            return _LLMErrorDisposition(
                message="API Key 无效或权限不足，请检查配置",
                should_fallback=False,
                log_level=logging.ERROR,
            )
        if isinstance(exc, (openai.RateLimitError, anthropic.RateLimitError)) or status_code == 429:
            return _LLMErrorDisposition(
                message="请求过于频繁，请稍后重试",
                should_fallback=True,
                log_level=logging.WARNING,
            )
        if isinstance(exc, httpx.TimeoutException):
            return _LLMErrorDisposition(
                message="连接超时，请检查网络或 Base URL",
                should_fallback=True,
                log_level=logging.WARNING,
            )
        if isinstance(exc, httpx.ConnectError):
            return _LLMErrorDisposition(
                message="无法连接到服务器，请检查网络或 Base URL",
                should_fallback=True,
                log_level=logging.WARNING,
            )
        if status_code == 503:
            return _LLMErrorDisposition(
                message="服务暂时不可用，请稍后重试",
                should_fallback=True,
                log_level=logging.WARNING,
            )
        if status_code == 400:
            return _LLMErrorDisposition(
                message="请求参数无效，请检查模型或 Base URL 配置",
                should_fallback=False,
                log_level=logging.ERROR,
            )
        if isinstance(exc, (openai.APIError, anthropic.APIError)):
            return _LLMErrorDisposition(
                message=self._compact_error_message(exc),
                should_fallback=True,
                log_level=logging.ERROR,
            )
        return _LLMErrorDisposition(
            message=self._compact_error_message(exc),
            should_fallback=True,
            log_level=logging.ERROR,
        )

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
        route = self._get_effective_purpose_route(purpose)
        route_provider = route.get("provider_id")
        route_model = route.get("model")
        route_base_url = route.get("base_url")
        configured_provider_ids = await self._get_user_configured_provider_ids()
        allow_user_fallback = len(configured_provider_ids) > 1

        # 待计费的内置模式（title 不计入限额）
        builtin_mode_to_count: str | None = None

        clients: list[BaseLLMClient] = []
        if route_provider == BUILTIN_PROVIDER_ID:
            # 显式路由到内置供应商：检查限额
            use_trial_fast_title = self._should_use_builtin_fast_for_trial_title(purpose)
            builtin_purpose = "default" if use_trial_fast_title else purpose
            builtin_mode = BUILTIN_MODE_FAST if use_trial_fast_title else route_model
            mode_candidate = (
                BUILTIN_MODE_FAST
                if use_trial_fast_title
                else self._normalize_builtin_mode(purpose, route_model)
            )
            if mode_candidate != BUILTIN_MODE_TITLE:
                from nini.config_manager import is_builtin_exhausted

                exhausted = await is_builtin_exhausted(mode_candidate)
            else:
                exhausted = False
            if not exhausted:
                builtin_client = self._get_builtin_client(builtin_purpose, builtin_mode)
                if builtin_client:
                    if mode_candidate != BUILTIN_MODE_TITLE:
                        builtin_mode_to_count = mode_candidate
                    clients = [builtin_client]
            if not clients:
                raise await self._build_builtin_quota_error(mode_candidate)
        elif route_provider:
            selected_client = self._get_specific_client_for_route(
                route_provider,
                model=route_model,
                base_url=route_base_url,
            )
            if selected_client:
                if allow_user_fallback:
                    clients = self._merge_fallback_clients(
                        selected_client,
                        self._get_ordered_clients(purpose),
                    )
                else:
                    clients = [selected_client]
            elif purpose == "title_generation":
                # 标题生成遇到无效路由时，优先回退到当前激活/试用来源，
                # 避免意外命中历史残留供应商。
                title_client = await self._get_title_client()
                if title_client:
                    clients = [title_client]
            elif allow_user_fallback:
                clients = self._get_ordered_clients(purpose)
        else:
            # 无显式路由：默认走系统内置；仅在用户明确配置多个服务商时才允许降级。
            # 测试注入模式下跳过系统内置，直接使用注入的客户端
            if purpose == "title_generation":
                # 试用模式下标题生成复用快速模式模型，避免依赖用户私有 AI 配置。
                if self._should_use_builtin_fast_for_trial_title(purpose):
                    from nini.config_manager import is_builtin_exhausted

                    exhausted = await is_builtin_exhausted(BUILTIN_MODE_FAST)
                    if not exhausted:
                        builtin_client = self._get_builtin_client("default", BUILTIN_MODE_FAST)
                        if builtin_client:
                            builtin_mode_to_count = BUILTIN_MODE_FAST
                            clients = [builtin_client]
                    else:
                        raise await self._build_builtin_quota_error(BUILTIN_MODE_FAST)
                if not clients:
                    # 已配置供应商时，标题生成仍优先走廉价模型偏好。
                    title_client = await self._get_title_client()
                    if title_client:
                        clients = [title_client]
            else:
                if not self._injected_clients:
                    from nini.config_manager import is_builtin_exhausted

                    exhausted = await is_builtin_exhausted(BUILTIN_MODE_FAST)
                    if not exhausted:
                        builtin_client = self._get_builtin_client(purpose, BUILTIN_MODE_FAST)
                        if builtin_client:
                            builtin_mode_to_count = BUILTIN_MODE_FAST
                            clients = [builtin_client]
                    else:
                        raise await self._build_builtin_quota_error(BUILTIN_MODE_FAST)
                if not clients:
                    if self._active_provider_id:
                        active_client = self._get_single_active_client()
                        if active_client:
                            clients = [active_client]
                    elif self._trial_client:
                        clients = [self._trial_client]
                    elif allow_user_fallback:
                        clients = self._get_ordered_clients(purpose)

        if not clients:
            raise RuntimeError("未配置 AI 服务，请先在「AI 设置」中配置供应商密钥")
        fallback_chain: list[dict[str, Any]] = []
        last_error: Exception | None = None
        builtin_usage_counted = False

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
            first_failed = next(
                (item for item in fallback_chain if item.get("status") == "failed"), None
            )

            try:
                async for chunk in client.chat(
                    messages=messages,
                    tools=tools,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ):
                    if builtin_mode_to_count is not None and not builtin_usage_counted:
                        from nini.config_manager import increment_builtin_usage

                        await increment_builtin_usage(builtin_mode_to_count)
                        builtin_usage_counted = True
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
                        fallback_from_provider_id=(
                            first_failed.get("provider_id") if first_failed else None
                        ),
                        fallback_from_model=first_failed.get("model") if first_failed else None,
                        fallback_reason=first_failed.get("error") if first_failed else None,
                        fallback_chain=[*fallback_chain, success_entry],
                    )
                return
            except Exception as e:
                last_error = e
                disposition = self._classify_llm_error(e)
                compact_error = disposition.message
                debug_dump_path = str(getattr(e, "debug_dump_path", "") or "").strip() or None
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
                log_message = (
                    "LLM 客户端调用失败，尝试下一个提供商: provider=%s model=%s reason=%s"
                    if disposition.should_fallback
                    else "LLM 客户端调用失败，停止 fallback: provider=%s model=%s reason=%s"
                )
                log_args: tuple[Any, ...] = (provider_id, model_name, compact_error)
                if debug_dump_path:
                    log_message += " dump=%s"
                    log_args = (*log_args, debug_dump_path)
                logger.log(disposition.log_level, log_message, *log_args)
                if not disposition.should_fallback:
                    raise RuntimeError(compact_error) from e

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
                usage["input_tokens"] = usage.get("input_tokens", 0) + chunk.usage.get(
                    "input_tokens", 0
                )
                usage["output_tokens"] = usage.get("output_tokens", 0) + chunk.usage.get(
                    "output_tokens", 0
                )
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
        api_key: str | None = None,
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
            MiniMaxClient,
            MoonshotClient,
            OllamaClient,
            OpenAIClient,
            ZhipuClient,
        )

        # 获取配置覆盖
        override = self._config_overrides.get(provider_id, {})
        default_api_key = override.get("api_key")
        default_model = override.get("model")
        default_base_url = override.get("base_url")

        # 使用传入的参数或配置覆盖
        final_api_key = api_key or default_api_key
        final_model = model or default_model
        final_base_url = base_url or default_base_url

        client_map: dict[str, type[BaseLLMClient]] = {
            "openai": OpenAIClient,
            "anthropic": AnthropicClient,
            "moonshot": MoonshotClient,
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
        if final_api_key:
            kwargs["api_key"] = final_api_key
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
        route = self._get_effective_purpose_route(purpose)
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

    @staticmethod
    def _merge_fallback_clients(
        primary_client: BaseLLMClient,
        fallback_clients: list[BaseLLMClient],
    ) -> list[BaseLLMClient]:
        """合并首选客户端与降级链，按 provider 去重保留首次出现项。"""
        merged: list[BaseLLMClient] = []
        seen_provider_ids: set[str] = set()

        for client in [primary_client, *fallback_clients]:
            provider_id = getattr(client, "provider_id", "") or ""
            if provider_id in seen_provider_ids:
                continue
            seen_provider_ids.add(provider_id)
            merged.append(client)

        return merged

    def get_active_model_info(self, purpose: str = "default") -> dict[str, Any]:
        """获取指定用途的活跃模型信息。

        Args:
            purpose: 用途标识，如 "default", "chat", "coding", "analysis", "vision"

        Returns:
            包含 provider_id, provider_name, model, preferred_provider 的字典
        """
        # 获取按用途排序的客户端列表
        route = self._get_effective_purpose_route(purpose)
        route_model = route.get("model") if route else None
        route_provider = route.get("provider_id") if route else None

        if route_provider == BUILTIN_PROVIDER_ID:
            return {
                "provider_id": BUILTIN_PROVIDER_ID,
                "provider_name": BUILTIN_PROVIDER_NAME,
                "model": self._get_builtin_display_name(purpose, route_model),
                "preferred_provider": BUILTIN_PROVIDER_ID,
                "purpose_preferred_providers": self.get_preferred_providers_by_purpose(),
            }

        # 无显式路由时，默认展示系统内置（不检查可用性；实际发送时由 chat() 降级）
        # 注意：不依赖 _active_provider_id，已配置供应商不影响默认展示
        if route_provider is None and not self._injected_clients:
            return {
                "provider_id": BUILTIN_PROVIDER_ID,
                "provider_name": BUILTIN_PROVIDER_NAME,
                "model": self._get_builtin_display_name(purpose, BUILTIN_MODE_FAST),
                "preferred_provider": BUILTIN_PROVIDER_ID,
                "purpose_preferred_providers": self.get_preferred_providers_by_purpose(),
            }

        ordered = self._get_ordered_clients(purpose)

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
        route = self._get_effective_purpose_route(purpose)
        return route.get("provider_id")

    def get_preferred_providers_by_purpose(self) -> dict[str, str | None]:
        """获取各用途的首选提供商。"""
        return {
            purpose: route.get("provider_id") for purpose, route in self._purpose_routes.items()
        }

    def get_purpose_routes(self) -> dict[str, PurposeRoute]:
        """获取用途路由配置。"""
        return self._purpose_routes.copy()

    def set_preferred_provider(self, provider_id: str | None, purpose: str = "default") -> None:
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
            return priorities.get(
                client.provider_id, default_priorities.get(client.provider_id, 999)
            )

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

    async def test_connection(
        self,
        provider_id: str,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ) -> dict[str, Any]:
        """测试指定提供商的连接。

        Args:
            provider_id: 提供商 ID

        Returns:
            包含测试结果的字典
        """
        resolved_model = model
        if not resolved_model and provider_id != "anthropic":
            from nini.agent.model_lister import list_available_models

            try:
                available = await list_available_models(
                    provider_id=provider_id,
                    api_key=api_key,
                    base_url=base_url,
                )
                supports_remote_listing = available.get("supports_remote_listing") is not False
                if available.get("source") == "remote":
                    models = available.get("models", [])
                    if isinstance(models, list):
                        first_model = next(
                            (
                                item.strip()
                                for item in models
                                if isinstance(item, str) and item.strip()
                            ),
                            None,
                        )
                        if first_model:
                            resolved_model = first_model
                if not resolved_model and not supports_remote_listing:
                    models = available.get("models", [])
                    if isinstance(models, list):
                        first_model = next(
                            (
                                item.strip()
                                for item in models
                                if isinstance(item, str) and item.strip()
                            ),
                            None,
                        )
                        if first_model:
                            resolved_model = first_model
            except Exception:
                # 测试连接仍应继续尝试默认模型，避免模型列表接口失败直接中断。
                pass

        has_override = any(value is not None for value in (api_key, model, base_url))
        client = (
            self._build_client_for_provider(
                provider_id,
                api_key=api_key,
                model=resolved_model,
                base_url=base_url,
            )
            if has_override
            else self._client_map.get(provider_id)
        )
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
            disposition = self._classify_llm_error(e)
            return {"success": False, "error": disposition.message}

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
        self._purpose_routes = _empty_purpose_routes()

        # 更新单一激活供应商
        self._active_provider_id = active_provider_id

        # 构建试用客户端（仅当有内嵌密钥时）
        if trial_api_key and not self._has_builtin_client_available():
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
                base_url=_get("dashscope", "base_url"),
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
    trial_api_key = ModelResolver._load_trial_api_key()

    resolver = get_model_resolver()
    resolver.reload_clients(
        configs,
        priorities=priorities,
        active_provider_id=active_provider_id,
        trial_api_key=trial_api_key,
    )

    # 应用 purpose_routes，但过滤掉指向未配置供应商的过期路由，
    # 避免历史配置干扰（如曾选 zhipu 但密钥已删除，不应再路由到 zhipu）
    for purpose, route in purpose_routes.items():
        provider_id = route.get("provider_id")
        if not provider_id:
            continue
        # builtin 路由始终应用；外部供应商须有有效 api_key 或 base_url 才应用
        if provider_id == BUILTIN_PROVIDER_ID:
            resolver.set_purpose_route(
                purpose=purpose,
                provider_id=provider_id,
                model=route.get("model"),
                base_url=route.get("base_url"),
            )
        elif configs.get(provider_id, {}).get("api_key") or configs.get(provider_id, {}).get(
            "base_url"
        ):
            resolver.set_purpose_route(
                purpose=purpose,
                provider_id=provider_id,
                model=route.get("model"),
                base_url=route.get("base_url"),
            )
        else:
            logger.debug(
                "跳过过期的用途路由: purpose=%s provider=%s（供应商未配置）", purpose, provider_id
            )


# Module-level singleton for convenient access
model_resolver = get_model_resolver()
