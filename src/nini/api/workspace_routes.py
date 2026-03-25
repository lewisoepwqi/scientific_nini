"""工作区和数据集路由。

此模块包含工作区相关的 API 端点。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Response

from nini.config import settings
from nini.workspace import WorkspaceManager
from nini.agent.session import session_manager

router = APIRouter()


def _ensure_workspace_session_exists(session_id: str) -> None:
    """校验会话存在，避免工作空间接口访问悬空路径。"""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")


@router.get("/workspace/{session_id}/tree")
async def get_workspace_tree(session_id: str):
    """获取工作空间文件树。"""
    _ensure_workspace_session_exists(session_id)
    workspace = WorkspaceManager(session_id)
    tree = workspace.get_tree()
    return {"success": True, "data": tree}


@router.get("/workspace/{session_id}/files")
async def list_workspace_files(session_id: str, q: str | None = None):
    """列出工作空间文件，支持 ?q= 搜索。"""
    _ensure_workspace_session_exists(session_id)
    workspace = WorkspaceManager(session_id)
    if q and q.strip():
        files = workspace.search_files_with_paths(q)
    else:
        files = workspace.list_workspace_files_with_paths()
    resources = workspace.list_resource_summaries()
    project_artifacts = workspace.list_project_artifacts()
    export_jobs = workspace.list_export_jobs()
    return {
        "success": True,
        "data": {
            "session_id": session_id,
            "files": files,
            "resources": resources,
            "project_artifacts": project_artifacts,
            "export_jobs": export_jobs,
        },
    }


@router.get("/workspace/{session_id}/executions")
async def list_workspace_executions(session_id: str):
    """获取工作空间执行历史。"""
    _ensure_workspace_session_exists(session_id)
    workspace = WorkspaceManager(session_id)
    executions = workspace.list_code_executions()
    resources = workspace.list_resource_summaries()
    return {
        "success": True,
        "data": {"session_id": session_id, "executions": executions, "resources": resources},
    }


@router.get("/workspace/{session_id}/resources")
async def list_workspace_resources(session_id: str):
    """列出工作空间资源摘要。"""
    _ensure_workspace_session_exists(session_id)
    workspace = WorkspaceManager(session_id)
    resources = workspace.list_resource_summaries()
    return {"success": True, "data": {"session_id": session_id, "resources": resources}}


@router.get("/workspace/{session_id}/project-artifacts")
async def list_project_artifacts(session_id: str):
    """列出项目级正式产物。"""
    _ensure_workspace_session_exists(session_id)
    workspace = WorkspaceManager(session_id)
    return {
        "success": True,
        "data": {
            "session_id": session_id,
            "project_artifacts": workspace.list_project_artifacts(),
            "export_jobs": workspace.list_export_jobs(),
        },
    }


@router.post("/workspace/{session_id}/project-artifacts/download-zip")
async def download_project_artifacts_zip(session_id: str, artifact_ids: list[str]):
    """按项目产物 ID 打包下载。"""
    _ensure_workspace_session_exists(session_id)
    if not artifact_ids:
        raise HTTPException(status_code=400, detail="artifact_ids 不能为空")
    workspace = WorkspaceManager(session_id)
    payload = workspace.batch_download_project_artifacts(artifact_ids)
    if not payload:
        raise HTTPException(status_code=404, detail="未找到可打包的项目产物")
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"project_artifacts_{session_id[:8]}_{ts}.zip"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(content=payload, media_type="application/zip", headers=headers)


@router.get("/workspace/{session_id}/folders")
async def list_workspace_folders(session_id: str):
    """列出工作空间文件夹。"""
    _ensure_workspace_session_exists(session_id)
    workspace = WorkspaceManager(session_id)
    folders = workspace.list_folders()
    return {"success": True, "data": {"session_id": session_id, "folders": folders}}


@router.post("/workspace/{session_id}/folders")
async def create_workspace_folder(session_id: str, req: dict[str, Any]):
    """创建工作空间文件夹。"""
    _ensure_workspace_session_exists(session_id)
    name = str(req.get("name", "")).strip()
    if not name:
        raise HTTPException(status_code=400, detail="文件夹名称不能为空")
    parent = req.get("parent")
    workspace = WorkspaceManager(session_id)
    folder = workspace.create_folder(name, parent)
    return {"success": True, "data": {"session_id": session_id, "folder": folder}}
