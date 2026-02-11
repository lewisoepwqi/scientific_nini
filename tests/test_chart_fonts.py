from __future__ import annotations

import plotly.graph_objects as go

from nini.utils.chart_fonts import (
    CJK_FONT_CANDIDATES,
    apply_plotly_cjk_font_fallback,
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


def test_apply_plotly_cjk_font_fallback_layout_and_annotation() -> None:
    fig = go.Figure()
    fig.update_layout(font={"family": "Arial", "size": 12})
    fig.add_annotation(x=1, y=1, text="中文注释", font={"family": "Arial", "size": 10})

    apply_plotly_cjk_font_fallback(fig)

    assert isinstance(fig.layout.font.family, str)
    assert CJK_FONT_CANDIDATES[0] in fig.layout.font.family
    assert len(fig.layout.annotations) == 1
    assert CJK_FONT_CANDIDATES[0] in fig.layout.annotations[0].font.family
