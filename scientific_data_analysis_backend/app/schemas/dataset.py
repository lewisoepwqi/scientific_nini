"""
数据集操作的 Schema 定义。
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class ColumnInfo(BaseModel):
    """Schema for column information."""
    name: str
    dtype: str
    nullable: bool
    unique_count: Optional[int] = None
    sample_values: Optional[List[Any]] = None


class ColumnStats(BaseModel):
    """Schema for column statistics."""
    column: str
    dtype: str
    count: int
    null_count: int
    unique_count: int
    # Numeric stats
    mean: Optional[float] = None
    std: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    q25: Optional[float] = None
    q50: Optional[float] = None
    q75: Optional[float] = None
    # Categorical stats
    top_values: Optional[List[Dict[str, Any]]] = None


class DatasetPreview(BaseModel):
    """Schema for dataset preview."""
    columns: List[ColumnInfo]
    data: List[Dict[str, Any]]
    total_rows: int
    preview_rows: int


class DatasetCreate(BaseModel):
    """Schema for creating a dataset."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None


class DatasetUpdate(BaseModel):
    """Schema for updating a dataset."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None


class DatasetResponse(BaseModel):
    """数据集响应 Schema。"""
    id: str
    name: str
    description: Optional[str]
    filename: str
    file_size: int
    file_type: str
    row_count: Optional[int]
    column_count: Optional[int]
    columns: Optional[List[ColumnInfo]]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DatasetStatsResponse(BaseModel):
    """数据集统计响应 Schema。"""
    dataset_id: str
    column_stats: List[ColumnStats]
    computed_at: datetime


# 别名，保持向后兼容
DatasetStats = DatasetStatsResponse
