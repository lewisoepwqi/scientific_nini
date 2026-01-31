"""
数据版本 Schema。
"""
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, ConfigDict

from app.models.dataset_version import DatasetVersionSource


class DatasetVersionResponse(BaseModel):
    """数据版本响应。"""

    id: str
    dataset_id: str
    source_type: DatasetVersionSource
    transformations: Optional[Dict[str, Any]] = None
    row_count: Optional[int] = None
    column_count: Optional[int] = None
    created_at: datetime
    expires_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
