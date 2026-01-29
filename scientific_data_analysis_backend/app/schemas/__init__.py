"""请求/响应验证的 Pydantic Schema 定义。"""
from app.schemas.dataset import (
    DatasetCreate, DatasetUpdate, DatasetResponse,
    DatasetPreview, DatasetStats, ColumnInfo, ColumnStats
)
from app.schemas.analysis import (
    AnalysisCreate, AnalysisUpdate, AnalysisResponse,
    AnalysisResultResponse, TTestRequest, ANOVARequest,
    CorrelationRequest, RegressionRequest
)
from app.schemas.visualization import (
    VisualizationCreate, VisualizationUpdate, VisualizationResponse,
    ChartConfig, ScatterConfig, BoxConfig, HeatmapConfig
)
from app.schemas.common import (
    APIResponse, PaginatedResponse, ErrorResponse
)

__all__ = [
    # Dataset schemas
    "DatasetCreate", "DatasetUpdate", "DatasetResponse",
    "DatasetPreview", "DatasetStats", "ColumnInfo", "ColumnStats",
    # Analysis schemas
    "AnalysisCreate", "AnalysisUpdate", "AnalysisResponse",
    "AnalysisResultResponse", "TTestRequest", "ANOVARequest",
    "CorrelationRequest", "RegressionRequest",
    # Visualization schemas
    "VisualizationCreate", "VisualizationUpdate", "VisualizationResponse",
    "ChartConfig", "ScatterConfig", "BoxConfig", "HeatmapConfig",
    # Common schemas
    "APIResponse", "PaginatedResponse", "ErrorResponse"
]
