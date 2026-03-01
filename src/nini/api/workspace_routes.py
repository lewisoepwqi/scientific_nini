"""工作区和数据集路由。"""

from __future__ import annotations

import io
import shutil
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response

from nini.agent.session import session_manager
from nini.config import settings
from nini.models.schemas import APIResponse, FileRenameRequest, SaveWorkspaceTextRequest
from nini.utils.dataframe_io import read_dataframe
from nini.workspace import WorkspaceManager

router = APIRouter()


def _fix_excel_serial_dates(df: pd.DataFrame) -> pd.DataFrame:
    """修复 Excel 序列化日期（如 44561 → 2022-01-01）。"""
    import re

    date_pattern = re.compile(r"^\d{5,6}$")

    for col in df.columns:
        if df[col].dtype == object:
            sample = df[col].dropna().head(10).astype(str)
            if sample.str.match(date_pattern).any():
                try:
                    df[col] = pd.to_datetime(df[col].astype(float), origin="1899-12-30", unit="D")
                except Exception:
                    pass
    return df


def _build_download_response(path: Path, filename: str, *, inline: bool = False) -> Response:
    """构建文件下载响应。"""
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    mime, _ = mimetypes.guess_type(str(path))
    mime = mime or "application/octet-stream"

    content = path.read_bytes()
    headers: dict[str, str] = {
        "Content-Type": mime,
    }

    disposition = "inline" if inline else "attachment"
    encoded = quote(filename)
    headers["Content-Disposition"] = f"{disposition}; filename*=UTF-8''{encoded}"

    return Response(content=content, headers=headers)


@router.post("/upload", response_model=APIResponse)
async def upload_file(
    session_id: str = File(...),
    file: UploadFile = File(...),
) -> APIResponse:
    """上传数据文件并创建数据集。"""
    session = session_manager.get_or_create(session_id)

    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    ext = Path(file.filename).suffix.lower()
    if ext.lstrip(".") not in settings.allowed_extensions_list:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext}")

    content = await file.read()
    if len(content) > settings.max_upload_size:
        raise HTTPException(status_code=413, detail="文件过大")

    dataset_id = str(uuid.uuid4())
    dataset_dir = settings.upload_dir / session_id
    dataset_dir.mkdir(parents=True, exist_ok=True)
    file_path = dataset_dir / f"{dataset_id}{ext}"

    with open(file_path, "wb") as f:
        f.write(content)

    try:
        df = read_dataframe(file_path)
        df = _fix_excel_serial_dates(df)
    except Exception as e:
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"无法解析文件: {e}") from e

    dataset_name = Path(file.filename).stem
    session.datasets[dataset_name] = df

    info = {
        "id": dataset_id,
        "name": dataset_name,
        "file_type": ext.lstrip("."),
        "file_size": len(content),
        "row_count": len(df),
        "column_count": len(df.columns),
        "loaded": True,
    }

    return APIResponse(success=True, data=info)


@router.get("/datasets/{session_id}", response_model=APIResponse)
async def list_datasets(session_id: str):
    """列出会话的所有数据集。"""
    session = session_manager.get_or_create(session_id)

    datasets = []
    for name, df in session.datasets.items():
        datasets.append({
            "name": name,
            "row_count": len(df),
            "column_count": len(df.columns),
            "columns": df.columns.tolist(),
        })

    return APIResponse(success=True, data=datasets)


@router.post("/datasets/{session_id}/{dataset_id}/load", response_model=APIResponse)
async def load_dataset_into_session(session_id: str, dataset_id: str):
    """加载数据集到会话。"""
    session = session_manager.get_or_create(session_id)

    dataset_dir = settings.upload_dir / session_id
    file_path = dataset_dir / dataset_id

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="数据集文件不存在")

    try:
        df = read_dataframe(file_path)
        df = _fix_excel_serial_dates(df)
        dataset_name = file_path.stem
        session.datasets[dataset_name] = df

        return APIResponse(
            success=True,
            data={
                "name": dataset_name,
                "row_count": len(df),
                "column_count": len(df.columns),
            },
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"无法加载数据集: {e}") from e


@router.get("/datasets/{session_id}/{dataset_name}")
async def get_dataset(session_id: str, dataset_name: str, limit: int = 100):
    """获取数据集内容。"""
    session = session_manager.get_or_create(session_id)

    if dataset_name not in session.datasets:
        raise HTTPException(status_code=404, detail="数据集不存在")

    df = session.datasets[dataset_name]
    preview_df = df.head(limit)

    return APIResponse(
        success=True,
        data={
            "name": dataset_name,
            "columns": df.columns.tolist(),
            "rows": preview_df.to_dict("records"),
            "total_rows": len(df),
            "returned_rows": len(preview_df),
        },
    )


@router.get("/datasets/{session_id}/{dataset_name}/preview")
async def get_dataset_preview(session_id: str, dataset_name: str):
    """获取数据集预览（前 5 行）。"""
    session = session_manager.get_or_create(session_id)

    if dataset_name not in session.datasets:
        raise HTTPException(status_code=404, detail="数据集不存在")

    df = session.datasets[dataset_name]
    preview_df = df.head(5)

    return APIResponse(
        success=True,
        data={
            "name": dataset_name,
            "columns": df.columns.tolist(),
            "preview": preview_df.to_dict("records"),
            "total_rows": len(df),
        },
    )


@router.delete("/datasets/{session_id}/{dataset_name}")
async def delete_dataset(session_id: str, dataset_name: str):
    """删除数据集。"""
    session = session_manager.get_or_create(session_id)

    if dataset_name in session.datasets:
        del session.datasets[dataset_name]

    return APIResponse(success=True)


@router.get("/datasets/{session_id}/{dataset_name}/export")
async def export_dataset(
    session_id: str,
    dataset_name: str,
    format: str = "csv",
):
    """导出数据集。"""
    from fastapi.responses import StreamingResponse

    session = session_manager.get_or_create(session_id)

    if dataset_name not in session.datasets:
        raise HTTPException(status_code=404, detail="数据集不存在")

    df = session.datasets[dataset_name]

    if format == "csv":
        output = io.StringIO()
        df.to_csv(output, index=False)
        content = output.getvalue().encode("utf-8")
        media_type = "text/csv"
        ext = "csv"
    elif format == "json":
        content = df.to_json(orient="records").encode("utf-8")
        media_type = "application/json"
        ext = "json"
    elif format == "xlsx":
        output = io.BytesIO()
        df.to_excel(output, index=False)
        content = output.getvalue()
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ext = "xlsx"
    else:
        raise HTTPException(status_code=400, detail=f"不支持的格式: {format}")

    return StreamingResponse(
        io.BytesIO(content),
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename={dataset_name}.{ext}"
        },
    )


@router.get("/workspace/{session_id}/tree")
async def get_workspace_tree(session_id: str):
    """获取工作区文件树。"""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")

    manager = WorkspaceManager(session_id)
    tree = manager.get_file_tree()

    return APIResponse(success=True, data=tree)


@router.get("/workspace/{session_id}/files")
async def list_workspace_files(session_id: str, q: str | None = None):
    """列出工作区文件。"""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")

    manager = WorkspaceManager(session_id)
    if q:
        files = manager.search_files_with_paths(query=q)
    else:
        files = manager.list_workspace_files_with_paths()

    return APIResponse(success=True, data={"files": files})


@router.get("/workspace/{session_id}/files/{file_path:path}/preview")
async def preview_workspace_file(session_id: str, file_path: str):
    """预览工作区文件（文本文件）。"""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")

    manager = WorkspaceManager(session_id)
    try:
        content = manager.read_file(file_path)
        # 限制行数
        lines = content.splitlines()
        if len(lines) > 50:
            content = "\n".join(lines[:50]) + "\n\n... (仅显示前50行)"
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="文件不存在")
    except Exception:
        raise HTTPException(status_code=400, detail="文件无法读取或不是文本文件")

    return APIResponse(success=True, data={"content": content, "path": file_path})


@router.get("/workspace/{session_id}/files/{file_path:path}")
async def get_workspace_file(session_id: str, file_path: str):
    """获取工作区文件内容或下载。"""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")

    manager = WorkspaceManager(session_id)
    try:
        target_path = manager.resolve_workspace_path(file_path, allow_missing=False)
        filename = target_path.name
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="文件不存在")

    return _build_download_response(target_path, filename)


@router.post("/workspace/{session_id}/files/{file_id}/move")
async def move_workspace_file(
    session_id: str,
    file_id: str,
    request: dict[str, Any],
):
    """移动工作区文件到指定文件夹。"""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")

    folder_id = request.get("folder_id")

    manager = WorkspaceManager(session_id)
    result = manager.move_file(file_id, folder_id)

    if result is None:
        raise HTTPException(status_code=404, detail="文件不存在")

    return APIResponse(success=True)


@router.post("/workspace/{session_id}/files/{file_id}/rename")
async def rename_workspace_file(
    session_id: str,
    file_id: str,
    request: FileRenameRequest,
):
    """重命名工作区文件。"""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")

    manager = WorkspaceManager(session_id)
    result = manager.rename_file(file_id, request.new_name)

    if result is None:
        raise HTTPException(status_code=404, detail="文件不存在")

    return APIResponse(success=True)


@router.post("/workspace/{session_id}/files/{file_path:path}")
async def save_workspace_file(
    session_id: str,
    file_path: str,
    request: SaveWorkspaceTextRequest,
):
    """保存文本文件到工作区。"""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")

    manager = WorkspaceManager(session_id)
    success = manager.save_text_file(file_path, request.content)

    if not success:
        raise HTTPException(status_code=500, detail="保存文件失败")

    return APIResponse(success=True, data={"path": file_path})


@router.delete("/workspace/{session_id}/files/{file_id}")
async def delete_workspace_file(session_id: str, file_id: str):
    """删除工作区文件。"""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")

    manager = WorkspaceManager(session_id)
    result = manager.delete_file(file_id)

    if result is None:
        raise HTTPException(status_code=404, detail="文件不存在")

    return APIResponse(success=True)


@router.get("/workspace/{session_id}/download/{file_path:path}")
async def download_workspace_file(
    session_id: str,
    file_path: str,
    inline: bool = False,
):
    """下载工作区文件。"""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")

    manager = WorkspaceManager(session_id)
    try:
        target_path = manager.resolve_workspace_path(file_path, allow_missing=False)
        filename = target_path.name
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="文件不存在")

    return _build_download_response(
        target_path,
        filename,
        inline=inline,
    )


@router.post("/workspace/{session_id}/download-zip")
async def download_workspace_zip(session_id: str, request: dict[str, Any]):
    """打包下载多个工作区文件。"""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")

    file_paths = request.get("files", [])
    if not file_paths:
        raise HTTPException(status_code=400, detail="文件列表不能为空")

    manager = WorkspaceManager(session_id)
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in file_paths:
            try:
                target_path = manager.resolve_workspace_path(file_path, allow_missing=False)
                if target_path.exists():
                    zf.write(target_path, target_path.name)
            except FileNotFoundError:
                continue

    zip_buffer.seek(0)

    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=workspace_{session_id}.zip"
        },
    )


@router.get("/workspace/{session_id}/executions")
async def list_workspace_executions(session_id: str):
    """列出工作区代码执行记录。"""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")

    manager = WorkspaceManager(session_id)
    executions = manager.list_executions()

    return APIResponse(success=True, data=executions)


@router.get("/workspace/{session_id}/folders")
async def list_workspace_folders(session_id: str):
    """列出工作区文件夹。"""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")

    manager = WorkspaceManager(session_id)
    folders = manager.list_folders()

    return APIResponse(success=True, data=folders)


@router.post("/workspace/{session_id}/folders")
async def create_workspace_folder(session_id: str, req: dict[str, Any]):
    """创建工作区文件夹。"""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")

    folder_path = req.get("path")
    if not folder_path:
        raise HTTPException(status_code=400, detail="文件夹路径不能为空")

    manager = WorkspaceManager(session_id)
    success = manager.create_folder(folder_path)

    if not success:
        raise HTTPException(status_code=400, detail="创建文件夹失败")

    return APIResponse(success=True, data={"path": folder_path})


# 导入需要在文件末尾以避免循环导入
import mimetypes
import uuid
from datetime import datetime, timezone
