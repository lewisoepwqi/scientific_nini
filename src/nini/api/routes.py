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
    DraftGenerateRequest,
    DraftGenerateResponse,
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
from nini.memory.conversation import ConversationMemory, canonicalize_message_entries
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


def _serialize_history_message(msg: dict[str, Any]) -> dict[str, Any]:
    """序列化会话消息历史，返回统一对外契约。"""
    chart_data = msg.get("chart_data")
    normalized_chart_data = normalize_chart_payload(chart_data)
    item = {
        "role": msg.get("role", ""),
        "content": msg.get("content", ""),
        "_ts": msg.get("_ts"),
        "message_id": msg.get("message_id"),
        "turn_id": msg.get("turn_id"),
        "event_type": msg.get("event_type"),
        "operation": msg.get("operation"),
        "tool_calls": msg.get("tool_calls"),
        "tool_call_id": msg.get("tool_call_id"),
        "tool_name": msg.get("tool_name"),
        "status": msg.get("status"),
        "intent": msg.get("intent"),
        "execution_id": msg.get("execution_id"),
        "reasoning_id": msg.get("reasoning_id"),
        "reasoning_live": msg.get("reasoning_live"),
        "reasoning_type": msg.get("reasoning_type"),
        "key_decisions": msg.get("key_decisions"),
        "confidence_score": msg.get("confidence_score"),
        "chart_data": normalized_chart_data if normalized_chart_data else chart_data,
        "data_preview": msg.get("data_preview"),
        "artifacts": msg.get("artifacts"),
        "images": msg.get("images"),
    }
    return item


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
            f'filename="{ascii_fallback}"; '
            f"filename*=UTF-8''{utf8_encoded}"
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


# ---- 会话消息历史 ----


@router.get("/sessions/{session_id}/messages", response_model=APIResponse)
async def get_session_messages(session_id: str):
    """获取指定会话的消息历史。"""
    session = session_manager.get_session(session_id)
    if session is not None:
        messages = canonicalize_message_entries(session.messages)
    else:
        mem = ConversationMemory(session_id)
        messages = mem.load_messages(resolve_refs=True)
        if not messages and not session_manager.session_exists(session_id):
            raise HTTPException(status_code=404, detail="会话不存在或无消息记录")

    cleaned = [_serialize_history_message(msg) for msg in messages]
    return APIResponse(data={"session_id": session_id, "messages": cleaned})


# ---- 工作空间 ----


def _ensure_workspace_session_exists(session_id: str) -> None:
    """校验会话存在，避免新版工作空间接口访问悬空路径。"""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")


def _resolve_file_path(session_id: str, file_path: str) -> Path | None:
    """按优先级在多个位置查找文件。

    查找顺序（优先级从高到低）：
    1. workspace/{file_path} - 直接路径（支持子目录）
    2. workspace/artifacts/{filename} - 产物目录
    3. workspace/notes/{filename} - 笔记目录
    4. workspace/uploads/{filename} - 上传目录
    5. artifacts/{filename} - 旧版产物目录（兼容）

    Args:
        session_id: 会话 ID
        file_path: 文件路径（可能包含子目录）

    Returns:
        找到的 Path 对象，如果未找到则返回 None
    """
    session_dir = settings.sessions_dir / session_id
    workspace_dir = session_dir / "workspace"
    filename = Path(file_path).name

    # 1. 直接路径（支持子目录）
    direct_path = workspace_dir / file_path
    if direct_path.exists() and direct_path.is_file():
        return direct_path

    # 2. artifacts 子目录
    artifact_path = workspace_dir / "artifacts" / filename
    if artifact_path.exists() and artifact_path.is_file():
        return artifact_path

    # 3. notes 子目录
    notes_path = workspace_dir / "notes" / filename
    if notes_path.exists() and notes_path.is_file():
        return notes_path

    # 4. uploads 子目录
    uploads_path = workspace_dir / "uploads" / filename
    if uploads_path.exists() and uploads_path.is_file():
        return uploads_path

    # 5. 旧版产物目录（兼容）
    legacy_path = session_dir / "artifacts" / filename
    if legacy_path.exists() and legacy_path.is_file():
        return legacy_path

    return None


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


# 图片文件扩展名集合，用于直接返回文件流
_IMAGE_EXTENSIONS = frozenset([".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico"])

# 二进制文件扩展名集合，用于直接返回文件流（不尝试读取为文本）
_BINARY_EXTENSIONS = frozenset(
    [
        # 文档格式
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        # 压缩格式
        ".zip",
        ".tar",
        ".gz",
        ".bz2",
        ".xz",
        ".rar",
        ".7z",
        # 其他二进制格式
        ".bin",
        ".exe",
        ".dll",
        ".so",
        ".dylib",
    ]
)


def _is_image_file(filename: str) -> bool:
    """检查文件名是否为图片文件（不区分大小写）。"""
    name_lower = filename.lower()
    return any(name_lower.endswith(ext) for ext in _IMAGE_EXTENSIONS)


def _is_binary_file(filename: str) -> bool:
    """检查文件名是否为二进制文件（不区分大小写）。"""
    name_lower = filename.lower()
    return any(name_lower.endswith(ext) for ext in _BINARY_EXTENSIONS)


@router.get("/workspace/{session_id}/files/{file_path:path}")
async def get_workspace_file(
    session_id: str,
    file_path: str,
    inline: bool = False,
    raw: bool = False,
    bundle: bool = False,
    download: bool = False,
):
    """获取或下载工作空间文件。

    默认返回文件内容 JSON。当 download=1 时返回文件下载。
    图片文件（.png/.jpg/.jpeg/.gif/.webp/.svg/.bmp/.ico）默认直接返回文件流。
    二进制文件（.pdf/.doc/.docx/.xls/.xlsx 等）默认直接返回文件流。

    参数:
        inline: 是否内联显示（而非下载）
        raw: plotly.json 是否返回原始 JSON（而非转 PNG）
        bundle: Markdown 文件是否打包关联图片为 ZIP
        download: 是否直接下载文件（而非返回内容 JSON）
    """
    _ensure_workspace_session_exists(session_id)

    # 使用多路径查找定位文件
    target_path = _resolve_file_path(session_id, file_path)
    if target_path is None:
        raise HTTPException(status_code=404, detail=f"文件不存在: {file_path}")

    filename = target_path.name

    # 图片文件默认直接返回文件流（支持 markdown 内嵌图片显示）
    if _is_image_file(filename):
        return _build_download_response(target_path, filename, inline=True)

    # 二进制文件（PDF、Office 文档等）默认直接返回文件流
    # 注意：尊重 inline 参数，用于 PDF 预览（inline=True）vs 下载（inline=False）
    if _is_binary_file(filename):
        return _build_download_response(target_path, filename, inline=inline)

    # 如果不下载，返回文件内容 JSON（向后兼容）
    if not download and not bundle:
        workspace = WorkspaceManager(session_id)
        try:
            content = workspace.read_file(file_path)
            return APIResponse(success=True, data={"path": file_path, "content": content})
        except (FileNotFoundError, ValueError, IsADirectoryError):
            # 如果通过 workspace manager 读取失败，尝试直接读取
            try:
                content = target_path.read_text(encoding="utf-8")
                return APIResponse(success=True, data={"path": file_path, "content": content})
            except UnicodeDecodeError:
                # 二进制文件，返回下载
                return _build_download_response(target_path, filename, inline=inline)

    # Plotly JSON 自动转 PNG
    if filename.lower().endswith(".plotly.json") and not raw:
        png_response = await _convert_plotly_json_to_png(
            target_path, session_id=session_id, width=1400, height=900, scale=2.0
        )
        if png_response:
            return png_response

    # Markdown 打包下载
    if bundle and filename.lower().endswith(".md"):
        md_content = target_path.read_text(encoding="utf-8")
        image_urls = _extract_image_urls(md_content, session_id)

        if not image_urls:
            return _build_download_response(target_path, filename, inline=inline)

        zip_bytes = _bundle_markdown_with_images(target_path, image_urls, session_id)
        zip_filename = filename.replace(".md", "_bundle.zip")

        try:
            zip_filename.encode("latin-1")
            disposition = f'attachment; filename="{zip_filename}"'
        except UnicodeEncodeError:
            ascii_fallback = zip_filename.encode("ascii", errors="replace").decode("ascii")
            utf8_encoded = quote(zip_filename, safe="")
            disposition = (
                f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{utf8_encoded}"
            )

        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={"Content-Disposition": disposition},
        )

    return _build_download_response(target_path, filename, inline=inline)


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
async def create_markdown_skill_directory(skill_name: str, request: MarkdownSkillDirCreateRequest):
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
    """从 Markdown 提取图片 URL 及本地路径。

    支持两种格式的图片 URL：
    1. 旧格式: /api/artifacts/{session_id}/filename
    2. 新格式: /api/workspace/{session_id}/files/artifacts/filename
    """
    results = []

    # 匹配旧格式: /api/artifacts/{session_id}/filename
    old_pattern = r"!\[([^\]]*)\]\((/api/artifacts/" + re.escape(session_id) + r"/[^)]+)\)"
    old_matches = re.findall(old_pattern, md_content)

    for alt_text, url in old_matches:
        filename = unquote(url.split("/")[-1])
        artifact_path = settings.sessions_dir / session_id / "workspace" / "artifacts" / filename
        if artifact_path.exists():
            results.append(
                {"url": url, "path": str(artifact_path), "filename": filename, "alt": alt_text}
            )

    # 匹配新格式: /api/workspace/{session_id}/files/artifacts/filename
    new_pattern = r"!\[([^\]]*)\]\((/api/workspace/" + re.escape(session_id) + r"/files/[^)]+)\)"
    new_matches = re.findall(new_pattern, md_content)

    for alt_text, url in new_matches:
        # 从 URL 中提取文件路径（如 artifacts/filename 或 notes/filename）
        path_part = url.split(f"/api/workspace/{session_id}/files/")[-1]
        if not path_part:
            continue

        filename = unquote(path_part.split("/")[-1])
        # 尝试在 workspace 目录中定位文件
        workspace_dir = settings.sessions_dir / session_id / "workspace"

        # 首先尝试作为完整路径
        full_path = workspace_dir / path_part
        if full_path.exists() and full_path.is_file():
            results.append(
                {"url": url, "path": str(full_path), "filename": filename, "alt": alt_text}
            )
            continue

        # 然后尝试在 artifacts 目录中查找
        artifact_path = workspace_dir / "artifacts" / filename
        if artifact_path.exists() and artifact_path.is_file():
            results.append(
                {"url": url, "path": str(artifact_path), "filename": filename, "alt": alt_text}
            )
            continue

        # 最后尝试在 notes 目录中查找
        notes_path = workspace_dir / "notes" / filename
        if notes_path.exists() and notes_path.is_file():
            results.append(
                {"url": url, "path": str(notes_path), "filename": filename, "alt": alt_text}
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
    """下载会话产物（.plotly.json 默认自动转 PNG；raw=1 时返回原始 JSON）。

    已废弃：请使用 GET /api/workspace/{session_id}/files/{filename}
    """
    # 记录废弃警告
    logger.warning(
        "Deprecated API used: /api/artifacts/%s/%s. "
        "Please migrate to /api/workspace/{sid}/files/{path}",
        session_id,
        filename,
    )

    safe_name = Path(unquote(filename)).name
    workspace_path = settings.sessions_dir / session_id / "workspace"
    artifact_path = workspace_path / "artifacts" / safe_name
    if not artifact_path.exists():
        artifact_path = settings.sessions_dir / session_id / "artifacts" / safe_name
    # edit_file 等工具创建的文件直接在工作区根目录
    if not artifact_path.exists():
        artifact_path = workspace_path / safe_name
    if not artifact_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    if safe_name.lower().endswith(".plotly.json") and not raw:
        png_response = await _convert_plotly_json_to_png(
            artifact_path, session_id=session_id, width=1400, height=900, scale=2.0
        )
        if png_response:
            # 添加废弃响应头
            png_response.headers["Deprecation"] = "true"
            png_response.headers["Sunset"] = "2025-06-01"
            return png_response

    response = _build_download_response(artifact_path, safe_name, inline=inline)
    # 添加废弃响应头
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2025-06-01"
    return response


@router.get("/workspace/{session_id}/uploads/{filename}")
async def download_workspace_upload(session_id: str, filename: str, inline: bool = False):
    """下载会话工作空间中的上传文件。

    已废弃：请使用 GET /api/workspace/{session_id}/files/uploads/{filename}
    """
    logger.warning(
        "Deprecated API used: /api/workspace/%s/uploads/%s. "
        "Please migrate to /api/workspace/{sid}/files/{path}",
        session_id,
        filename,
    )

    safe_name = Path(filename).name
    path = settings.sessions_dir / session_id / "workspace" / "uploads" / safe_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    response = _build_download_response(path, safe_name, inline=inline)
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2025-06-01"
    return response


@router.get("/workspace/{session_id}/notes/{filename}")
async def download_workspace_note(session_id: str, filename: str, inline: bool = False):
    """下载会话工作空间中的文本文件。

    已废弃：请使用 GET /api/workspace/{session_id}/files/notes/{filename}
    """
    logger.warning(
        "Deprecated API used: /api/workspace/%s/notes/%s. "
        "Please migrate to /api/workspace/{sid}/files/{path}",
        session_id,
        filename,
    )

    safe_name = Path(filename).name
    path = settings.sessions_dir / session_id / "workspace" / "notes" / safe_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    response = _build_download_response(path, safe_name, inline=inline)
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2025-06-01"
    return response


@router.get("/workspace/{session_id}/artifacts/{filename}/bundle")
async def download_markdown_with_images(session_id: str, filename: str):
    """下载 Markdown 文件并自动打包相关图片。

    已废弃：请使用 GET /api/workspace/{session_id}/files/{filename}?bundle=1
    """
    logger.warning(
        "Deprecated API used: /api/workspace/%s/artifacts/%s/bundle. "
        "Please migrate to /api/workspace/{sid}/files/{path}?bundle=1",
        session_id,
        filename,
    )

    safe_name = Path(unquote(filename)).name
    workspace_path = settings.sessions_dir / session_id / "workspace"
    md_path = workspace_path / "artifacts" / safe_name

    if not md_path.exists():
        md_path = workspace_path / "notes" / safe_name
    # edit_file 等工具创建的文件直接在工作区根目录
    if not md_path.exists():
        md_path = workspace_path / safe_name
    if not md_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    if not safe_name.endswith(".md"):
        response = _build_download_response(md_path, safe_name)
        response.headers["Deprecation"] = "true"
        response.headers["Sunset"] = "2025-06-01"
        return response

    md_content = md_path.read_text(encoding="utf-8")
    image_urls = _extract_image_urls(md_content, session_id)

    if not image_urls:
        response = _build_download_response(md_path, safe_name)
        response.headers["Deprecation"] = "true"
        response.headers["Sunset"] = "2025-06-01"
        return response

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
        headers={
            "Content-Disposition": disposition,
            "Deprecation": "true",
            "Sunset": "2025-06-01",
        },
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


# ---- 健康检查 ----


@router.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


# ---- 包含新拆分的路由模块（渐进式重构） ----
# 注意：新路由模块使用相同的前缀，但由于路由不重叠，可以共存
# 后续迭代将完全迁移到新的路由模块

_route_import_errors: list[str] = []

try:
    from .session_routes import router as session_router

    router.include_router(session_router)
except Exception as _e:
    _route_import_errors.append(f"session_routes: {_e}")

try:
    from .workspace_routes import router as workspace_router

    router.include_router(workspace_router)
except Exception as _e:
    _route_import_errors.append(f"workspace_routes: {_e}")

try:
    from .skill_routes import router as skill_router

    router.include_router(skill_router)
except Exception as _e:
    _route_import_errors.append(f"skill_routes: {_e}")

try:
    from .profile_routes import router as profile_router

    router.include_router(profile_router)
except Exception as _e:
    _route_import_errors.append(f"profile_routes: {_e}")

try:
    from .models_routes import router as models_router

    router.include_router(models_router)
except Exception as _e:
    _route_import_errors.append(f"models_routes: {_e}")

try:
    from .intent_routes import router as intent_router

    router.include_router(intent_router)
except Exception as _e:
    _route_import_errors.append(f"intent_routes: {_e}")

if _route_import_errors:
    logger.warning("部分路由模块加载失败: %s", "; ".join(_route_import_errors))
