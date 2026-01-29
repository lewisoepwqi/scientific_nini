"""
数据集模型，用于存储上传的数据文件。
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Integer, Text, JSON
from sqlalchemy.orm import relationship

from app.db.base import Base


def generate_uuid():
    """生成唯一的 UUID 字符串。"""
    return str(uuid.uuid4())


def utcnow():
    """获取当前 UTC 时间（兼容 Python 3.12+）。"""
    return datetime.now(timezone.utc)


class Dataset(Base):
    """Dataset model for uploaded data files."""
    
    __tablename__ = "datasets"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=False)
    file_type = Column(String(50), nullable=False)  # xlsx, csv, tsv, txt
    
    # Data metadata
    row_count = Column(Integer, nullable=True)
    column_count = Column(Integer, nullable=True)
    columns = Column(JSON, nullable=True)  # List of column names with types
    preview_data = Column(JSON, nullable=True)  # First few rows for preview
    
    # Statistics cache
    column_stats = Column(JSON, nullable=True)  # Basic statistics per column
    
    # 时间戳
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    
    # Relationships
    analyses = relationship("Analysis", back_populates="dataset", cascade="all, delete-orphan")
    visualizations = relationship("Visualization", back_populates="dataset", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Dataset(id={self.id}, name={self.name}, type={self.file_type})>"
