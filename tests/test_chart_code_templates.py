"""图表代码模板字节等价测试。

每个 chart_type 都断言：
    exec(render_plotly_script(...)) 产出的 fig.to_plotly_json()
    == 现有 CreateChartTool._create_plotly_figure + apply_plotly_style 产物

这是 Phase 2 的护栏：只要此测试通过，就允许把 visualization.py 的渲染分支
替换为 exec(template)，而代码档案里的脚本与实际渲染不会再漂移。
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import pytest

from nini.charts.code_templates import render_plotly_script
from nini.charts.renderers import apply_plotly_style
from nini.charts.style_contract import build_style_spec
from nini.tools.visualization import CreateChartTool


def _exec_template(code: str, df: pd.DataFrame) -> go.Figure:
    """在隔离 namespace 里执行模板并取回 fig。"""
    namespace: dict[str, Any] = {"df": df}
    exec(compile(code, "<template>", "exec"), namespace)
    fig = namespace.get("fig")
    assert isinstance(fig, go.Figure), "模板未生成 fig 变量"
    return fig


def _legacy_render(
    df: pd.DataFrame,
    chart_type: str,
    kwargs: dict[str, Any],
    style_key: str,
    title: str | None,
) -> dict[str, Any]:
    skill = CreateChartTool()
    spec = build_style_spec(style_key)
    fig = skill._create_plotly_figure(df, chart_type, kwargs, list(spec.colors))
    apply_plotly_style(fig, spec, title)
    return json.loads(json.dumps(fig.to_plotly_json(), default=str))


def _template_render(
    df: pd.DataFrame,
    chart_type: str,
    params: dict[str, Any],
    style_key: str,
    title: str | None,
) -> dict[str, Any]:
    spec = build_style_spec(style_key)
    code = render_plotly_script(chart_type, params, spec, title=title)
    fig = _exec_template(code, df)
    return json.loads(json.dumps(fig.to_plotly_json(), default=str))


@pytest.fixture
def scatter_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "x": [1, 2, 3, 4, 5, 6],
            "y": [1.1, 1.9, 3.2, 4.1, 5.3, 6.2],
            "grp": ["A", "B", "A", "B", "A", "B"],
        }
    )


@pytest.mark.parametrize("style_key", ["default", "nature"])
@pytest.mark.parametrize(
    "title,color_col",
    [
        (None, None),
        ("散点图", "grp"),
    ],
)
def test_scatter_plotly_template_byte_equivalent(
    scatter_df: pd.DataFrame,
    style_key: str,
    title: str | None,
    color_col: str | None,
) -> None:
    params = {"x_column": "x", "y_column": "y", "color_column": color_col}
    legacy = _legacy_render(scatter_df, "scatter", params, style_key, title)
    via_template = _template_render(scatter_df, "scatter", params, style_key, title)
    assert via_template == legacy


def test_scatter_plotly_template_requires_xy() -> None:
    spec = build_style_spec("default")
    with pytest.raises(ValueError, match="x_column 和 y_column"):
        render_plotly_script("scatter", {"x_column": "x"}, spec)


@pytest.fixture
def line_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "t": [1, 2, 3, 4, 5, 6],
            "v": [1.0, 2.5, 2.0, 3.5, 3.0, 4.2],
            "series": ["a", "a", "b", "b", "a", "b"],
        }
    )


@pytest.mark.parametrize("color_col", [None, "series"])
def test_line_plotly_template_byte_equivalent(line_df: pd.DataFrame, color_col: str | None) -> None:
    params = {"x_column": "t", "y_column": "v", "color_column": color_col}
    legacy = _legacy_render(line_df, "line", params, "default", None)
    via_template = _template_render(line_df, "line", params, "default", None)
    assert via_template == legacy


def test_line_plotly_template_handles_mixed_x(line_df: pd.DataFrame) -> None:
    # 混合类型 x 列，走字符串兜底路径
    df = line_df.copy()
    df["t"] = [1, "two", 3, "four", 5, "six"]
    params = {"x_column": "t", "y_column": "v", "color_column": None}
    legacy = _legacy_render(df, "line", params, "default", None)
    via_template = _template_render(df, "line", params, "default", None)
    assert via_template == legacy


@pytest.fixture
def bar_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "cat": ["A", "A", "B", "B", "C", "C"],
            "sub": ["x", "y", "x", "y", "x", "y"],
            "val": [1, 2, 3, 4, 5, 6],
        }
    )


@pytest.mark.parametrize(
    "y_col,group_col",
    [
        ("val", None),
        ("val", "sub"),
        (None, None),  # value_counts 路径
    ],
)
def test_bar_plotly_template_byte_equivalent(
    bar_df: pd.DataFrame, y_col: str | None, group_col: str | None
) -> None:
    params = {"x_column": "cat", "y_column": y_col, "group_column": group_col}
    legacy = _legacy_render(bar_df, "bar", params, "default", None)
    via_template = _template_render(bar_df, "bar", params, "default", None)
    assert via_template == legacy


@pytest.fixture
def box_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "grp": ["A", "A", "A", "B", "B", "B"],
            "sub": ["x", "y", "x", "y", "x", "y"],
            "val": [1.0, 1.5, 2.0, 3.0, 3.5, 4.0],
        }
    )


@pytest.mark.parametrize(
    "params",
    [
        {"x_column": "grp", "y_column": "val", "group_column": None},
        {"x_column": "grp", "y_column": "val", "group_column": "sub"},
        {"x_column": None, "y_column": "val", "group_column": None},  # 仅数值列
    ],
)
def test_box_plotly_template_byte_equivalent(box_df: pd.DataFrame, params: dict[str, Any]) -> None:
    legacy = _legacy_render(box_df, "box", params, "default", None)
    via_template = _template_render(box_df, "box", params, "default", None)
    assert via_template == legacy


@pytest.mark.parametrize(
    "params",
    [
        {"x_column": "grp", "y_column": "val", "group_column": None},
        {"x_column": "grp", "y_column": "val", "group_column": "sub"},
    ],
)
def test_violin_plotly_template_byte_equivalent(
    box_df: pd.DataFrame, params: dict[str, Any]
) -> None:
    legacy = _legacy_render(box_df, "violin", params, "default", None)
    via_template = _template_render(box_df, "violin", params, "default", None)
    assert via_template == legacy


@pytest.fixture
def hist_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "val": [1.0, 1.2, 1.5, 2.0, 2.1, 2.3, 2.5, 3.0, 3.1, 3.3],
            "grp": ["a"] * 5 + ["b"] * 5,
        }
    )


@pytest.mark.parametrize(
    "color_col,bins",
    [
        (None, 10),
        ("grp", 5),
    ],
)
def test_histogram_plotly_template_byte_equivalent(
    hist_df: pd.DataFrame, color_col: str | None, bins: int
) -> None:
    params = {"x_column": "val", "color_column": color_col, "bins": bins}
    legacy = _legacy_render(hist_df, "histogram", params, "default", None)
    via_template = _template_render(hist_df, "histogram", params, "default", None)
    assert via_template == legacy


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


@pytest.mark.parametrize(
    "columns",
    [
        None,  # 触发自动选择数值列
        ["a", "b", "c"],
    ],
)
def test_heatmap_plotly_template_byte_equivalent(
    heatmap_df: pd.DataFrame, columns: list[str] | None
) -> None:
    params = {"columns": columns}
    legacy = _legacy_render(heatmap_df, "heatmap", params, "default", None)
    via_template = _template_render(heatmap_df, "heatmap", params, "default", None)
    assert via_template == legacy
