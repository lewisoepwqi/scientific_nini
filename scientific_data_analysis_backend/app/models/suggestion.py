"""
AI 建议模型。
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, JSON, Enum, ForeignKey
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.models.enums import SuggestionStatus


def generate_uuid() -> str:
    """生成唯一的 UUID 字符串。"""
    return str(uuid.uuid4())


def utcnow():
    """获取当前 UTC 时间（兼容 Python 3.12+）。"""
    return datetime.now(timezone.utc)


class Suggestion(Base):
    """AI 建议模型。"""

    __tablename__ = "suggestions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    task_id = Column(String(36), ForeignKey("analysis_tasks.id"), nullable=False)
    payload = Column(JSON, nullable=False)
    status = Column(Enum(SuggestionStatus, native_enum=False), nullable=False)
    created_at = Column(DateTime, default=utcnow)

    task = relationship("AnalysisTask", back_populates="suggestions")

    def __repr__(self) -> str:
        return f"<Suggestion(id={self.id}, status={self.status})>"
