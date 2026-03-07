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

# 面向用户暴露的 4 个供应商（外部分发版）
_MODEL_PROVIDERS = [
    {
        "id": "deepseek",
        "name": "DeepSeek",
        "description": "国内直连，性价比优先",
        "key_url": "https://platform.deepseek.com",
        "key_field": "deepseek_api_key",
        "model_field": "deepseek_model",
    },
    {
        "id": "zhipu",
        "name": "智谱 GLM",
        "description": "国内直连，含免费额度",
        "key_url": "https://open.bigmodel.cn",
        "key_field": "zhipu_api_key",
        "model_field": "zhipu_model",
    },
    {
        "id": "dashscope",
        "name": "通义千问",
        "description": "阿里百炼，国内直连",
        "key_url": "https://bailian.console.aliyun.com",
        "key_field": "dashscope_api_key",
        "model_field": "dashscope_model",
    },
    {
        "id": "ollama",
        "name": "本地模型",
        "description": "数据不出境，需安装 Ollama",
        "key_url": "https://ollama.com",
        "key_field": None,
        "model_field": "ollama_model",
    },
]


@router.get("/models", response_model=APIResponse)
async def list_models():
    """列出面向用户的 4 个供应商及其配置状态（合并 DB 与 .env 配置）。"""
    from nini.config import settings
    from nini.config_manager import get_active_provider_id, load_all_model_configs
    from nini.utils.crypto import mask_api_key

    try:
        db_configs = await load_all_model_configs()
    except Exception:
        db_configs = {}

    try:
        active_provider_id = await get_active_provider_id()
    except Exception:
        active_provider_id = None

    result = []
    for provider in _MODEL_PROVIDERS:
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
            # Ollama 无 API Key 概念，"已配置"须依赖 DB 中的显式记录。
            # settings.ollama_base_url / ollama_model 均有非空默认值，不能作为
            # 判断依据，否则删除配置后 configured 仍为 True。
            db_base = db_cfg.get("base_url") or ""
            db_model = db_cfg.get("model") or ""
            configured = bool(db_base or db_model)
            config_source = "db" if configured else "none"
        else:
            configured = bool(effective_key)
            config_source = (
                "db"
                if db_cfg.get("api_key") or db_cfg.get("model")
                else ("env" if env_key else "none")
            )

        result.append(
            {
                "id": pid,
                "name": provider["name"],
                "description": provider.get("description", ""),
                "key_url": provider.get("key_url", ""),
                "configured": configured,
                "is_active": pid == active_provider_id,
                "current_model": effective_model,
                "api_key_hint": db_cfg.get("api_key_hint") or mask_api_key(env_key or ""),
                "base_url": effective_base_url,
                "config_source": config_source,
            }
        )

    return APIResponse(success=True, data=result)


@router.get("/models/{provider_id}/available", response_model=APIResponse)
async def get_provider_available_models(provider_id: str):
    """动态获取指定提供商的可用模型列表。"""
    from nini.agent.model_lister import list_available_models
    from nini.config_manager import get_effective_config

    cfg = await get_effective_config(provider_id)
    result = await list_available_models(
        provider_id=provider_id,
        api_key=cfg.get("api_key"),
        base_url=cfg.get("base_url"),
    )
    return APIResponse(data=result)


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
async def set_model_routing(req: ModelRoutingRequest):
    """保存用途模型路由配置（支持部分更新）。"""
    from nini.agent.model_resolver import get_model_resolver
    from nini.config_manager import (
        set_default_provider,
        set_model_purpose_routes,
        VALID_MODEL_PURPOSES,
        VALID_PROVIDERS,
        VALID_ROUTE_PROVIDERS,
    )

    resolver = get_model_resolver()

    update_global_preferred = "preferred_provider" in req.model_fields_set
    preferred_provider: str | None = None
    if update_global_preferred:
        preferred_provider_raw = (req.preferred_provider or "").strip()
        preferred_provider = preferred_provider_raw or None
        if preferred_provider and preferred_provider not in VALID_PROVIDERS:
            return APIResponse(success=False, error=f"未知的模型提供商: {preferred_provider}")

    updates: dict[str, dict[str, str | None]] = {}
    # 兼容旧版字段：purpose_providers（仅 provider）
    for purpose, provider in req.purpose_providers.items():
        if purpose not in VALID_MODEL_PURPOSES:
            return APIResponse(success=False, error=f"未知的模型用途: {purpose}")
        provider_id = (provider or "").strip() or None
        if provider_id and provider_id not in VALID_ROUTE_PROVIDERS:
            return APIResponse(success=False, error=f"未知的模型提供商: {provider_id}")
        updates[purpose] = {
            "provider_id": provider_id,
            "model": None,
            "base_url": None,
        }

    # 新版字段：purpose_routes（provider + model + base_url）
    for purpose, route in req.purpose_routes.items():
        if purpose not in VALID_MODEL_PURPOSES:
            return APIResponse(success=False, error=f"未知的模型用途: {purpose}")
        provider_id = (route.provider_id or "").strip() or None
        model = (route.model or "").strip() or None
        base_url = (route.base_url or "").strip() or None
        if provider_id and provider_id not in VALID_ROUTE_PROVIDERS:
            return APIResponse(success=False, error=f"未知的模型提供商: {provider_id}")
        updates[purpose] = {
            "provider_id": provider_id,
            "model": model,
            "base_url": base_url,
        }

    # 更新全局首选（为空表示清除）
    if update_global_preferred:
        await set_default_provider(preferred_provider)
        resolver.set_preferred_provider(preferred_provider)

    # 更新用途路由（增量）
    merged_routes = await set_model_purpose_routes(updates)
    for purpose_key, merged_route in merged_routes.items():
        resolver.set_purpose_route(
            purpose_key,
            provider_id=merged_route.get("provider_id"),
            model=merged_route.get("model"),
            base_url=merged_route.get("base_url"),
        )

    active_by_purpose: dict[str, dict[str, str]] = {}
    purpose_providers: dict[str, str | None] = {}
    for item in _MODEL_PURPOSES:
        purpose_id: str = item["id"]
        merged_r = merged_routes.get(purpose_id)
        purpose_providers[purpose_id] = merged_r.get("provider_id") if merged_r else None
        active_by_purpose[purpose_id] = resolver.get_active_model_info(purpose=purpose_id)

    return APIResponse(
        data={
            "preferred_provider": resolver.get_preferred_provider(),
            "purpose_routes": merged_routes,
            "purpose_providers": purpose_providers,
            "active_by_purpose": active_by_purpose,
        }
    )


@router.post("/models/config", response_model=APIResponse)
async def update_model_config(request: ModelConfigRequest):
    """更新模型配置。

    保存配置到数据库并重新加载模型客户端，使新配置立即生效。
    """
    from nini.config_manager import save_model_config

    try:
        # 保存配置到数据库
        result = await save_model_config(
            provider=request.provider_id,
            api_key=request.api_key,
            model=request.model,
            base_url=request.base_url,
            priority=request.priority,
            is_active=request.is_active,
        )

        # 将该供应商设为唯一激活供应商
        from nini.config_manager import set_active_provider

        await set_active_provider(request.provider_id)

        # 重新加载模型客户端，使新配置生效
        from nini.agent.model_resolver import reload_model_resolver

        await reload_model_resolver()

        return APIResponse(
            success=True,
            data={
                "provider": result["provider"],
                "model": result["model"],
                "api_key_hint": result["api_key_hint"],
                "base_url": result["base_url"],
            },
        )
    except ValueError as e:
        return APIResponse(success=False, error=str(e))
    except Exception as e:
        return APIResponse(success=False, error=f"保存配置失败: {e}")


@router.post("/models/{provider_id}/test", response_model=APIResponse)
async def test_model_connection(provider_id: str):
    """测试模型连接。"""
    from nini.agent.model_resolver import get_model_resolver

    resolver = get_model_resolver()

    try:
        result = await resolver.test_connection(provider_id)
        if result.get("success"):
            return APIResponse(
                success=True,
                data={
                    "provider": result.get("provider"),
                    "model": result.get("model"),
                    "message": result.get("message", "连接成功"),
                },
            )
        else:
            return APIResponse(
                success=False,
                error=result.get("error", "连接测试失败"),
            )
    except Exception as e:
        return APIResponse(
            success=False,
            error=f"连接测试失败: {e}",
        )


@router.get("/trial/status", response_model=APIResponse)
async def get_trial_status():
    """获取试用状态（按调用次数限额、是否耗尽、内置用量）。"""
    from nini.config import settings
    from nini.config_manager import get_active_provider_id, get_trial_status

    status = await get_trial_status()
    # 若已配置自有密钥，前端不需要显示横幅
    active_provider = await get_active_provider_id()
    status["has_own_key"] = active_provider is not None
    # 附加限额上限，方便前端展示进度条
    status["fast_limit"] = settings.builtin_fast_limit
    status["deep_limit"] = settings.builtin_deep_limit
    return APIResponse(success=True, data=status)


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
    resolver.set_preferred_model(request.provider_id, request.model)

    return APIResponse(success=True)


@router.delete("/models/{provider_id}/config", response_model=APIResponse)
async def delete_model_config(provider_id: str):
    """删除指定供应商的配置，并清除其激活状态与用途路由。"""
    from nini.agent.model_resolver import reload_model_resolver
    from nini.config_manager import (
        get_active_provider_id,
        get_model_purpose_routes,
        remove_model_config,
        set_active_provider,
        set_model_purpose_routes,
    )

    try:
        # 若被删供应商是当前激活供应商，先清除激活状态
        active_id = await get_active_provider_id()
        if active_id == provider_id:
            await set_active_provider(None)

        # 清除所有指向该供应商的用途路由，避免残留路由干扰后续行为
        current_routes = await get_model_purpose_routes()
        routes_to_clear = {
            purpose: {"provider_id": None, "model": None, "base_url": None}
            for purpose, route in current_routes.items()
            if route.get("provider_id") == provider_id
        }
        if routes_to_clear:
            await set_model_purpose_routes(routes_to_clear)

        await remove_model_config(provider_id)
        await reload_model_resolver()

        return APIResponse(success=True, data={"provider": provider_id})
    except ValueError as e:
        return APIResponse(success=False, error=str(e))
    except Exception as e:
        return APIResponse(success=False, error=f"删除配置失败: {e}")


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
