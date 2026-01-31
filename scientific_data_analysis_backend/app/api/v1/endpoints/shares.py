"""任务分享 API 端点。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.schemas.common import APIResponse
from app.schemas.share import TaskShareCreateRequest, TaskShareResponse
from app.services.task_service import task_service
from app.models.task_share import TaskShare

router = APIRouter()


@router.post(
    "/tasks/{task_id}/shares",
    response_model=APIResponse[TaskShareResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_task_share(
    task_id: str,
    request: TaskShareCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """创建任务分享。"""
    task = await task_service.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")

    share = TaskShare(
        task_id=task.id,
        member_id=request.member_id,
        permission=request.permission,
        expires_at=request.expires_at,
    )
    db.add(share)
    await db.commit()

    return APIResponse(success=True, data=TaskShareResponse.model_validate(share))
