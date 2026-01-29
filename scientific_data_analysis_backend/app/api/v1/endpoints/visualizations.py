"""
Visualization API endpoints.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Response
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.models.visualization import Visualization, ChartType, JournalStyle
from app.models.dataset import Dataset
from app.schemas.visualization import (
    VisualizationCreate, VisualizationResponse,
    ScatterConfig, BoxConfig, ViolinConfig, BarConfig,
    HeatmapConfig, PairedConfig, HistogramConfig,
    VisualizationExportRequest
)
from app.schemas.common import APIResponse
from app.services.visualization_service import visualization_service
from app.services.data_service import data_service

router = APIRouter()


@router.post("/scatter", response_model=APIResponse[dict])
async def create_scatter_plot(
    dataset_id: str,
    config: ScatterConfig,
    db: AsyncSession = Depends(get_db)
):
    """
    Create scatter plot with optional regression line.
    
    - **x_column**: X-axis column
    - **y_column**: Y-axis column
    - **show_regression**: Whether to show regression line
    - **journal_style**: Color style ("nature", "science", "cell", etc.)
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
    
    # Create plot
    fig = visualization_service.create_scatter(
        df,
        x_column=config.x_column,
        y_column=config.y_column,
        color_column=config.color_column,
        size_column=config.size_column,
        text_column=config.text_column,
        show_regression=config.show_regression,
        regression_type=config.regression_type,
        show_equation=config.show_equation,
        show_r_squared=config.show_r_squared,
        title=config.title,
        journal_style=config.journal_style,
        width=config.width,
        height=config.height,
        opacity=config.opacity,
        marker_size=config.marker_size
    )
    
    return APIResponse(
        success=True,
        data=visualization_service.figure_to_json(fig)
    )


@router.post("/box", response_model=APIResponse[dict])
async def create_box_plot(
    dataset_id: str,
    config: BoxConfig,
    db: AsyncSession = Depends(get_db)
):
    """Create box plot."""
    from sqlalchemy import select
    
    result = await db.execute(
        select(Dataset).where(Dataset.id == dataset_id)
    )
    dataset = result.scalar_one_or_none()
    
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset {dataset_id} not found"
        )
    
    df = data_service.load_dataset(dataset.file_path)
    
    fig = visualization_service.create_box(
        df,
        value_column=config.value_column,
        group_column=config.group_column,
        x_column=config.x_column,
        show_points=config.show_points,
        show_mean=config.show_mean,
        title=config.title,
        journal_style=config.journal_style,
        width=config.width,
        height=config.height
    )
    
    return APIResponse(
        success=True,
        data=visualization_service.figure_to_json(fig)
    )


@router.post("/violin", response_model=APIResponse[dict])
async def create_violin_plot(
    dataset_id: str,
    config: ViolinConfig,
    db: AsyncSession = Depends(get_db)
):
    """Create violin plot."""
    from sqlalchemy import select
    
    result = await db.execute(
        select(Dataset).where(Dataset.id == dataset_id)
    )
    dataset = result.scalar_one_or_none()
    
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset {dataset_id} not found"
        )
    
    df = data_service.load_dataset(dataset.file_path)
    
    fig = visualization_service.create_violin(
        df,
        value_column=config.value_column,
        group_column=config.group_column,
        show_box=config.show_box,
        show_points=config.show_points,
        title=config.title,
        journal_style=config.journal_style,
        width=config.width,
        height=config.height
    )
    
    return APIResponse(
        success=True,
        data=visualization_service.figure_to_json(fig)
    )


@router.post("/bar", response_model=APIResponse[dict])
async def create_bar_chart(
    dataset_id: str,
    config: BarConfig,
    db: AsyncSession = Depends(get_db)
):
    """Create bar chart with error bars (Mean ± SEM)."""
    from sqlalchemy import select
    
    result = await db.execute(
        select(Dataset).where(Dataset.id == dataset_id)
    )
    dataset = result.scalar_one_or_none()
    
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset {dataset_id} not found"
        )
    
    df = data_service.load_dataset(dataset.file_path)
    
    fig = visualization_service.create_bar_with_error(
        df,
        x_column=config.x_column,
        y_column=config.y_column,
        group_column=config.group_column,
        error_type=config.error_type,
        title=config.title,
        journal_style=config.journal_style,
        width=config.width,
        height=config.height
    )
    
    return APIResponse(
        success=True,
        data=visualization_service.figure_to_json(fig)
    )


@router.post("/heatmap", response_model=APIResponse[dict])
async def create_heatmap(
    dataset_id: str,
    config: HeatmapConfig,
    db: AsyncSession = Depends(get_db)
):
    """Create heatmap (typically for correlation matrix)."""
    from sqlalchemy import select
    
    result = await db.execute(
        select(Dataset).where(Dataset.id == dataset_id)
    )
    dataset = result.scalar_one_or_none()
    
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset {dataset_id} not found"
        )
    
    df = data_service.load_dataset(dataset.file_path)
    
    fig = visualization_service.create_heatmap(
        df,
        columns=config.columns,
        row_column=config.row_column,
        colorscale=config.colorscale,
        center_at_zero=config.center_at_zero,
        show_values=config.show_values,
        title=config.title,
        journal_style=config.journal_style,
        width=config.width,
        height=config.height,
        is_correlation=True
    )
    
    return APIResponse(
        success=True,
        data=visualization_service.figure_to_json(fig)
    )


@router.post("/paired", response_model=APIResponse[dict])
async def create_paired_plot(
    dataset_id: str,
    config: PairedConfig,
    db: AsyncSession = Depends(get_db)
):
    """Create paired line plot (before/after comparison)."""
    from sqlalchemy import select
    
    result = await db.execute(
        select(Dataset).where(Dataset.id == dataset_id)
    )
    dataset = result.scalar_one_or_none()
    
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset {dataset_id} not found"
        )
    
    df = data_service.load_dataset(dataset.file_path)
    
    fig = visualization_service.create_paired(
        df,
        subject_column=config.subject_column,
        condition_column=config.condition_column,
        value_column=config.value_column,
        title=config.title,
        journal_style=config.journal_style,
        width=config.width,
        height=config.height,
        line_width=config.line_width,
        marker_size=config.marker_size,
        mean_line_color=config.mean_line_color,
        mean_line_width=config.mean_line_width
    )
    
    return APIResponse(
        success=True,
        data=visualization_service.figure_to_json(fig)
    )


@router.post("/histogram", response_model=APIResponse[dict])
async def create_histogram(
    dataset_id: str,
    config: HistogramConfig,
    db: AsyncSession = Depends(get_db)
):
    """Create histogram."""
    from sqlalchemy import select
    
    result = await db.execute(
        select(Dataset).where(Dataset.id == dataset_id)
    )
    dataset = result.scalar_one_or_none()
    
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset {dataset_id} not found"
        )
    
    df = data_service.load_dataset(dataset.file_path)
    
    fig = visualization_service.create_histogram(
        df,
        column=config.column,
        group_column=config.group_column,
        bins=config.bins,
        title=config.title,
        journal_style=config.journal_style,
        width=config.width,
        height=config.height,
        opacity=config.opacity
    )
    
    return APIResponse(
        success=True,
        data=visualization_service.figure_to_json(fig)
    )


@router.get("/types", response_model=APIResponse[List[dict]])
async def list_chart_types():
    """List available chart types."""
    chart_types = [
        {"id": "scatter", "name": "Scatter Plot", "description": "Scatter plot with optional regression line"},
        {"id": "box", "name": "Box Plot", "description": "Box plot with optional data points"},
        {"id": "violin", "name": "Violin Plot", "description": "Violin plot showing distribution"},
        {"id": "bar", "name": "Bar Chart", "description": "Bar chart with error bars (Mean ± SEM)"},
        {"id": "heatmap", "name": "Heatmap", "description": "Heatmap for correlation matrices"},
        {"id": "paired", "name": "Paired Plot", "description": "Paired line plot for before/after comparison"},
        {"id": "histogram", "name": "Histogram", "description": "Distribution histogram"}
    ]
    
    return APIResponse(
        success=True,
        data=chart_types
    )


@router.get("/journal-styles", response_model=APIResponse[List[dict]])
async def list_journal_styles():
    """List available journal color styles."""
    styles = [
        {"id": "nature", "name": "Nature", "description": "Nature journal color palette"},
        {"id": "science", "name": "Science", "description": "Science journal color palette"},
        {"id": "cell", "name": "Cell", "description": "Cell journal color palette"},
        {"id": "nejm", "name": "NEJM", "description": "New England Journal of Medicine palette"},
        {"id": "lancet", "name": "Lancet", "description": "Lancet journal color palette"},
        {"id": "default", "name": "Default", "description": "Default Plotly color palette"}
    ]
    
    return APIResponse(
        success=True,
        data=styles
    )


@router.post("/export/{viz_id}")
async def export_visualization(
    viz_id: str,
    request: VisualizationExportRequest,
    db: AsyncSession = Depends(get_db)
):
    """Export visualization to file."""
    from sqlalchemy import select
    
    result = await db.execute(
        select(Visualization).where(Visualization.id == viz_id)
    )
    viz = result.scalar_one_or_none()
    
    if not viz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Visualization {viz_id} not found"
        )
    
    if not viz.plotly_config:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Visualization has no plot configuration"
        )
    
    import plotly.graph_objects as go
    
    # Recreate figure from config
    fig = go.Figure(viz.plotly_config)
    
    # Export
    output_path = visualization_service.export_figure(
        fig,
        filename=viz_id,
        format=request.format,
        width=request.width,
        height=request.height,
        scale=request.scale
    )
    
    if request.format == "html":
        with open(output_path, "r") as f:
            content = f.read()
        return HTMLResponse(content=content)
    
    return FileResponse(
        output_path,
        media_type=f"image/{request.format}",
        filename=f"{viz.name}.{request.format}"
    )
