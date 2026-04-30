"""应用内更新 API。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from nini.models.schemas import APIResponse
from nini.update.apply import (
    ApplyUpdateError,
    launch_updater,
    prepare_apply_update,
    schedule_current_process_exit,
)
from nini.update.service import update_service
from nini.update.signature import SignatureVerificationError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/update")


@router.get("/check")
async def check_update(request: Request) -> APIResponse:
    """检查是否有可用更新。"""
    logger.info("API: 检查更新请求, client=%s", request.client.host if request.client else "unknown")
    result = await update_service.check_update()
    return APIResponse(data=result.model_dump())


@router.post("/download")
async def download_update(request: Request) -> APIResponse:
    """下载更新包。"""
    logger.info("API: 下载更新请求, client=%s", request.client.host if request.client else "unknown")
    state = await update_service.download_update()
    return APIResponse(success=state.status == "ready", data=state.model_dump(), error=state.error)


@router.get("/status")
async def get_update_status() -> APIResponse:
    """查询更新状态。"""
    return APIResponse(data=update_service.status().model_dump())


@router.post("/apply")
async def apply_update(request: Request) -> APIResponse:
    """启动独立 updater 准备安装更新。

    安全注意：此操作将终止当前进程并执行安装程序。
    仅在打包环境中可用，且需要通过认证保护。
    """
    client_host = request.client.host if request.client else "unknown"
    logger.warning("API: 触发更新安装, client=%s", client_host)

    state = update_service.status().download
    try:
        command = prepare_apply_update(state)
        logger.info("API: 启动 updater, installer=%s", state.installer_path)
        launch_updater(command)
        schedule_current_process_exit()
    except ApplyUpdateError as exc:
        logger.warning("API: 更新安装被拒绝: %s", exc)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SignatureVerificationError as exc:
        logger.warning("API: 签名校验失败: %s", exc)
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    logger.info("API: 更新安装已启动，进程即将退出")
    return APIResponse(data={"status": "restarting"})
