"""沙箱图表默认配置可观测性测试。"""

from __future__ import annotations

import logging
import sys
from types import ModuleType, SimpleNamespace

import pytest

from nini.sandbox.executor import _configure_chart_defaults


def _mock_style() -> SimpleNamespace:
    return SimpleNamespace(
        colors=["#1f77b4", "#ff7f0e"],
        line_width=1.8,
        font_size=12,
        text_color="#111111",
        background_color="#ffffff",
        axis_color="#333333",
        grid_color="#dddddd",
    )


def test_configure_chart_defaults_logs_warning_for_matplotlib_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Matplotlib 样式配置异常应记录 warning 并继续执行。"""
    fake_matplotlib = ModuleType("matplotlib")
    fake_matplotlib.rcParams = {}
    fake_matplotlib.use = lambda *_args, **_kwargs: None

    fake_cycler = ModuleType("cycler")
    fake_cycler.cycler = lambda **kwargs: kwargs

    monkeypatch.setitem(sys.modules, "matplotlib", fake_matplotlib)
    monkeypatch.setitem(sys.modules, "cycler", fake_cycler)
    monkeypatch.setattr("nini.sandbox.executor.build_style_spec", _mock_style)

    def _raise_matplotlib_failure(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("matplotlib failed")

    monkeypatch.setattr(
        "nini.sandbox.executor.apply_matplotlib_rc_style",
        _raise_matplotlib_failure,
    )

    with caplog.at_level(logging.WARNING):
        _configure_chart_defaults()

    assert "配置 Matplotlib 默认样式失败" in caplog.text


def test_configure_chart_defaults_logs_warning_for_plotly_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Plotly 样式配置异常应记录 warning 并继续执行。"""
    fake_matplotlib = ModuleType("matplotlib")
    fake_matplotlib.rcParams = {}
    fake_matplotlib.use = lambda *_args, **_kwargs: None

    fake_cycler = ModuleType("cycler")
    fake_cycler.cycler = lambda **kwargs: kwargs

    fake_plotly = ModuleType("plotly")
    fake_px = ModuleType("plotly.express")
    fake_px.defaults = SimpleNamespace(template=None, color_discrete_sequence=None)

    fake_go = ModuleType("plotly.graph_objects")

    class _Layout:
        @staticmethod
        def Template(_base: object) -> object:
            raise ValueError("plotly failed")

    fake_go.layout = _Layout

    fake_pio = ModuleType("plotly.io")

    class _Templates(dict):
        default = "plotly_white"

    fake_pio.templates = _Templates({"plotly_white": object()})

    monkeypatch.setitem(sys.modules, "matplotlib", fake_matplotlib)
    monkeypatch.setitem(sys.modules, "cycler", fake_cycler)
    monkeypatch.setitem(sys.modules, "plotly", fake_plotly)
    monkeypatch.setitem(sys.modules, "plotly.express", fake_px)
    monkeypatch.setitem(sys.modules, "plotly.graph_objects", fake_go)
    monkeypatch.setitem(sys.modules, "plotly.io", fake_pio)

    monkeypatch.setattr("nini.sandbox.executor.build_style_spec", _mock_style)
    monkeypatch.setattr("nini.sandbox.executor.apply_matplotlib_rc_style", lambda *_a, **_k: None)

    with caplog.at_level(logging.WARNING):
        _configure_chart_defaults()

    assert "配置 Plotly 默认样式失败" in caplog.text
