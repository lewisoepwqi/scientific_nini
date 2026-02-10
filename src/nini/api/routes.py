"""HTTP 端点（文件上传/下载、会话管理）。"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response

from nini.agent.session import session_manager
from nini.config import settings
from nini.models.schemas import (
    APIResponse,
    DatasetInfo,
    FileRenameRequest,
    ModelConfigRequest,
    SaveWorkspaceTextRequest,
    SessionInfo,
    SessionUpdateRequest,
    SetActiveModelRequest,
    UploadResponse,
)
from nini.workspace import WorkspaceManager

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


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
        if not messages and not session_manager.session_exists(session_id):
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
    from nini.utils.token_counter import remove_tracker

    session_manager.remove_session(session_id, delete_persistent=True)
    remove_tracker(session_id)
    return APIResponse(data={"deleted": session_id})


@router.post("/sessions/{session_id}/compress", response_model=APIResponse)
async def compress_session(session_id: str, mode: str = "auto"):
    """压缩会话历史并归档。

    Args:
        mode: 压缩模式。"lightweight" 使用轻量摘要，"llm" 使用 LLM 摘要，
              "auto" 自动选择（优先 LLM，失败回退轻量）。
    """
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")

    session = session_manager.get_or_create(session_id)

    if mode in ("llm", "auto"):
        from nini.memory.compression import compress_session_history_with_llm

        result = await compress_session_history_with_llm(session)
    else:
        from nini.memory.compression import compress_session_history

        result = compress_session_history(session)

    if not result.get("success"):
        return APIResponse(success=False, error=str(result.get("message", "压缩失败")))

    session_manager.save_session_compression(
        session.id,
        compressed_context=str(session.compressed_context),
        compressed_rounds=int(session.compressed_rounds),
        last_compressed_at=session.last_compressed_at,
    )
    return APIResponse(data=result)


@router.get("/skills", response_model=APIResponse)
async def list_skills(skill_type: str | None = None):
    """获取技能目录（Function + Markdown）。"""
    from nini.api.websocket import get_skill_registry

    registry = get_skill_registry()
    if registry is None:
        return APIResponse(data={"skills": []})

    # 每次请求都刷新 Markdown 技能快照，确保前端看到最新状态
    registry.reload_markdown_skills()
    registry.write_skills_snapshot()

    skills = registry.list_skill_catalog(skill_type)
    return APIResponse(data={"skills": skills})


# ---- 文件上传 ----


@router.post("/upload", response_model=UploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    session_id: str = Form(...),
):
    """上传数据文件到指定会话。"""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    session = session_manager.get_or_create(session_id)

    # 验证文件类型
    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少文件名")

    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in settings.allowed_extensions_list:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: .{ext}，支持: {settings.allowed_extensions}",
        )

    manager = WorkspaceManager(session_id)
    manager.ensure_dirs()
    safe_filename = manager.sanitize_filename(file.filename, default_name="dataset.csv")
    dataset_name = manager.unique_dataset_name(safe_filename)

    # 保存文件（会话工作空间）
    dataset_id = uuid.uuid4().hex[:12]
    save_path = manager.uploads_dir / f"{dataset_id}_{dataset_name}"

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

    # 注册到会话（内存）
    session.datasets[dataset_name] = df
    session.workspace_hydrated = True

    # 写入工作空间索引
    manager.add_dataset_record(
        dataset_id=dataset_id,
        name=dataset_name,
        file_path=save_path,
        file_type=ext,
        file_size=len(content),
        row_count=len(df),
        column_count=len(df.columns),
    )

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

    workspace_file = {
        "id": dataset_id,
        "name": dataset_name,
        "kind": "dataset",
        "size": len(content),
        "download_url": f"/api/workspace/{session_id}/uploads/{quote(save_path.name)}",
        "meta": {
            "row_count": len(df),
            "column_count": len(df.columns),
            "file_type": ext,
        },
    }
    return UploadResponse(success=True, dataset=dataset_info, workspace_file=workspace_file)


@router.get("/sessions/{session_id}/datasets", response_model=APIResponse)
async def list_session_datasets(session_id: str):
    """获取会话工作空间中的数据集列表。"""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")

    manager = WorkspaceManager(session_id)
    session = session_manager.get_session(session_id)
    loaded_names = set(session.datasets.keys()) if session is not None else set()
    datasets: list[dict[str, Any]] = []
    for item in manager.list_datasets():
        datasets.append(
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "file_type": item.get("file_type"),
                "file_size": item.get("file_size"),
                "row_count": item.get("row_count"),
                "column_count": item.get("column_count"),
                "created_at": item.get("created_at"),
                "loaded": item.get("name") in loaded_names,
            }
        )
    return APIResponse(data={"session_id": session_id, "datasets": datasets})


@router.post("/sessions/{session_id}/datasets/{dataset_id}/load", response_model=APIResponse)
async def load_session_dataset(session_id: str, dataset_id: str):
    """将工作空间数据集加载到会话内存。"""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")

    session = session_manager.get_or_create(session_id)
    manager = WorkspaceManager(session_id)

    record = manager.get_dataset_by_id(dataset_id)
    if record is None:
        raise HTTPException(status_code=404, detail="数据集不存在")

    try:
        _, df = manager.load_dataset_by_id(dataset_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    name = str(record.get("name", ""))
    if not name:
        raise HTTPException(status_code=400, detail="数据集记录损坏：缺少名称")

    session.datasets[name] = df
    session.workspace_hydrated = True
    return APIResponse(
        data={
            "session_id": session_id,
            "dataset": {
                "id": record.get("id"),
                "name": name,
                "row_count": len(df),
                "column_count": len(df.columns),
                "loaded": True,
            },
        }
    )


@router.get("/sessions/{session_id}/workspace/files", response_model=APIResponse)
async def list_workspace_files(session_id: str, q: str | None = None):
    """列出会话工作空间文件（数据集/产物/文本），支持 ?q= 搜索。"""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    manager = WorkspaceManager(session_id)
    if q and q.strip():
        files = manager.search_files(q)
    else:
        files = manager.list_workspace_files()
    return APIResponse(data={"session_id": session_id, "files": files})


@router.post("/sessions/{session_id}/workspace/save_text", response_model=APIResponse)
async def save_workspace_text(session_id: str, req: SaveWorkspaceTextRequest):
    """保存文本到会话工作空间。"""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    content = req.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="content 不能为空")

    manager = WorkspaceManager(session_id)
    note = manager.save_text_note(content, req.filename)
    return APIResponse(data={"session_id": session_id, "file": note})


@router.delete("/sessions/{session_id}/workspace/files/{file_id}", response_model=APIResponse)
async def delete_workspace_file(session_id: str, file_id: str):
    """删除工作空间中的文件。"""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    manager = WorkspaceManager(session_id)
    deleted = manager.delete_file(file_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="文件不存在")

    # 如果删除的是数据集，同步移除内存中的 DataFrame
    session = session_manager.get_session(session_id)
    if session is not None:
        name = deleted.get("name", "")
        if name and name in session.datasets:
            del session.datasets[name]

    return APIResponse(data={"session_id": session_id, "deleted": file_id})


@router.patch("/sessions/{session_id}/workspace/files/{file_id}", response_model=APIResponse)
async def rename_workspace_file(session_id: str, file_id: str, req: FileRenameRequest):
    """重命名工作空间中的文件。"""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    new_name = req.name.strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="文件名不能为空")
    manager = WorkspaceManager(session_id)

    # 如果重命名的是数据集，同步更新内存中的 key
    kind, old_record = manager._find_record_by_id(file_id)
    old_name = old_record.get("name", "") if old_record else ""

    updated = manager.rename_file(file_id, new_name)
    if updated is None:
        raise HTTPException(status_code=404, detail="文件不存在")

    # 更新内存中的数据集引用
    if kind == "dataset" and old_name:
        session = session_manager.get_session(session_id)
        if session is not None and old_name in session.datasets:
            df = session.datasets.pop(old_name)
            session.datasets[updated.get("name", new_name)] = df

    return APIResponse(data={"session_id": session_id, "file": updated})


@router.get("/sessions/{session_id}/workspace/files/{file_id}/preview", response_model=APIResponse)
async def preview_workspace_file(session_id: str, file_id: str):
    """获取工作空间文件的预览内容。"""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    manager = WorkspaceManager(session_id)
    preview = manager.get_file_preview(file_id)
    if preview is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    return APIResponse(data=preview)


@router.get("/sessions/{session_id}/workspace/executions", response_model=APIResponse)
async def list_code_executions(session_id: str):
    """获取会话的代码执行历史。"""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    manager = WorkspaceManager(session_id)
    executions = manager.list_code_executions()
    return APIResponse(data={"session_id": session_id, "executions": executions})


@router.post("/sessions/{session_id}/workspace/folders", response_model=APIResponse)
async def create_folder(session_id: str, req: dict[str, Any]):
    """创建自定义文件夹。"""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    name = req.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="文件夹名称不能为空")
    parent = req.get("parent")
    manager = WorkspaceManager(session_id)
    folder = manager.create_folder(name, parent)
    return APIResponse(data={"session_id": session_id, "folder": folder})


@router.get("/sessions/{session_id}/workspace/folders", response_model=APIResponse)
async def list_folders(session_id: str):
    """列出自定义文件夹。"""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    manager = WorkspaceManager(session_id)
    folders = manager.list_folders()
    return APIResponse(data={"session_id": session_id, "folders": folders})


@router.post("/sessions/{session_id}/workspace/files/{file_id}/move", response_model=APIResponse)
async def move_file(session_id: str, file_id: str, req: dict[str, Any]):
    """将文件移动到指定文件夹。"""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    folder_id = req.get("folder_id")
    manager = WorkspaceManager(session_id)
    updated = manager.move_file(file_id, folder_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    return APIResponse(data={"session_id": session_id, "file": updated})


@router.post("/sessions/{session_id}/workspace/files", response_model=APIResponse)
async def create_workspace_file(session_id: str, req: dict[str, Any]):
    """创建新文件（文本/Markdown）。"""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    content = req.get("content", "")
    filename = req.get("filename", "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")
    manager = WorkspaceManager(session_id)
    note = manager.save_text_note(content, filename)
    return APIResponse(data={"session_id": session_id, "file": note})


@router.post("/sessions/{session_id}/workspace/batch-download")
async def batch_download(session_id: str, req: dict[str, Any]):
    """批量下载工作空间文件（ZIP 打包）。"""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    file_ids = req.get("file_ids", [])
    if not isinstance(file_ids, list) or not file_ids:
        raise HTTPException(status_code=400, detail="file_ids 不能为空")
    manager = WorkspaceManager(session_id)
    zip_bytes = manager.batch_download(file_ids)
    if not zip_bytes:
        raise HTTPException(status_code=404, detail="没有可下载的文件")
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="workspace_{session_id[:8]}.zip"'},
    )


# ---- 文件下载 ----


@router.get("/artifacts/{session_id}/{filename}")
async def download_artifact(session_id: str, filename: str):
    """下载会话产物。"""
    safe_name = Path(filename).name
    artifact_path = settings.sessions_dir / session_id / "workspace" / "artifacts" / safe_name
    if not artifact_path.exists():
        # 兼容旧目录
        artifact_path = settings.sessions_dir / session_id / "artifacts" / safe_name
    if not artifact_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(str(artifact_path), filename=safe_name)


@router.get("/workspace/{session_id}/uploads/{filename}")
async def download_workspace_upload(session_id: str, filename: str):
    """下载会话工作空间中的上传文件。"""
    safe_name = Path(filename).name
    path = settings.sessions_dir / session_id / "workspace" / "uploads" / safe_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(str(path), filename=safe_name)


@router.get("/workspace/{session_id}/notes/{filename}")
async def download_workspace_note(session_id: str, filename: str):
    """下载会话工作空间中的文本文件。"""
    safe_name = Path(filename).name
    path = settings.sessions_dir / session_id / "workspace" / "notes" / safe_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(str(path), filename=safe_name)


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
        error_text = str(e)
        if "socksio" in error_text.lower():
            error_text = (
                "检测到 SOCKS 代理配置，但环境未安装 socksio 依赖。"
                "请执行 `pip install httpx[socks]`，"
                "或移除 ALL_PROXY/HTTPS_PROXY 后重试。"
            )
        return APIResponse(success=False, error=f"连接失败: {error_text}")
    finally:
        # 显式关闭底层 HTTP 客户端，避免 GC 阶段
        # AsyncHttpxClientWrapper.__del__ 触发 _mounts 属性缺失错误
        try:
            await client.aclose()
        except Exception as close_error:
            logger.warning("关闭模型测试客户端失败（%s）: %s", provider_id, close_error)


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
        if not session_manager.session_exists(session_id):
            raise HTTPException(status_code=404, detail="会话不存在")
        session = session_manager.get_or_create(session_id)
        if not session.workspace_hydrated:
            WorkspaceManager(session_id).hydrate_session_datasets(session)
            session.workspace_hydrated = True
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


# ---- Token 统计 ----


@router.get("/sessions/{session_id}/token-usage", response_model=APIResponse)
async def get_session_token_usage(session_id: str):
    """获取会话的 token 消耗统计。"""
    from nini.utils.token_counter import get_tracker

    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    tracker = get_tracker(session_id)
    return APIResponse(data=tracker.to_dict())


@router.get("/sessions/{session_id}/context-size", response_model=APIResponse)
async def get_session_context_size(session_id: str):
    """获取当前会话上下文的 token 预估。"""
    from nini.utils.token_counter import count_messages_tokens

    session = session_manager.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在或未加载")

    message_tokens = count_messages_tokens(session.messages)
    compressed_tokens = 0
    if getattr(session, "compressed_context", ""):
        from nini.utils.token_counter import count_tokens

        compressed_tokens = count_tokens(str(session.compressed_context))

    return APIResponse(
        data={
            "session_id": session_id,
            "message_count": len(session.messages),
            "message_tokens": message_tokens,
            "compressed_context_tokens": compressed_tokens,
            "total_context_tokens": message_tokens + compressed_tokens,
        }
    )


# ---- 健康检查 ----


@router.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
