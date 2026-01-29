"""
Data visualization service using Plotly.
"""
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import plotly.figure_factory as ff

from app.core.config import settings
from app.core.exceptions import VisualizationException
from app.models.visualization import ChartType, JournalStyle
from app.services.data_service import data_service
from app.utils.dataframe_utils import safe_json_serialize


# Journal color palettes
JOURNAL_PALETTES = {
    JournalStyle.NATURE: ["#E64B35", "#4DBBD5", "#00A087", "#3C5488", "#F39B7F", "#8491B4"],
    JournalStyle.SCIENCE: ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"],
    JournalStyle.CELL: ["#E41A1C", "#377EB8", "#4DAF4A", "#984EA3", "#FF7F00", "#FFFF33"],
    JournalStyle.NEJM: ["#BC3C29", "#0072B5", "#E18727", "#20854E", "#7876B1", "#6F99AD"],
    JournalStyle.LANCET: ["#00468B", "#ED0000", "#42B540", "#0099B4", "#925E9F", "#FDAF91"],
    JournalStyle.DEFAULT: px.colors.qualitative.Plotly
}


class VisualizationService:
    """Service for generating data visualizations."""
    
    def __init__(self):
        self.default_width = 800
        self.default_height = 600
        self.export_dir = Path(settings.UPLOAD_DIR) / "exports"
        self.export_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_palette(self, journal_style: JournalStyle) -> List[str]:
        """Get color palette for journal style."""
        return JOURNAL_PALETTES.get(journal_style, JOURNAL_PALETTES[JournalStyle.DEFAULT])
    
    def _apply_journal_style(
        self,
        fig: go.Figure,
        journal_style: JournalStyle,
        title: Optional[str] = None
    ) -> go.Figure:
        """Apply journal-specific styling."""
        palette = self._get_palette(journal_style)
        
        # Update layout
        layout_updates = {
            "font": {"family": "Arial, sans-serif", "size": 12},
            "title": {"font": {"size": 14, "color": "black"}} if title else None,
            "paper_bgcolor": "white",
            "plot_bgcolor": "white",
        }
        
        # Journal-specific customizations
        if journal_style == JournalStyle.NATURE:
            layout_updates["font"] = {"family": "Helvetica, Arial, sans-serif", "size": 11}
        elif journal_style == JournalStyle.SCIENCE:
            layout_updates["font"] = {"family": "Arial, sans-serif", "size": 12}
        elif journal_style == JournalStyle.CELL:
            layout_updates["font"] = {"family": "Arial, sans-serif", "size": 11}
        
        fig.update_layout(**{k: v for k, v in layout_updates.items() if v is not None})
        
        # Update traces with palette
        for i, trace in enumerate(fig.data):
            if hasattr(trace, "marker") and trace.marker:
                color_idx = i % len(palette)
                if trace.marker.color is None or isinstance(trace.marker.color, str):
                    trace.marker.color = palette[color_idx]
        
        return fig
    
    # ==================== Scatter Plot ====================
    
    def create_scatter(
        self,
        df: pd.DataFrame,
        x_column: str,
        y_column: str,
        color_column: Optional[str] = None,
        size_column: Optional[str] = None,
        text_column: Optional[str] = None,
        show_regression: bool = False,
        regression_type: str = "linear",
        show_equation: bool = False,
        show_r_squared: bool = False,
        title: Optional[str] = None,
        journal_style: JournalStyle = JournalStyle.DEFAULT,
        **kwargs
    ) -> go.Figure:
        """Create scatter plot with optional regression line."""
        if x_column not in df.columns:
            raise VisualizationException(f"X column '{x_column}' not found")
        if y_column not in df.columns:
            raise VisualizationException(f"Y column '{y_column}' not found")
        
        # Prepare data
        plot_df = df[[x_column, y_column]].dropna()
        
        if color_column and color_column in df.columns:
            plot_df[color_column] = df.loc[plot_df.index, color_column]
        if size_column and size_column in df.columns:
            plot_df[size_column] = df.loc[plot_df.index, size_column]
        if text_column and text_column in df.columns:
            plot_df[text_column] = df.loc[plot_df.index, text_column]
        
        # Create figure
        fig = px.scatter(
            plot_df,
            x=x_column,
            y=y_column,
            color=color_column,
            size=size_column,
            text=text_column,
            title=title,
            opacity=kwargs.get("opacity", 0.7),
            labels={x_column: x_column, y_column: y_column}
        )
        
        # Add regression line
        if show_regression:
            from scipy import stats
            
            x = plot_df[x_column].values
            y = plot_df[y_column].values
            
            # Fit regression
            slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
            
            # Generate line points
            x_line = np.linspace(x.min(), x.max(), 100)
            y_line = slope * x_line + intercept
            
            # Add regression line
            fig.add_trace(go.Scatter(
                x=x_line,
                y=y_line,
                mode="lines",
                name="Regression",
                line=dict(color="red", width=2, dash="dash")
            ))
            
            # Add equation and R² annotation
            if show_equation or show_r_squared:
                annotations = []
                if show_equation:
                    annotations.append(f"y = {slope:.3f}x + {intercept:.3f}")
                if show_r_squared:
                    annotations.append(f"R² = {r_value**2:.3f}")
                
                fig.add_annotation(
                    x=0.05,
                    y=0.95,
                    xref="paper",
                    yref="paper",
                    text="<br>".join(annotations),
                    showarrow=False,
                    bgcolor="white",
                    bordercolor="black",
                    borderwidth=1
                )
        
        # Apply journal style
        fig = self._apply_journal_style(fig, journal_style, title)
        
        # Update layout
        fig.update_layout(
            width=kwargs.get("width", self.default_width),
            height=kwargs.get("height", self.default_height),
            showlegend=kwargs.get("show_legend", True)
        )
        
        return fig
    
    # ==================== Box Plot ====================
    
    def create_box(
        self,
        df: pd.DataFrame,
        value_column: str,
        group_column: Optional[str] = None,
        x_column: Optional[str] = None,
        show_points: bool = True,
        show_mean: bool = True,
        title: Optional[str] = None,
        journal_style: JournalStyle = JournalStyle.DEFAULT,
        **kwargs
    ) -> go.Figure:
        """Create box plot."""
        if value_column not in df.columns:
            raise VisualizationException(f"Value column '{value_column}' not found")
        
        # Determine x axis
        if x_column and x_column in df.columns:
            x = x_column
        elif group_column and group_column in df.columns:
            x = group_column
        else:
            x = None
        
        # Create box plot
        fig = px.box(
            df,
            x=x if x else None,
            y=value_column,
            title=title,
            points="all" if show_points else False,
            labels={value_column: value_column}
        )
        
        # Show mean
        if show_mean:
            fig.update_traces(boxmean=True)
        
        # Apply journal style
        fig = self._apply_journal_style(fig, journal_style, title)
        
        fig.update_layout(
            width=kwargs.get("width", self.default_width),
            height=kwargs.get("height", self.default_height)
        )
        
        return fig
    
    # ==================== Violin Plot ====================
    
    def create_violin(
        self,
        df: pd.DataFrame,
        value_column: str,
        group_column: Optional[str] = None,
        show_box: bool = True,
        show_points: bool = False,
        title: Optional[str] = None,
        journal_style: JournalStyle = JournalStyle.DEFAULT,
        **kwargs
    ) -> go.Figure:
        """Create violin plot."""
        if value_column not in df.columns:
            raise VisualizationException(f"Value column '{value_column}' not found")
        
        fig = px.violin(
            df,
            x=group_column if group_column and group_column in df.columns else None,
            y=value_column,
            title=title,
            box=show_box,
            points="all" if show_points else False,
            labels={value_column: value_column}
        )
        
        # Apply journal style
        fig = self._apply_journal_style(fig, journal_style, title)
        
        fig.update_layout(
            width=kwargs.get("width", self.default_width),
            height=kwargs.get("height", self.default_height)
        )
        
        return fig
    
    # ==================== Bar Chart with Error Bars ====================
    
    def create_bar_with_error(
        self,
        df: pd.DataFrame,
        x_column: str,
        y_column: str,
        group_column: Optional[str] = None,
        error_type: str = "sem",
        title: Optional[str] = None,
        journal_style: JournalStyle = JournalStyle.DEFAULT,
        **kwargs
    ) -> go.Figure:
        """Create bar chart with error bars (Mean ± SEM/SD)."""
        if x_column not in df.columns:
            raise VisualizationException(f"X column '{x_column}' not found")
        if y_column not in df.columns:
            raise VisualizationException(f"Y column '{y_column}' not found")
        
        # Compute statistics
        if group_column and group_column in df.columns:
            stats_df = df.groupby([x_column, group_column])[y_column].agg([
                "mean", "std", "count"
            ]).reset_index()
            stats_df["sem"] = stats_df["std"] / np.sqrt(stats_df["count"])
        else:
            stats_df = df.groupby(x_column)[y_column].agg([
                "mean", "std", "count"
            ]).reset_index()
            stats_df["sem"] = stats_df["std"] / np.sqrt(stats_df["count"])
        
        # Select error column
        if error_type == "sem":
            error_col = "sem"
        elif error_type == "sd":
            error_col = "std"
        else:
            # 95% CI
            stats_df["ci"] = 1.96 * stats_df["sem"]
            error_col = "ci"
        
        # Create bar chart
        if group_column and group_column in df.columns:
            fig = go.Figure()
            for group_name, group_df in stats_df.groupby(group_column):
                x_values = group_df[x_column].astype(str).tolist()
                group_values = [str(group_name)] * len(group_df)
                fig.add_trace(go.Bar(
                    x=[x_values, group_values],
                    y=group_df["mean"].tolist(),
                    name=str(group_name),
                    error_y=dict(type="data", array=group_df[error_col].tolist())
                ))
            fig.update_layout(
                title=title,
                xaxis_title=x_column,
                yaxis_title=f"{y_column} (Mean ± {error_type.upper()})",
                barmode="group"
            )
            fig.update_xaxes(type="multicategory")
        else:
            fig = px.bar(
                stats_df,
                x=x_column,
                y="mean",
                color=None,
                error_y=error_col,
                title=title,
                labels={"mean": f"{y_column} (Mean ± {error_type.upper()})"}
            )
        
        # Apply journal style
        fig = self._apply_journal_style(fig, journal_style, title)
        
        fig.update_layout(
            width=kwargs.get("width", self.default_width),
            height=kwargs.get("height", self.default_height)
        )
        
        return fig
    
    # ==================== Heatmap ====================
    
    def create_heatmap(
        self,
        df: pd.DataFrame,
        columns: List[str],
        row_column: Optional[str] = None,
        colorscale: str = "RdBu_r",
        center_at_zero: bool = True,
        show_values: bool = True,
        title: Optional[str] = None,
        journal_style: JournalStyle = JournalStyle.DEFAULT,
        **kwargs
    ) -> go.Figure:
        """Create heatmap (typically for correlation matrix)."""
        # Validate columns
        for col in columns:
            if col not in df.columns:
                raise VisualizationException(f"Column '{col}' not found")
        
        # Compute correlation or use data directly
        if kwargs.get("is_correlation", False):
            matrix_df = df[columns].corr()
        else:
            if row_column and row_column in df.columns:
                matrix_df = df.set_index(row_column)[columns]
            else:
                matrix_df = df[columns]
        
        # Determine zmid for colorscale centering
        zmid = 0 if center_at_zero else None
        
        # Create heatmap
        fig = go.Figure(data=go.Heatmap(
            z=matrix_df.values,
            x=matrix_df.columns,
            y=matrix_df.index,
            colorscale=colorscale,
            zmid=zmid,
            text=matrix_df.round(2).values if show_values else None,
            texttemplate="%{text}" if show_values else None,
            textfont={"size": 10},
            hoverongaps=False
        ))
        
        # Add title
        if title:
            fig.update_layout(title=title)
        
        # Apply journal style
        fig = self._apply_journal_style(fig, journal_style, title)
        
        fig.update_layout(
            width=kwargs.get("width", self.default_width),
            height=kwargs.get("height", self.default_height),
            xaxis={"side": "bottom"}
        )
        
        return fig
    
    # ==================== Paired Line Plot ====================
    
    def create_paired(
        self,
        df: pd.DataFrame,
        subject_column: str,
        condition_column: str,
        value_column: str,
        title: Optional[str] = None,
        journal_style: JournalStyle = JournalStyle.DEFAULT,
        **kwargs
    ) -> go.Figure:
        """Create paired line plot (before/after comparison)."""
        if subject_column not in df.columns:
            raise VisualizationException(f"Subject column '{subject_column}' not found")
        if condition_column not in df.columns:
            raise VisualizationException(f"Condition column '{condition_column}' not found")
        if value_column not in df.columns:
            raise VisualizationException(f"Value column '{value_column}' not found")
        
        # Get conditions
        conditions = df[condition_column].unique()
        if len(conditions) != 2:
            raise VisualizationException(
                f"Paired plot requires exactly 2 conditions, found {len(conditions)}"
            )
        
        # Prepare data
        palette = self._get_palette(journal_style)
        
        fig = go.Figure()
        
        # Add individual lines
        for subject in df[subject_column].unique():
            subject_data = df[df[subject_column] == subject]
            if len(subject_data) == 2:
                fig.add_trace(go.Scatter(
                    x=subject_data[condition_column],
                    y=subject_data[value_column],
                    mode="lines+markers",
                    line=dict(color="gray", width=kwargs.get("line_width", 1)),
                    marker=dict(size=kwargs.get("marker_size", 6)),
                    showlegend=False,
                    opacity=0.5
                ))
        
        # Add mean line
        mean_data = df.groupby(condition_column)[value_column].mean()
        fig.add_trace(go.Scatter(
            x=mean_data.index,
            y=mean_data.values,
            mode="lines+markers",
            name="Mean",
            line=dict(
                color=kwargs.get("mean_line_color", "red"),
                width=kwargs.get("mean_line_width", 3)
            ),
            marker=dict(size=kwargs.get("marker_size", 10))
        ))
        
        # Update layout
        fig.update_layout(
            title=title,
            xaxis_title=condition_column,
            yaxis_title=value_column,
            width=kwargs.get("width", self.default_width),
            height=kwargs.get("height", self.default_height)
        )
        
        # Apply journal style
        fig = self._apply_journal_style(fig, journal_style, title)
        
        return fig
    
    # ==================== Histogram ====================
    
    def create_histogram(
        self,
        df: pd.DataFrame,
        column: str,
        group_column: Optional[str] = None,
        bins: int = 30,
        show_density: bool = False,
        title: Optional[str] = None,
        journal_style: JournalStyle = JournalStyle.DEFAULT,
        **kwargs
    ) -> go.Figure:
        """Create histogram."""
        if column not in df.columns:
            raise VisualizationException(f"Column '{column}' not found")
        
        fig = px.histogram(
            df,
            x=column,
            color=group_column if group_column and group_column in df.columns else None,
            nbins=bins,
            title=title,
            opacity=kwargs.get("opacity", 0.7),
            marginal="box" if kwargs.get("show_box", True) else None
        )
        
        # Apply journal style
        fig = self._apply_journal_style(fig, journal_style, title)
        
        fig.update_layout(
            width=kwargs.get("width", self.default_width),
            height=kwargs.get("height", self.default_height),
            bargap=0.1
        )
        
        return fig
    
    # ==================== Export Functions ====================
    
    def export_figure(
        self,
        fig: go.Figure,
        filename: str,
        format: str = "png",
        width: Optional[int] = None,
        height: Optional[int] = None,
        scale: float = 2.0
    ) -> str:
        """Export figure to file."""
        output_path = self.export_dir / f"{filename}.{format}"
        
        if format == "html":
            fig.write_html(str(output_path))
        else:
            fig.write_image(
                str(output_path),
                width=width,
                height=height,
                scale=scale
            )
        
        return str(output_path)
    
    def figure_to_json(self, fig: go.Figure) -> Dict[str, Any]:
        """Convert figure to JSON-serializable dict."""
        return safe_json_serialize(fig.to_plotly_json())


# Singleton instance
visualization_service = VisualizationService()
