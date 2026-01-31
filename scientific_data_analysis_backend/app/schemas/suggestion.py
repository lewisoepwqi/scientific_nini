"""
AI 建议 Schema。
"""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, ConfigDict

from app.models.enums import SuggestionStatus


class SuggestionCreateRequest(BaseModel):
    """建议生成请求。"""

    summary: Optional[dict] = None


class SuggestionResponse(BaseModel):
    """建议响应。"""

    id: str
    task_id: str
    cleaning: List[str] = []
    statistics: List[str] = []
    chart_recommendations: List[str] = []
    notes: List[str] = []
    status: SuggestionStatus
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
