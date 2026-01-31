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
    ChartConfig, ScatterConfig, BoxConfig, HeatmapConfig,
    TaskVisualizationCreate, TaskVisualizationResponse
)
from app.schemas.common import (
    APIResponse, PaginatedResponse, ErrorResponse
)
from app.schemas.task import TaskCreateRequest, TaskResponse, TaskStatusResponse
from app.schemas.dataset_version import DatasetVersionResponse
from app.schemas.suggestion import SuggestionCreateRequest, SuggestionResponse
from app.schemas.export import ExportPackageResponse
from app.schemas.share import TaskShareCreateRequest, TaskShareResponse

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
    "TaskVisualizationCreate", "TaskVisualizationResponse",
    # Common schemas
    "APIResponse", "PaginatedResponse", "ErrorResponse",
    # Task schemas
    "TaskCreateRequest", "TaskResponse", "TaskStatusResponse",
    # Dataset version schemas
    "DatasetVersionResponse",
    # Suggestion schemas
    "SuggestionCreateRequest", "SuggestionResponse",
    # Export schemas
    "ExportPackageResponse",
    # Share schemas
    "TaskShareCreateRequest", "TaskShareResponse",
]
