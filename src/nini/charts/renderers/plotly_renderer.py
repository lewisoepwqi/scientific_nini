"""Plotly 渲染器适配。"""

from __future__ import annotations

from typing import Any

from nini.charts.style_contract import ChartStyleSpec


def apply_plotly_style(fig: Any, spec: ChartStyleSpec, title: str | None = None) -> None:
    """对 Plotly Figure 应用统一风格。"""
    fig.update_layout(**spec.to_plotly_layout(title=title))
    fig.update_xaxes(
        showgrid=spec.show_grid,
        gridcolor=spec.grid_color,
        zeroline=False,
        showline=True,
        linecolor=spec.axis_color,
        tickcolor=spec.axis_color,
        ticks="outside",
    )
    fig.update_yaxes(
        showgrid=spec.show_grid,
        gridcolor=spec.grid_color,
        zeroline=False,
        showline=True,
        linecolor=spec.axis_color,
        tickcolor=spec.axis_color,
        ticks="outside",
    )
