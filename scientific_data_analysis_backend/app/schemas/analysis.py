"""
统计分析操作的 Schema 定义。
"""
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

from app.models.analysis import AnalysisType, AnalysisStatus


# ==================== Analysis Request Schemas ====================

class TTestRequest(BaseModel):
    """Schema for t-test request."""
    column: str = Field(..., description="Column to test")
    group_column: Optional[str] = Field(None, description="Grouping column for independent t-test")
    test_value: Optional[float] = Field(None, description="Test value for one-sample t-test")
    alternative: str = Field(default="two-sided", pattern="^(two-sided|less|greater)$")
    paired: bool = False
    confidence_level: float = Field(default=0.95, ge=0.8, le=0.99)


class ANOVARequest(BaseModel):
    """Schema for ANOVA request."""
    value_column: str = Field(..., description="Column with values")
    group_columns: List[str] = Field(..., description="Grouping column(s)")
    anova_type: str = Field(default="one-way", pattern="^(one-way|two-way|repeated)$")
    post_hoc: bool = True
    post_hoc_method: str = Field(default="tukey", pattern="^(tukey|bonferroni|sidak|holm)$")


class CorrelationRequest(BaseModel):
    """Schema for correlation analysis request."""
    columns: List[str] = Field(..., min_length=2, description="Columns to correlate")
    method: str = Field(default="pearson", pattern="^(pearson|spearman|kendall)$")
    plot_matrix: bool = True


class RegressionRequest(BaseModel):
    """Schema for regression analysis request."""
    dependent_var: str = Field(..., description="Dependent variable")
    independent_vars: List[str] = Field(..., min_length=1, description="Independent variables")
    regression_type: str = Field(default="linear", pattern="^(linear|logistic|polynomial)$")
    polynomial_degree: Optional[int] = Field(default=2, ge=2, le=5)
    include_intercept: bool = True


class DescriptiveStatsRequest(BaseModel):
    """Schema for descriptive statistics request."""
    columns: Optional[List[str]] = Field(None, description="Columns to analyze (None = all)")
    group_by: Optional[str] = Field(None, description="Column to group by")
    include_percentiles: List[float] = Field(default=[0.25, 0.5, 0.75])


# ==================== Analysis CRUD Schemas ====================

class AnalysisCreate(BaseModel):
    """Schema for creating an analysis."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    analysis_type: AnalysisType
    parameters: Dict[str, Any]
    dataset_id: str


class AnalysisUpdate(BaseModel):
    """Schema for updating an analysis."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None


class AnalysisResponse(BaseModel):
    """分析响应 Schema。"""
    id: str
    name: str
    description: Optional[str]
    analysis_type: AnalysisType
    parameters: Dict[str, Any]
    status: AnalysisStatus
    error_message: Optional[str]
    dataset_id: str
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


# ==================== Analysis Result Schemas ====================

class TTestResult(BaseModel):
    """Schema for t-test result."""
    statistic: float
    pvalue: float
    df: float
    confidence_interval: List[float]
    effect_size: Optional[float] = None  # Cohen's d
    mean_diff: Optional[float] = None
    std_diff: Optional[float] = None


class ANOVAResult(BaseModel):
    """Schema for ANOVA result."""
    f_statistic: float
    pvalue: float
    df_between: float
    df_within: float
    sum_sq_between: float
    sum_sq_within: float
    mean_sq_between: float
    mean_sq_within: float
    eta_squared: Optional[float] = None
    post_hoc_results: Optional[List[Dict[str, Any]]] = None


class CorrelationResult(BaseModel):
    """Schema for correlation analysis result."""
    correlation_matrix: Dict[str, Dict[str, float]]
    pvalue_matrix: Optional[Dict[str, Dict[str, float]]] = None
    method: str
    sample_size: int


class RegressionResult(BaseModel):
    """Schema for regression analysis result."""
    r_squared: float
    adjusted_r_squared: float
    f_statistic: float
    f_pvalue: float
    coefficients: Dict[str, Dict[str, float]]
    residuals_summary: Optional[Dict[str, float]] = None
    predictions: Optional[List[float]] = None


class DescriptiveStatsResult(BaseModel):
    """Schema for descriptive statistics result."""
    column: str
    count: int
    mean: Optional[float] = None
    std: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    median: Optional[float] = None
    percentiles: Optional[Dict[str, float]] = None
    skewness: Optional[float] = None
    kurtosis: Optional[float] = None


class AnalysisResultResponse(BaseModel):
    """分析结果响应 Schema。"""
    id: str
    result_type: str
    result_data: Union[
        TTestResult, ANOVAResult, CorrelationResult,
        RegressionResult, DescriptiveStatsResult,
        Dict[str, Any]
    ]
    interpretation: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AnalysisWithResultsResponse(AnalysisResponse):
    """Schema for analysis with results."""
    results: List[AnalysisResultResponse]
