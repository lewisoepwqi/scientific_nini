from __future__ import annotations

import plotly.graph_objects as go

from nini.utils.chart_fonts import (
    CJK_FONT_CANDIDATES,
    apply_plotly_cjk_font_fallback,
    get_matplotlib_font_list,
    with_cjk_font_fallback,
)


def test_with_cjk_font_fallback_empty() -> None:
    family = with_cjk_font_fallback("")
    assert family
    for candidate in CJK_FONT_CANDIDATES:
        assert candidate in family


def test_with_cjk_font_fallback_keeps_existing_family() -> None:
    family = with_cjk_font_fallback("Arial")
    assert family.startswith("Arial")
    assert CJK_FONT_CANDIDATES[0] in family


def test_get_matplotlib_font_list_returns_available_fonts() -> None:
    """get_matplotlib_font_list() 返回的字体均应为 matplotlib 实际可用。"""
    from matplotlib import font_manager

    result = get_matplotlib_font_list()
    assert isinstance(result, list)
    assert len(result) > 0
    # 调用后重新获取可用字体（函数内部可能触发字体下载与注册）
    available = {
        entry.name.lower()
        for entry in font_manager.fontManager.ttflist
        if getattr(entry, "name", None)
    }
    for font_name in result:
        assert font_name.lower() in available, f"字体 '{font_name}' 在系统中不可用"


def test_get_matplotlib_font_list_with_family() -> None:
    """传入自定义 family 时，返回列表仅含可用字体。"""
    from matplotlib import font_manager

    available = {
        entry.name.lower()
        for entry in font_manager.fontManager.ttflist
        if getattr(entry, "name", None)
    }
    result = get_matplotlib_font_list("NonExistentFont123, DejaVu Sans")
    assert isinstance(result, list)
    for font_name in result:
        assert font_name.lower() in available, f"字体 '{font_name}' 在系统中不可用"


def test_apply_plotly_cjk_font_fallback_layout_and_annotation() -> None:
    fig = go.Figure()
    fig.update_layout(font={"family": "Arial", "size": 12})
    fig.add_annotation(x=1, y=1, text="中文注释", font={"family": "Arial", "size": 10})

    apply_plotly_cjk_font_fallback(fig)

    assert isinstance(fig.layout.font.family, str)
    assert CJK_FONT_CANDIDATES[0] in fig.layout.font.family
    assert len(fig.layout.annotations) == 1
    assert CJK_FONT_CANDIDATES[0] in fig.layout.annotations[0].font.family
