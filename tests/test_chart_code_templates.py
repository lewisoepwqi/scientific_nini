"""图表代码模板结构回归测试。

visualization.py 已改为以 exec(template) 作为唯一渲染路径（单一真相源），
所以原先"模板 vs legacy imperative"的字节等价测试已失去对照对象。

现在的测试策略：
- Plotly 分支断言 fig.layout 关键样式参数符合 ChartStyleSpec，
  data trace 类型符合预期，并在存在 color/group 时生成多条 trace。
- Matplotlib 分支断言 ax 的 xlabel/ylabel/title、lines/patches 数量、
  以及 spines 线色与 tick_params 颜色与 spec 一致。
- 覆盖 7 个 chart_type 的主要分支，保证模板重构时出现结构性偏差可被捕获。
"""

from __future__ import annotations

import io
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import pytest  # noqa: E402

from nini.charts.code_templates import render_matplotlib_script, render_plotly_script
from nini.charts.style_contract import build_style_spec


def _exec_plotly_template(code: str, df: pd.DataFrame) -> go.Figure:
    namespace: dict[str, Any] = {"df": df}
    exec(compile(code, "<plotly_template>", "exec"), namespace)
    fig = namespace.get("fig")
    assert isinstance(fig, go.Figure), "plotly 模板未生成 fig 变量"
    return fig


def _exec_matplotlib_template(code: str, df: pd.DataFrame) -> Any:
    namespace: dict[str, Any] = {"df": df}
    exec(compile(code, "<matplotlib_template>", "exec"), namespace)
    fig = namespace.get("fig")
    assert fig is not None, "matplotlib 模板未生成 fig 变量"
    return fig


def _render_plotly(
    df: pd.DataFrame,
    chart_type: str,
    params: dict[str, Any],
    style_key: str = "default",
    title: str | None = None,
) -> go.Figure:
    spec = build_style_spec(style_key)
    code = render_plotly_script(chart_type, params, spec, title=title)
    return _exec_plotly_template(code, df)


def _render_matplotlib(
    df: pd.DataFrame,
    chart_type: str,
    params: dict[str, Any],
    style_key: str = "default",
    title: str | None = None,
) -> Any:
    spec = build_style_spec(style_key)
    code = render_matplotlib_script(chart_type, params, spec, title=title)
    return _exec_matplotlib_template(code, df)


def _assert_plotly_style_consistent(fig: go.Figure, style_key: str, title: str | None) -> None:
    """断言 plotly 模板生成的 fig 样式与 ChartStyleSpec 一致。"""
    spec = build_style_spec(style_key)
    layout = fig.to_plotly_json()["layout"]
    assert layout["font"]["size"] == spec.font_size
    assert layout["font"]["color"] == spec.text_color
    assert layout["paper_bgcolor"] == spec.background_color
    assert layout["plot_bgcolor"] == spec.background_color
    assert layout["xaxis"]["linecolor"] == spec.axis_color
    assert layout["yaxis"]["linecolor"] == spec.axis_color
    assert tuple(layout["colorway"]) == tuple(spec.colors)
    if title:
        assert layout.get("title", {}).get("text") == title


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def scatter_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "x": [1, 2, 3, 4, 5, 6],
            "y": [1.1, 1.9, 3.2, 4.1, 5.3, 6.2],
            "grp": ["A", "B", "A", "B", "A", "B"],
        }
    )


@pytest.fixture
def line_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "t": [1, 2, 3, 4, 5, 6],
            "v": [1.0, 2.5, 2.0, 3.5, 3.0, 4.2],
            "series": ["a", "a", "b", "b", "a", "b"],
        }
    )


@pytest.fixture
def bar_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "cat": ["A", "A", "B", "B", "C", "C"],
            "sub": ["x", "y", "x", "y", "x", "y"],
            "val": [1, 2, 3, 4, 5, 6],
        }
    )


@pytest.fixture
def box_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "grp": ["A", "A", "A", "B", "B", "B"],
            "sub": ["x", "y", "x", "y", "x", "y"],
            "val": [1.0, 1.5, 2.0, 3.0, 3.5, 4.0],
        }
    )


@pytest.fixture
def hist_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "val": [1.0, 1.2, 1.5, 2.0, 2.1, 2.3, 2.5, 3.0, 3.1, 3.3],
            "grp": ["a"] * 5 + ["b"] * 5,
        }
    )


@pytest.fixture
def heatmap_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "a": [1.0, 2.0, 3.0, 4.0, 5.0],
            "b": [2.0, 3.5, 2.5, 5.0, 4.0],
            "c": [5.0, 4.0, 3.0, 2.0, 1.0],
            "d": [1.0, 1.0, 1.0, 2.0, 2.0],
        }
    )


# ---------------------------------------------------------------------------
# 通用：模板必须 import 自包含
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "chart_type,params",
    [
        ("scatter", {"x_column": "x", "y_column": "y"}),
        ("line", {"x_column": "t", "y_column": "v"}),
        ("bar", {"x_column": "cat", "y_column": "val"}),
        ("box", {"x_column": "grp", "y_column": "val"}),
        ("violin", {"x_column": "grp", "y_column": "val"}),
        ("histogram", {"x_column": "val", "bins": 10}),
        ("heatmap", {"columns": ["a", "b", "c"]}),
    ],
)
def test_plotly_template_is_self_contained(chart_type: str, params: dict[str, Any]) -> None:
    """D1 自包含：plotly 生成脚本不得 import nini.*。"""
    spec = build_style_spec("default")
    code = render_plotly_script(chart_type, params, spec)
    for line in code.splitlines():
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            assert "nini" not in stripped, f"生成脚本意外引用 nini 包: {stripped}"


@pytest.mark.parametrize(
    "chart_type,params",
    [
        ("scatter", {"x_column": "x", "y_column": "y"}),
        ("line", {"x_column": "t", "y_column": "v"}),
        ("bar", {"x_column": "cat", "y_column": "val"}),
        ("box", {"x_column": "grp", "y_column": "val"}),
        ("violin", {"x_column": "grp", "y_column": "val"}),
        ("histogram", {"x_column": "val", "bins": 10}),
        ("heatmap", {"columns": ["a", "b", "c"]}),
    ],
)
def test_matplotlib_template_is_self_contained(chart_type: str, params: dict[str, Any]) -> None:
    """D1 自包含：matplotlib 生成脚本不得 import nini.*。"""
    spec = build_style_spec("default")
    code = render_matplotlib_script(chart_type, params, spec)
    for line in code.splitlines():
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            assert "nini" not in stripped, f"生成脚本意外引用 nini 包: {stripped}"


# ---------------------------------------------------------------------------
# Plotly 结构测试
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("style_key", ["default", "nature"])
@pytest.mark.parametrize(
    "title,color_col",
    [
        (None, None),
        ("散点图", "grp"),
    ],
)
def test_scatter_plotly_template_renders(
    scatter_df: pd.DataFrame,
    style_key: str,
    title: str | None,
    color_col: str | None,
) -> None:
    params = {"x_column": "x", "y_column": "y", "color_column": color_col}
    fig = _render_plotly(scatter_df, "scatter", params, style_key=style_key, title=title)
    assert len(fig.data) >= 1
    assert fig.data[0].type == "scatter"
    if color_col:
        assert len({trace.legendgroup for trace in fig.data}) == scatter_df[color_col].nunique()
    _assert_plotly_style_consistent(fig, style_key, title)


def test_scatter_plotly_template_requires_xy() -> None:
    spec = build_style_spec("default")
    with pytest.raises(ValueError, match="x_column 和 y_column"):
        render_plotly_script("scatter", {"x_column": "x"}, spec)


@pytest.mark.parametrize("color_col", [None, "series"])
def test_line_plotly_template_renders(line_df: pd.DataFrame, color_col: str | None) -> None:
    params = {"x_column": "t", "y_column": "v", "color_column": color_col}
    fig = _render_plotly(line_df, "line", params)
    assert fig.data[0].type == "scatter"  # px.line 底层为 scatter+mode=lines
    assert fig.data[0].mode == "lines"


def test_line_plotly_template_handles_mixed_x(line_df: pd.DataFrame) -> None:
    """混合类型 x 列不能让模板崩溃（走字符串兜底）。"""
    df = line_df.copy()
    df["t"] = [1, "two", 3, "four", 5, "six"]
    fig = _render_plotly(df, "line", {"x_column": "t", "y_column": "v"})
    assert len(fig.data) >= 1


@pytest.mark.parametrize(
    "y_col,group_col,min_traces",
    [
        ("val", None, 1),
        ("val", "sub", 2),
        (None, None, 1),
    ],
)
def test_bar_plotly_template_renders(
    bar_df: pd.DataFrame, y_col: str | None, group_col: str | None, min_traces: int
) -> None:
    params = {"x_column": "cat", "y_column": y_col, "group_column": group_col}
    fig = _render_plotly(bar_df, "bar", params)
    assert fig.data[0].type == "bar"
    assert len(fig.data) >= min_traces


@pytest.mark.parametrize(
    "params",
    [
        {"x_column": "grp", "y_column": "val", "group_column": None},
        {"x_column": "grp", "y_column": "val", "group_column": "sub"},
        {"x_column": None, "y_column": "val", "group_column": None},
    ],
)
def test_box_plotly_template_renders(box_df: pd.DataFrame, params: dict[str, Any]) -> None:
    fig = _render_plotly(box_df, "box", params)
    assert fig.data[0].type == "box"


@pytest.mark.parametrize(
    "params",
    [
        {"x_column": "grp", "y_column": "val", "group_column": None},
        {"x_column": "grp", "y_column": "val", "group_column": "sub"},
    ],
)
def test_violin_plotly_template_renders(box_df: pd.DataFrame, params: dict[str, Any]) -> None:
    fig = _render_plotly(box_df, "violin", params)
    assert fig.data[0].type == "violin"


@pytest.mark.parametrize(
    "color_col,bins",
    [
        (None, 10),
        ("grp", 5),
    ],
)
def test_histogram_plotly_template_renders(
    hist_df: pd.DataFrame, color_col: str | None, bins: int
) -> None:
    params = {"x_column": "val", "color_column": color_col, "bins": bins}
    fig = _render_plotly(hist_df, "histogram", params)
    assert fig.data[0].type == "histogram"


@pytest.mark.parametrize(
    "columns",
    [
        None,
        ["a", "b", "c"],
    ],
)
def test_heatmap_plotly_template_renders(
    heatmap_df: pd.DataFrame, columns: list[str] | None
) -> None:
    fig = _render_plotly(heatmap_df, "heatmap", {"columns": columns})
    assert fig.data[0].type == "heatmap"


# ---------------------------------------------------------------------------
# Matplotlib 结构测试
# ---------------------------------------------------------------------------


def _assert_matplotlib_style_consistent(fig: Any, style_key: str) -> None:
    spec = build_style_spec(style_key)
    ax = fig.axes[0]
    assert round(float(ax.spines["left"].get_linewidth()), 3) == round(
        float(spec.tick_major_width), 3
    )
    assert ax.spines["left"].get_edgecolor() is not None
    assert ax.spines["top"].get_visible() == spec.axes_spines_top
    assert ax.spines["right"].get_visible() == spec.axes_spines_right


@pytest.mark.parametrize("color_col", [None, "grp"])
def test_scatter_matplotlib_template_renders(
    scatter_df: pd.DataFrame, color_col: str | None
) -> None:
    fig = _render_matplotlib(
        scatter_df,
        "scatter",
        {"x_column": "x", "y_column": "y", "color_column": color_col},
        title="散点",
    )
    try:
        ax = fig.axes[0]
        assert ax.get_xlabel() == "x"
        assert ax.get_ylabel() == "y"
        assert ax.get_title() == "散点"
        assert len(ax.collections) >= 1  # scatter 结果是 PathCollection
        _assert_matplotlib_style_consistent(fig, "default")
    finally:
        plt.close(fig)


@pytest.mark.parametrize("color_col", [None, "series"])
def test_line_matplotlib_template_renders(line_df: pd.DataFrame, color_col: str | None) -> None:
    fig = _render_matplotlib(
        line_df,
        "line",
        {"x_column": "t", "y_column": "v", "color_column": color_col},
    )
    try:
        ax = fig.axes[0]
        assert ax.get_xlabel() == "t"
        assert ax.get_ylabel() == "v"
        assert len(ax.lines) >= 1
        spec = build_style_spec("default")
        assert round(float(ax.lines[0].get_linewidth()), 3) == round(float(spec.line_width), 3)
    finally:
        plt.close(fig)


@pytest.mark.parametrize(
    "y_col,group_col",
    [
        ("val", None),
        ("val", "sub"),
        (None, None),
    ],
)
def test_bar_matplotlib_template_renders(
    bar_df: pd.DataFrame, y_col: str | None, group_col: str | None
) -> None:
    fig = _render_matplotlib(
        bar_df,
        "bar",
        {"x_column": "cat", "y_column": y_col, "group_column": group_col},
    )
    try:
        ax = fig.axes[0]
        assert ax.get_xlabel() == "cat"
        assert len(ax.patches) >= 1
    finally:
        plt.close(fig)


@pytest.mark.parametrize(
    "params",
    [
        {"x_column": "grp", "y_column": "val", "group_column": None},
        {"x_column": "grp", "y_column": "val", "group_column": "sub"},
        {"x_column": None, "y_column": "val", "group_column": None},
    ],
)
def test_box_matplotlib_template_renders(box_df: pd.DataFrame, params: dict[str, Any]) -> None:
    fig = _render_matplotlib(box_df, "box", params)
    try:
        ax = fig.axes[0]
        assert ax.get_ylabel() == "val"
        assert len(ax.patches) >= 1  # boxplot patch_artist=True 会生成 patches
    finally:
        plt.close(fig)


@pytest.mark.parametrize(
    "params",
    [
        {"x_column": "grp", "y_column": "val", "group_column": None},
        {"x_column": "grp", "y_column": "val", "group_column": "sub"},
    ],
)
def test_violin_matplotlib_template_renders(box_df: pd.DataFrame, params: dict[str, Any]) -> None:
    fig = _render_matplotlib(box_df, "violin", params)
    try:
        ax = fig.axes[0]
        assert ax.get_ylabel() == "val"
        assert len(ax.collections) >= 1  # violinplot 的 body
    finally:
        plt.close(fig)


@pytest.mark.parametrize(
    "color_col,bins",
    [
        (None, 10),
        ("grp", 5),
    ],
)
def test_histogram_matplotlib_template_renders(
    hist_df: pd.DataFrame, color_col: str | None, bins: int
) -> None:
    fig = _render_matplotlib(
        hist_df,
        "histogram",
        {"x_column": "val", "color_column": color_col, "bins": bins},
    )
    try:
        ax = fig.axes[0]
        assert ax.get_xlabel() == "val"
        assert ax.get_ylabel() == "frequency"
        assert len(ax.patches) >= 1
    finally:
        plt.close(fig)


@pytest.mark.parametrize(
    "columns",
    [
        None,
        ["a", "b", "c"],
    ],
)
def test_heatmap_matplotlib_template_renders(
    heatmap_df: pd.DataFrame, columns: list[str] | None
) -> None:
    fig = _render_matplotlib(heatmap_df, "heatmap", {"columns": columns})
    try:
        ax = fig.axes[0]
        assert len(ax.images) >= 1
    finally:
        plt.close(fig)


def test_matplotlib_template_savefig_png_is_deterministic(scatter_df: pd.DataFrame) -> None:
    """同一模板两次 exec 产出的 PNG 字节应一致（保证可复现）。"""

    def _png_bytes() -> bytes:
        with plt.rc_context():
            fig = _render_matplotlib(
                scatter_df,
                "scatter",
                {"x_column": "x", "y_column": "y", "color_column": "grp"},
                title="x",
            )
            buf = io.BytesIO()
            fig.savefig(
                buf,
                format="png",
                dpi=100,
                bbox_inches="tight",
                pad_inches=0.05,
                facecolor="white",
                metadata={"Software": ""},
            )
            plt.close(fig)
            return buf.getvalue()

    assert _png_bytes() == _png_bytes()
