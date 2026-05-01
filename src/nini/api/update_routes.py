"""应用内更新 API。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from nini.api.origin_guard import verify_local_origin
from nini.models.schemas import APIResponse
from nini.update.apply import (
    ApplyUpdateError,
    launch_updater,
    prepare_apply_update,
    schedule_current_process_exit,
)
from nini.update.service import UpdateService, update_service
from nini.update.signature import SignatureVerificationError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/update")


def get_update_service() -> UpdateService:
    """更新服务依赖入口；保留模块级 shim 便于测试替换。"""
    return update_service


@router.get("/check")
async def check_update(
    request: Request,
    service: UpdateService = Depends(get_update_service),
) -> APIResponse:
    """检查是否有可用更新。"""
    logger.info(
        "API: 检查更新请求, client=%s", request.client.host if request.client else "unknown"
    )
    result = await service.check_update()
    return APIResponse(data=result.model_dump())


@router.post("/download", dependencies=[Depends(verify_local_origin)])
async def download_update(
    request: Request,
    service: UpdateService = Depends(get_update_service),
) -> APIResponse:
    """下载更新包。"""
    logger.info(
        "API: 下载更新请求, client=%s", request.client.host if request.client else "unknown"
    )
    state = await service.download_update()
    return APIResponse(success=state.status == "ready", data=state.model_dump(), error=state.error)


@router.get("/status")
async def get_update_status(service: UpdateService = Depends(get_update_service)) -> APIResponse:
    """查询更新状态。"""
    return APIResponse(data=service.status().model_dump())


@router.post("/apply", dependencies=[Depends(verify_local_origin)])
async def apply_update(
    request: Request,
    service: UpdateService = Depends(get_update_service),
) -> APIResponse:
    """启动独立 updater 准备安装更新。

    安全注意：此操作将终止当前进程并执行安装程序。
    仅在打包环境中可用，且需要通过认证保护。
    """
    client_host = request.client.host if request.client else "unknown"
    logger.warning("API: 触发更新安装, client=%s", client_host)

    state = service.status().download
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
