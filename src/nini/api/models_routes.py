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


@router.get("/models", response_model=APIResponse)
async def list_models():
    """列出所有可用的模型提供商和模型。"""
    from nini.config import settings

    models = []

    # OpenAI
    if settings.openai_api_key:
        models.append({
            "provider": "openai",
            "name": "OpenAI",
            "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
        })

    # Anthropic
    if settings.anthropic_api_key:
        models.append({
            "provider": "anthropic",
            "name": "Anthropic",
            "models": ["claude-sonnet-4-20250514", "claude-3-5-sonnet-20241022", "claude-3-haiku-20240307"],
        })

    # Ollama
    models.append({
        "provider": "ollama",
        "name": "Ollama (本地)",
        "models": ["qwen2.5:7b", "llama3.2", "mistral"],
    })

    # DeepSeek
    if settings.deepseek_api_key:
        models.append({
            "provider": "deepseek",
            "name": "DeepSeek",
            "models": ["deepseek-chat", "deepseek-coder"],
        })

    return APIResponse(success=True, data=models)


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
    """获取模型路由配置。"""
    from nini.agent.model_resolver import ModelResolver

    resolver = ModelResolver()
    routing = resolver.get_routing_config()

    return APIResponse(success=True, data=routing)


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
