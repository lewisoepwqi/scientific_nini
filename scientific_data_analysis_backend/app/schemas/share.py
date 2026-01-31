"""
分享授权 Schema。
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

from app.models.enums import SharePermission


class TaskShareCreateRequest(BaseModel):
    """创建分享请求。"""

    member_id: str
    permission: SharePermission = SharePermission.VIEW
    expires_at: Optional[datetime] = None


class TaskShareResponse(BaseModel):
    """分享响应。"""

    id: str
    task_id: str
    member_id: str
    permission: SharePermission
    created_at: datetime
    expires_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
