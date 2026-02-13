"""图表渲染器适配层。"""

from nini.charts.renderers.matplotlib_renderer import (
    apply_matplotlib_axes_style,
    apply_matplotlib_rc_style,
)
from nini.charts.renderers.plotly_renderer import apply_plotly_style

__all__ = [
    "apply_plotly_style",
    "apply_matplotlib_rc_style",
    "apply_matplotlib_axes_style",
]
