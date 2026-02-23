"""HTTP 端点（文件上传/下载、会话管理）。"""

from __future__ import annotations

import asyncio
import io
import logging
import mimetypes
import re
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
from nini.models.schemas import (
    APIResponse,
    DatasetInfo,
    FileRenameRequest,
    ModelConfigRequest,
    ModelPrioritiesRequest,
    ModelRoutingRequest,
    SaveWorkspaceTextRequest,
    SessionInfo,
    SessionUpdateRequest,
    SetActiveModelRequest,
    UploadResponse,
)
from nini.utils.chart_payload import normalize_chart_payload
from nini.utils.dataframe_io import read_dataframe
from nini.workspace import WorkspaceManager

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


# Excel 序列日期关键词（用于启发式检测）
_DATE_HINTS = {"日期", "时间", "时刻", "date", "time", "datetime", "timestamp"}


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
            f"filename=\"{ascii_fallback}\"; filename*=UTF-8''{utf8_encoded}"
        )
    return Response(
        content=path.read_bytes(),
        media_type=media_type,
        headers={"Content-Disposition": disposition},
    )


async def _convert_plotly_json_to_png(
    json_path: Path,
    session_id: str,
    width: int | None = None,
    height: int | None = None,
    scale: float | None = None,
) -> Response | None:
    """
    将 Plotly JSON 转换为高清 PNG 并返回响应。

    失败时返回 None，调用方应降级到返回原始 JSON。
    """
    import json
    import plotly.graph_objects as go
    from nini.utils.chart_fonts import apply_plotly_cjk_font_fallback

    # 使用配置值作为默认值
    width = width or settings.plotly_export_width
    height = height or settings.plotly_export_height
    scale = scale or settings.plotly_export_scale
    timeout = settings.plotly_export_timeout

    try:
        # 1. 读取 JSON
        chart_data = json.loads(json_path.read_text(encoding="utf-8"))

        # 2. 重建 Figure
        fig = go.Figure(chart_data)

        # 3. 应用中文字体
        apply_plotly_cjk_font_fallback(fig)

        # 4. 转换为 PNG（在线程池中执行，避免阻塞）
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        # 异步执行，使用配置的超时时间
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

        # 5. 读取并返回
        png_bytes = tmp_path.read_bytes()
        tmp_path.unlink()  # 清理临时文件

        # 构建文件名：移除 .plotly.json 后缀，添加 .png
        png_filename = json_path.stem.replace(".plotly", "") + ".png"

        return Response(
            content=png_bytes,
            media_type="image/png",
            headers={"Content-Disposition": f'attachment; filename="{png_filename}"'},
        )

    except asyncio.TimeoutError:
        logger.warning(f"Plotly PNG 转换超时: {json_path.name}")
        return None
    except Exception as e:
        logger.warning(f"Plotly PNG 转换失败: {json_path.name}, 错误: {e}")
        return None


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
        messages = mem.load_messages(resolve_refs=True)
        if not messages and not session_manager.session_exists(session_id):
            raise HTTPException(status_code=404, detail="会话不存在或无消息记录")

    # 过滤掉内部字段（如 _ts），只返回前端需要的字段
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
    """获取能力目录（Function Tool + Markdown Skill）。"""
    from nini.api.websocket import get_skill_registry

    registry = get_skill_registry()
    if registry is None:
        return APIResponse(data={"skills": []})

    # 每次请求都刷新 Markdown Skills 快照，确保前端看到最新状态
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
        df = read_dataframe(save_path, ext)
    except Exception as e:
        save_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"无法解析文件: {e}")

    # Excel 序列日期自动转换：检测 object 列中混入的 Excel 序列日期数值
    if ext in ("xlsx", "xls"):
        df = _fix_excel_serial_dates(df)

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
async def download_artifact(
    session_id: str,
    filename: str,
    inline: bool = False,
    raw: bool = False,
):
    """下载会话产物（.plotly.json 默认自动转 PNG；raw=1 时返回原始 JSON）。"""
    # 兼容已编码/双重编码文件名（如 %25E8...），统一解码一次后再做安全裁剪。
    safe_name = Path(unquote(filename)).name
    artifact_path = settings.sessions_dir / session_id / "workspace" / "artifacts" / safe_name
    if not artifact_path.exists():
        # 兼容旧目录
        artifact_path = settings.sessions_dir / session_id / "artifacts" / safe_name
    if not artifact_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    # 检测是否为 Plotly JSON
    if safe_name.lower().endswith(".plotly.json") and not raw:
        logger.info(f"检测到 Plotly JSON，尝试转换为 PNG: {safe_name}")
        png_response = await _convert_plotly_json_to_png(
            artifact_path,
            session_id=session_id,
            width=1400,
            height=900,
            scale=2.0,
        )
        if png_response:
            logger.info(f"Plotly PNG 转换成功: {safe_name}")
            return png_response
        else:
            logger.warning(f"Plotly PNG 转换失败，降级返回原始 JSON: {safe_name}")
            # 降级：返回原始 JSON

    # 普通文件下载
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


def _extract_image_urls(md_content: str, session_id: str) -> list[dict[str, str]]:
    """从 Markdown 提取图片 URL 及本地路径。

    Returns:
        [{"url": "/api/artifacts/...", "path": Path(...), "filename": "...", "alt": "..."}]
    """
    pattern = r"!\[([^\]]*)\]\((/api/artifacts/" + re.escape(session_id) + r"/[^)]+)\)"
    matches = re.findall(pattern, md_content)

    results = []
    for alt_text, url in matches:
        # 解析 URL 获取文件名
        filename = unquote(url.split("/")[-1])
        artifact_path = settings.sessions_dir / session_id / "workspace" / "artifacts" / filename

        if artifact_path.exists():
            results.append(
                {
                    "url": url,
                    "path": str(artifact_path),
                    "filename": filename,
                    "alt": alt_text,
                }
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
    """将 Markdown 和图片打包为 ZIP。

    ZIP 结构:
        report.md          # 修改后的 Markdown（图片路径改为相对路径）
        images/
            chart1.png
            chart2.plotly.json  (仅在 PNG 转换失败时)

    对于 .plotly.json 文件，尝试转换为 PNG；
    成功则打包 PNG 并更新 Markdown 路径，失败则保留原始 JSON。
    """
    buf = io.BytesIO()
    md_content = md_path.read_text(encoding="utf-8")

    # 修改 Markdown 中的图片路径为相对路径，并处理 plotly.json → PNG
    updated_md = md_content
    png_cache: dict[str, bytes] = {}  # filename → png bytes

    for img in image_urls:
        old_url = img["url"]
        filename = img["filename"]

        if filename.lower().endswith(".plotly.json"):
            img_path = Path(img["path"])
            png_data = _plotly_json_to_png_bytes(img_path) if img_path.exists() else None
            if png_data:
                # 成功：替换为 PNG
                png_name = filename[: -len(".plotly.json")] + ".png"
                png_cache[png_name] = png_data
                new_url = f"images/{png_name}"
            else:
                # 失败：保留原始 JSON
                new_url = f"images/{filename}"
        else:
            new_url = f"images/{filename}"

        updated_md = updated_md.replace(f"]({old_url})", f"]({new_url})")

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # 添加修改后的 Markdown
        zf.writestr(md_path.name, updated_md.encode("utf-8"))

        # 添加转换后的 PNG 文件
        for png_name, png_data in png_cache.items():
            zf.writestr(f"images/{png_name}", png_data)

        # 添加原始图片文件（跳过已转换为 PNG 的 plotly.json）
        converted_plotly_names = set()
        for png_name in png_cache:
            # 反推原始 plotly.json 名称
            base = png_name[: -len(".png")]
            converted_plotly_names.add(f"{base}.plotly.json")

        for img in image_urls:
            filename = img["filename"]
            if filename in converted_plotly_names:
                continue  # 已转为 PNG，跳过
            img_path = Path(img["path"])
            if img_path.exists():
                zf.write(img_path, f"images/{filename}")

    return buf.getvalue()


@router.get("/workspace/{session_id}/artifacts/{filename}/bundle")
async def download_markdown_with_images(
    session_id: str,
    filename: str,
):
    """下载 Markdown 文件并自动打包相关图片。

    如果文件是 .md 且包含图片引用，返回 ZIP 打包（markdown + images）。
    否则返回原文件。
    """
    safe_name = Path(unquote(filename)).name
    md_path = settings.sessions_dir / session_id / "workspace" / "artifacts" / safe_name

    # 也支持从 notes 下载
    if not md_path.exists():
        md_path = settings.sessions_dir / session_id / "workspace" / "notes" / safe_name

    if not md_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    if not safe_name.endswith(".md"):
        # 非 Markdown 文件直接返回
        return _build_download_response(md_path, safe_name)

    # 解析 Markdown 中的图片引用
    md_content = md_path.read_text(encoding="utf-8")
    image_urls = _extract_image_urls(md_content, session_id)

    if not image_urls:
        # 无图片引用，直接返回原文件
        return _build_download_response(md_path, safe_name)

    # ZIP 打包模式
    logger.info(f"检测到 {len(image_urls)} 个图片引用，打包下载: {safe_name}")
    zip_bytes = _bundle_markdown_with_images(md_path, image_urls, session_id)
    zip_filename = safe_name.replace(".md", "_bundle.zip")

    # 构造文件名编码（复用 _build_download_response 的逻辑）
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
    """批量导出会话的所有产物为 ZIP 文件。

    包含：
    - artifacts/ 目录中的所有分析产物（图表、报告等）
    - uploads/ 目录中的上传文件
    - notes/ 目录中的笔记文件
    - memory.jsonl 会话记忆（可选）
    """
    session_dir = settings.sessions_dir / session_id
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail="会话不存在")

    workspace_dir = session_dir / "workspace"

    # 创建内存中的 ZIP 文件
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        file_count = 0

        # 1. 添加 artifacts（产物）
        artifacts_dir = workspace_dir / "artifacts"
        if artifacts_dir.exists():
            for file_path in artifacts_dir.rglob("*"):
                if file_path.is_file():
                    # 跳过内部引用文件
                    if "memory-payloads" in str(file_path):
                        continue
                    arcname = f"artifacts/{file_path.relative_to(artifacts_dir)}"
                    zip_file.write(file_path, arcname)
                    file_count += 1

        # 2. 添加 uploads（上传文件）
        uploads_dir = workspace_dir / "uploads"
        if uploads_dir.exists():
            for file_path in uploads_dir.rglob("*"):
                if file_path.is_file():
                    arcname = f"uploads/{file_path.relative_to(uploads_dir)}"
                    zip_file.write(file_path, arcname)
                    file_count += 1

        # 3. 添加 notes（笔记）
        notes_dir = workspace_dir / "notes"
        if notes_dir.exists():
            for file_path in notes_dir.rglob("*"):
                if file_path.is_file():
                    arcname = f"notes/{file_path.relative_to(notes_dir)}"
                    zip_file.write(file_path, arcname)
                    file_count += 1

        # 4. 添加 memory.jsonl（可选，格式化版本）
        memory_file = session_dir / "memory.jsonl"
        if memory_file.exists():
            zip_file.write(memory_file, "memory.jsonl")
            file_count += 1

        # 5. 添加元数据文件
        from nini.agent.session import session_manager

        session = session_manager.get_session(session_id)
        if session:
            metadata = {
                "session_id": session_id,
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "file_count": file_count,
                "datasets": list(session.datasets.keys()),
            }
            import json

            zip_file.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2))

    # 准备下载响应
    zip_buffer.seek(0)
    zip_bytes = zip_buffer.read()

    # 生成文件名
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"nini_session_{session_id[:8]}_{timestamp}.zip"

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
        "key_field": None,  # Ollama 不需要 API Key
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

    # 从 DB 加载用户保存的配置
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
        set_default_provider,
        set_model_purpose_routes,
        VALID_MODEL_PURPOSES,
        VALID_PROVIDERS,
    )

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
        if provider_id and provider_id not in VALID_PROVIDERS:
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
        if provider_id and provider_id not in VALID_PROVIDERS:
            return APIResponse(success=False, error=f"未知的模型提供商: {provider_id}")
        updates[purpose] = {
            "provider_id": provider_id,
            "model": model,
            "base_url": base_url,
        }

    # 更新全局首选（为空表示清除）
    if update_global_preferred:
        await set_default_provider(preferred_provider)
        model_resolver.set_preferred_provider(preferred_provider)

    # 更新用途路由（增量）
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
    from nini.config_manager import save_model_config
    from nini.agent.model_resolver import reload_model_resolver

    try:
        result = await save_model_config(
            provider=req.provider_id,
            api_key=req.api_key,
            model=req.model,
            base_url=req.base_url,
            priority=req.priority,
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
        MiniMaxClient,
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

    # 获取有效配置（DB 优先，.env 兜底）
    cfg = await get_effective_config(provider_id)
    client_cls = client_map[provider_id]

    # 使用有效配置创建客户端实例
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

    info: dict[str, Any] = model_resolver.get_active_model_info(purpose="chat")
    info["preferred_provider"] = model_resolver.get_preferred_provider()
    info["purpose_preferred_providers"] = model_resolver.get_preferred_providers_by_purpose()
    info["purpose_routes"] = model_resolver.get_purpose_routes()
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


# ---- Token 统计 ----


@router.get("/sessions/{session_id}/token-usage", response_model=APIResponse)
async def get_session_token_usage(session_id: str):
    """获取会话的 token 消耗统计。"""
    from nini.utils.token_counter import get_tracker

    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    tracker = get_tracker(session_id)
    return APIResponse(data=tracker.to_dict())


@router.get("/sessions/{session_id}/memory-files", response_model=APIResponse)
async def list_memory_files(session_id: str):
    """列出会话记忆文件（memory.jsonl、knowledge.md、meta.json、archive/*.json）。"""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")

    session_dir = settings.sessions_dir / session_id
    files: list[dict[str, Any]] = []

    # 检查标准记忆文件
    for filename in ("memory.jsonl", "knowledge.md", "meta.json"):
        fpath = session_dir / filename
        if fpath.exists() and fpath.is_file():
            stat = fpath.stat()
            info: dict[str, Any] = {
                "name": filename,
                "size": stat.st_size,
                "modified_at": stat.st_mtime,
            }
            # 对 memory.jsonl 统计行数
            if filename == "memory.jsonl":
                try:
                    info["line_count"] = sum(1 for _ in open(fpath, "r", encoding="utf-8"))
                except Exception:
                    info["line_count"] = 0
            files.append(info)

    # 检查 archive 目录
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

    # 获取压缩状态
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


@router.get("/sessions/{session_id}/memory/formatted", response_model=APIResponse)
async def export_formatted_memory(session_id: str):
    """
    导出格式化的会话记忆。

    返回格式化的 JSON，包含会话消息摘要和统计信息。
    """
    from nini.memory.conversation import ConversationMemory, format_memory_entries

    session = session_manager.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 加载记忆（不解析引用，节省内存）
    mem = ConversationMemory(session_id)
    entries = mem.load_messages(resolve_refs=False)

    # 格式化
    formatted = format_memory_entries(entries)

    # 统计信息
    stats = {
        "total_entries": len(entries),
        "user_messages": sum(1 for e in entries if e.get("role") == "user"),
        "assistant_messages": sum(1 for e in entries if e.get("role") == "assistant"),
        "tool_results": sum(1 for e in entries if e.get("role") == "tool"),
        "has_attachments": sum(1 for f in formatted if f.get("has_attachments")),
    }

    return APIResponse(
        success=True,
        data={
            "message": "记忆导出成功",
            "session_id": session_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "statistics": stats,
            "entries": formatted,
        },
    )


@router.get("/sessions/{session_id}/memory-files/{filename:path}", response_model=APIResponse)
async def read_memory_file(session_id: str, filename: str):
    """读取记忆文件内容（前 200 行）。"""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")

    # 安全检查：防止路径遍历
    safe_name = Path(filename)
    if ".." in safe_name.parts:
        raise HTTPException(status_code=400, detail="无效的文件路径")

    session_dir = settings.sessions_dir / session_id
    fpath = session_dir / safe_name
    if not fpath.exists() or not fpath.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    # 确保文件在会话目录内
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


@router.get("/sessions/{session_id}/context-size", response_model=APIResponse)
async def get_session_context_size(session_id: str):
    """获取当前会话上下文的 token 预估。"""
    from nini.utils.token_counter import count_messages_tokens

    # 使用 get_or_create 确保只存在于磁盘上的会话也能被加载
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
