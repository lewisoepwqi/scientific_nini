"""Matplotlib 图表代码模板：生成可独立运行的绘图脚本。

设计原则：
- 自包含（D1 内联）：只依赖 pandas / numpy / matplotlib，生成脚本不 import nini.*。
- 字节等价（D2 完全替代）：exec(template) 产出的 Figure savefig PNG 字节
  必须与原 visualization._create_matplotlib_figure 路径一致。
"""

from __future__ import annotations

from typing import Any

from nini.charts.style_contract import ChartStyleSpec
from nini.utils.chart_fonts import get_matplotlib_font_list, with_cjk_font_fallback


def _fmt_literal(value: Any) -> str:
    return repr(value)


def _build_style_header(spec: ChartStyleSpec, title: str | None) -> str:
    font_family = with_cjk_font_fallback(spec.font_family)
    font_list = get_matplotlib_font_list(spec.font_family)
    palette = list(spec.colors)
    return (
        f"_TITLE = {_fmt_literal(title)}\n"
        f"_FIGSIZE = {_fmt_literal(tuple(spec.figure_size))}\n"
        f"_FONT_FAMILY = {_fmt_literal(font_family)}\n"
        f"_FONT_SIZE = {spec.font_size}\n"
        f"_LINE_WIDTH = {spec.line_width}\n"
        f"_PALETTE = {_fmt_literal(palette)}\n"
        f"_TEXT_COLOR = {_fmt_literal(spec.text_color)}\n"
        f"_AXIS_COLOR = {_fmt_literal(spec.axis_color)}\n"
        f"_TICK_COLOR = {_fmt_literal(spec.tick_color)}\n"
        f"_GRID_COLOR = {_fmt_literal(spec.grid_color)}\n"
        f"_BG_COLOR = {_fmt_literal(spec.background_color)}\n"
        f"_SHOW_GRID = {_fmt_literal(spec.show_grid)}\n"
        f"_AXES_SPINES_TOP = {_fmt_literal(spec.axes_spines_top)}\n"
        f"_AXES_SPINES_RIGHT = {_fmt_literal(spec.axes_spines_right)}\n"
        f"_TICK_MAJOR_WIDTH = {spec.tick_major_width}\n"
        f"_TICK_MAJOR_SIZE = {spec.tick_major_size}\n"
        f"_FONT_LIST = {_fmt_literal(font_list)}\n"
    )


_SETUP_BLOCK = """\
fig, ax = plt.subplots(figsize=_FIGSIZE)
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = _FONT_LIST
plt.rcParams["font.size"] = _FONT_SIZE
"""

_TITLE_BLOCK = """\
if _TITLE:
    ax.set_title(str(_TITLE))
"""

_APPLY_AXES_STYLE_BLOCK = """\
# === 应用轴级样式（内联 ChartStyleSpec.apply_matplotlib_axes）===
if not _SHOW_GRID:
    ax.grid(False)
else:
    ax.grid(True, color=_GRID_COLOR, linewidth=0.8, alpha=0.85)
for side in ("top", "right"):
    if side in ax.spines:
        show = _AXES_SPINES_TOP if side == "top" else _AXES_SPINES_RIGHT
        ax.spines[side].set_visible(show)
for side in ("left", "bottom"):
    if side in ax.spines:
        ax.spines[side].set_color(_AXIS_COLOR)
        ax.spines[side].set_linewidth(_TICK_MAJOR_WIDTH)
ax.tick_params(
    axis="both",
    colors=_TICK_COLOR,
    width=_TICK_MAJOR_WIDTH,
    length=_TICK_MAJOR_SIZE,
)
fig.tight_layout()
"""

_PREPARE_LINE_HELPER = '''\
def _prepare_line_dataframe(df, x_col):
    """为折线图准备可排序数据（内联自 visualization._prepare_line_dataframe）。"""
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
    x_lit = _fmt_literal(x_col)
    y_lit = _fmt_literal(y_col)
    c_lit = _fmt_literal(color_col)
    body = (
        f"if {c_lit}:\n"
        f"    for idx, (label, part) in enumerate(df.groupby({c_lit}, dropna=False)):\n"
        "        ax.scatter(\n"
        f"            part[{x_lit}],\n"
        f"            part[{y_lit}],\n"
        "            s=20,\n"
        "            alpha=0.9,\n"
        "            label=str(label),\n"
        "            color=_PALETTE[idx % len(_PALETTE)],\n"
        "        )\n"
        "    ax.legend(frameon=False)\n"
        "else:\n"
        f"    ax.scatter(df[{x_lit}], df[{y_lit}], s=20, alpha=0.9, color=_PALETTE[0])\n"
        f"ax.set_xlabel(str({x_lit}))\n"
        f"ax.set_ylabel(str({y_lit}))\n"
    )
    return "", body


def _render_line(params: dict[str, Any]) -> tuple[str, str]:
    x_col = params.get("x_column")
    y_col = params.get("y_column")
    color_col = params.get("color_column")
    if not x_col or not y_col:
        raise ValueError("line 需要 x_column 和 y_column")
    x_lit = _fmt_literal(x_col)
    y_lit = _fmt_literal(y_col)
    c_lit = _fmt_literal(color_col)
    body = (
        f"plot_df = _prepare_line_dataframe(df, {x_lit})\n"
        f"if {c_lit}:\n"
        f"    for idx, (label, part) in enumerate(plot_df.groupby({c_lit}, dropna=False)):\n"
        "        ax.plot(\n"
        f"            part[{x_lit}],\n"
        f"            part[{y_lit}],\n"
        "            marker='o',\n"
        "            linewidth=_LINE_WIDTH,\n"
        "            markersize=4,\n"
        "            label=str(label),\n"
        "            color=_PALETTE[idx % len(_PALETTE)],\n"
        "        )\n"
        "    ax.legend(frameon=False)\n"
        "else:\n"
        "    ax.plot(\n"
        f"        plot_df[{x_lit}],\n"
        f"        plot_df[{y_lit}],\n"
        "        marker='o',\n"
        "        linewidth=_LINE_WIDTH,\n"
        "        markersize=4,\n"
        "        color=_PALETTE[0],\n"
        "    )\n"
        f"ax.set_xlabel(str({x_lit}))\n"
        f"ax.set_ylabel(str({y_lit}))\n"
    )
    return _PREPARE_LINE_HELPER, body


def _render_bar(params: dict[str, Any]) -> tuple[str, str]:
    x_col = params.get("x_column")
    y_col = params.get("y_column")
    group_col = params.get("group_column")
    if not x_col:
        raise ValueError("bar 需要 x_column")
    x_lit = _fmt_literal(x_col)
    g_lit = _fmt_literal(group_col)
    if y_col:
        y_lit = _fmt_literal(y_col)
        body = (
            f"_group_keys = [{x_lit}] + ([{g_lit}] if {g_lit} else [])\n"
            "_grouped = (\n"
            f"    df[_group_keys + [{y_lit}]]\n"
            "    .dropna()\n"
            f"    .groupby(_group_keys, as_index=False)[{y_lit}]\n"
            "    .mean()\n"
            ")\n"
            f"if {g_lit}:\n"
            f"    _pivot = _grouped.pivot(index={x_lit}, columns={g_lit}, values={y_lit}).fillna(0)\n"
            "    _x = np.arange(len(_pivot.index))\n"
            "    _groups = list(_pivot.columns)\n"
            "    _width = 0.8 / max(1, len(_groups))\n"
            "    for idx, label in enumerate(_groups):\n"
            "        offset = (idx - (len(_groups) - 1) / 2.0) * _width\n"
            "        ax.bar(\n"
            "            _x + offset,\n"
            "            _pivot[label].values,\n"
            "            width=_width,\n"
            "            color=_PALETTE[idx % len(_PALETTE)],\n"
            "            label=str(label),\n"
            "        )\n"
            "    ax.set_xticks(_x)\n"
            "    ax.set_xticklabels([str(v) for v in _pivot.index.tolist()])\n"
            "    ax.legend(frameon=False)\n"
            "else:\n"
            "    ax.bar(\n"
            f"        _grouped[{x_lit}].astype(str),\n"
            f"        _grouped[{y_lit}],\n"
            "        color=_PALETTE[0],\n"
            "    )\n"
            f"ax.set_ylabel(str({y_lit}))\n"
        )
    else:
        body = (
            "_count_df = (\n"
            f"    df[{x_lit}].dropna().value_counts().rename_axis({x_lit}).reset_index(name='count')\n"
            ")\n"
            f"ax.bar(_count_df[{x_lit}].astype(str), _count_df['count'], color=_PALETTE[0])\n"
            "ax.set_ylabel('count')\n"
        )
    body += f"ax.set_xlabel(str({x_lit}))\n"
    return "", body


def _render_box(params: dict[str, Any]) -> tuple[str, str]:
    x_col = params.get("x_column")
    y_col = params.get("y_column")
    group_col = params.get("group_column")
    value_col = y_col or x_col
    if not value_col:
        raise ValueError("box 需要 y_column 或 x_column 作为数值列")
    category_col = group_col if group_col else (x_col if x_col != value_col else None)
    v_lit = _fmt_literal(value_col)
    cat_lit = _fmt_literal(category_col)
    body = (
        f"_value_col = {v_lit}\n"
        f"_category_col = {cat_lit}\n"
        "if _category_col:\n"
        "    _grouped_values = [\n"
        "        part[_value_col].dropna().to_list()\n"
        "        for _, part in df.groupby(_category_col, dropna=False)\n"
        "    ]\n"
        "    _labels = [str(label) for label, _ in df.groupby(_category_col, dropna=False)]\n"
        "    bp = ax.boxplot(_grouped_values, patch_artist=True, tick_labels=_labels)\n"
        "    for idx, patch in enumerate(bp['boxes']):\n"
        "        patch.set_facecolor(_PALETTE[idx % len(_PALETTE)])\n"
        "        patch.set_alpha(0.8)\n"
        "else:\n"
        "    bp = ax.boxplot(\n"
        "        [df[_value_col].dropna().to_list()],\n"
        "        patch_artist=True,\n"
        "        tick_labels=[_value_col],\n"
        "    )\n"
        "    bp['boxes'][0].set_facecolor(_PALETTE[0])\n"
        "ax.set_ylabel(str(_value_col))\n"
        "ax.set_xlabel(str(_category_col or 'group'))\n"
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
    v_lit = _fmt_literal(value_col)
    cat_lit = _fmt_literal(category_col)
    body = (
        f"_value_col = {v_lit}\n"
        f"_category_col = {cat_lit}\n"
        "if _category_col:\n"
        "    _grouped_values = [\n"
        "        part[_value_col].dropna().to_list()\n"
        "        for _, part in df.groupby(_category_col, dropna=False)\n"
        "    ]\n"
        "    _labels = [str(label) for label, _ in df.groupby(_category_col, dropna=False)]\n"
        "    _positions = list(range(1, len(_grouped_values) + 1))\n"
        "    vp = ax.violinplot(\n"
        "        _grouped_values, positions=_positions, showmeans=False, showextrema=True\n"
        "    )\n"
        "    for idx, body in enumerate(vp['bodies']):\n"
        "        body.set_facecolor(_PALETTE[idx % len(_PALETTE)])\n"
        "        body.set_alpha(0.7)\n"
        "    ax.set_xticks(_positions)\n"
        "    ax.set_xticklabels(_labels)\n"
        "else:\n"
        "    vp = ax.violinplot(\n"
        "        [df[_value_col].dropna().to_list()], showmeans=False, showextrema=True\n"
        "    )\n"
        "    for body in vp['bodies']:\n"
        "        body.set_facecolor(_PALETTE[0])\n"
        "        body.set_alpha(0.7)\n"
        "    ax.set_xticks([1])\n"
        "    ax.set_xticklabels([_value_col])\n"
        "ax.set_ylabel(str(_value_col))\n"
        "ax.set_xlabel(str(_category_col or 'group'))\n"
    )
    return "", body


def _render_histogram(params: dict[str, Any]) -> tuple[str, str]:
    x_col = params.get("x_column")
    color_col = params.get("color_column")
    if not x_col:
        raise ValueError("histogram 需要 x_column")
    bins = int(params.get("bins", 20))
    x_lit = _fmt_literal(x_col)
    c_lit = _fmt_literal(color_col)
    body = (
        f"_bins = {bins}\n"
        f"if {c_lit}:\n"
        f"    for idx, (label, part) in enumerate(df.groupby({c_lit}, dropna=False)):\n"
        "        ax.hist(\n"
        f"            part[{x_lit}].dropna(),\n"
        "            bins=_bins,\n"
        "            alpha=0.55,\n"
        "            label=str(label),\n"
        "            color=_PALETTE[idx % len(_PALETTE)],\n"
        "        )\n"
        "    ax.legend(frameon=False)\n"
        "else:\n"
        f"    ax.hist(df[{x_lit}].dropna(), bins=_bins, color=_PALETTE[0], alpha=0.85)\n"
        f"ax.set_xlabel(str({x_lit}))\n"
        "ax.set_ylabel('frequency')\n"
    )
    return "", body


def _render_heatmap(params: dict[str, Any]) -> tuple[str, str]:
    columns = params.get("columns") or []
    columns_lit = _fmt_literal(list(columns))
    body = (
        f"_columns = {columns_lit} or df.select_dtypes(include='number').columns.tolist()[:20]\n"
        "if len(_columns) < 2:\n"
        "    raise ValueError('heatmap 至少需要两列数值列')\n"
        "_corr = df[_columns].corr(numeric_only=True)\n"
        "im = ax.imshow(_corr.values, cmap='RdBu_r', vmin=-1, vmax=1)\n"
        "ax.set_xticks(range(len(_columns)))\n"
        "ax.set_yticks(range(len(_columns)))\n"
        "ax.set_xticklabels(_columns, rotation=45, ha='right')\n"
        "ax.set_yticklabels(_columns)\n"
        "fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)\n"
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


def render_matplotlib_script(
    chart_type: str,
    params: dict[str, Any],
    spec: ChartStyleSpec,
    title: str | None = None,
    data_loader: str = "",
) -> str:
    """生成一段可独立执行的 Matplotlib 绘图脚本。

    Exec 后 namespace 中会提供 `fig` 变量；脚本假定 `df` 已由调用方准备。
    """
    builder = _CHART_BUILDERS.get(chart_type)
    if builder is None:
        raise ValueError(f"暂未支持的图表类型: {chart_type}")

    helper_block, chart_body = builder(params)

    header = (
        '"""Auto-generated chart script. Reproducible via `python this_file.py`."""\n'
        "from __future__ import annotations\n"
        "\n"
        "import matplotlib.pyplot as plt\n"
        "import numpy as np\n"
        "import pandas as pd\n"
        "\n"
    )
    data_block = f"# === 数据加载 ===\n{data_loader}\n\n" if data_loader else ""
    helper_section = f"# === 辅助函数 ===\n{helper_block}" if helper_block else ""
    style_header = (
        "# === 样式参数（内联自 ChartStyleSpec）===\n" + _build_style_header(spec, title) + "\n"
    )
    setup = "# === 画布与 rcParams ===\n" + _SETUP_BLOCK + "\n"
    chart = "# === 绘图 ===\n" + chart_body + "\n"
    return (
        header
        + data_block
        + helper_section
        + style_header
        + setup
        + chart
        + _TITLE_BLOCK
        + _APPLY_AXES_STYLE_BLOCK
    )
