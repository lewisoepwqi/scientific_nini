"""
任务相关 Schema。
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

from app.models.enums import TaskStage, SuggestionStatus


class TaskCreateRequest(BaseModel):
    """创建任务请求。"""

    dataset_id: str


class TaskResponse(BaseModel):
    """任务响应。"""

    id: str
    dataset_id: str
    owner_id: str
    stage: TaskStage
    suggestion_status: SuggestionStatus
    active_version_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskStatusResponse(BaseModel):
    """任务状态响应。"""

    task_id: str
    stage: TaskStage
    message: Optional[str] = None
