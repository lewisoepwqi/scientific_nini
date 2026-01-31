"""
图表配置模型。
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Integer, JSON

from app.db.base import Base


def generate_uuid() -> str:
    """生成唯一的 UUID 字符串。"""
    return str(uuid.uuid4())


def utcnow():
    """获取当前 UTC 时间（兼容 Python 3.12+）。"""
    return datetime.now(timezone.utc)


class ChartConfig(Base):
    """图表配置模型。"""

    __tablename__ = "chart_configs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    semantic_config = Column(JSON, nullable=True)
    style_config = Column(JSON, nullable=True)
    export_config = Column(JSON, nullable=True)
    version = Column(Integer, default=1)

    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    def __repr__(self) -> str:
        return f"<ChartConfig(id={self.id}, version={self.version})>"
