"""建议相关 API 端点。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.schemas.common import APIResponse
from app.schemas.suggestion import SuggestionCreateRequest, SuggestionResponse
from app.services.task_service import task_service
from app.services.ai_suggestion_service import ai_suggestion_service
from app.services.suggestion_service import suggestion_service

router = APIRouter()


@router.post(
    "/tasks/{task_id}/suggestions",
    response_model=APIResponse[SuggestionResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_suggestion(
    task_id: str,
    request: SuggestionCreateRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    """生成并保存建议。"""
    task = await task_service.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")

    payload = await ai_suggestion_service.generate_suggestions(request.summary if request else None)
    suggestion = await suggestion_service.create_suggestion(db, task, payload)
    await db.commit()

    response = SuggestionResponse(
        id=suggestion.id,
        task_id=suggestion.task_id,
        cleaning=payload.get("cleaning", []),
        statistics=payload.get("statistics", []),
        chart_recommendations=payload.get("chart_recommendations", []),
        notes=payload.get("notes", []),
        status=suggestion.status,
        created_at=suggestion.created_at,
    )
    return APIResponse(success=True, data=response)


@router.post("/tasks/{task_id}/suggestions/accept", response_model=APIResponse[dict])
async def accept_suggestion(task_id: str, db: AsyncSession = Depends(get_db)):
    """采纳建议。"""
    task = await task_service.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")

    await suggestion_service.accept(db, task)
    await db.commit()
    return APIResponse(success=True, data={"task_id": task.id, "status": task.suggestion_status.value})


@router.post("/tasks/{task_id}/suggestions/reject", response_model=APIResponse[dict])
async def reject_suggestion(task_id: str, db: AsyncSession = Depends(get_db)):
    """拒绝建议。"""
    task = await task_service.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")

    await suggestion_service.reject(db, task)
    await db.commit()
    return APIResponse(success=True, data={"task_id": task.id, "status": task.suggestion_status.value})
