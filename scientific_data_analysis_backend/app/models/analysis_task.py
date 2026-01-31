"""
分析任务模型。
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.models.enums import TaskStage, SuggestionStatus


def generate_uuid() -> str:
    """生成唯一的 UUID 字符串。"""
    return str(uuid.uuid4())


def utcnow():
    """获取当前 UTC 时间（兼容 Python 3.12+）。"""
    return datetime.now(timezone.utc)


class AnalysisTask(Base):
    """分析任务模型，用于管理任务上下文。"""

    __tablename__ = "analysis_tasks"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    dataset_id = Column(String(36), ForeignKey("datasets.id"), nullable=False)
    owner_id = Column(String(36), nullable=False)

    stage = Column(Enum(TaskStage, native_enum=False), nullable=False)
    suggestion_status = Column(Enum(SuggestionStatus, native_enum=False), nullable=False)
    active_version_id = Column(String(36), ForeignKey("dataset_versions.id"), nullable=True)

    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    dataset = relationship("Dataset")
    active_version = relationship("DatasetVersion")
    visualizations = relationship("Visualization", back_populates="task", cascade="all, delete-orphan")
    suggestions = relationship("Suggestion", back_populates="task", cascade="all, delete-orphan")
    shares = relationship("TaskShare", back_populates="task", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<AnalysisTask(id={self.id}, stage={self.stage})>"
