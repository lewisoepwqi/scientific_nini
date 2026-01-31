"""
数据版本模型。
"""
import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Integer, JSON, Enum, ForeignKey
from sqlalchemy.orm import relationship

from app.db.base import Base


def generate_uuid() -> str:
    """生成唯一的 UUID 字符串。"""
    return str(uuid.uuid4())


def utcnow():
    """获取当前 UTC 时间（兼容 Python 3.12+）。"""
    return datetime.now(timezone.utc)


class DatasetVersionSource(str, enum.Enum):
    """数据版本来源。"""

    RAW = "raw"
    DEFAULT = "default"
    AI = "ai"
    CUSTOM = "custom"


class DatasetVersion(Base):
    """数据版本模型。"""

    __tablename__ = "dataset_versions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    dataset_id = Column(String(36), ForeignKey("datasets.id"), nullable=False)
    source_type = Column(Enum(DatasetVersionSource, native_enum=False), nullable=False)
    transformations = Column(JSON, nullable=True)
    row_count = Column(Integer, nullable=True)
    column_count = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    expires_at = Column(DateTime, nullable=True)

    dataset = relationship("Dataset")
    visualizations = relationship("Visualization", back_populates="dataset_version")

    def __repr__(self) -> str:
        return f"<DatasetVersion(id={self.id}, source={self.source_type})>"
