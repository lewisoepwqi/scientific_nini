"""HTTP 端点（文件上传/下载、会话管理）。"""

from __future__ import annotations

import asyncio
import io
import logging
import mimetypes
import re
import shutil
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from nini.agent.session import session_manager
from nini.config import settings
from nini.intent import default_intent_analyzer
from nini.models.schemas import (
    APIResponse,
    DatasetInfo,
    FileRenameRequest,
    MarkdownSkillDirCreateRequest,
    MarkdownSkillEnabledRequest,
    MarkdownSkillFileWriteRequest,
    MarkdownSkillPathDeleteRequest,
    MarkdownSkillUpdateRequest,
    ModelConfigRequest,
    ModelPrioritiesRequest,
    ModelRoutingRequest,
    ReportExportRequest,
    ReportGenerateRequest,
    ResearchProfileData,
    ResearchProfileUpdateRequest,
    SaveWorkspaceTextRequest,
    SessionInfo,
    SessionUpdateRequest,
    SetActiveModelRequest,
    UploadResponse,
)
from nini.tools.markdown_skill_admin import (
    MarkdownSkillDocument,
    guess_skill_name_from_filename,
    normalize_category,
    parse_skill_document,
    render_skill_document,
    validate_skill_name,
)
from nini.utils.chart_payload import normalize_chart_payload
from nini.utils.dataframe_io import read_dataframe
from nini.workspace import WorkspaceManager

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


# Excel 序列日期关键词（用于启发式检测）
_DATE_HINTS = {"日期", "时间", "时刻", "date", "time", "datetime", "timestamp"}
_SKILL_UPLOAD_EXTENSIONS = {".md", ".markdown", ".txt"}


def _get_skill_registry():
    from nini.api.websocket import get_skill_registry

    registry = get_skill_registry()
    if registry is None:
        raise HTTPException(status_code=503, detail="技能注册中心尚未初始化")
    return registry


def _refresh_skill_registry(registry: Any) -> None:
    registry.reload_markdown_skills()
    registry.write_skills_snapshot()


def _resolve_skill_path_inside_root(path_str: str) -> Path:
    path = Path(path_str).resolve()
    allowed_roots = settings.skills_search_dirs
    if not any(path.is_relative_to(root) for root in allowed_roots):
        raise HTTPException(status_code=400, detail="非法技能路径（不在允许的 skills 目录中）")
    return path


def _get_markdown_skill_item_or_404(registry: Any, skill_name: str) -> dict[str, Any]:
    item = registry.get_markdown_skill(skill_name)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Markdown 技能 '{skill_name}' 不存在")
    if not isinstance(item, dict):
        raise HTTPException(status_code=500, detail="Markdown 技能索引格式错误")
    return item


def _get_markdown_skill_dir_or_404(registry: Any, skill_name: str) -> Path:
    """获取 Markdown Skill 所在目录。"""
    item = _get_markdown_skill_item_or_404(registry, skill_name)
    skill_path = _resolve_skill_path_inside_root(str(item.get("location", "")))
    if not skill_path.exists():
        raise HTTPException(status_code=404, detail=f"技能文件不存在: {skill_path}")
    return skill_path.parent


def _resolve_skill_relative_path(skill_dir: Path, relative_path: str) -> Path:
    """将技能相对路径解析为安全绝对路径。"""
    raw = relative_path.strip().replace("\\", "/")
    if not raw:
        raise HTTPException(status_code=400, detail="path 不能为空")

    rel = Path(raw)
    if rel.is_absolute():
        raise HTTPException(status_code=400, detail="path 不能为绝对路径")
    if any(part in (".", "..", "") for part in rel.parts):
        raise HTTPException(status_code=400, detail="path 非法")

    target = (skill_dir / rel).resolve()
    if not target.is_relative_to(skill_dir):
        raise HTTPException(status_code=400, detail="path 超出技能目录")
    return target


def _build_skill_file_entries(skill_dir: Path) -> list[dict[str, Any]]:
    """构建技能目录的文件树（扁平列表）。"""
    entries: list[dict[str, Any]] = []
    for path in sorted(skill_dir.rglob("*")):
        if path.name.startswith(".") and path.name != ".gitkeep":
            continue
        rel = path.relative_to(skill_dir).as_posix()
        stat = path.stat()
        entries.append(
            {
                "path": rel,
                "name": path.name,
                "type": "dir" if path.is_dir() else "file",
                "size": stat.st_size if path.is_file() else 0,
                "updated_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            }
        )
    return entries


def _fix_excel_serial_dates(df: pd.DataFrame) -> pd.DataFrame:
    """检测并修复 Excel 序列日期：object 列中混入的浮点型日期值。

    Excel 序列日期以 1899-12-30 为 day 0，合理范围 ~25000-55000 对应 ~1968-2050。
    pd.to_datetime() 对 float 按纳秒解释会得到 1970 年附近的错误值。
    此函数将此类值转为正确的 datetime。
    """
    excel_epoch = pd.Timestamp("1899-12-30")

    for col in df.columns:
        # 仅处理列名含日期/时间关键词的 object 列
        col_lower = str(col).lower()
        if not any(hint in col_lower for hint in _DATE_HINTS):
            continue
        if df[col].dtype != "object":
            continue

        def _convert_value(val: Any) -> Any:
            """单值转换：Excel 序列日期 float/int → datetime。"""
            if isinstance(val, (int, float)):
                try:
                    serial = float(val)
                    if 25000 <= serial <= 55000:
                        return excel_epoch + pd.to_timedelta(serial, unit="D")
                except (ValueError, OverflowError):
                    pass
            return val

        converted = df[col].map(_convert_value)
        # 尽量将整列统一为 datetime，避免 datetime 与 str 混排导致后续排序报错
        parsed = pd.to_datetime(converted, errors="coerce")
        non_null_count = int(converted.notna().sum())
        parsed_count = int(parsed.notna().sum())
        if non_null_count > 0 and (parsed_count / non_null_count) >= 0.8:
            df[col] = parsed
        else:
            df[col] = converted

    return df


def _build_download_response(path: Path, filename: str, *, inline: bool = False) -> Response:
    """构造文件响应（支持 attachment/inline，避免 FileResponse 在线程池路径上的阻塞）。"""
    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    disposition_type = "inline" if inline else "attachment"
    # RFC 5987 / RFC 6266: 非 ASCII 文件名用 filename* 编码，ASCII 用 filename 降级
    try:
        filename.encode("latin-1")
        disposition = f'{disposition_type}; filename="{filename}"'
    except UnicodeEncodeError:
        ascii_fallback = filename.encode("ascii", errors="replace").decode("ascii")
        utf8_encoded = quote(filename, safe="")
        disposition = (
            f"{disposition_type}; "
            f'filename="{ascii_fallback}"; filename*=UTF-8''{utf8_encoded}'
        )
    return Response(
        content=path.read_bytes(),
        media_type=media_type,
        headers={"Content-Disposition": disposition},
    )


@router.post("/upload", response_model=UploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    session_id: str = Form(...),
) -> UploadResponse:
    """上传数据文件到指定会话。"""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    session = session_manager.get_or_create(session_id)

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

    dataset_id = uuid.uuid4().hex[:12]
    save_path = manager.uploads_dir / f"{dataset_id}_{dataset_name}"

    content = await file.read()
    if len(content) > settings.max_upload_size:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大（{len(content)} 字节），最大 {settings.max_upload_size} 字节",
        )

    save_path.write_bytes(content)

    try:
        df = read_dataframe(save_path, ext)
    except Exception as e:
        save_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"无法解析文件: {e}")

    if ext in ("xlsx", "xls"):
        df = _fix_excel_serial_dates(df)

    session.datasets[dataset_name] = df
    session.workspace_hydrated = True

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


@router.get("/datasets/{session_id}", response_model=APIResponse)
async def list_datasets(session_id: str):
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
    return APIResponse(success=True, data={"session_id": session_id, "datasets": datasets})


@router.post("/datasets/{session_id}/{dataset_id}/load", response_model=APIResponse)
async def load_dataset_into_session(session_id: str, dataset_id: str):
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

    name = str(record.get("name", "")).strip()
    if not name:
        raise HTTPException(status_code=400, detail="数据集记录损坏：缺少名称")

    session.datasets[name] = df
    session.workspace_hydrated = True
    return APIResponse(
        success=True,
        data={
            "session_id": session_id,
            "dataset": {
                "id": record.get("id"),
                "name": name,
                "row_count": len(df),
                "column_count": len(df.columns),
                "loaded": True,
            },
        },
    )


@router.get("/datasets/{session_id}/{dataset_name}")
async def get_dataset(session_id: str, dataset_name: str, limit: int = 100):
    """获取数据集内容（默认前100行）。"""
    session = session_manager.get_or_create(session_id)

    if dataset_name not in session.datasets:
        raise HTTPException(status_code=404, detail=f"数据集 '{dataset_name}' 不存在")

    df = session.datasets[dataset_name]
    preview_df = df.head(limit)

    return APIResponse(
        success=True,
        data={
            "name": dataset_name,
            "total_rows": len(df),
            "total_columns": len(df.columns),
            "preview": preview_df.to_dict(orient="records"),
            "columns": df.columns.tolist(),
        },
    )


@router.get("/datasets/{session_id}/{dataset_name}/preview")
async def get_dataset_preview(session_id: str, dataset_name: str):
    """获取数据集预览（统计信息）。"""
    session = session_manager.get_or_create(session_id)

    if dataset_name not in session.datasets:
        raise HTTPException(status_code=404, detail=f"数据集 '{dataset_name}' 不存在")

    df = session.datasets[dataset_name]

    # 基础统计
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
    categorical_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()

    stats = {
        "total_rows": len(df),
        "total_columns": len(df.columns),
        "numeric_columns": numeric_cols,
        "categorical_columns": categorical_cols,
        "missing_values": df.isnull().sum().to_dict(),
        "memory_usage": df.memory_usage(deep=True).sum(),
    }

    return APIResponse(success=True, data=stats)


@router.delete("/datasets/{session_id}/{dataset_name}")
async def delete_dataset(session_id: str, dataset_name: str):
    """删除数据集。"""
    session = session_manager.get_or_create(session_id)

    if dataset_name not in session.datasets:
        raise HTTPException(status_code=404, detail=f"数据集 '{dataset_name}' 不存在")

    del session.datasets[dataset_name]

    return APIResponse(success=True, message=f"数据集 '{dataset_name}' 已删除")


@router.get("/datasets/{session_id}/{dataset_name}/export")
async def export_dataset(
    session_id: str,
    dataset_name: str,
    format: str = "csv",  # noqa: A002
) -> Response:
    """导出数据集为 CSV 或 Excel。"""
    session = session_manager.get_or_create(session_id)

    if dataset_name not in session.datasets:
        raise HTTPException(status_code=404, detail=f"数据集 '{dataset_name}' 不存在")

    df = session.datasets[dataset_name]

    if format == "csv":
        content = df.to_csv(index=False).encode("utf-8")
        media_type = "text/csv"
        filename = f"{dataset_name}.csv"
    elif format == "excel":
        buffer = io.BytesIO()
        df.to_excel(buffer, index=False, engine="openpyxl")
        content = buffer.getvalue()
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = f"{dataset_name}.xlsx"
    elif format == "json":
        content = df.to_json(orient="records", force_ascii=False).encode("utf-8")
        media_type = "application/json"
        filename = f"{dataset_name}.json"
    else:
        raise HTTPException(status_code=400, detail=f"不支持的导出格式: {format}")

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---- 会话管理 ----


@router.get("/sessions", response_model=APIResponse)
async def list_sessions() -> APIResponse:
    """获取所有会话列表。"""
    sessions = session_manager.list_sessions()
    return APIResponse(
        success=True,
        data=[
            {
                "id": s["id"],
                "title": s["title"],
                "message_count": s["message_count"],
            }
            for s in sessions
        ],
    )


@router.get("/sessions/{session_id}", response_model=APIResponse)
async def get_session(session_id: str) -> APIResponse:
    """获取单个会话信息。"""
    session = session_manager.get_or_create(session_id, load_persisted_messages=True)

    return APIResponse(
        success=True,
        data={
            "id": session.id,
            "title": session.title,
            "message_count": len(session.messages),
        },
    )


@router.post("/sessions", response_model=APIResponse)
async def create_session() -> APIResponse:
    """创建新会话。"""
    session = session_manager.create_session(load_persisted_messages=False)
    return APIResponse(
        success=True,
        data={
            "session_id": session.id,
            "title": session.title,
            "message_count": 0,
        },
    )


@router.patch("/sessions/{session_id}", response_model=APIResponse)
async def update_session(
    session_id: str,
    request: SessionUpdateRequest,
) -> APIResponse:
    """更新会话信息（如标题）。"""
    if request.title:
        session_manager.save_session_title(session_id, request.title)
        if session_manager.get_session(session_id):
            session_manager.update_session_title(session_id, request.title)

    return APIResponse(success=True)


@router.post("/sessions/{session_id}/compress", response_model=APIResponse)
async def compress_session(session_id: str, mode: str = "auto"):
    """压缩会话历史。

    Args:
        session_id: 会话ID
        mode: 压缩模式 (auto / lightweight / llm)

    Returns:
        压缩结果
    """
    session = session_manager.get_or_create(session_id)

    if mode == "llm":
        from nini.memory.compression import compress_session_history_with_llm

        result = await compress_session_history_with_llm(session)
    else:
        from nini.memory.compression import compress_session_history

        result = compress_session_history(session, ratio=0.5 if mode == "lightweight" else 0.3)

    # 保存压缩元数据
    session_manager.save_session_compression(
        session_id,
        compressed_context=session.compressed_context,
        compressed_rounds=session.compressed_rounds,
        last_compressed_at=session.last_compressed_at,
    )

    return APIResponse(success=True, data=result)


@router.delete("/sessions/{session_id}", response_model=APIResponse)
async def delete_session(session_id: str) -> APIResponse:
    """删除会话。"""
    session_manager.remove_session(session_id, delete_persistent=True)
    return APIResponse(success=True)


@router.post("/sessions/{session_id}/rollback", response_model=APIResponse)
async def rollback_session(session_id: str) -> APIResponse:
    """回滚会话到上一用户消息（删除该消息后的所有模型输出）。"""
    session = session_manager.get_or_create(session_id, load_persisted_messages=True)
    user_content = session.rollback_last_turn()
    if user_content is None:
        return APIResponse(success=False, error="没有可回滚的用户消息")
    return APIResponse(success=True, data={"user_content": user_content})


# ---- 工作空间 ----


def _ensure_workspace_session_exists(session_id: str) -> None:
    """校验会话存在，避免新版工作空间接口访问悬空路径。"""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")


@router.get("/workspace/{session_id}/tree")
async def get_workspace_tree(session_id: str):
    """获取工作空间文件树。"""
    _ensure_workspace_session_exists(session_id)
    workspace = WorkspaceManager(session_id)
    tree = workspace.get_tree()
    return APIResponse(success=True, data=tree)


@router.get("/workspace/{session_id}/files")
async def list_workspace_files(session_id: str, q: str | None = None):
    """列出工作空间文件，支持 ?q= 搜索。"""
    _ensure_workspace_session_exists(session_id)
    workspace = WorkspaceManager(session_id)
    if q and q.strip():
        files = workspace.search_files_with_paths(q)
    else:
        files = workspace.list_workspace_files_with_paths()
    return APIResponse(success=True, data={"session_id": session_id, "files": files})


@router.get("/workspace/{session_id}/files/{file_path:path}/preview")
async def preview_workspace_file(session_id: str, file_path: str):
    """按路径获取工作空间文件预览。"""
    _ensure_workspace_session_exists(session_id)
    workspace = WorkspaceManager(session_id)
    try:
        preview = workspace.get_file_preview_by_path(file_path)
        return APIResponse(success=True, data=preview)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"文件不存在: {file_path}")
    except IsADirectoryError:
        raise HTTPException(status_code=400, detail="path 是目录，不支持预览")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/workspace/{session_id}/files/{file_path:path}")
async def get_workspace_file(session_id: str, file_path: str):
    """获取工作空间文件内容。"""
    _ensure_workspace_session_exists(session_id)
    workspace = WorkspaceManager(session_id)

    try:
        content = workspace.read_file(file_path)
        return APIResponse(success=True, data={"path": file_path, "content": content})
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"文件不存在: {file_path}")
    except IsADirectoryError:
        raise HTTPException(status_code=400, detail="path 是目录，不是文件")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/workspace/{session_id}/files/{file_path:path}/move")
async def move_workspace_file(
    session_id: str,
    file_path: str,
    req: dict[str, Any],
):
    """按路径将文件移动到指定文件夹。"""
    _ensure_workspace_session_exists(session_id)
    workspace = WorkspaceManager(session_id)
    folder_id = req.get("folder_id")

    try:
        result = workspace.move_path_to_folder(file_path, folder_id)
        return APIResponse(success=True, data={"path": file_path, "file": result.get("record")})
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"文件不存在: {file_path}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/workspace/{session_id}/files/{file_path:path}/rename")
async def rename_workspace_file(
    session_id: str,
    file_path: str,
    request: FileRenameRequest,
):
    """重命名工作空间文件。"""
    _ensure_workspace_session_exists(session_id)
    workspace = WorkspaceManager(session_id)

    try:
        result = workspace.rename_path(file_path, request.name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"文件不存在: {file_path}")
    except IsADirectoryError:
        raise HTTPException(status_code=400, detail="暂不支持目录重命名")
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=f"目标已存在: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"重命名失败: {exc}") from exc

    for updated in result.get("updated_records", []):
        if not isinstance(updated, dict) or updated.get("kind") != "dataset":
            continue
        old_record = updated.get("old_record", {})
        record = updated.get("record", {})
        if not isinstance(record, dict) or not isinstance(old_record, dict):
            continue
        new_name = str(record.get("name", "")).strip()
        old_name = str(old_record.get("name", "")).strip()
        if not new_name:
            continue
        session = session_manager.get_session(session_id)
        if session is None:
            continue
        if old_name in session.datasets:
            session.datasets[new_name] = session.datasets.pop(old_name)

    return APIResponse(success=True, data={"path": result.get("new_path", file_path)})


@router.post("/workspace/{session_id}/files/{file_path:path}")
async def save_workspace_file(
    session_id: str,
    file_path: str,
    request: SaveWorkspaceTextRequest,
):
    """保存文本文件到工作空间。"""
    _ensure_workspace_session_exists(session_id)
    workspace = WorkspaceManager(session_id)

    try:
        workspace.save_text_file(file_path, request.content)
        return APIResponse(success=True, data={"path": file_path})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"保存失败: {exc}") from exc


@router.delete("/workspace/{session_id}/files/{file_path:path}")
async def delete_workspace_file(session_id: str, file_path: str):
    """删除工作空间文件。"""
    _ensure_workspace_session_exists(session_id)
    workspace = WorkspaceManager(session_id)

    try:
        result = workspace.delete_path(file_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"文件不存在: {file_path}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    for deleted in result.get("deleted_records", []):
        if not isinstance(deleted, dict) or deleted.get("kind") != "dataset":
            continue
        record = deleted.get("record", {})
        if not isinstance(record, dict):
            continue
        name = str(record.get("name", "")).strip()
        if not name:
            continue
        session = session_manager.get_session(session_id)
        if session is not None and name in session.datasets:
            del session.datasets[name]

    return APIResponse(success=True, data={"path": file_path})


@router.get("/workspace/{session_id}/download/{file_path:path}")
async def download_workspace_file(
    session_id: str,
    file_path: str,
    inline: bool = False,
):
    """下载工作空间文件。"""
    _ensure_workspace_session_exists(session_id)
    workspace = WorkspaceManager(session_id)
    try:
        full_path = workspace.resolve_workspace_path(file_path, allow_missing=False)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"文件不存在: {file_path}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if full_path.is_dir():
        raise HTTPException(status_code=400, detail="path 是目录，不能直接下载")

    return _build_download_response(full_path, full_path.name, inline=inline)


@router.post("/workspace/{session_id}/download-zip")
async def download_workspace_zip(
    session_id: str,
    paths: list[str],
):
    """批量下载工作空间文件为 ZIP。"""
    _ensure_workspace_session_exists(session_id)
    if not paths:
        raise HTTPException(status_code=400, detail="paths 不能为空")

    workspace = WorkspaceManager(session_id)
    try:
        zip_bytes = workspace.batch_download_paths(paths)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"文件不存在: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not zip_bytes:
        raise HTTPException(status_code=404, detail="没有可下载的文件")
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="workspace.zip"'},
    )


@router.get("/workspace/{session_id}/executions")
async def list_workspace_executions(session_id: str):
    """获取新版工作空间执行历史。"""
    _ensure_workspace_session_exists(session_id)
    workspace = WorkspaceManager(session_id)
    executions = workspace.list_code_executions()
    return APIResponse(success=True, data={"session_id": session_id, "executions": executions})


@router.get("/workspace/{session_id}/folders")
async def list_workspace_folders(session_id: str):
    """列出新版工作空间文件夹。"""
    _ensure_workspace_session_exists(session_id)
    workspace = WorkspaceManager(session_id)
    folders = workspace.list_folders()
    return APIResponse(success=True, data={"session_id": session_id, "folders": folders})


@router.post("/workspace/{session_id}/folders")
async def create_workspace_folder(session_id: str, req: dict[str, Any]):
    """创建新版工作空间文件夹。"""
    _ensure_workspace_session_exists(session_id)
    name = str(req.get("name", "")).strip()
    if not name:
        raise HTTPException(status_code=400, detail="文件夹名称不能为空")
    parent = req.get("parent")
    workspace = WorkspaceManager(session_id)
    folder = workspace.create_folder(name, parent)
    return APIResponse(success=True, data={"session_id": session_id, "folder": folder})


# ---- Markdown Skills ----


@router.get("/skills/markdown", response_model=APIResponse)
async def list_markdown_skills():
    """获取所有 Markdown 技能（语义目录）。"""
    registry = _get_skill_registry()
    return APIResponse(success=True, data=registry.get_semantic_catalog())


@router.get("/skills/markdown/{skill_name}", response_model=APIResponse)
async def get_markdown_skill(skill_name: str):
    """获取 Markdown Skill 详情（含全文内容）。"""
    try:
        validated_name = validate_skill_name(skill_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    registry = _get_skill_registry()
    _refresh_skill_registry(registry)
    item = _get_markdown_skill_item_or_404(registry, validated_name)
    skill_path = _resolve_skill_path_inside_root(str(item.get("location", "")))
    if not skill_path.exists():
        raise HTTPException(status_code=404, detail=f"技能文件不存在: {skill_path}")

    content = skill_path.read_text(encoding="utf-8")
    parsed = parse_skill_document(content, fallback_name=validated_name)
    return APIResponse(
        data={
            "skill": {
                **item,
                "description": parsed.description,
                "category": parsed.category,
                "content": content,
            }
        }
    )


@router.get("/skills/markdown/{skill_name}/instruction", response_model=APIResponse)
async def get_markdown_skill_instruction(skill_name: str):
    """获取 Markdown Skill 的说明层内容（去除 frontmatter）。"""
    registry = _get_skill_registry()
    _refresh_skill_registry(registry)
    _get_markdown_skill_item_or_404(registry, skill_name)
    payload = registry.get_skill_instruction(skill_name)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"技能 '{skill_name}' 的说明不存在")
    return APIResponse(data=payload)


@router.get("/skills/markdown/{skill_name}/runtime-resources", response_model=APIResponse)
async def get_markdown_skill_runtime_resources(skill_name: str):
    """获取 Markdown Skill 的运行时资源目录。"""
    registry = _get_skill_registry()
    _refresh_skill_registry(registry)
    _get_markdown_skill_item_or_404(registry, skill_name)
    payload = registry.get_runtime_resources(skill_name)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"技能 '{skill_name}' 的运行时资源不存在")
    return APIResponse(data=payload)


@router.get("/skills/markdown/{skill_name}/files", response_model=APIResponse)
async def list_markdown_skill_files(skill_name: str):
    """获取 Markdown Skill 的文件树。"""
    registry = _get_skill_registry()
    skill_dir = _get_markdown_skill_dir_or_404(registry, skill_name)
    entries = _build_skill_file_entries(skill_dir)
    return APIResponse(
        success=True,
        data={"skill_name": skill_name, "root": str(skill_dir), "files": entries},
    )


@router.put("/skills/markdown/{skill_name}", response_model=APIResponse)
async def update_markdown_skill(skill_name: str, request: MarkdownSkillUpdateRequest):
    """更新 Markdown Skill（编辑元数据和内容）。"""
    try:
        validated_name = validate_skill_name(skill_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    description = request.description.strip()
    if not description:
        raise HTTPException(status_code=400, detail="描述不能为空")

    try:
        category = normalize_category(request.category, strict=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    registry = _get_skill_registry()
    _refresh_skill_registry(registry)
    item = _get_markdown_skill_item_or_404(registry, validated_name)
    skill_path = _resolve_skill_path_inside_root(str(item.get("location", "")))
    if not skill_path.exists():
        raise HTTPException(status_code=404, detail=f"技能文件不存在: {skill_path}")

    existing_content = skill_path.read_text(encoding="utf-8")
    existing_document = parse_skill_document(existing_content, fallback_name=validated_name)
    updated_document = MarkdownSkillDocument(
        name=validated_name,
        description=description,
        category=category,
        body=request.content.strip() or existing_document.body,
        frontmatter=existing_document.frontmatter,
    )
    skill_path.write_text(render_skill_document(updated_document), encoding="utf-8")

    _refresh_skill_registry(registry)
    updated_item = _get_markdown_skill_item_or_404(registry, validated_name)
    return APIResponse(
        data={
            "skill": {
                **updated_item,
                "content": skill_path.read_text(encoding="utf-8"),
            }
        }
    )


@router.patch("/skills/markdown/{skill_name}/enabled", response_model=APIResponse)
async def set_markdown_skill_enabled(skill_name: str, request: MarkdownSkillEnabledRequest):
    """启用/禁用 Markdown Skill。"""
    registry = _get_skill_registry()
    _refresh_skill_registry(registry)
    updated = registry.set_markdown_skill_enabled(skill_name, request.enabled)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Markdown 技能 '{skill_name}' 不存在")
    return APIResponse(data={"skill": updated})


@router.delete("/skills/markdown/{skill_name}", response_model=APIResponse)
async def delete_markdown_skill(skill_name: str):
    """删除 Markdown Skill。"""
    try:
        validated_name = validate_skill_name(skill_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    registry = _get_skill_registry()
    _refresh_skill_registry(registry)
    item = _get_markdown_skill_item_or_404(registry, validated_name)
    skill_path = _resolve_skill_path_inside_root(str(item.get("location", "")))
    if not skill_path.exists():
        raise HTTPException(status_code=404, detail=f"技能文件不存在: {skill_path}")

    shutil.rmtree(skill_path.parent, ignore_errors=False)
    registry.remove_markdown_skill_override(validated_name)
    _refresh_skill_registry(registry)
    return APIResponse(data={"deleted": validated_name})




@router.get("/skills/markdown/{skill_name}/files/content", response_model=APIResponse)
async def get_markdown_skill_file_content(skill_name: str, path: str):
    """读取 Markdown Skill 目录中的单个文件。"""
    try:
        validated_name = validate_skill_name(skill_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    registry = _get_skill_registry()
    _refresh_skill_registry(registry)
    skill_dir = _get_markdown_skill_dir_or_404(registry, validated_name)
    target = _resolve_skill_relative_path(skill_dir, path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail=f"文件不存在: {path}")

    raw = target.read_bytes()
    is_text = True
    content: str | None
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        is_text = False
        content = None

    return APIResponse(
        data={
            "skill_name": validated_name,
            "path": target.relative_to(skill_dir).as_posix(),
            "is_text": is_text,
            "size": len(raw),
            "content": content,
        }
    )


@router.put("/skills/markdown/{skill_name}/files/content", response_model=APIResponse)
async def save_markdown_skill_file_content(skill_name: str, req: MarkdownSkillFileWriteRequest):
    """保存 Markdown Skill 文本文件内容。"""
    try:
        validated_name = validate_skill_name(skill_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    registry = _get_skill_registry()
    _refresh_skill_registry(registry)
    skill_dir = _get_markdown_skill_dir_or_404(registry, validated_name)
    target = _resolve_skill_relative_path(skill_dir, req.path)
    if target.exists() and target.is_dir():
        raise HTTPException(status_code=400, detail="目标路径是目录，不能写入文本")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(req.content, encoding="utf-8")
    _refresh_skill_registry(registry)
    return APIResponse(
        data={
            "skill_name": validated_name,
            "path": target.relative_to(skill_dir).as_posix(),
            "size": target.stat().st_size,
        }
    )


@router.post("/skills/markdown/{skill_name}/files/upload", response_model=APIResponse)
async def upload_markdown_skill_attachment(
    skill_name: str,
    file: UploadFile = File(...),
    dir_path: str = Form(""),
    overwrite: bool = Form(False),
):
    """上传 Markdown Skill 附属文件。"""
    try:
        validated_name = validate_skill_name(skill_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少文件名")

    registry = _get_skill_registry()
    _refresh_skill_registry(registry)
    skill_dir = _get_markdown_skill_dir_or_404(registry, validated_name)

    safe_filename = Path(file.filename).name
    if not safe_filename:
        raise HTTPException(status_code=400, detail="非法文件名")

    target_relative = f"{dir_path.strip().strip('/')}/{safe_filename}".strip("/")
    target = _resolve_skill_relative_path(skill_dir, target_relative)

    content = await file.read()
    if len(content) > settings.max_upload_size:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大（{len(content)} 字节），最大 {settings.max_upload_size} 字节",
        )

    if target.exists() and target.is_dir():
        raise HTTPException(status_code=400, detail="目标路径是目录")
    if target.exists() and not overwrite:
        raise HTTPException(status_code=409, detail=f"文件已存在: {target_relative}")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    _refresh_skill_registry(registry)
    return APIResponse(
        data={
            "skill_name": validated_name,
            "path": target.relative_to(skill_dir).as_posix(),
            "size": len(content),
        }
    )


@router.post("/skills/markdown/{skill_name}/directories", response_model=APIResponse)
async def create_markdown_skill_directory(
    skill_name: str, request: MarkdownSkillDirCreateRequest
):
    """在 Markdown Skill 内创建目录。"""
    registry = _get_skill_registry()
    skill_dir = _get_markdown_skill_dir_or_404(registry, skill_name)
    target = _resolve_skill_relative_path(skill_dir, request.path)

    target.mkdir(parents=True, exist_ok=True)
    return APIResponse(success=True, data={"path": request.path})


@router.post("/skills/markdown/{skill_name}/dirs", response_model=APIResponse)
async def create_markdown_skill_dir(skill_name: str, req: MarkdownSkillDirCreateRequest):
    """创建 Markdown Skill 子目录。"""
    try:
        validated_name = validate_skill_name(skill_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    registry = _get_skill_registry()
    _refresh_skill_registry(registry)
    skill_dir = _get_markdown_skill_dir_or_404(registry, validated_name)
    target = _resolve_skill_relative_path(skill_dir, req.path)
    if target.exists() and target.is_file():
        raise HTTPException(status_code=400, detail="同名文件已存在，无法创建目录")
    target.mkdir(parents=True, exist_ok=True)
    return APIResponse(
        data={
            "skill_name": validated_name,
            "path": target.relative_to(skill_dir).as_posix(),
        }
    )


@router.delete("/skills/markdown/{skill_name}/paths", response_model=APIResponse)
async def delete_markdown_skill_path(skill_name: str, req: MarkdownSkillPathDeleteRequest):
    """删除 Markdown Skill 目录内文件或子目录。"""
    try:
        validated_name = validate_skill_name(skill_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    registry = _get_skill_registry()
    _refresh_skill_registry(registry)
    skill_dir = _get_markdown_skill_dir_or_404(registry, validated_name)
    target = _resolve_skill_relative_path(skill_dir, req.path)
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"路径不存在: {req.path}")

    if target.resolve() == skill_dir.resolve():
        raise HTTPException(status_code=400, detail="不能删除技能根目录")
    if target.name.lower() == "skill.md":
        raise HTTPException(status_code=400, detail="不能删除 SKILL.md，请使用技能删除接口")

    relative = target.relative_to(skill_dir).as_posix()
    if target.is_dir():
        shutil.rmtree(target, ignore_errors=False)
    else:
        target.unlink(missing_ok=False)
    _refresh_skill_registry(registry)
    return APIResponse(data={"skill_name": validated_name, "deleted": relative})


@router.get("/skills/markdown/{skill_name}/files/{file_path:path}", response_model=APIResponse)
async def get_markdown_skill_file(skill_name: str, file_path: str):
    """获取 Markdown Skill 内的文件内容。"""
    registry = _get_skill_registry()
    skill_dir = _get_markdown_skill_dir_or_404(registry, skill_name)
    target = _resolve_skill_relative_path(skill_dir, file_path)

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {file_path}")
    if target.is_dir():
        raise HTTPException(status_code=400, detail="path 是目录，不是文件")

    content = target.read_text(encoding="utf-8")
    return APIResponse(success=True, data={"path": file_path, "content": content})


@router.post("/skills/markdown/{skill_name}/files/{file_path:path}", response_model=APIResponse)
async def write_markdown_skill_file(
    skill_name: str, file_path: str, request: MarkdownSkillFileWriteRequest
):
    """写入 Markdown Skill 内的文件（支持子目录）。"""
    registry = _get_skill_registry()
    skill_dir = _get_markdown_skill_dir_or_404(registry, skill_name)
    target = _resolve_skill_relative_path(skill_dir, file_path)

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(request.content, encoding="utf-8")

    return APIResponse(success=True, data={"path": file_path})


@router.delete("/skills/markdown/{skill_name}/paths/{file_path:path}", response_model=APIResponse)
async def delete_markdown_skill_path_by_path(skill_name: str, file_path: str):
    """删除 Markdown Skill 内的文件或目录（路径式兼容接口）。"""
    registry = _get_skill_registry()
    skill_dir = _get_markdown_skill_dir_or_404(registry, skill_name)
    target = _resolve_skill_relative_path(skill_dir, file_path)

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"路径不存在: {file_path}")

    if target.is_dir():
        shutil.rmtree(target, ignore_errors=True)
    else:
        target.unlink(missing_ok=True)

    return APIResponse(success=True)


@router.get("/skills/markdown/{skill_name}/bundle")
async def download_markdown_skill_bundle(skill_name: str):
    """打包下载完整 Markdown Skill 目录。"""
    try:
        validated_name = validate_skill_name(skill_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    registry = _get_skill_registry()
    _refresh_skill_registry(registry)
    skill_dir = _get_markdown_skill_dir_or_404(registry, validated_name)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(skill_dir.rglob("*")):
            if path.is_file():
                arcname = f"{validated_name}/{path.relative_to(skill_dir).as_posix()}"
                zf.write(path, arcname)

    filename = f"{validated_name}.zip"
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/skills/upload", response_model=APIResponse)
@router.post("/skills/markdown/upload", response_model=APIResponse)
async def upload_skill_file(file: UploadFile = File(...)):
    """上传 Markdown Skill 文件。"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少文件名")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in _SKILL_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"仅支持上传 {sorted(_SKILL_UPLOAD_EXTENSIONS)}",
        )

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="上传文件为空")
    if len(raw) > settings.max_upload_size:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大（{len(raw)} 字节），最大 {settings.max_upload_size} 字节",
        )

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"文件不是合法 UTF-8 编码: {exc}") from exc

    fallback_name = guess_skill_name_from_filename(file.filename)
    try:
        document = parse_skill_document(text, fallback_name=fallback_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    registry = _get_skill_registry()
    _refresh_skill_registry(registry)
    if registry.get_markdown_skill(document.name):
        raise HTTPException(status_code=409, detail=f"技能 '{document.name}' 已存在")

    skill_dir = settings.skills_dir / document.name
    target = skill_dir / "SKILL.md"
    if target.exists():
        raise HTTPException(status_code=409, detail=f"技能 '{document.name}' 已存在")

    skill_dir.mkdir(parents=True, exist_ok=True)
    target.write_text(render_skill_document(document), encoding="utf-8")

    _refresh_skill_registry(registry)
    skill = registry.get_markdown_skill(document.name)
    return APIResponse(data={"skill": skill})


# ---- Intent Analysis ----


@router.post("/intent/analyze", response_model=APIResponse)
async def analyze_intent(
    user_message: str = "",
    capabilities: list[dict[str, Any]] | None = None,
    semantic_skills: list[dict[str, Any]] | None = None,
    analysis_mode: str = "rule",
):
    """分析用户意图并返回结构化结果。

    请求参数:
        - user_message: 用户输入消息
        - capabilities: 可选的能力目录列表（默认使用系统 capabilities）
        - semantic_skills: 可选的语义技能目录列表（默认使用已加载的 skills）
        - analysis_mode: 分析模式（rule/hybrid，默认 rule）
    """
    # 如果没有提供 capabilities，使用默认 capabilities
    if capabilities is None:
        cap_registry = _get_capability_registry()
        capabilities = [cap.to_dict() for cap in cap_registry.list_capabilities()]

    # 如果没有提供 semantic_skills，从 skill registry 获取
    if semantic_skills is None:
        try:
            skill_registry = _get_skill_registry()
            semantic_skills = skill_registry.get_semantic_catalog()
        except Exception:
            semantic_skills = []
    
    if analysis_mode == "hybrid":
        # 使用增强版语义分析
        try:
            from nini.intent import get_enhanced_intent_analyzer
            enhanced = get_enhanced_intent_analyzer()
            
            # 先获取规则分析结果
            rule_analysis = default_intent_analyzer.analyze(
                user_message,
                capabilities=capabilities,
                semantic_skills=semantic_skills,
            )
            
            # 应用语义增强
            analysis = enhanced.analyze(
                user_message,
                capabilities=capabilities,
                semantic_skills=semantic_skills,
                rule_based_analysis=rule_analysis,
            )
        except Exception as exc:
            logger.warning("语义分析失败，回退到规则分析: %s", exc)
            analysis = default_intent_analyzer.analyze(
                user_message,
                capabilities=capabilities,
                semantic_skills=semantic_skills,
            )
    else:
        # 使用规则分析
        analysis = default_intent_analyzer.analyze(
            user_message,
            capabilities=capabilities,
            semantic_skills=semantic_skills,
        )

    return APIResponse(
        success=True,
        data=analysis.to_dict(),
    )


@router.get("/intent/status", response_model=APIResponse)
async def get_intent_analysis_status():
    """获取意图分析系统状态。
    
    返回规则版和语义增强版的可用状态。
    """
    from nini.intent import default_intent_analyzer
    
    # 检查语义增强版是否可用
    semantic_available = False
    try:
        from nini.intent import get_enhanced_intent_analyzer
        enhanced = get_enhanced_intent_analyzer()
        semantic_available = enhanced.is_semantic_available
    except Exception:
        pass
    
    return APIResponse(
        success=True,
        data={
            "rule_based": {
                "available": True,
                "version": "v2",
                "features": ["同义词扩展", "元数据加权", "关键词匹配"],
            },
            "semantic": {
                "available": semantic_available,
                "features": ["embedding 相似度", "语义检索", "规则+语义融合"] if semantic_available else [],
            },
            "default_mode": "rule",
        },
    )


# ---- Capabilities ----


_capability_registry = None


def _get_capability_registry():
    global _capability_registry
    if _capability_registry is None:
        from nini.capabilities import CapabilityRegistry, create_default_capabilities

        _capability_registry = CapabilityRegistry()
        for cap in create_default_capabilities():
            _capability_registry.register(cap)
    return _capability_registry


@router.get("/capabilities", response_model=APIResponse)
async def list_capabilities():
    """获取所有可用能力列表。"""
    registry = _get_capability_registry()
    return APIResponse(success=True, data={"capabilities": registry.to_catalog()})


@router.get("/capabilities/{name}", response_model=APIResponse)
async def get_capability(name: str):
    """获取单个能力的详细信息。"""
    registry = _get_capability_registry()
    capability = registry.get(name)
    if capability is None:
        raise HTTPException(status_code=404, detail=f"能力 '{name}' 不存在")
    return APIResponse(success=True, data=capability.to_dict())


@router.post("/capabilities/suggest", response_model=APIResponse)
async def suggest_capabilities(user_message: str):
    """根据用户消息推荐相关能力。

    Args:
        user_message: 用户输入消息

    Returns:
        推荐的能力列表和意图分析结果
    """
    registry = _get_capability_registry()

    # 获取意图分析
    analysis = registry.analyze_intent(user_message)

    # 获取推荐的能力
    suggested = registry.suggest_for_intent(user_message)

    # 构建响应数据（将分析结果展平到顶层以兼容测试）
    analysis_dict = analysis.to_dict()
    return APIResponse(
        success=True,
        data={
            "suggestions": [cap.to_dict() for cap in suggested],
            "tool_hints": analysis_dict.get("tool_hints", []),
            "clarification_needed": analysis_dict.get("clarification_needed", False),
            "analysis_method": analysis_dict.get("analysis_method", "rule_based_v2"),
            **{k: v for k, v in analysis_dict.items() if k not in ["suggestions"]},
        },
    )


@router.post("/capabilities/{name}/execute", response_model=APIResponse)
async def execute_capability(
    name: str,
    session_id: str,
    params: dict[str, Any],
):
    """执行指定的 Capability。

    当前支持:
    - difference_analysis: params需包含 dataset_name, value_column, group_column
    - correlation_analysis: params需包含 dataset_name; 可选 columns, method, correction

    Args:
        name: Capability 名称
        session_id: 会话ID
        params: 执行参数（必须包含 dataset_name）

    Returns:
        执行结果
    """
    from nini.agent.session import session_manager
    from nini.capabilities.registry import (
        CapabilityNotExecutableError,
        CapabilityExecutorNotConfiguredError,
    )
    from nini.tools.registry import create_default_tool_registry

    capability_registry = _get_capability_registry()
    capability = capability_registry.get(name)
    if capability is None:
        raise HTTPException(status_code=404, detail=f"能力 '{name}' 不存在")
    if not capability.supports_direct_execution():
        message = capability.execution_message or f"能力 '{name}' 暂不支持直接执行"
        raise HTTPException(status_code=409, detail=message)

    # 校验必填参数
    if "dataset_name" not in params:
        raise HTTPException(status_code=422, detail="缺少必填参数: dataset_name")

    # 获取会话
    session = session_manager.get_or_create(session_id)

    # 获取 ToolRegistry（用于执行底层工具）
    tool_registry = create_default_tool_registry()

    capability_params = dict(params)
    capability_params.setdefault("alpha", 0.05)

    try:
        result = await capability_registry.execute(
            name,
            session,
            capability_params,
            tool_registry=tool_registry,
        )
    except CapabilityNotExecutableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CapabilityExecutorNotConfiguredError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc

    return APIResponse(
        success=result.success,
        data=result.to_dict(),
        message=result.message if not result.success else None,
    )


# ---- ResearchProfile ----


def _get_research_profile_manager():
    """获取研究画像管理器。"""
    from nini.memory.research_profile import get_research_profile_manager

    return get_research_profile_manager()


def _profile_to_dict(profile) -> dict[str, Any]:
    """将 ResearchProfile 转换为字典。"""
    return {
        "user_id": profile.user_id,
        "domain": profile.domain,
        "research_interest": profile.research_interest,
        "significance_level": profile.significance_level,
        "preferred_correction": profile.preferred_correction,
        "confidence_interval": profile.confidence_interval,
        "journal_style": profile.journal_style,
        "color_palette": profile.color_palette,
        "figure_width": profile.figure_width,
        "figure_height": profile.figure_height,
        "figure_dpi": profile.figure_dpi,
        "auto_check_assumptions": profile.auto_check_assumptions,
        "include_effect_size": profile.include_effect_size,
        "include_ci": profile.include_ci,
        "include_power_analysis": profile.include_power_analysis,
        "total_analyses": profile.total_analyses,
        "favorite_tests": profile.favorite_tests,
        "recent_datasets": profile.recent_datasets,
        "research_domains": profile.research_domains,
        "preferred_methods": profile.preferred_methods,
        "output_language": profile.output_language,
        "report_detail_level": profile.report_detail_level,
        "typical_sample_size": profile.typical_sample_size,
        "research_notes": profile.research_notes,
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


@router.get("/research-profile", response_model=APIResponse)
async def get_research_profile(profile_id: str = "default"):
    """获取研究画像。

    Args:
        profile_id: 画像标识（默认 default）

    Returns:
        研究画像数据
    """
    manager = _get_research_profile_manager()
    profile = manager.get_or_create_sync(profile_id)

    return APIResponse(success=True, data=_profile_to_dict(profile))


@router.put("/research-profile", response_model=APIResponse)
async def update_research_profile(
    request: ResearchProfileUpdateRequest,
    profile_id: str = "default",
):
    """更新研究画像。

    Args:
        request: 更新请求（只更新提供的字段）
        profile_id: 画像标识（默认 default）

    Returns:
        更新后的研究画像数据
    """
    manager = _get_research_profile_manager()

    # 构建更新字典（只包含非 None 字段）
    updates = {}
    for key, value in request.model_dump().items():
        if value is not None:
            updates[key] = value

    if not updates:
        # 没有需要更新的字段，直接返回当前画像
        profile = manager.get_or_create_sync(profile_id)
        return APIResponse(success=True, data=_profile_to_dict(profile))

    # 执行更新
    profile = manager.update_sync(profile_id, **updates)

    return APIResponse(success=True, data=_profile_to_dict(profile))


@router.get("/research-profile/prompt", response_model=APIResponse)
async def get_research_profile_prompt(profile_id: str = "default"):
    """获取研究画像的运行时提示文本（用于调试）。

    Args:
        profile_id: 画像标识（默认 default）

    Returns:
        prompt 文本
    """
    manager = _get_research_profile_manager()
    profile = manager.get_or_create_sync(profile_id)
    prompt = manager.get_research_profile_prompt(profile)

    return APIResponse(success=True, data={"prompt": prompt})


@router.post("/research-profile/record-analysis", response_model=APIResponse)
async def record_analysis(
    test_method: str,
    journal_style: str | None = None,
    profile_id: str = "default",
):
    """记录分析活动（用于测试画像积累功能）。

    Args:
        test_method: 使用的检验方法
        journal_style: 期刊风格
        profile_id: 画像标识

    Returns:
        更新后的研究画像
    """
    manager = _get_research_profile_manager()
    profile = manager.record_analysis_sync(profile_id, test_method, journal_style)

    return APIResponse(success=True, data=_profile_to_dict(profile))


# ---- Report Generation ----


@router.get("/report/templates", response_model=APIResponse)
async def list_report_templates():
    """获取所有可用的报告模板。"""
    from nini.tools.report_template import list_templates

    templates = list_templates()
    return APIResponse(success=True, data={"templates": templates})


@router.post("/report/generate", response_model=APIResponse)
async def generate_report(
    request: ReportGenerateRequest,
    session_id: str,
):
    """生成结构化分析报告。

    Args:
        request: 报告生成配置
        session_id: 会话ID

    Returns:
        生成的报告内容和文件信息
    """
    from nini.agent.session import session_manager
    from nini.tools.report_template import (
        get_template,
        get_section_order,
        get_section_prompt,
    )
    from nini.memory.storage import ArtifactStorage
    from nini.workspace import WorkspaceManager
    from datetime import datetime, timezone

    session = session_manager.get_or_create(session_id)

    # 获取模板
    template = get_template(request.template)
    if not template:
        raise HTTPException(status_code=400, detail=f"未知的模板: {request.template}")

    # 确定章节顺序
    section_order = get_section_order(request.template, request.sections)

    # 生成报告内容
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    report_lines = [
        f"# {request.title}",
        "",
        f"> 会话 ID: `{session.id}` | 生成时间: {now}",
        f"> 模板: {template.name} | 详细程度: {request.detail_level}",
        "",
    ]

    # 为每个章节生成内容
    for section_id in section_order:
        prompt = get_section_prompt(request.template, section_id, request.detail_level)
        section_title = {
            "abstract": "摘要",
            "introduction": "引言",
            "methods": "方法",
            "results": "结果",
            "discussion": "讨论",
            "conclusion": "结论",
            "limitations": "局限性",
            "references": "参考文献",
        }.get(section_id, section_id.capitalize())

        report_lines.extend([
            f"## {section_title}",
            "",
            f"*{prompt}*",
            "",
            "（此章节内容由模型根据会话历史自动生成）",
            "",
        ])

    # 合并为完整报告
    report_markdown = "\n".join(report_lines)

    # 保存报告
    storage = ArtifactStorage(session.id)
    ws = WorkspaceManager(session.id)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{request.template}_{request.detail_level}_report_{ts}.md"

    path = storage.save_text(report_markdown, filename)

    artifact = {
        "name": filename,
        "type": "report",
        "path": str(path),
        "download_url": ws.build_artifact_download_url(filename),
    }

    ws.add_artifact_record(
        name=filename,
        artifact_type="report",
        file_path=path,
        format_hint="md",
    )

    return APIResponse(
        success=True,
        data={
            "filename": filename,
            "template": template.id,
            "template_name": template.name,
            "sections": section_order,
            "report_markdown": report_markdown,
            "artifact": artifact,
        },
    )


@router.post("/report/export", response_model=APIResponse)
async def export_report(
    request: ReportExportRequest,
    session_id: str,
):
    """导出报告为指定格式。

    Args:
        request: 导出配置
        session_id: 会话ID

    Returns:
        导出文件信息
    """
    from nini.agent.session import session_manager
    from nini.memory.storage import ArtifactStorage
    from nini.workspace import WorkspaceManager
    from fastapi.responses import FileResponse

    session = session_manager.get_or_create(session_id)

    if request.format not in ("md", "docx", "pdf"):
        raise HTTPException(status_code=400, detail=f"不支持的导出格式: {request.format}")

    # 获取最新的报告文件
    storage = ArtifactStorage(session.id)
    ws = WorkspaceManager(session.id)

    # 查找最新的报告文件
    artifacts = ws.list_artifacts()
    report_artifacts = [
        a for a in artifacts
        if isinstance(a, dict) and str(a.get("type", "")).lower() == "report"
    ]

    if not report_artifacts:
        raise HTTPException(status_code=404, detail="未找到可导出的报告，请先生成报告")

    # 获取最新的报告
    latest_report = sorted(
        report_artifacts,
        key=lambda x: str(x.get("updated_at", "")),
        reverse=True,
    )[0]

    report_name = str(latest_report.get("name", "report.md"))
    report_path = storage.get_path(report_name)

    if not report_path.exists():
        raise HTTPException(status_code=404, detail="报告文件不存在")

    # 如果请求的是 markdown 格式，直接返回
    if request.format == "md":
        return APIResponse(
            success=True,
            data={
                "filename": report_name,
                "format": "md",
                "download_url": latest_report.get("download_url", ""),
            },
        )

    # DOCX 或 PDF 格式转换
    try:
        from nini.tools.report_exporter import export_report as do_export
        
        # 读取 Markdown 内容
        markdown_content = report_path.read_text(encoding="utf-8")
        
        # 导出为指定格式
        exported_bytes = do_export(
            markdown_content,
            format=request.format,
            title=request.filename or report_name.replace(".md", ""),
        )
        
        # 保存导出文件
        new_filename = report_name.replace(".md", f".{request.format}")
        if request.filename:
            new_filename = request.filename
            if not new_filename.endswith(f".{request.format}"):
                new_filename += f".{request.format}"
        
        export_path = storage.get_path(new_filename)
        export_path.write_bytes(exported_bytes)
        
        # 添加到工作区
        ws.add_artifact_record(
            name=new_filename,
            artifact_type="report",
            file_path=export_path,
            format_hint=request.format,
        )
        
        return APIResponse(
            success=True,
            data={
                "filename": new_filename,
                "format": request.format,
                "size": len(exported_bytes),
                "download_url": ws.build_artifact_download_url(new_filename),
            },
        )
        
    except ImportError as exc:
        # 缺少依赖
        logger.warning("导出 %s 失败: %s", request.format, exc)
        return APIResponse(
            success=False,
            error=f"缺少 {request.format.upper()} 导出依赖",
            message=f"请安装依赖: pip install {'python-docx' if request.format == 'docx' else 'reportlab'}",
        )
    except Exception as exc:
        logger.error("导出 %s 失败: %s", request.format, exc, exc_info=True)
        return APIResponse(
            success=False,
            error=f"导出失败: {exc}",
        )


@router.get("/report/preview", response_model=APIResponse)
async def preview_report(
    session_id: str,
    filename: Optional[str] = None,
):
    """预览报告内容。

    Args:
        session_id: 会话ID
        filename: 报告文件名（可选，默认最新报告）

    Returns:
        报告内容
    """
    from nini.agent.session import session_manager
    from nini.memory.storage import ArtifactStorage
    from nini.workspace import WorkspaceManager

    session = session_manager.get_or_create(session_id)
    storage = ArtifactStorage(session.id)
    ws = WorkspaceManager(session.id)

    if filename:
        report_path = storage.get_path(filename)
    else:
        # 查找最新的报告
        artifacts = ws.list_artifacts()
        report_artifacts = [
            a for a in artifacts
            if isinstance(a, dict) and str(a.get("type", "")).lower() == "report"
        ]
        if not report_artifacts:
            raise HTTPException(status_code=404, detail="未找到报告文件")

        latest_report = sorted(
            report_artifacts,
            key=lambda x: str(x.get("updated_at", "")),
            reverse=True,
        )[0]
        report_name = str(latest_report.get("name", "report.md"))
        report_path = storage.get_path(report_name)

    if not report_path.exists():
        raise HTTPException(status_code=404, detail="报告文件不存在")

    content = report_path.read_text(encoding="utf-8")

    return APIResponse(
        success=True,
        data={
            "filename": report_path.name,
            "content": content,
        },
    )


# ---- 会话消息历史 ----


@router.get("/sessions/{session_id}/messages", response_model=APIResponse)
async def get_session_messages(session_id: str):
    """获取指定会话的消息历史。"""
    session = session_manager.get_session(session_id)
    if session is not None:
        messages = session.messages
    else:
        from nini.memory.conversation import ConversationMemory

        mem = ConversationMemory(session_id)
        messages = mem.load_messages(resolve_refs=True)
        if not messages and not session_manager.session_exists(session_id):
            raise HTTPException(status_code=404, detail="会话不存在或无消息记录")

    cleaned: list[dict] = []
    for msg in messages:
        chart_data = msg.get("chart_data")
        normalized_chart_data = normalize_chart_payload(chart_data)
        item = {
            "role": msg.get("role", ""),
            "content": msg.get("content", ""),
            "tool_calls": msg.get("tool_calls"),
            "tool_call_id": msg.get("tool_call_id"),
            "event_type": msg.get("event_type"),
            "chart_data": normalized_chart_data if normalized_chart_data else chart_data,
            "data_preview": msg.get("data_preview"),
            "artifacts": msg.get("artifacts"),
            "images": msg.get("images"),
        }
        cleaned.append(item)
    return APIResponse(data={"session_id": session_id, "messages": cleaned})


# ---- 工具 / 技能目录 ----


@router.get("/tools", response_model=APIResponse)
async def list_tools():
    """获取可执行工具目录（Function Tools）。"""
    registry = _get_skill_registry()
    _refresh_skill_registry(registry)
    tools = registry.list_tools_catalog()
    return APIResponse(data={"tools": tools})


@router.get("/skills", response_model=APIResponse)
async def list_skills(skill_type: str | None = None):
    """获取技能目录。

    参数：
    - 未传或 markdown：返回 Markdown Skills
    - function：返回 Function Tools
    - all：返回聚合目录
    """
    registry = _get_skill_registry()
    _refresh_skill_registry(registry)

    normalized_type = (skill_type or "markdown").strip().lower()
    if normalized_type == "markdown":
        skills = registry.list_markdown_skill_catalog()
    elif normalized_type == "function":
        skills = registry.list_tools_catalog()
    elif normalized_type == "all":
        skills = registry.list_skill_catalog()
    else:
        raise HTTPException(
            status_code=400,
            detail="skill_type 仅支持 markdown/function/all",
        )
    return APIResponse(data={"skills": skills})


@router.get("/skills/semantic-catalog", response_model=APIResponse)
async def get_semantic_catalog(skill_type: str | None = None):
    """获取面向检索与渐进式披露的轻量语义目录。"""
    registry = _get_skill_registry()
    _refresh_skill_registry(registry)
    catalog = registry.get_semantic_catalog(skill_type=skill_type)
    return APIResponse(data={"skills": catalog})


# ---- 产物下载 ----


async def _convert_plotly_json_to_png(
    json_path: Path,
    session_id: str,
    width: int | None = None,
    height: int | None = None,
    scale: float | None = None,
) -> Response | None:
    """将 Plotly JSON 转换为高清 PNG 并返回响应。失败时返回 None。"""
    import json
    import tempfile

    import plotly.graph_objects as go

    from nini.utils.chart_fonts import apply_plotly_cjk_font_fallback

    width = width or settings.plotly_export_width
    height = height or settings.plotly_export_height
    scale = scale or settings.plotly_export_scale
    timeout = settings.plotly_export_timeout

    try:
        chart_data = json.loads(json_path.read_text(encoding="utf-8"))
        fig = go.Figure(chart_data)
        apply_plotly_cjk_font_fallback(fig)

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        await asyncio.wait_for(
            asyncio.to_thread(
                fig.write_image,
                str(tmp_path),
                width=width,
                height=height,
                scale=scale,
                format="png",
            ),
            timeout=timeout,
        )

        png_bytes = tmp_path.read_bytes()
        tmp_path.unlink()
        png_filename = json_path.stem.replace(".plotly", "") + ".png"

        return Response(
            content=png_bytes,
            media_type="image/png",
            headers={"Content-Disposition": f'attachment; filename="{png_filename}"'},
        )
    except asyncio.TimeoutError:
        logger.warning("Plotly PNG 转换超时: %s", json_path.name)
        return None
    except Exception as e:
        logger.warning("Plotly PNG 转换失败: %s, 错误: %s", json_path.name, e)
        return None


def _extract_image_urls(md_content: str, session_id: str) -> list[dict[str, str]]:
    """从 Markdown 提取图片 URL 及本地路径。"""
    pattern = r"!\[([^\]]*)\]\((/api/artifacts/" + re.escape(session_id) + r"/[^)]+)\)"
    matches = re.findall(pattern, md_content)

    results = []
    for alt_text, url in matches:
        filename = unquote(url.split("/")[-1])
        artifact_path = settings.sessions_dir / session_id / "workspace" / "artifacts" / filename
        if artifact_path.exists():
            results.append(
                {"url": url, "path": str(artifact_path), "filename": filename, "alt": alt_text}
            )
    return results


def _plotly_json_to_png_bytes(json_path: Path) -> bytes | None:
    """将 Plotly JSON 文件转换为 PNG 字节。失败返回 None。"""
    import json as _json

    import plotly.graph_objects as go

    from nini.utils.chart_fonts import apply_plotly_cjk_font_fallback

    try:
        chart_data = _json.loads(json_path.read_text(encoding="utf-8"))
        fig = go.Figure(chart_data)
        apply_plotly_cjk_font_fallback(fig)
        png_data: bytes = fig.to_image(format="png", width=1400, height=900, scale=2)  # type: ignore[assignment]
        return png_data
    except Exception as exc:
        logger.debug("Plotly PNG 转换失败 (%s): %s", json_path.name, exc)
        return None


def _bundle_markdown_with_images(
    md_path: Path,
    image_urls: list[dict[str, str]],
    session_id: str,
) -> bytes:
    """将 Markdown 和图片打包为 ZIP。"""
    buf = io.BytesIO()
    md_content = md_path.read_text(encoding="utf-8")

    updated_md = md_content
    png_cache: dict[str, bytes] = {}

    for img in image_urls:
        old_url = img["url"]
        filename = img["filename"]

        if filename.lower().endswith(".plotly.json"):
            img_path = Path(img["path"])
            png_data = _plotly_json_to_png_bytes(img_path) if img_path.exists() else None
            if png_data:
                png_name = filename[: -len(".plotly.json")] + ".png"
                png_cache[png_name] = png_data
                new_url = f"images/{png_name}"
            else:
                new_url = f"images/{filename}"
        else:
            new_url = f"images/{filename}"

        updated_md = updated_md.replace(f"]({old_url})", f"]({new_url})")

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(md_path.name, updated_md.encode("utf-8"))

        for png_name, png_data in png_cache.items():
            zf.writestr(f"images/{png_name}", png_data)

        converted_plotly_names = set()
        for png_name in png_cache:
            base = png_name[: -len(".png")]
            converted_plotly_names.add(f"{base}.plotly.json")

        for img in image_urls:
            filename = img["filename"]
            if filename in converted_plotly_names:
                continue
            img_path = Path(img["path"])
            if img_path.exists():
                zf.write(img_path, f"images/{filename}")

    return buf.getvalue()


@router.get("/artifacts/{session_id}/{filename}")
async def download_artifact(
    session_id: str,
    filename: str,
    inline: bool = False,
    raw: bool = False,
):
    """下载会话产物（.plotly.json 默认自动转 PNG；raw=1 时返回原始 JSON）。"""
    safe_name = Path(unquote(filename)).name
    artifact_path = settings.sessions_dir / session_id / "workspace" / "artifacts" / safe_name
    if not artifact_path.exists():
        artifact_path = settings.sessions_dir / session_id / "artifacts" / safe_name
    if not artifact_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    if safe_name.lower().endswith(".plotly.json") and not raw:
        png_response = await _convert_plotly_json_to_png(
            artifact_path, session_id=session_id, width=1400, height=900, scale=2.0
        )
        if png_response:
            return png_response

    return _build_download_response(artifact_path, safe_name, inline=inline)


@router.get("/workspace/{session_id}/uploads/{filename}")
async def download_workspace_upload(session_id: str, filename: str, inline: bool = False):
    """下载会话工作空间中的上传文件。"""
    safe_name = Path(filename).name
    path = settings.sessions_dir / session_id / "workspace" / "uploads" / safe_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return _build_download_response(path, safe_name, inline=inline)


@router.get("/workspace/{session_id}/notes/{filename}")
async def download_workspace_note(session_id: str, filename: str, inline: bool = False):
    """下载会话工作空间中的文本文件。"""
    safe_name = Path(filename).name
    path = settings.sessions_dir / session_id / "workspace" / "notes" / safe_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return _build_download_response(path, safe_name, inline=inline)


@router.get("/workspace/{session_id}/artifacts/{filename}/bundle")
async def download_markdown_with_images(session_id: str, filename: str):
    """下载 Markdown 文件并自动打包相关图片。"""
    safe_name = Path(unquote(filename)).name
    md_path = settings.sessions_dir / session_id / "workspace" / "artifacts" / safe_name

    if not md_path.exists():
        md_path = settings.sessions_dir / session_id / "workspace" / "notes" / safe_name
    if not md_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    if not safe_name.endswith(".md"):
        return _build_download_response(md_path, safe_name)

    md_content = md_path.read_text(encoding="utf-8")
    image_urls = _extract_image_urls(md_content, session_id)

    if not image_urls:
        return _build_download_response(md_path, safe_name)

    zip_bytes = _bundle_markdown_with_images(md_path, image_urls, session_id)
    zip_filename = safe_name.replace(".md", "_bundle.zip")

    try:
        zip_filename.encode("latin-1")
        disposition = f'attachment; filename="{zip_filename}"'
    except UnicodeEncodeError:
        ascii_fallback = zip_filename.encode("ascii", errors="replace").decode("ascii")
        utf8_encoded = quote(zip_filename, safe="")
        disposition = f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{utf8_encoded}"

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": disposition},
    )


@router.get("/sessions/{session_id}/export-all")
async def export_all_artifacts(session_id: str):
    """批量导出会话的所有产物为 ZIP 文件。"""
    session_dir = settings.sessions_dir / session_id
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail="会话不存在")

    workspace_dir = session_dir / "workspace"
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        file_count = 0

        for subdir in ("artifacts", "uploads", "notes"):
            sub_path = workspace_dir / subdir
            if sub_path.exists():
                for file_path in sub_path.rglob("*"):
                    if file_path.is_file() and "memory-payloads" not in str(file_path):
                        arcname = f"{subdir}/{file_path.relative_to(sub_path)}"
                        zip_file.write(file_path, arcname)
                        file_count += 1

        memory_file = session_dir / "memory.jsonl"
        if memory_file.exists():
            zip_file.write(memory_file, "memory.jsonl")
            file_count += 1

        session = session_manager.get_session(session_id)
        if session:
            import json

            metadata = {
                "session_id": session_id,
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "file_count": file_count,
                "datasets": list(session.datasets.keys()),
            }
            zip_file.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2))

    zip_buffer.seek(0)
    zip_bytes = zip_buffer.read()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"nini_session_{session_id[:8]}_{timestamp}.zip"

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---- 模型配置 ----

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

_MODEL_PURPOSES = [
    {"id": "chat", "label": "主对话"},
    {"id": "title_generation", "label": "标题生成"},
    {"id": "image_analysis", "label": "图片识别"},
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

    return APIResponse(data=result)


@router.post("/models/priorities", response_model=APIResponse)
async def set_model_priorities_endpoint(req: ModelPrioritiesRequest):
    """批量更新模型提供商优先级，并立即生效。"""
    from nini.agent.model_resolver import reload_model_resolver
    from nini.config_manager import set_model_priorities

    try:
        normalized: dict[str, int] = {
            provider: int(priority) for provider, priority in req.priorities.items()
        }
        priorities = await set_model_priorities(normalized)
        await reload_model_resolver()
        return APIResponse(data={"priorities": priorities})
    except ValueError as e:
        return APIResponse(success=False, error=str(e))
    except Exception as e:
        return APIResponse(success=False, error=f"保存优先级失败: {e}")


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
    from nini.agent.model_resolver import model_resolver
    from nini.config_manager import (
        VALID_MODEL_PURPOSES,
        VALID_PROVIDERS,
        set_default_provider,
        set_model_purpose_routes,
    )

    update_global_preferred = "preferred_provider" in req.model_fields_set
    preferred_provider: str | None = None
    if update_global_preferred:
        preferred_provider_raw = (req.preferred_provider or "").strip()
        preferred_provider = preferred_provider_raw or None
        if preferred_provider and preferred_provider not in VALID_PROVIDERS:
            return APIResponse(success=False, error=f"未知的模型提供商: {preferred_provider}")

    updates: dict[str, dict[str, str | None]] = {}
    for purpose, provider in req.purpose_providers.items():
        if purpose not in VALID_MODEL_PURPOSES:
            return APIResponse(success=False, error=f"未知的模型用途: {purpose}")
        provider_id = (provider or "").strip() or None
        if provider_id and provider_id not in VALID_PROVIDERS:
            return APIResponse(success=False, error=f"未知的模型提供商: {provider_id}")
        updates[purpose] = {"provider_id": provider_id, "model": None, "base_url": None}

    for purpose, route in req.purpose_routes.items():
        if purpose not in VALID_MODEL_PURPOSES:
            return APIResponse(success=False, error=f"未知的模型用途: {purpose}")
        provider_id = (route.provider_id or "").strip() or None
        model = (route.model or "").strip() or None
        base_url = (route.base_url or "").strip() or None
        if provider_id and provider_id not in VALID_PROVIDERS:
            return APIResponse(success=False, error=f"未知的模型提供商: {provider_id}")
        updates[purpose] = {"provider_id": provider_id, "model": model, "base_url": base_url}

    if update_global_preferred:
        await set_default_provider(preferred_provider)
        model_resolver.set_preferred_provider(preferred_provider)

    merged_routes = await set_model_purpose_routes(updates)
    for purpose_key, merged_route in merged_routes.items():
        model_resolver.set_purpose_route(
            purpose_key,
            provider_id=merged_route.get("provider_id"),
            model=merged_route.get("model"),
            base_url=merged_route.get("base_url"),
        )

    active_by_purpose: dict[str, dict[str, str]] = {}
    purpose_providers: dict[str, str | None] = {}
    for item in _MODEL_PURPOSES:
        purpose_id: str = item["id"]  # type: ignore[assignment]
        merged_r = merged_routes.get(purpose_id)
        purpose_providers[purpose_id] = merged_r.get("provider_id") if merged_r else None
        active_by_purpose[purpose_id] = model_resolver.get_active_model_info(purpose=purpose_id)

    return APIResponse(
        data={
            "preferred_provider": model_resolver.get_preferred_provider(),
            "purpose_routes": merged_routes,
            "purpose_providers": purpose_providers,
            "active_by_purpose": active_by_purpose,
            "purposes": _MODEL_PURPOSES,
        }
    )


@router.post("/models/config", response_model=APIResponse)
async def save_model_config_endpoint(req: ModelConfigRequest):
    """保存模型配置到数据库，并立即重载模型客户端。"""
    from nini.agent.model_resolver import reload_model_resolver
    from nini.config_manager import save_model_config

    try:
        result = await save_model_config(
            provider=req.provider_id,
            api_key=req.api_key,
            model=req.model,
            base_url=req.base_url,
            priority=req.priority,
            is_active=req.is_active,
        )
        await reload_model_resolver()
        return APIResponse(data=result)
    except ValueError as e:
        return APIResponse(success=False, error=str(e))
    except Exception as e:
        return APIResponse(success=False, error=f"保存配置失败: {e}")


@router.post("/models/{provider_id}/test", response_model=APIResponse)
async def test_model_connection(provider_id: str):
    """测试指定模型提供商的连接。"""
    from nini.agent.model_resolver import (
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
    from nini.config_manager import get_effective_config

    client_map: dict[str, Any] = {
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

    if provider_id not in client_map:
        raise HTTPException(status_code=404, detail=f"未知的模型提供商: {provider_id}")

    cfg = await get_effective_config(provider_id)
    client_cls = client_map[provider_id]

    if provider_id == "ollama":
        client = client_cls(base_url=cfg.get("base_url"), model=cfg.get("model"))
    elif provider_id in {"openai", "moonshot", "kimi_coding", "zhipu", "minimax"}:
        client = client_cls(
            api_key=cfg.get("api_key"),
            base_url=cfg.get("base_url"),
            model=cfg.get("model"),
        )
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
        try:
            await client.aclose()
        except Exception as close_error:
            logger.warning("关闭模型测试客户端失败（%s）: %s", provider_id, close_error)


# ---- 活跃模型管理 ----


@router.get("/models/active", response_model=APIResponse)
async def get_active_model():
    """获取当前活跃的模型信息。"""
    from nini.agent.model_resolver import model_resolver

    info: dict[str, Any] = model_resolver.get_active_model_info(purpose="chat")
    info["preferred_provider"] = model_resolver.get_preferred_provider()
    info["purpose_preferred_providers"] = model_resolver.get_preferred_providers_by_purpose()
    info["purpose_routes"] = model_resolver.get_purpose_routes()
    return APIResponse(data=info)


@router.post("/models/preferred", response_model=APIResponse)
async def set_preferred_model(req: SetActiveModelRequest):
    """设置全局首选模型提供商。"""
    from nini.agent.model_resolver import model_resolver
    from nini.config_manager import set_default_provider

    provider_id = req.provider_id.strip() or None

    valid_ids = {c.provider_id for c in model_resolver._clients}
    if provider_id and provider_id not in valid_ids:
        return APIResponse(success=False, error=f"未知的模型提供商: {provider_id}")

    model_resolver.set_preferred_provider(provider_id)
    await set_default_provider(provider_id)

    info: dict[str, Any] = model_resolver.get_active_model_info()
    info["preferred_provider"] = model_resolver.get_preferred_provider()
    return APIResponse(data=info)


@router.get("/models/default", response_model=APIResponse)
async def get_default_model():
    """获取用户设置的默认模型提供商。"""
    from nini.config_manager import get_default_provider

    provider_id = await get_default_provider()
    return APIResponse(data={"default_provider": provider_id})


# ---- Token 统计 ----


@router.get("/sessions/{session_id}/token-usage", response_model=APIResponse)
async def get_session_token_usage(session_id: str):
    """获取会话的 token 消耗统计。"""
    from nini.utils.token_counter import get_tracker

    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    tracker = get_tracker(session_id)
    return APIResponse(data=tracker.to_dict())


# ---- 记忆文件 ----


@router.get("/sessions/{session_id}/memory-files", response_model=APIResponse)
async def list_memory_files(session_id: str):
    """列出会话记忆文件。"""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")

    session_dir = settings.sessions_dir / session_id
    files: list[dict[str, Any]] = []

    for filename in ("memory.jsonl", "knowledge.md", "meta.json"):
        fpath = session_dir / filename
        if fpath.exists() and fpath.is_file():
            stat = fpath.stat()
            info: dict[str, Any] = {
                "name": filename,
                "size": stat.st_size,
                "modified_at": stat.st_mtime,
            }
            if filename == "memory.jsonl":
                try:
                    info["line_count"] = sum(1 for _ in open(fpath, "r", encoding="utf-8"))
                except Exception:
                    info["line_count"] = 0
            files.append(info)

    archive_dir = session_dir / "archive"
    if archive_dir.exists() and archive_dir.is_dir():
        for apath in sorted(archive_dir.glob("*.json")):
            stat = apath.stat()
            files.append(
                {
                    "name": f"archive/{apath.name}",
                    "size": stat.st_size,
                    "modified_at": stat.st_mtime,
                }
            )

    session = session_manager.get_session(session_id)
    compression_info: dict[str, Any] = {}
    if session is not None:
        compression_info = {
            "compressed_rounds": getattr(session, "compressed_rounds", 0),
            "last_compressed_at": getattr(session, "last_compressed_at", None),
        }

    return APIResponse(
        data={
            "session_id": session_id,
            "files": files,
            "compression": compression_info,
        }
    )


@router.get("/sessions/{session_id}/memory-files/{filename:path}", response_model=APIResponse)
async def read_memory_file(session_id: str, filename: str):
    """读取记忆文件内容（前 200 行）。"""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")

    safe_name = Path(filename)
    if ".." in safe_name.parts:
        raise HTTPException(status_code=400, detail="无效的文件路径")

    session_dir = settings.sessions_dir / session_id
    fpath = session_dir / safe_name
    if not fpath.exists() or not fpath.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    try:
        fpath.resolve().relative_to(session_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的文件路径")

    lines: list[str] = []
    try:
        with open(fpath, "r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i >= 200:
                    break
                lines.append(line.rstrip("\n"))
    except Exception:
        raise HTTPException(status_code=500, detail="无法读取文件")

    return APIResponse(
        data={
            "session_id": session_id,
            "filename": filename,
            "content": "\n".join(lines),
            "total_lines_read": len(lines),
            "truncated": len(lines) >= 200,
        }
    )


# ---- 上下文大小 ----


@router.get("/sessions/{session_id}/context-size", response_model=APIResponse)
async def get_session_context_size(session_id: str):
    """获取当前会话上下文的 token 预估。"""
    from nini.utils.token_counter import count_messages_tokens

    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    session = session_manager.get_or_create(session_id)

    message_tokens = count_messages_tokens(session.messages)
    compressed_tokens = 0
    if getattr(session, "compressed_context", ""):
        from nini.utils.token_counter import count_tokens

        compressed_tokens = count_tokens(str(session.compressed_context))
    total_tokens = message_tokens + compressed_tokens
    threshold_tokens = int(settings.auto_compress_threshold_tokens)
    target_tokens = int(settings.auto_compress_target_tokens)
    remaining_until_compress = max(threshold_tokens - total_tokens, 0)

    return APIResponse(
        data={
            "session_id": session_id,
            "message_count": len(session.messages),
            "message_tokens": message_tokens,
            "compressed_context_tokens": compressed_tokens,
            "total_context_tokens": total_tokens,
            "auto_compress_enabled": bool(settings.auto_compress_enabled),
            "compress_threshold_tokens": threshold_tokens,
            "compress_target_tokens": target_tokens,
            "remaining_until_compress_tokens": remaining_until_compress,
        }
    )


# ---- 健康检查 ----


@router.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
