"""动态获取模型提供商的可用模型列表。

对 OpenAI 兼容提供商调用 /v1/models 端点获取，失败回退静态列表。
结果缓存 5 分钟。
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from nini.config import settings

logger = logging.getLogger(__name__)

# 缓存：{provider_id: (timestamp, models)}
_cache: dict[str, tuple[float, list[str]]] = {}
_CACHE_TTL = 300  # 5 分钟

# 各提供商的 models API 端点和静态兜底列表
_PROVIDER_CONFIG: dict[str, dict[str, Any]] = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "static": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
    },
    "anthropic": {
        "base_url": None,  # Anthropic 不支持 /models 端点
        "static": [
            "claude-sonnet-4-20250514",
            "claude-3-5-sonnet-20241022",
            "claude-3-haiku-20240307",
            "claude-opus-4-20250514",
        ],
    },
    "moonshot": {
        "base_url": "https://api.moonshot.cn/v1",
        "static": [
            "moonshot-v1-8k",
            "moonshot-v1-32k",
            "moonshot-v1-128k",
            "kimi-k2-0711-preview",
        ],
    },
    "kimi_coding": {
        "base_url": settings.kimi_coding_base_url,
        "static": ["kimi-for-coding"],
    },
    "zhipu": {
        "base_url": settings.zhipu_base_url,
        "static": [
            "glm-5",
            "glm-5-plus",
            "glm-5-air",
            "glm-4.7",
            "glm-4.6",
            "glm-4.5",
            "glm-4.5-air",
            "glm-4",
            "glm-4-plus",
            "glm-4-flash",
        ],
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "static": ["deepseek-chat", "deepseek-coder", "deepseek-reasoner"],
    },
    "dashscope": {
        "base_url": settings.dashscope_base_url,
        "static": ["qwen-plus", "qwen-turbo", "qwen-max"],
    },
    "minimax": {
        "base_url": settings.minimax_base_url,
        "static": ["MiniMax-M2.5", "MiniMax-M2.1", "abab6.5s-chat"],
    },
    "ollama": {
        "base_url": None,  # 由用户配置
        "static": ["qwen2.5:7b", "llama3:8b", "mistral:7b"],
    },
}

_DASHSCOPE_CODING_PLAN_MODELS = [
    "qwen3-max-2026-01-23",
    "qwen3-coder-plus",
    "qwen3-coder-next",
    "qwen3.5-plus",
    "glm-5",
    "glm-4.7",
    "kimi-k2.5",
    "MiniMax-M2.5",
]


async def list_available_models(
    provider_id: str,
    api_key: str | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    """获取指定提供商的可用模型列表。

    Args:
        provider_id: 提供商 ID
        api_key: API Key（用于认证）
        base_url: 自定义 base URL

    Returns:
        {"models": [...], "source": "remote" | "static", "supports_remote_listing": bool}
    """
    config = _PROVIDER_CONFIG.get(provider_id, {})
    static_models = config.get("static", [])

    # 检查缓存
    cache_key = f"{provider_id}:{api_key or ''}:{base_url or ''}"
    cached = _cache.get(cache_key)
    if cached and (time.time() - cached[0]) < _CACHE_TTL:
        return {"models": cached[1], "source": "remote", "supports_remote_listing": True}

    # Anthropic 不支持动态获取
    if provider_id == "anthropic":
        return {"models": static_models, "source": "static", "supports_remote_listing": False}

    # 确定 API 端点
    effective_base = base_url or config.get("base_url")
    if not effective_base:
        return {"models": static_models, "source": "static", "supports_remote_listing": True}

    # Ollama 使用不同的端点格式
    if provider_id == "ollama":
        return await _list_ollama_models(effective_base, static_models, cache_key)

    # 阿里 Coding Plan 不支持 /v1/models，直接返回官方支持模型清单。
    if provider_id == "dashscope" and _is_dashscope_coding_plan_base_url(effective_base):
        return {
            "models": _DASHSCOPE_CODING_PLAN_MODELS,
            "source": "static",
            "supports_remote_listing": False,
        }

    # 没有 API Key 的提供商无法调用
    if not api_key:
        return {"models": static_models, "source": "static", "supports_remote_listing": True}

    # 调用 OpenAI 兼容的 /v1/models 端点
    try:
        models_url = _build_models_url(provider_id, effective_base)
        async with httpx.AsyncClient(timeout=10, trust_env=settings.llm_trust_env_proxy) as client:
            resp = await client.get(
                models_url,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()

        model_list: list[str] = []
        if isinstance(data, dict) and "data" in data:
            for item in data["data"]:
                if isinstance(item, dict) and "id" in item:
                    model_list.append(item["id"])

        if model_list:
            # 排序：优先把静态列表中的模型放前面
            static_set = set(static_models)
            prioritized = [m for m in model_list if m in static_set]
            others = sorted(m for m in model_list if m not in static_set)
            result = prioritized + others
            _cache[cache_key] = (time.time(), result)
            return {"models": result, "source": "remote", "supports_remote_listing": True}

        return {"models": static_models, "source": "static", "supports_remote_listing": True}
    except Exception as e:
        logger.debug("获取 %s 模型列表失败: %s", provider_id, e)
        return {"models": static_models, "source": "static", "supports_remote_listing": True}


def _build_models_url(provider_id: str, base_url: str) -> str:
    """为不同形态的兼容端点拼接模型列表地址。"""
    normalized = base_url.rstrip("/")
    if provider_id == "zhipu" and normalized.endswith("/chat/completions"):
        normalized = normalized[: -len("/chat/completions")]
    return f"{normalized}/models"


def _is_dashscope_coding_plan_base_url(base_url: str) -> bool:
    """判断是否为阿里 Coding Plan OpenAI 兼容端点。"""
    normalized = base_url.strip().rstrip("/").lower()
    return normalized == "https://coding.dashscope.aliyuncs.com/v1"


async def _list_ollama_models(
    base_url: str,
    static_models: list[str],
    cache_key: str,
) -> dict[str, Any]:
    """获取 Ollama 本地模型列表。"""
    try:
        url = f"{base_url.rstrip('/')}/api/tags"
        async with httpx.AsyncClient(timeout=5, trust_env=settings.llm_trust_env_proxy) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        models: list[str] = []
        if isinstance(data, dict) and "models" in data:
            for item in data["models"]:
                if isinstance(item, dict) and "name" in item:
                    models.append(item["name"])

        if models:
            _cache[cache_key] = (time.time(), models)
            return {"models": models, "source": "remote", "supports_remote_listing": True}

        return {"models": static_models, "source": "static", "supports_remote_listing": True}
    except Exception as e:
        logger.debug("获取 Ollama 模型列表失败: %s", e)
        return {"models": static_models, "source": "static", "supports_remote_listing": True}
