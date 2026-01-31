"""任务相关 API 端点。"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.schemas.common import APIResponse
from app.schemas.task import TaskCreateRequest, TaskResponse, TaskStatusResponse
from app.schemas.visualization import TaskVisualizationCreate, TaskVisualizationResponse
from app.services.task_service import task_service
from app.services.visualization_service import visualization_record_service

router = APIRouter()


def _get_user_id(x_user_id: Optional[str]) -> str:
    """获取用户标识。"""
    return x_user_id or "anonymous"


@router.post("", response_model=APIResponse[TaskResponse], status_code=status.HTTP_201_CREATED)
async def create_task(
    request: TaskCreateRequest,
    db: AsyncSession = Depends(get_db),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    """创建分析任务。"""
    try:
        task = await task_service.create_task(db, request.dataset_id, _get_user_id(x_user_id))
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return APIResponse(success=True, data=TaskResponse.model_validate(task))


@router.get("", response_model=APIResponse[List[TaskResponse]])
async def list_tasks(
    db: AsyncSession = Depends(get_db),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    """获取任务列表。"""
    tasks = await task_service.list_tasks(db, _get_user_id(x_user_id))
    return APIResponse(success=True, data=[TaskResponse.model_validate(task) for task in tasks])


@router.get("/{task_id}", response_model=APIResponse[TaskResponse])
async def get_task(task_id: str, db: AsyncSession = Depends(get_db)):
    """获取任务详情。"""
    task = await task_service.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    return APIResponse(success=True, data=TaskResponse.model_validate(task))


@router.get("/{task_id}/status", response_model=APIResponse[TaskStatusResponse])
async def get_task_status(task_id: str, db: AsyncSession = Depends(get_db)):
    """获取任务状态。"""
    task = await task_service.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    status_payload = TaskStatusResponse(task_id=task.id, stage=task.stage, message=None)
    return APIResponse(success=True, data=status_payload)


@router.post(
    "/{task_id}/visualizations",
    response_model=APIResponse[TaskVisualizationResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_task_visualization(
    task_id: str,
    payload: TaskVisualizationCreate,
    db: AsyncSession = Depends(get_db),
):
    """创建任务图表。"""
    task = await task_service.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")

    try:
        visualization = await visualization_record_service.create_task_visualization(
            db,
            task,
            payload.chart_type,
            payload.config,
            payload.dataset_version_id,
        )
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return APIResponse(success=True, data=TaskVisualizationResponse.model_validate(visualization))


@router.get("/{task_id}/visualizations", response_model=APIResponse[List[TaskVisualizationResponse]])
async def list_task_visualizations(task_id: str, db: AsyncSession = Depends(get_db)):
    """获取任务图表列表。"""
    task = await task_service.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")

    items = await visualization_record_service.list_task_visualizations(db, task_id)
    return APIResponse(success=True, data=[TaskVisualizationResponse.model_validate(item) for item in items])
