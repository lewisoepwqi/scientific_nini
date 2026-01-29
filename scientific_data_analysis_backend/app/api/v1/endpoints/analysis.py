"""
Statistical analysis API endpoints.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.models.analysis import Analysis, AnalysisResult, AnalysisType, AnalysisStatus
from app.models.dataset import Dataset
from app.schemas.analysis import (
    AnalysisCreate, AnalysisResponse, AnalysisResultResponse,
    TTestRequest, ANOVARequest, CorrelationRequest, RegressionRequest,
    DescriptiveStatsRequest, TTestResult, ANOVAResult, CorrelationResult, RegressionResult
)
from app.schemas.common import APIResponse
from app.services.analysis_service import analysis_service
from app.services.data_service import data_service

router = APIRouter()


@router.post("/descriptive", response_model=APIResponse[List[dict]])
async def descriptive_statistics(
    dataset_id: str,
    request: DescriptiveStatsRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Compute descriptive statistics for a dataset.
    
    - **dataset_id**: ID of the dataset
    - **columns**: List of columns to analyze (None = all numeric)
    - **group_by**: Column to group by
    - **include_percentiles**: Percentiles to include
    """
    from sqlalchemy import select
    
    # Get dataset
    result = await db.execute(
        select(Dataset).where(Dataset.id == dataset_id)
    )
    dataset = result.scalar_one_or_none()
    
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset {dataset_id} not found"
        )
    
    # Load data
    df = data_service.load_dataset(dataset.file_path)
    
    # Compute statistics
    stats_results = analysis_service.descriptive_stats(
        df,
        columns=request.columns,
        group_by=request.group_by,
        include_percentiles=request.include_percentiles
    )
    
    return APIResponse(
        success=True,
        data=[result.model_dump() for result in stats_results]
    )


@router.post("/t-test", response_model=APIResponse[TTestResult])
async def t_test(
    dataset_id: str,
    request: TTestRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Perform t-test.
    
    - **column**: Column to test
    - **group_column**: Grouping column (for independent t-test)
    - **test_value**: Test value (for one-sample t-test)
    - **alternative**: "two-sided", "less", or "greater"
    - **paired**: Whether to perform paired t-test
    - **confidence_level**: Confidence level (0.8-0.99)
    """
    from sqlalchemy import select
    
    # Get dataset
    result = await db.execute(
        select(Dataset).where(Dataset.id == dataset_id)
    )
    dataset = result.scalar_one_or_none()
    
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset {dataset_id} not found"
        )
    
    # Load data
    df = data_service.load_dataset(dataset.file_path)
    
    # Perform t-test
    result = analysis_service.t_test(
        df,
        column=request.column,
        group_column=request.group_column,
        test_value=request.test_value,
        alternative=request.alternative,
        paired=request.paired,
        confidence_level=request.confidence_level
    )
    
    return APIResponse(
        success=True,
        data=result
    )


@router.post("/anova", response_model=APIResponse[ANOVAResult])
async def one_way_anova(
    dataset_id: str,
    request: ANOVARequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Perform one-way ANOVA.
    
    - **value_column**: Column with values
    - **group_columns**: Grouping column(s)
    - **post_hoc**: Whether to perform post-hoc tests
    - **post_hoc_method**: Post-hoc method ("tukey", "bonferroni", etc.)
    """
    from sqlalchemy import select
    
    # Get dataset
    result = await db.execute(
        select(Dataset).where(Dataset.id == dataset_id)
    )
    dataset = result.scalar_one_or_none()
    
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset {dataset_id} not found"
        )
    
    # Load data
    df = data_service.load_dataset(dataset.file_path)
    
    # Perform ANOVA
    result = analysis_service.one_way_anova(
        df,
        value_column=request.value_column,
        group_column=request.group_columns[0],  # Use first group column
        post_hoc=request.post_hoc,
        post_hoc_method=request.post_hoc_method
    )
    
    return APIResponse(
        success=True,
        data=result
    )


@router.post("/correlation", response_model=APIResponse[CorrelationResult])
async def correlation_analysis(
    dataset_id: str,
    request: CorrelationRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Perform correlation analysis.
    
    - **columns**: Columns to correlate
    - **method**: Correlation method ("pearson", "spearman", "kendall")
    """
    from sqlalchemy import select
    
    # Get dataset
    result = await db.execute(
        select(Dataset).where(Dataset.id == dataset_id)
    )
    dataset = result.scalar_one_or_none()
    
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset {dataset_id} not found"
        )
    
    # Load data
    df = data_service.load_dataset(dataset.file_path)
    
    # Perform correlation
    result = analysis_service.correlation(
        df,
        columns=request.columns,
        method=request.method
    )
    
    return APIResponse(
        success=True,
        data=result
    )


@router.post("/regression", response_model=APIResponse[RegressionResult])
async def linear_regression(
    dataset_id: str,
    request: RegressionRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Perform linear regression.
    
    - **dependent_var**: Dependent variable
    - **independent_vars**: Independent variables
    - **include_intercept**: Whether to include intercept
    """
    from sqlalchemy import select
    
    # Get dataset
    result = await db.execute(
        select(Dataset).where(Dataset.id == dataset_id)
    )
    dataset = result.scalar_one_or_none()
    
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset {dataset_id} not found"
        )
    
    # Load data
    df = data_service.load_dataset(dataset.file_path)
    
    # Perform regression
    result = analysis_service.linear_regression(
        df,
        dependent_var=request.dependent_var,
        independent_vars=request.independent_vars,
        include_intercept=request.include_intercept
    )
    
    return APIResponse(
        success=True,
        data=result
    )


@router.post("/normality", response_model=APIResponse[dict])
async def normality_test(
    dataset_id: str,
    column: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Perform Shapiro-Wilk normality test.
    
    - **column**: Column to test
    """
    from sqlalchemy import select
    
    # Get dataset
    result = await db.execute(
        select(Dataset).where(Dataset.id == dataset_id)
    )
    dataset = result.scalar_one_or_none()
    
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset {dataset_id} not found"
        )
    
    # Load data
    df = data_service.load_dataset(dataset.file_path)
    
    # Perform normality test
    result = analysis_service.shapiro_wilk(df, column)
    
    return APIResponse(
        success=True,
        data=result
    )


@router.get("/types", response_model=APIResponse[List[dict]])
async def list_analysis_types():
    """List available analysis types."""
    analysis_types = [
        {"id": "descriptive", "name": "Descriptive Statistics", "description": "Mean, std, percentiles, etc."},
        {"id": "t_test", "name": "T-Test", "description": "One-sample, independent, or paired t-test"},
        {"id": "anova", "name": "ANOVA", "description": "One-way or two-way analysis of variance"},
        {"id": "correlation", "name": "Correlation", "description": "Pearson, Spearman, or Kendall correlation"},
        {"id": "regression", "name": "Regression", "description": "Linear or logistic regression"},
        {"id": "normality", "name": "Normality Test", "description": "Shapiro-Wilk normality test"}
    ]
    
    return APIResponse(
        success=True,
        data=analysis_types
    )
