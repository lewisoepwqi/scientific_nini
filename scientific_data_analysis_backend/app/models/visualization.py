"""
可视化模型，用于存储图表配置和输出。
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Text, JSON, ForeignKey, Enum
from sqlalchemy.orm import relationship
import enum

from app.db.base import Base


def generate_uuid():
    """生成唯一的 UUID 字符串。"""
    return str(uuid.uuid4())


def utcnow():
    """获取当前 UTC 时间（兼容 Python 3.12+）。"""
    return datetime.now(timezone.utc)


class ChartType(str, enum.Enum):
    """图表/可视化类型。"""
    SCATTER = "scatter"
    SCATTER_WITH_REGRESSION = "scatter_with_regression"
    BOX = "box"
    VIOLIN = "violin"
    BAR = "bar"
    BAR_WITH_ERROR = "bar_with_error"
    LINE = "line"
    LINE_WITH_ERROR = "line_with_error"
    HEATMAP = "heatmap"
    PAIRED = "paired"
    HISTOGRAM = "histogram"
    CORRELATION_MATRIX = "correlation_matrix"
    PCA = "pca"
    VOLCANO = "volcano"
    MA_PLOT = "ma_plot"


class JournalStyle(str, enum.Enum):
    """学术期刊配色风格。"""
    NATURE = "nature"
    SCIENCE = "science"
    CELL = "cell"
    NEJM = "nejm"
    LANCET = "lancet"
    DEFAULT = "default"


class Visualization(Base):
    """可视化模型，用于图表和图形。"""

    __tablename__ = "visualizations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # 图表配置
    chart_type = Column(Enum(ChartType, native_enum=False), nullable=False)
    journal_style = Column(Enum(JournalStyle, native_enum=False), default=JournalStyle.DEFAULT)

    # 数据映射
    x_column = Column(String(255), nullable=True)
    y_column = Column(String(255), nullable=True)
    group_column = Column(String(255), nullable=True)
    color_column = Column(String(255), nullable=True)
    size_column = Column(String(255), nullable=True)

    # 额外配置
    config = Column(JSON, nullable=True)  # 图表特定配置

    # 输出
    plotly_config = Column(JSON, nullable=True)  # Plotly 图表 JSON
    image_path = Column(String(500), nullable=True)  # 渲染图像路径

    # 外键
    dataset_id = Column(String(36), ForeignKey("datasets.id"), nullable=False)

    # 时间戳
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    # 关联关系
    dataset = relationship("Dataset", back_populates="visualizations")

    def __repr__(self):
        return f"<Visualization(id={self.id}, type={self.chart_type})>"
