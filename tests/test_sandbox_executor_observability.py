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


def test_set_resource_limits_applies_low_memory_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """低于 1GB 的内存限制配置也应调用 RLIMIT_AS。"""
    calls: list[tuple[int, tuple[int, int]]] = []

    class _FakeResource:
        RLIMIT_CPU = 1
        RLIMIT_AS = 2
        RUSAGE_SELF = 3

        @staticmethod
        def setrlimit(kind: int, value: tuple[int, int]) -> None:
            calls.append((kind, value))

        @staticmethod
        def getrusage(_kind: int) -> SimpleNamespace:
            # 约 100MB (KB 单位)
            return SimpleNamespace(ru_maxrss=1024 * 100)

    monkeypatch.setattr("nini.sandbox.executor.resource", _FakeResource)

    from nini.sandbox.executor import _set_resource_limits

    _set_resource_limits(timeout_seconds=5, max_memory_mb=512)

    as_calls = [item for item in calls if item[0] == _FakeResource.RLIMIT_AS]
    assert as_calls, "应设置 RLIMIT_AS"
    _, (soft, hard) = as_calls[-1]
    assert soft == hard
    assert soft >= 512 * 1024 * 1024


def test_collect_figures_logs_debug_for_plotly_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Plotly 序列化异常应记录 debug 日志而不是静默吞掉。"""

    class _FakeFigure:
        def __init__(self) -> None:
            self.layout = None

        def to_json(self) -> str:
            raise RuntimeError("to_json failed")

    fake_plotly = ModuleType("plotly")
    fake_go = ModuleType("plotly.graph_objects")
    fake_go.Figure = _FakeFigure
    monkeypatch.setitem(sys.modules, "plotly", fake_plotly)
    monkeypatch.setitem(sys.modules, "plotly.graph_objects", fake_go)

    from nini.sandbox.executor import _collect_figures

    with caplog.at_level(logging.DEBUG):
        figures = _collect_figures({"broken": _FakeFigure()}, {})

    assert figures == []
    assert "Plotly 图表序列化失败（变量 broken）" in caplog.text
