"""Plotly 图表代码模板：生成可独立运行的绘图脚本。

设计原则：
- 自包含（D1 内联）：生成脚本只依赖 pandas / plotly，不 import nini.*。
- 字节等价（D2 完全替代）：exec(template) 产出的 fig.to_plotly_json() 必须与
  原 visualization._create_plotly_figure + apply_plotly_style 完全一致。

为保证等价性，样式参数在生成时解析为字面值（如字体回退链、配色），
避免运行时依赖外部状态。
"""

from __future__ import annotations

from typing import Any

from nini.charts.style_contract import ChartStyleSpec
from nini.utils.chart_fonts import with_cjk_font_fallback


def _fmt_literal(value: Any) -> str:
    """把 Python 值序列化为源码字面值。"""
    return repr(value)


def _build_style_header(spec: ChartStyleSpec, title: str | None) -> str:
    """生成内联样式常量块。与 ChartStyleSpec.to_plotly_layout 等价。"""
    font_family = with_cjk_font_fallback(spec.font_family)
    palette = list(spec.colors)
    return (
        f"_TITLE = {_fmt_literal(title)}\n"
        f"_FONT_FAMILY = {_fmt_literal(font_family)}\n"
        f"_FONT_SIZE = {spec.font_size}\n"
        f"_TEXT_COLOR = {_fmt_literal(spec.text_color)}\n"
        f"_AXIS_COLOR = {_fmt_literal(spec.axis_color)}\n"
        f"_TICK_COLOR = {_fmt_literal(spec.tick_color)}\n"
        f"_GRID_COLOR = {_fmt_literal(spec.grid_color)}\n"
        f"_BG_COLOR = {_fmt_literal(spec.background_color)}\n"
        f"_SHOW_GRID = {_fmt_literal(spec.show_grid)}\n"
        f"_PALETTE = {_fmt_literal(palette)}\n"
    )


_APPLY_STYLE_BLOCK = """\
# === 应用统一风格（内联 apply_plotly_style）===
fig.update_layout(
    title=_TITLE,
    font={'family': _FONT_FAMILY, 'size': _FONT_SIZE, 'color': _TEXT_COLOR},
    colorway=_PALETTE,
    paper_bgcolor=_BG_COLOR,
    plot_bgcolor=_BG_COLOR,
    legend={'title': None},
    margin={'l': 56, 'r': 24, 't': 56, 'b': 48},
)
fig.update_xaxes(
    showgrid=_SHOW_GRID,
    gridcolor=_GRID_COLOR,
    zeroline=False,
    showline=True,
    linecolor=_AXIS_COLOR,
    tickcolor=_AXIS_COLOR,
    ticks='outside',
)
fig.update_yaxes(
    showgrid=_SHOW_GRID,
    gridcolor=_GRID_COLOR,
    zeroline=False,
    showline=True,
    linecolor=_AXIS_COLOR,
    tickcolor=_AXIS_COLOR,
    ticks='outside',
)
"""


_PREPARE_LINE_HELPER = '''\
def _prepare_line_dataframe(df, x_col):
    """为折线图准备可排序数据（内联自 nini.tools.visualization._prepare_line_dataframe）。"""
    plot_df = df.copy()
    try:
        return plot_df.sort_values(by=x_col, kind="mergesort")
    except TypeError:
        pass
    coerced = pd.to_datetime(plot_df[x_col], errors="coerce")
    non_null = int(plot_df[x_col].notna().sum())
    parsed_non_null = int(coerced.notna().sum())
    if non_null > 0 and (parsed_non_null / non_null) >= 0.8:
        return plot_df.assign(**{x_col: coerced}).sort_values(by=x_col, kind="mergesort")
    sort_key = plot_df[x_col].map(lambda v: "" if pd.isna(v) else str(v))
    return (
        plot_df.assign(__x_sort_key=sort_key)
        .sort_values(by="__x_sort_key", kind="mergesort")
        .drop(columns=["__x_sort_key"])
    )

'''


def _render_scatter(params: dict[str, Any]) -> tuple[str, str]:
    x_col = params.get("x_column")
    y_col = params.get("y_column")
    color_col = params.get("color_column")
    if not x_col or not y_col:
        raise ValueError("scatter 需要 x_column 和 y_column")
    body = (
        "fig = px.scatter(\n"
        "    df,\n"
        f"    x={_fmt_literal(x_col)},\n"
        f"    y={_fmt_literal(y_col)},\n"
        f"    color={_fmt_literal(color_col)},\n"
        "    color_discrete_sequence=_PALETTE,\n"
        ")\n"
    )
    return "", body


def _render_line(params: dict[str, Any]) -> tuple[str, str]:
    x_col = params.get("x_column")
    y_col = params.get("y_column")
    color_col = params.get("color_column")
    if not x_col or not y_col:
        raise ValueError("line 需要 x_column 和 y_column")
    body = (
        f"plot_df = _prepare_line_dataframe(df, {_fmt_literal(x_col)})\n"
        "fig = px.line(\n"
        "    plot_df,\n"
        f"    x={_fmt_literal(x_col)},\n"
        f"    y={_fmt_literal(y_col)},\n"
        f"    color={_fmt_literal(color_col)},\n"
        "    color_discrete_sequence=_PALETTE,\n"
        ")\n"
    )
    return _PREPARE_LINE_HELPER, body


def _render_bar(params: dict[str, Any]) -> tuple[str, str]:
    x_col = params.get("x_column")
    y_col = params.get("y_column")
    group_col = params.get("group_column")
    if not x_col:
        raise ValueError("bar 需要 x_column")
    x_lit = _fmt_literal(x_col)
    if y_col:
        y_lit = _fmt_literal(y_col)
        g_lit = _fmt_literal(group_col)
        body = (
            f"_group_keys = [{x_lit}] + ([{g_lit}] if {g_lit} else [])\n"
            f"_grouped = (\n"
            f"    df[_group_keys + [{y_lit}]]\n"
            "    .dropna()\n"
            f"    .groupby(_group_keys, as_index=False)[{y_lit}]\n"
            "    .mean()\n"
            ")\n"
            "fig = px.bar(\n"
            "    _grouped,\n"
            f"    x={x_lit},\n"
            f"    y={y_lit},\n"
            f"    color={g_lit},\n"
            "    barmode='group',\n"
            "    color_discrete_sequence=_PALETTE,\n"
            ")\n"
        )
    else:
        body = (
            f"_count_df = (\n"
            f"    df[{x_lit}].dropna().value_counts().rename_axis({x_lit}).reset_index(name='count')\n"
            ")\n"
            f"fig = px.bar(_count_df, x={x_lit}, y='count', color_discrete_sequence=_PALETTE)\n"
        )
    return "", body


def _render_box(params: dict[str, Any]) -> tuple[str, str]:
    x_col = params.get("x_column")
    y_col = params.get("y_column")
    group_col = params.get("group_column")
    value_col = y_col or x_col
    if not value_col:
        raise ValueError("box 需要 y_column 或 x_column 作为数值列")
    category_col = group_col if group_col else (x_col if x_col != value_col else None)
    body = (
        "fig = px.box(\n"
        "    df,\n"
        f"    x={_fmt_literal(category_col)},\n"
        f"    y={_fmt_literal(value_col)},\n"
        "    points='all',\n"
        f"    color={_fmt_literal(group_col)},\n"
        "    color_discrete_sequence=_PALETTE,\n"
        ")\n"
    )
    return "", body


def _render_violin(params: dict[str, Any]) -> tuple[str, str]:
    x_col = params.get("x_column")
    y_col = params.get("y_column")
    group_col = params.get("group_column")
    value_col = y_col or x_col
    if not value_col:
        raise ValueError("violin 需要 y_column 或 x_column 作为数值列")
    category_col = group_col if group_col else (x_col if x_col != value_col else None)
    body = (
        "fig = px.violin(\n"
        "    df,\n"
        f"    x={_fmt_literal(category_col)},\n"
        f"    y={_fmt_literal(value_col)},\n"
        "    box=True,\n"
        "    points=False,\n"
        f"    color={_fmt_literal(group_col)},\n"
        "    color_discrete_sequence=_PALETTE,\n"
        ")\n"
    )
    return "", body


def _render_histogram(params: dict[str, Any]) -> tuple[str, str]:
    x_col = params.get("x_column")
    color_col = params.get("color_column")
    if not x_col:
        raise ValueError("histogram 需要 x_column")
    nbins = int(params.get("bins", 20))
    body = (
        "fig = px.histogram(\n"
        "    df,\n"
        f"    x={_fmt_literal(x_col)},\n"
        f"    color={_fmt_literal(color_col)},\n"
        f"    nbins={nbins},\n"
        "    color_discrete_sequence=_PALETTE,\n"
        ")\n"
    )
    return "", body


def _render_heatmap(params: dict[str, Any]) -> tuple[str, str]:
    columns = params.get("columns") or []
    # 列为空时按数值列自动取前 20 列——与 _create_plotly_figure 行为一致。
    # 在模板中延迟到运行时解析，以保证对任意 df 都可复现。
    columns_lit = _fmt_literal(list(columns))
    body = (
        f"_columns = {columns_lit} or df.select_dtypes(include='number').columns.tolist()[:20]\n"
        "if len(_columns) < 2:\n"
        "    raise ValueError('heatmap 至少需要两列数值列')\n"
        "_corr = df[_columns].corr(numeric_only=True)\n"
        "fig = px.imshow(\n"
        "    _corr,\n"
        "    text_auto=True,\n"
        "    color_continuous_scale='RdBu',\n"
        "    zmin=-1,\n"
        "    zmax=1,\n"
        ")\n"
    )
    return "", body


_CHART_BUILDERS = {
    "scatter": _render_scatter,
    "line": _render_line,
    "bar": _render_bar,
    "box": _render_box,
    "violin": _render_violin,
    "histogram": _render_histogram,
    "heatmap": _render_heatmap,
}


def render_plotly_script(
    chart_type: str,
    params: dict[str, Any],
    spec: ChartStyleSpec,
    title: str | None = None,
    data_loader: str = "",
) -> str:
    """生成一段可独立执行的 Plotly 绘图脚本。

    参数:
        chart_type: scatter / line / bar / box / violin / histogram / heatmap
        params: 列映射与可选参数（x_column/y_column/color_column/group_column/columns/bins）
        spec: ChartStyleSpec，用于内联样式常量
        title: 图表标题，允许为 None
        data_loader: 数据加载代码片段（如 "df = pd.read_csv('data.csv')"）。
                     留空时脚本假定调用方已在 namespace 中准备好 df。
    """
    builder = _CHART_BUILDERS.get(chart_type)
    if builder is None:
        raise ValueError(f"暂未支持的图表类型: {chart_type}")

    helper_block, chart_body = builder(params)

    header = (
        '"""Auto-generated chart script. Reproducible via `python this_file.py`."""\n'
        "from __future__ import annotations\n"
        "\n"
        "import pandas as pd\n"
        "import plotly.express as px\n"
        "import plotly.graph_objects as go\n"
        "\n"
    )
    data_block = f"# === 数据加载 ===\n{data_loader}\n\n" if data_loader else ""
    helper_section = f"# === 辅助函数 ===\n{helper_block}" if helper_block else ""
    style_header = (
        "# === 样式参数（内联自 ChartStyleSpec）===\n" + _build_style_header(spec, title) + "\n"
    )
    chart_block = "# === 绘图 ===\n" + chart_body + "\n"
    return header + data_block + helper_section + style_header + chart_block + _APPLY_STYLE_BLOCK
