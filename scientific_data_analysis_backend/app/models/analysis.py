"""
统计分析模型，用于存储分析配置和结果。
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


class AnalysisType(str, enum.Enum):
    """统计分析类型。"""
    DESCRIPTIVE = "descriptive"
    T_TEST = "t_test"
    PAIRED_T_TEST = "paired_t_test"
    ONE_WAY_ANOVA = "one_way_anova"
    TWO_WAY_ANOVA = "two_way_anova"
    CORRELATION = "correlation"
    REGRESSION = "regression"
    CHI_SQUARE = "chi_square"
    MANN_WHITNEY = "mann_whitney"
    WILCOXON = "wilcoxon"
    KRUSKAL_WALLIS = "kruskal_wallis"


class AnalysisStatus(str, enum.Enum):
    """分析执行状态。"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Analysis(Base):
    """统计分析任务模型。"""

    __tablename__ = "analyses"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # 分析配置
    analysis_type = Column(Enum(AnalysisType, native_enum=False), nullable=False)
    parameters = Column(JSON, nullable=False)  # 分析特定参数

    # 状态追踪
    status = Column(Enum(AnalysisStatus, native_enum=False), default=AnalysisStatus.PENDING)
    error_message = Column(Text, nullable=True)

    # 外键
    dataset_id = Column(String(36), ForeignKey("datasets.id"), nullable=False)

    # 时间戳
    created_at = Column(DateTime, default=utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # 关联关系
    dataset = relationship("Dataset", back_populates="analyses")
    results = relationship("AnalysisResult", back_populates="analysis", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Analysis(id={self.id}, type={self.analysis_type}, status={self.status})>"


class AnalysisResult(Base):
    """分析结果模型，用于存储分析输出。"""

    __tablename__ = "analysis_results"

    id = Column(String(36), primary_key=True, default=generate_uuid)

    # 结果数据
    result_type = Column(String(50), nullable=False)  # 如 "statistics", "test", "model"
    result_data = Column(JSON, nullable=False)  # 结构化结果数据

    # 解释说明
    interpretation = Column(Text, nullable=True)  # 人类可读的解释

    # 外键
    analysis_id = Column(String(36), ForeignKey("analyses.id"), nullable=False)

    # 时间戳
    created_at = Column(DateTime, default=utcnow)

    # 关联关系
    analysis = relationship("Analysis", back_populates="results")

    def __repr__(self):
        return f"<AnalysisResult(id={self.id}, type={self.result_type})>"
