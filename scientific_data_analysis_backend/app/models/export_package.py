"""
分享包模型。
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship

from app.db.base import Base


def generate_uuid() -> str:
    """生成唯一的 UUID 字符串。"""
    return str(uuid.uuid4())


def utcnow():
    """获取当前 UTC 时间（兼容 Python 3.12+）。"""
    return datetime.now(timezone.utc)


class ExportPackage(Base):
    """分享包模型，用于复现与分享。"""

    __tablename__ = "export_packages"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    visualization_id = Column(String(36), ForeignKey("visualizations.id"), nullable=False)
    dataset_version_ref = Column(String(36), nullable=False)
    config_snapshot = Column(JSON, nullable=False)
    render_log_snapshot = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    expires_at = Column(DateTime, nullable=True)

    visualization = relationship("Visualization")

    def __repr__(self) -> str:
        return f"<ExportPackage(id={self.id})>"
