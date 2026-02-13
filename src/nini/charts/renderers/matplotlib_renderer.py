"""Matplotlib 渲染器适配。"""

from __future__ import annotations

from typing import Any

from nini.charts.style_contract import ChartStyleSpec


def apply_matplotlib_rc_style(rc_params: Any, spec: ChartStyleSpec) -> None:
    """应用 Matplotlib 全局风格。"""
    spec.apply_matplotlib_rc(rc_params)


def apply_matplotlib_axes_style(ax: Any, spec: ChartStyleSpec) -> None:
    """应用 Matplotlib 轴级风格。"""
    spec.apply_matplotlib_axes(ax)
