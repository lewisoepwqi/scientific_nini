"""分享包 API 端点。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.schemas.common import APIResponse
from app.schemas.export import ExportPackageResponse
from app.services.export_service import export_service

router = APIRouter()


@router.post(
    "/visualizations/{visualization_id}/exports",
    response_model=APIResponse[ExportPackageResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_export(visualization_id: str, db: AsyncSession = Depends(get_db)):
    """创建分享包。"""
    try:
        export = await export_service.create_export(db, visualization_id)
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return APIResponse(success=True, data=ExportPackageResponse.model_validate(export))


@router.get("/exports/{export_id}", response_model=APIResponse[ExportPackageResponse])
async def get_export(export_id: str, db: AsyncSession = Depends(get_db)):
    """获取分享包元数据。"""
    export = await export_service.get_export(db, export_id)
    if not export:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分享包不存在")
    return APIResponse(success=True, data=ExportPackageResponse.model_validate(export))
