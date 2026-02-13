"""统一图表风格契约。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nini.config import settings
from nini.skills.templates.journal_styles import get_template, get_template_names
from nini.utils.chart_fonts import CJK_FONT_FAMILY, with_cjk_font_fallback

_SUPPORTED_ENGINES = {"auto", "plotly", "matplotlib"}


def parse_export_formats(raw: str | None) -> list[str]:
    """解析导出格式配置，自动去重并保留顺序。"""
    values = [part.strip().lower() for part in (raw or "").split(",") if part.strip()]
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    if not result:
        return ["pdf", "svg", "png"]
    return result


def normalize_render_engine(engine: str | None) -> str:
    """归一化渲染引擎，非法值回退到配置默认值。"""
    normalized = (engine or "").strip().lower()
    if normalized in _SUPPORTED_ENGINES:
        return normalized
    default_engine = str(settings.chart_default_render_engine or "auto").strip().lower()
    return default_engine if default_engine in _SUPPORTED_ENGINES else "auto"


@dataclass(frozen=True)
class ChartStyleSpec:
    """图表风格契约。

    该对象作为 Plotly / Matplotlib 的统一输入，不直接依赖具体绘图库。
    """

    style_key: str
    font_family: str
    font_size: int
    line_width: float
    dpi: int
    figure_size: tuple[float, float]
    colors: tuple[str, ...]
    text_color: str = "#111827"
    axis_color: str = "#9CA3AF"
    tick_color: str = "#374151"
    grid_color: str = "#E5E7EB"
    background_color: str = "#FFFFFF"
    show_grid: bool = True
    axes_spines_top: bool = False
    axes_spines_right: bool = False
    tick_major_width: float = 0.8
    tick_major_size: float = 3.0
    export_formats: tuple[str, ...] = ("pdf", "svg", "png")

    def to_plotly_layout(self, title: str | None = None) -> dict[str, Any]:
        """转换为 Plotly layout 参数。"""
        layout: dict[str, Any] = {
            "title": title,
            "font": {
                "family": with_cjk_font_fallback(self.font_family),
                "size": self.font_size,
                "color": self.text_color,
            },
            "colorway": list(self.colors),
            "paper_bgcolor": self.background_color,
            "plot_bgcolor": self.background_color,
            "legend": {"title": None},
            "margin": {"l": 56, "r": 24, "t": 56, "b": 48},
        }
        return layout

    def apply_matplotlib_rc(self, rc_params: Any) -> None:
        """应用 Matplotlib rcParams。"""
        rc_params["font.family"] = "sans-serif"
        rc_params["font.sans-serif"] = [
            part.strip() for part in with_cjk_font_fallback(self.font_family).split(",")
        ]
        rc_params["font.size"] = self.font_size
        rc_params["axes.titlesize"] = max(9, self.font_size)
        rc_params["axes.labelsize"] = max(8, self.font_size - 1)
        rc_params["xtick.labelsize"] = max(7, self.font_size - 2)
        rc_params["ytick.labelsize"] = max(7, self.font_size - 2)
        rc_params["legend.fontsize"] = max(7, self.font_size - 2)
        rc_params["axes.linewidth"] = self.tick_major_width
        rc_params["lines.linewidth"] = self.line_width
        rc_params["xtick.major.width"] = self.tick_major_width
        rc_params["ytick.major.width"] = self.tick_major_width
        rc_params["xtick.major.size"] = self.tick_major_size
        rc_params["ytick.major.size"] = self.tick_major_size
        rc_params["axes.spines.top"] = self.axes_spines_top
        rc_params["axes.spines.right"] = self.axes_spines_right
        rc_params["axes.facecolor"] = self.background_color
        rc_params["figure.facecolor"] = self.background_color
        rc_params["axes.edgecolor"] = self.axis_color
        rc_params["axes.labelcolor"] = self.text_color
        rc_params["xtick.color"] = self.tick_color
        rc_params["ytick.color"] = self.tick_color
        rc_params["axes.grid"] = self.show_grid
        rc_params["grid.color"] = self.grid_color
        rc_params["grid.linewidth"] = 0.8
        rc_params["grid.alpha"] = 0.85
        rc_params["savefig.dpi"] = self.dpi
        rc_params["figure.dpi"] = 150
        rc_params["savefig.bbox"] = "tight"
        rc_params["savefig.pad_inches"] = 0.05

    def apply_matplotlib_axes(self, ax: Any) -> None:
        """应用 Matplotlib 轴级样式。"""
        if not self.show_grid:
            ax.grid(False)
        else:
            ax.grid(True, color=self.grid_color, linewidth=0.8, alpha=0.85)
        for side in ("top", "right"):
            if side in ax.spines:
                show = self.axes_spines_top if side == "top" else self.axes_spines_right
                ax.spines[side].set_visible(show)
        for side in ("left", "bottom"):
            if side in ax.spines:
                ax.spines[side].set_color(self.axis_color)
                ax.spines[side].set_linewidth(self.tick_major_width)
        ax.tick_params(
            axis="both",
            colors=self.tick_color,
            width=self.tick_major_width,
            length=self.tick_major_size,
        )


def build_style_spec(style: str | None = None) -> ChartStyleSpec:
    """根据模板构建统一风格契约。"""
    key = (style or settings.chart_default_style or "default").strip().lower()
    template = get_template(key)
    # 若模板不存在，get_template 会回退到 default
    available = {name.strip().lower() for name in get_template_names()}
    if key not in available:
        key = str(settings.chart_default_style or "default").strip().lower() or "default"
        template = get_template(key)

    font_family = str(template.get("font") or CJK_FONT_FAMILY)
    font_size = int(template.get("font_size") or 12)
    line_width = float(template.get("line_width") or 1.2)
    dpi = int(template.get("dpi") or settings.chart_bitmap_dpi or 300)
    figure_size_raw = template.get("figure_size") or [6.4, 4.8]
    if not isinstance(figure_size_raw, list | tuple) or len(figure_size_raw) != 2:
        figure_size_raw = [6.4, 4.8]
    figure_size = (float(figure_size_raw[0]), float(figure_size_raw[1]))

    colors_raw = template.get("colors") or []
    colors = tuple(str(c) for c in colors_raw if isinstance(c, str))
    if not colors:
        colors = ("#4477AA", "#EE6677", "#228833", "#CCBB44", "#66CCEE", "#AA3377", "#BBBBBB")

    return ChartStyleSpec(
        style_key=key,
        font_family=font_family,
        font_size=font_size,
        line_width=line_width,
        dpi=max(300, dpi),
        figure_size=figure_size,
        colors=colors,
        export_formats=tuple(parse_export_formats(settings.chart_default_export_formats)),
    )
