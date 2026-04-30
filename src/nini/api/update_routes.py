"""应用内更新 API。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from nini.models.schemas import APIResponse
from nini.update.apply import (
    ApplyUpdateError,
    launch_updater,
    prepare_apply_update,
    schedule_current_process_exit,
)
from nini.update.service import update_service
from nini.update.signature import SignatureVerificationError

router = APIRouter(prefix="/api/update")


@router.get("/check")
async def check_update() -> APIResponse:
    """检查是否有可用更新。"""
    result = await update_service.check_update()
    return APIResponse(data=result.model_dump())


@router.post("/download")
async def download_update() -> APIResponse:
    """下载更新包。"""
    state = await update_service.download_update()
    return APIResponse(success=state.status == "ready", data=state.model_dump(), error=state.error)


@router.get("/status")
async def get_update_status() -> APIResponse:
    """查询更新状态。"""
    return APIResponse(data=update_service.status().model_dump())


@router.post("/apply")
async def apply_update() -> APIResponse:
    """启动独立 updater 准备安装更新。"""
    state = update_service.status().download
    try:
        command = prepare_apply_update(state)
        launch_updater(command)
        schedule_current_process_exit()
    except (ApplyUpdateError, SignatureVerificationError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return APIResponse(data={"status": "restarting"})
