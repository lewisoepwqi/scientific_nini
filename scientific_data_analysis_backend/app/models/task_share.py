"""
任务分享模型。
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Enum, ForeignKey
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.models.enums import SharePermission


def generate_uuid() -> str:
    """生成唯一的 UUID 字符串。"""
    return str(uuid.uuid4())


def utcnow():
    """获取当前 UTC 时间（兼容 Python 3.12+）。"""
    return datetime.now(timezone.utc)


class TaskShare(Base):
    """任务分享记录。"""

    __tablename__ = "task_shares"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    task_id = Column(String(36), ForeignKey("analysis_tasks.id"), nullable=False)
    member_id = Column(String(36), nullable=False)
    permission = Column(Enum(SharePermission, native_enum=False), nullable=False)
    created_at = Column(DateTime, default=utcnow)
    expires_at = Column(DateTime, nullable=True)

    task = relationship("AnalysisTask", back_populates="shares")

    def __repr__(self) -> str:
        return f"<TaskShare(id={self.id}, member={self.member_id})>"
