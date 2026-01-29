"""
数据集 API 端点。
"""
import asyncio
from typing import List, Optional
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.base import get_db
from app.models.dataset import Dataset
from app.schemas.dataset import (
    DatasetCreate, DatasetUpdate, DatasetResponse,
    DatasetPreview, DatasetStats, ColumnInfo, ColumnStats
)
from app.schemas.common import APIResponse, PaginatedResponse
from app.services.file_service import file_service
from app.services.data_service import data_service
import uuid

router = APIRouter()


@router.post("/upload", response_model=APIResponse[DatasetResponse])
async def upload_dataset(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db)
):
    """
    上传新的数据集文件（Excel、CSV、TSV）。

    - **file**: 要上传的数据文件
    - **name**: 可选的数据集自定义名称
    - **description**: 可选的描述
    """
    # 生成数据集 ID
    dataset_id = str(uuid.uuid4())

    # 保存文件
    file_info = await file_service.save_file(file, dataset_id)

    # 在线程池中执行同步的 Pandas 操作，避免阻塞事件循环
    df = await asyncio.to_thread(data_service.load_dataset, file_info["file_path"])
    preview = await asyncio.to_thread(data_service.get_preview, df)
    column_stats = await asyncio.to_thread(data_service.compute_all_stats, df)

    # 创建数据集记录
    dataset = Dataset(
        id=dataset_id,
        name=name or file_info["filename"],
        description=description,
        filename=file_info["filename"],
        file_path=file_info["file_path"],
        file_size=file_info["file_size"],
        file_type=file_info["file_type"],
        row_count=len(df),
        column_count=len(df.columns),
        columns=[col.model_dump() for col in preview["columns"]],
        preview_data=preview["data"],
        column_stats=[stats.model_dump() for stats in column_stats]
    )

    db.add(dataset)
    await db.commit()
    await db.refresh(dataset)

    return APIResponse(
        success=True,
        message="数据集上传成功",
        data=DatasetResponse.model_validate(dataset)
    )


@router.get("/", response_model=APIResponse[List[DatasetResponse]])
async def list_datasets(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """列出所有数据集。"""
    result = await db.execute(
        select(Dataset).offset(skip).limit(limit).order_by(Dataset.created_at.desc())
    )
    datasets = result.scalars().all()

    return APIResponse(
        success=True,
        data=[DatasetResponse.model_validate(d) for d in datasets]
    )


@router.get("/{dataset_id}", response_model=APIResponse[DatasetResponse])
async def get_dataset(
    dataset_id: str,
    db: AsyncSession = Depends(get_db)
):
    """根据 ID 获取数据集。"""
    result = await db.execute(
        select(Dataset).where(Dataset.id == dataset_id)
    )
    dataset = result.scalar_one_or_none()

    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"数据集 {dataset_id} 未找到"
        )

    return APIResponse(
        success=True,
        data=DatasetResponse.model_validate(dataset)
    )


@router.get("/{dataset_id}/preview", response_model=APIResponse[DatasetPreview])
async def get_dataset_preview(
    dataset_id: str,
    rows: int = 10,
    db: AsyncSession = Depends(get_db)
):
    """获取数据集预览（前 N 行）。"""
    result = await db.execute(
        select(Dataset).where(Dataset.id == dataset_id)
    )
    dataset = result.scalar_one_or_none()

    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"数据集 {dataset_id} 未找到"
        )

    # 在线程池中执行同步操作
    df = await asyncio.to_thread(data_service.load_dataset, dataset.file_path)
    preview = await asyncio.to_thread(data_service.get_preview, df, rows)

    return APIResponse(
        success=True,
        data=DatasetPreview.model_validate(preview)
    )


@router.get("/{dataset_id}/stats", response_model=APIResponse[List[ColumnStats]])
async def get_dataset_stats(
    dataset_id: str,
    db: AsyncSession = Depends(get_db)
):
    """获取数据集所有列的统计信息。"""
    result = await db.execute(
        select(Dataset).where(Dataset.id == dataset_id)
    )
    dataset = result.scalar_one_or_none()

    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"数据集 {dataset_id} 未找到"
        )

    # 在线程池中执行同步操作
    df = await asyncio.to_thread(data_service.load_dataset, dataset.file_path)
    stats = await asyncio.to_thread(data_service.compute_all_stats, df)

    return APIResponse(
        success=True,
        data=stats
    )


@router.put("/{dataset_id}", response_model=APIResponse[DatasetResponse])
async def update_dataset(
    dataset_id: str,
    update_data: DatasetUpdate,
    db: AsyncSession = Depends(get_db)
):
    """更新数据集元数据。"""
    result = await db.execute(
        select(Dataset).where(Dataset.id == dataset_id)
    )
    dataset = result.scalar_one_or_none()

    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"数据集 {dataset_id} 未找到"
        )

    # 更新字段
    if update_data.name is not None:
        dataset.name = update_data.name
    if update_data.description is not None:
        dataset.description = update_data.description

    await db.commit()
    await db.refresh(dataset)

    return APIResponse(
        success=True,
        message="数据集更新成功",
        data=DatasetResponse.model_validate(dataset)
    )


@router.delete("/{dataset_id}", response_model=APIResponse[dict])
async def delete_dataset(
    dataset_id: str,
    db: AsyncSession = Depends(get_db)
):
    """删除数据集。"""
    result = await db.execute(
        select(Dataset).where(Dataset.id == dataset_id)
    )
    dataset = result.scalar_one_or_none()

    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"数据集 {dataset_id} 未找到"
        )

    # 删除文件
    file_service.delete_file(dataset.file_path)

    # 删除记录
    await db.delete(dataset)
    await db.commit()

    return APIResponse(
        success=True,
        message="数据集删除成功",
        data={"deleted_id": dataset_id}
    )


@router.get("/{dataset_id}/columns", response_model=APIResponse[List[ColumnInfo]])
async def get_dataset_columns(
    dataset_id: str,
    db: AsyncSession = Depends(get_db)
):
    """获取数据集的列信息。"""
    result = await db.execute(
        select(Dataset).where(Dataset.id == dataset_id)
    )
    dataset = result.scalar_one_or_none()

    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"数据集 {dataset_id} 未找到"
        )

    # 在线程池中执行同步操作
    df = await asyncio.to_thread(data_service.load_dataset, dataset.file_path)
    columns = await asyncio.to_thread(data_service.get_column_info, df)

    return APIResponse(
        success=True,
        data=columns
    )
