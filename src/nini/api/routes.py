"""HTTP 端点（文件上传/下载、会话管理）。"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from nini.agent.session import session_manager
from nini.config import settings
from nini.models.schemas import (
    APIResponse,
    DatasetInfo,
    ModelConfigRequest,
    SessionInfo,
    SessionUpdateRequest,
    SetActiveModelRequest,
    UploadResponse,
)

router = APIRouter(prefix="/api")


# ---- 会话管理 ----


@router.get("/sessions", response_model=APIResponse)
async def list_sessions():
    """获取会话列表。"""
    sessions = session_manager.list_sessions()
    return APIResponse(data=sessions)


@router.post("/sessions", response_model=APIResponse)
async def create_session():
    """创建新会话。"""
    session = session_manager.create_session()
    return APIResponse(data={"session_id": session.id})


@router.get("/sessions/{session_id}/messages", response_model=APIResponse)
async def get_session_messages(session_id: str):
    """获取指定会话的消息历史。"""
    session = session_manager.get_session(session_id)
    if session is not None:
        # 会话在内存中，直接返回消息
        messages = session.messages
    else:
        # 尝试从磁盘加载
        from nini.memory.conversation import ConversationMemory

        mem = ConversationMemory(session_id)
        messages = mem.load_messages()
        if not messages:
            raise HTTPException(status_code=404, detail="会话不存在或无消息记录")

    # 过滤掉内部字段（如 _ts），只返回前端需要的字段
    cleaned: list[dict] = []
    for msg in messages:
        item = {
            "role": msg.get("role", ""),
            "content": msg.get("content", ""),
            "tool_calls": msg.get("tool_calls"),
            "tool_call_id": msg.get("tool_call_id"),
            "event_type": msg.get("event_type"),
            "chart_data": msg.get("chart_data"),
            "data_preview": msg.get("data_preview"),
            "artifacts": msg.get("artifacts"),
            "images": msg.get("images"),
        }
        cleaned.append(item)
    return APIResponse(data={"session_id": session_id, "messages": cleaned})


@router.patch("/sessions/{session_id}", response_model=APIResponse)
async def update_session(session_id: str, req: SessionUpdateRequest):
    """更新会话信息（如标题）。"""
    if req.title is not None:
        title = req.title.strip() or "新会话"
        session_manager.update_session_title(session_id, title)
        session_manager.save_session_title(session_id, title)
    return APIResponse(data={"session_id": session_id, "title": req.title})


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """删除会话。"""
    session_manager.remove_session(session_id, delete_persistent=True)
    return APIResponse(data={"deleted": session_id})


# ---- 文件上传 ----


@router.post("/upload", response_model=UploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    session_id: str = Form(...),
):
    """上传数据文件到指定会话。"""
    session = session_manager.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 验证文件类型
    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少文件名")

    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in settings.allowed_extensions_list:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: .{ext}，支持: {settings.allowed_extensions}",
        )

    # 保存文件
    dataset_id = uuid.uuid4().hex[:12]
    save_path = settings.upload_dir / f"{dataset_id}.{ext}"

    content = await file.read()
    if len(content) > settings.max_upload_size:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大（{len(content)} 字节），最大 {settings.max_upload_size} 字节",
        )

    save_path.write_bytes(content)

    # 读取为 DataFrame
    try:
        if ext in ("xlsx", "xls"):
            df = pd.read_excel(save_path)
        elif ext == "csv":
            df = pd.read_csv(save_path)
        elif ext in ("tsv", "txt"):
            df = pd.read_csv(save_path, sep="\t")
        else:
            raise ValueError(f"不支持的扩展名: {ext}")
    except Exception as e:
        save_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"无法解析文件: {e}")

    # 注册到会话
    dataset_name = file.filename
    session.datasets[dataset_name] = df

    dataset_info = DatasetInfo(
        id=dataset_id,
        session_id=session_id,
        name=dataset_name,
        file_path=str(save_path),
        file_type=ext,
        file_size=len(content),
        row_count=len(df),
        column_count=len(df.columns),
    )

    return UploadResponse(success=True, dataset=dataset_info)


# ---- 文件下载 ----


@router.get("/artifacts/{session_id}/{filename}")
async def download_artifact(session_id: str, filename: str):
    """下载会话产物。"""
    from fastapi.responses import FileResponse

    artifact_path = settings.sessions_dir / session_id / "artifacts" / filename
    if not artifact_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(str(artifact_path), filename=filename)


# ---- 模型配置 ----

# 所有支持的模型提供商定义
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
        "models": ["glm-4", "glm-4-plus", "glm-4-flash"],
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
        "id": "ollama",
        "name": "Ollama（本地）",
        "models": ["qwen2.5:7b", "llama3:8b", "mistral:7b"],
        "key_field": None,  # Ollama 不需要 API Key
        "model_field": "ollama_model",
    },
]


@router.get("/models/{provider_id}/available", response_model=APIResponse)
async def list_available_models_endpoint(provider_id: str):
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


@router.get("/models", response_model=APIResponse)
async def list_models():
    """获取所有模型提供商及其配置状态（合并 DB 与 .env 配置）。"""
    from nini.config_manager import load_all_model_configs
    from nini.utils.crypto import mask_api_key

    # 从 DB 加载用户保存的配置
    try:
        db_configs = await load_all_model_configs()
    except Exception:
        db_configs = {}

    result = []
    for idx, provider in enumerate(_MODEL_PROVIDERS):
        pid = provider["id"]
        key_field = provider["key_field"]
        model_field = provider["model_field"]
        db_cfg = db_configs.get(pid, {})

        # 有效 API Key：DB 优先，.env 兜底
        env_key = getattr(settings, key_field, None) if key_field else None
        effective_key = db_cfg.get("api_key") or env_key or ""

        # 有效模型名：DB 优先，.env 兜底
        env_model = getattr(settings, model_field, "") if model_field else ""
        effective_model = db_cfg.get("model") or env_model

        # 有效 base_url
        effective_base_url = db_cfg.get("base_url") or ""

        # 判断是否已配置
        if pid == "ollama":
            env_base = settings.ollama_base_url
            configured = bool((effective_base_url or env_base) and effective_model)
        else:
            configured = bool(effective_key)

        # 配置来源标记
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
                "api_key_hint": db_cfg.get("api_key_hint")
                or mask_api_key(env_key or ""),
                "base_url": effective_base_url,
                "priority": idx,
                "config_source": config_source,
            }
        )

    return APIResponse(data=result)


@router.post("/models/config", response_model=APIResponse)
async def save_model_config_endpoint(req: ModelConfigRequest):
    """保存模型配置到数据库，并立即重载模型客户端。"""
    from nini.config_manager import save_model_config
    from nini.agent.model_resolver import reload_model_resolver

    try:
        result = await save_model_config(
            provider=req.provider_id,
            api_key=req.api_key,
            model=req.model,
            base_url=req.base_url,
            is_active=req.is_active,
        )
        # 立即重载模型客户端，使配置生效
        await reload_model_resolver()
        return APIResponse(data=result)
    except ValueError as e:
        return APIResponse(success=False, error=str(e))
    except Exception as e:
        return APIResponse(success=False, error=f"保存配置失败: {e}")


@router.post("/models/{provider_id}/test", response_model=APIResponse)
async def test_model_connection(provider_id: str):
    """测试指定模型提供商的连接（使用有效配置：DB 优先）。"""
    from nini.agent.model_resolver import (
        OpenAIClient,
        AnthropicClient,
        OllamaClient,
        MoonshotClient,
        KimiCodingClient,
        ZhipuClient,
        DeepSeekClient,
        DashScopeClient,
    )
    from nini.config_manager import get_effective_config

    client_map: dict[str, Any] = {
        "openai": OpenAIClient,
        "anthropic": AnthropicClient,
        "moonshot": MoonshotClient,
        "kimi_coding": KimiCodingClient,
        "zhipu": ZhipuClient,
        "deepseek": DeepSeekClient,
        "dashscope": DashScopeClient,
        "ollama": OllamaClient,
    }

    if provider_id not in client_map:
        raise HTTPException(status_code=404, detail=f"未知的模型提供商: {provider_id}")

    # 获取有效配置（DB 优先，.env 兜底）
    cfg = await get_effective_config(provider_id)
    client_cls = client_map[provider_id]

    # 使用有效配置创建客户端实例
    if provider_id == "ollama":
        client = client_cls(base_url=cfg.get("base_url"), model=cfg.get("model"))
    elif provider_id == "anthropic":
        client = client_cls(api_key=cfg.get("api_key"), model=cfg.get("model"))
    else:
        client = client_cls(api_key=cfg.get("api_key"), model=cfg.get("model"))

    if not client.is_available():
        return APIResponse(
            success=False,
            error=f"{provider_id or '该提供商'} 未配置或不可用，请先设置对应的 API Key",
        )

    try:
        # 发送简单测试消息
        chunks = []
        async for chunk in client.chat(
            [{"role": "user", "content": "你好，请回复'连接成功'"}],
            temperature=0.1,
            max_tokens=20,
        ):
            chunks.append(chunk)
        text = "".join(c.text for c in chunks)
        return APIResponse(data={"message": f"连接成功: {text[:50]}"})
    except Exception as e:
        return APIResponse(success=False, error=f"连接失败: {e}")


# ---- 活跃模型管理 ----


@router.get("/models/active", response_model=APIResponse)
async def get_active_model():
    """获取当前活跃的模型信息（提供商 + 模型名称）。"""
    from nini.agent.model_resolver import model_resolver

    info: dict[str, Any] = model_resolver.get_active_model_info()
    info["preferred_provider"] = model_resolver.get_preferred_provider()
    return APIResponse(data=info)


@router.post("/models/preferred", response_model=APIResponse)
async def set_preferred_model(req: SetActiveModelRequest):
    """统一设置全局首选模型提供商（同时更新内存和持久化）。

    点选即为全局首选，刷新页面/重启后仍生效。
    传入空字符串恢复自动选择（按优先级）。
    """
    from nini.agent.model_resolver import model_resolver
    from nini.config_manager import set_default_provider

    provider_id = req.provider_id.strip() or None

    # 验证 provider_id 是否有效
    valid_ids = {c.provider_id for c in model_resolver._clients}
    if provider_id and provider_id not in valid_ids:
        return APIResponse(success=False, error=f"未知的模型提供商: {provider_id}")

    # 1. 设置内存级首选
    model_resolver.set_preferred_provider(provider_id)

    # 2. 持久化到数据库
    await set_default_provider(provider_id)

    # 返回更新后的活跃模型信息
    info: dict[str, Any] = model_resolver.get_active_model_info()
    info["preferred_provider"] = model_resolver.get_preferred_provider()
    return APIResponse(data=info)


@router.get("/models/default", response_model=APIResponse)
async def get_default_model():
    """获取用户设置的默认模型提供商。"""
    from nini.config_manager import get_default_provider

    provider_id = await get_default_provider()
    return APIResponse(data={"default_provider": provider_id})


# ---- 工作流模板管理 ----


@router.get("/workflows", response_model=APIResponse)
async def list_workflows():
    """获取所有工作流模板。"""
    from nini.workflow.store import list_templates

    templates = await list_templates()
    return APIResponse(data=templates)


@router.post("/workflows/{template_id}/run", response_model=APIResponse)
async def run_workflow(template_id: str, session_id: str | None = None):
    """通过 HTTP 触发工作流执行（非 WebSocket 场景的简易版本）。

    实际的流式执行推荐通过 WebSocket 触发，此接口用于验证和启动。
    """
    from nini.workflow.store import get_template

    template = await get_template(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="工作流模板不存在")

    if session_id:
        session = session_manager.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        if not session.datasets:
            return APIResponse(
                success=False, error="当前会话无已加载的数据集，请先上传数据"
            )

    return APIResponse(
        data={
            "template": template.to_dict(),
            "message": f"工作流「{template.name}」已准备好执行（{len(template.steps)} 步）",
        }
    )


@router.delete("/workflows/{template_id}", response_model=APIResponse)
async def delete_workflow(template_id: str):
    """删除工作流模板。"""
    from nini.workflow.store import delete_template

    deleted = await delete_template(template_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="工作流模板不存在")
    return APIResponse(data={"deleted": template_id})


# ---- 健康检查 ----


@router.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
