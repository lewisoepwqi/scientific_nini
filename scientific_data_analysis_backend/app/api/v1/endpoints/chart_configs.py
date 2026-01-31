"""图表配置 API 端点。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.schemas.common import APIResponse
from app.models.chart_config import ChartConfig
from app.services.chart_config_service import chart_config_service

router = APIRouter()


@router.post("/{config_id}/clone", response_model=APIResponse[dict], status_code=status.HTTP_201_CREATED)
async def clone_chart_config(config_id: str, db: AsyncSession = Depends(get_db)):
    """克隆图表配置。"""
    try:
        config = await chart_config_service.clone_config(db, config_id)
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return APIResponse(success=True, data={"id": config.id, "version": config.version})
