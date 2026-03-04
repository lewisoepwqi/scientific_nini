"""模型配置和路由路由。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from nini.models.schemas import (
    APIResponse,
    ModelConfigRequest,
    ModelPrioritiesRequest,
    ModelRoutingRequest,
    SetActiveModelRequest,
)

router = APIRouter()


# 模型用途定义
_MODEL_PURPOSES = [
    {"id": "chat", "label": "主对话"},
    {"id": "title_generation", "label": "标题生成"},
    {"id": "image_analysis", "label": "图片识别"},
]

# 模型提供商配置列表
_MODEL_PROVIDERS = [
    {
        "id": "openai",
        "name": "OpenAI",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
        "key_field": "openai_api_key",
        "model_field": "openai_model",
    },
    {
        "id": "anthropic",
        "name": "Anthropic Claude",
        "models": [
            "claude-sonnet-4-20250514",
            "claude-3-5-sonnet-20241022",
            "claude-3-haiku-20240307",
        ],
        "key_field": "anthropic_api_key",
        "model_field": "anthropic_model",
    },
    {
        "id": "moonshot",
        "name": "Moonshot AI (Kimi)",
        "models": [
            "moonshot-v1-8k",
            "moonshot-v1-32k",
            "moonshot-v1-128k",
            "kimi-k2-0711-preview",
        ],
        "key_field": "moonshot_api_key",
        "model_field": "moonshot_model",
    },
    {
        "id": "kimi_coding",
        "name": "Kimi Coding",
        "models": ["kimi-for-coding"],
        "key_field": "kimi_coding_api_key",
        "model_field": "kimi_coding_model",
    },
    {
        "id": "zhipu",
        "name": "智谱 AI (GLM)",
        "models": [
            "glm-4.7",
            "glm-4.6",
            "glm-4.5",
            "glm-4.5-air",
            "glm-4",
            "glm-4-plus",
            "glm-4-flash",
        ],
        "key_field": "zhipu_api_key",
        "model_field": "zhipu_model",
    },
    {
        "id": "deepseek",
        "name": "DeepSeek",
        "models": ["deepseek-chat", "deepseek-coder", "deepseek-reasoner"],
        "key_field": "deepseek_api_key",
        "model_field": "deepseek_model",
    },
    {
        "id": "dashscope",
        "name": "阿里百炼（通义千问）",
        "models": ["qwen-plus", "qwen-turbo", "qwen-max"],
        "key_field": "dashscope_api_key",
        "model_field": "dashscope_model",
    },
    {
        "id": "minimax",
        "name": "MiniMax",
        "models": ["MiniMax-M2.5", "MiniMax-M2.1", "abab6.5s-chat"],
        "key_field": "minimax_api_key",
        "model_field": "minimax_model",
    },
    {
        "id": "ollama",
        "name": "Ollama（本地）",
        "models": ["qwen2.5:7b", "llama3:8b", "mistral:7b"],
        "key_field": None,
        "model_field": "ollama_model",
    },
]


@router.get("/models", response_model=APIResponse)
async def list_models():
    """列出所有可用的模型提供商和模型。

    返回所有模型提供商及其配置状态（合并 DB 与 .env 配置）。
    """
    from nini.config import settings
    from nini.config_manager import get_model_priorities, load_all_model_configs
    from nini.utils.crypto import mask_api_key

    try:
        db_configs = await load_all_model_configs()
    except Exception:
        db_configs = {}
    try:
        priorities = await get_model_priorities()
    except Exception:
        priorities = {p["id"]: idx for idx, p in enumerate(_MODEL_PROVIDERS)}

    result = []
    for idx, provider in enumerate(_MODEL_PROVIDERS):
        pid = provider["id"]
        key_field = provider["key_field"]
        model_field = provider["model_field"]
        db_cfg = db_configs.get(pid, {})

        env_key = getattr(settings, key_field, None) if key_field else None
        effective_key = db_cfg.get("api_key") or env_key or ""
        env_model = getattr(settings, model_field, "") if model_field else ""
        effective_model = db_cfg.get("model") or env_model
        effective_base_url = db_cfg.get("base_url") or ""

        if pid == "ollama":
            env_base = settings.ollama_base_url
            configured = bool((effective_base_url or env_base) and effective_model)
        else:
            configured = bool(effective_key)

        config_source = (
            "db"
            if db_cfg.get("api_key") or db_cfg.get("model")
            else ("env" if (env_key or env_model) else "none")
        )

        result.append(
            {
                "id": pid,
                "name": provider["name"],
                "configured": configured,
                "current_model": effective_model,
                "available_models": provider["models"],
                "api_key_hint": db_cfg.get("api_key_hint") or mask_api_key(env_key or ""),
                "base_url": effective_base_url,
                "priority": int(priorities.get(pid, idx)),
                "config_source": config_source,
            }
        )

    default_idx_map = {provider["id"]: idx for idx, provider in enumerate(_MODEL_PROVIDERS)}
    result.sort(key=lambda item: (item["priority"], default_idx_map.get(item["id"], 999)))

    return APIResponse(success=True, data=result)


@router.get("/models/{provider_id}/available", response_model=APIResponse)
async def get_provider_available_models(provider_id: str):
    """获取指定提供商的可用模型列表。"""
    from nini.agent.model_resolver import ModelResolver

    resolver = ModelResolver()
    models = resolver.get_available_models(provider_id)

    return APIResponse(success=True, data=models)


@router.post("/models/priorities", response_model=APIResponse)
async def set_model_priorities(request: ModelPrioritiesRequest):
    """设置模型优先级。"""
    from nini.agent.model_resolver import ModelResolver

    resolver = ModelResolver()
    resolver.set_priorities(request.priorities)

    return APIResponse(success=True)


@router.get("/models/routing", response_model=APIResponse)
async def get_model_routing():
    """获取用途模型路由配置与当前生效模型。"""
    from nini.agent.model_resolver import model_resolver
    from nini.config_manager import get_model_purpose_routes

    preferred_provider = model_resolver.get_preferred_provider()
    purpose_routes = await get_model_purpose_routes()
    active_by_purpose: dict[str, dict[str, str]] = {}
    purpose_providers: dict[str, str | None] = {}
    for item in _MODEL_PURPOSES:
        purpose = item["id"]
        purpose_providers[purpose] = purpose_routes.get(purpose, {}).get("provider_id")
        active_by_purpose[purpose] = model_resolver.get_active_model_info(purpose=purpose)

    return APIResponse(
        data={
            "preferred_provider": preferred_provider,
            "purpose_routes": purpose_routes,
            "purpose_providers": purpose_providers,
            "active_by_purpose": active_by_purpose,
            "purposes": _MODEL_PURPOSES,
        }
    )


@router.post("/models/routing", response_model=APIResponse)
async def set_model_routing(request: ModelRoutingRequest):
    """设置模型路由配置。"""
    from nini.agent.model_resolver import ModelResolver, get_model_resolver
    from nini.config_manager import set_model_purpose_routes

    # 更新内存中的配置
    resolver = ModelResolver()
    resolver.set_routing_config(request.config)

    # 持久化到数据库
    if "purpose_routes" in request.config:
        await set_model_purpose_routes(request.config["purpose_routes"])

    # 同步更新全局 resolver
    global_resolver = get_model_resolver()
    if global_resolver is not resolver:
        global_resolver.set_routing_config(request.config)

    return APIResponse(success=True)


@router.post("/models/config", response_model=APIResponse)
async def update_model_config(request: ModelConfigRequest):
    """更新模型配置。"""
    # 这里可以实现模型配置的持久化
    return APIResponse(success=True)


@router.post("/models/{provider_id}/test", response_model=APIResponse)
async def test_model_connection(provider_id: str):
    """测试模型连接。"""
    from nini.agent.model_resolver import ModelResolver

    resolver = ModelResolver()

    try:
        result = await resolver.test_connection(provider_id)
        return APIResponse(
            success=result.get("success", False),
            data=result,
        )
    except Exception as e:
        return APIResponse(
            success=False,
            error=f"连接测试失败: {e}",
        )


@router.get("/models/active", response_model=APIResponse)
async def get_active_models():
    """获取当前活动的模型（用于聊天用途）。"""
    from nini.agent.model_resolver import get_model_resolver

    resolver = get_model_resolver()
    # 使用 "chat" purpose 获取用户为对话选择的模型
    active = resolver.get_active_model_info(purpose="chat")

    return APIResponse(success=True, data=active)


@router.post("/models/preferred", response_model=APIResponse)
async def set_preferred_model(request: SetActiveModelRequest):
    """设置首选模型。"""
    from nini.agent.model_resolver import ModelResolver

    resolver = ModelResolver()
    resolver.set_preferred_model(request.provider, request.model)

    return APIResponse(success=True)


@router.get("/models/default", response_model=APIResponse)
async def get_default_model():
    """获取默认模型配置。"""
    from nini.config import settings

    return APIResponse(
        success=True,
        data={
            "provider": "openai",
            "model": settings.openai_model,
        },
    )
