"""
可视化操作的 Schema 定义。
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, model_validator

from app.models.visualization import ChartType, JournalStyle


# ==================== 常量定义 ====================

# 最大叠加图层数
MAX_OVERLAY_LAYERS = 3


# ==================== 图表配置 Schemas ====================

class AxisConfig(BaseModel):
    """坐标轴配置 Schema。"""
    title: Optional[str] = None
    label: Optional[str] = None
    log_scale: bool = False
    range: Optional[List[float]] = None
    tick_format: Optional[str] = None


class ChartConfig(BaseModel):
    """图表配置基础 Schema。"""
    title: Optional[str] = None
    subtitle: Optional[str] = None
    width: Optional[int] = Field(default=800, ge=400, le=2000)
    height: Optional[int] = Field(default=600, ge=300, le=1500)
    journal_style: JournalStyle = JournalStyle.DEFAULT
    show_legend: bool = True
    legend_position: str = Field(default="right", pattern="^(right|left|top|bottom)$")
    color_palette: Optional[str] = None


class ScatterConfig(ChartConfig):
    """散点图配置 Schema。"""
    x_column: str
    y_column: str
    color_column: Optional[str] = None
    size_column: Optional[str] = None
    text_column: Optional[str] = None
    show_regression: bool = False
    regression_type: str = Field(default="linear", pattern="^(linear|polynomial|loess)$")
    regression_ci: float = Field(default=0.95, ge=0.8, le=0.99)
    show_equation: bool = False
    show_r_squared: bool = False
    marker_size: int = Field(default=8, ge=2, le=30)
    opacity: float = Field(default=0.7, ge=0.1, le=1.0)


class BoxConfig(ChartConfig):
    """箱线图配置 Schema。"""
    value_column: str
    group_column: Optional[str] = None
    x_column: Optional[str] = None
    show_points: bool = True
    point_jitter: float = Field(default=0.1, ge=0, le=0.5)
    show_mean: bool = True
    show_notch: bool = False
    orientation: str = Field(default="vertical", pattern="^(vertical|horizontal)$")


class ViolinConfig(ChartConfig):
    """小提琴图配置 Schema。"""
    value_column: str
    group_column: Optional[str] = None
    x_column: Optional[str] = None
    show_box: bool = True
    show_points: bool = False
    bandwidth: Optional[float] = None
    orientation: str = Field(default="vertical", pattern="^(vertical|horizontal)$")


class BarConfig(ChartConfig):
    """柱状图配置 Schema。"""
    x_column: str
    y_column: str
    group_column: Optional[str] = None
    error_column: Optional[str] = None
    orientation: str = Field(default="vertical", pattern="^(vertical|horizontal)$")
    show_error_bars: bool = False
    error_type: str = Field(default="sem", pattern="^(sem|sd|ci)$")
    bar_width: float = Field(default=0.7, ge=0.1, le=1.0)


class HeatmapConfig(ChartConfig):
    """热图配置 Schema。"""
    columns: List[str]
    row_column: Optional[str] = None
    color_column: Optional[str] = None
    annotation_column: Optional[str] = None
    colorscale: str = Field(default="RdBu_r", description="Plotly 颜色比例")
    center_at_zero: bool = True
    show_values: bool = True
    value_format: str = ".2f"
    cluster_rows: bool = False
    cluster_cols: bool = False


class PairedConfig(ChartConfig):
    """配对线图配置 Schema。"""
    subject_column: str
    condition_column: str
    value_column: str
    line_color: Optional[str] = None
    line_width: float = Field(default=1.5, ge=0.5, le=5)
    marker_size: int = Field(default=8, ge=4, le=20)
    show_mean_line: bool = True
    mean_line_color: str = "red"
    mean_line_width: float = Field(default=2, ge=1, le=5)


class HistogramConfig(ChartConfig):
    """直方图配置 Schema。"""
    column: str
    group_column: Optional[str] = None
    bins: Optional[int] = Field(default=30, ge=5, le=100)
    show_density: bool = False
    show_kde: bool = False
    cumulative: bool = False
    opacity: float = Field(default=0.7, ge=0.1, le=1.0)


# ==================== 可视化 CRUD Schemas ====================

class VisualizationCreate(BaseModel):
    """创建可视化 Schema。"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    chart_type: ChartType
    journal_style: JournalStyle = JournalStyle.DEFAULT
    x_column: Optional[str] = None
    y_column: Optional[str] = None
    group_column: Optional[str] = None
    color_column: Optional[str] = None
    size_column: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    dataset_id: str


class VisualizationUpdate(BaseModel):
    """更新可视化 Schema。"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


class VisualizationResponse(BaseModel):
    """可视化响应 Schema。"""
    id: str
    name: str
    description: Optional[str]
    chart_type: ChartType
    journal_style: JournalStyle
    x_column: Optional[str]
    y_column: Optional[str]
    group_column: Optional[str]
    color_column: Optional[str]
    size_column: Optional[str]
    config: Optional[Dict[str, Any]]
    plotly_config: Optional[Dict[str, Any]]
    image_path: Optional[str]
    dataset_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VisualizationExportRequest(BaseModel):
    """可视化导出请求 Schema。"""
    format: str = Field(default="png", pattern="^(png|svg|pdf|jpeg|html)$")
    width: Optional[int] = Field(default=None, ge=400, le=4000)
    height: Optional[int] = Field(default=None, ge=300, le=3000)
    scale: float = Field(default=2.0, ge=1.0, le=4.0)


# ==================== 叠加图表 Schemas ====================

# 图表兼容性组定义
CHART_COMPATIBILITY = {
    ChartType.SCATTER: {ChartType.SCATTER, ChartType.LINE, ChartType.BAR},
    ChartType.LINE: {ChartType.SCATTER, ChartType.LINE, ChartType.BAR},
    ChartType.BAR: {ChartType.SCATTER, ChartType.LINE, ChartType.BAR},
    ChartType.BOX: {ChartType.BOX, ChartType.VIOLIN},
    ChartType.VIOLIN: {ChartType.BOX, ChartType.VIOLIN},
    ChartType.HISTOGRAM: set(),
    ChartType.HEATMAP: set(),
    ChartType.CORRELATION_MATRIX: set(),
}


class OverlayLayerConfig(BaseModel):
    """单个叠加层配置。"""
    chart_type: ChartType
    name: Optional[str] = None

    # 数据列配置
    x_column: Optional[str] = None
    y_column: Optional[str] = None
    value_column: Optional[str] = None
    group_column: Optional[str] = None
    color_column: Optional[str] = None

    # 样式配置
    opacity: float = Field(default=0.7, ge=0.1, le=1.0)
    color_override: Optional[str] = None
    y_axis: str = Field(default="primary", pattern="^(primary|secondary)$")

    # 图表类型特定配置
    show_regression: bool = False  # scatter 专用
    error_type: str = Field(default="sem", pattern="^(sem|sd|ci)$")  # bar 专用
    show_points: bool = True  # box/violin 专用
    show_mean: bool = True  # box 专用
    show_box: bool = True  # violin 专用


class OverlayChartConfig(ChartConfig):
    """叠加图表配置。"""
    primary_layer: OverlayLayerConfig
    overlay_layers: List[OverlayLayerConfig] = Field(
        default_factory=list, max_length=MAX_OVERLAY_LAYERS
    )

    @model_validator(mode='after')
    def validate_compatibility(self) -> 'OverlayChartConfig':
        """验证图表类型兼容性（自动执行）。"""
        primary_type = self.primary_layer.chart_type
        allowed = CHART_COMPATIBILITY.get(primary_type, set())

        if not allowed:
            raise ValueError(f"图表类型 {primary_type.value} 不支持叠加")

        for i, layer in enumerate(self.overlay_layers):
            if layer.chart_type not in allowed:
                raise ValueError(
                    f"叠加层 {i+1} 的图表类型 {layer.chart_type.value} "
                    f"无法与主图表类型 {primary_type.value} 叠加"
                )

        return self
