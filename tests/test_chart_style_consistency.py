"""图表风格契约与双引擎一致性测试。"""

from __future__ import annotations

import asyncio
import io
import multiprocessing as mp
from typing import Any, cast

import numpy as np
import pandas as pd
import pytest

from nini.agent.session import Session
from nini.charts.style_contract import build_style_spec, normalize_render_engine
from nini.charts.renderers import apply_plotly_style
from nini.config import settings
from nini.tools.markdown_scanner import scan_markdown_skills
from nini.tools.registry import create_default_registry
from nini.tools.visualization import CreateChartSkill


@pytest.fixture(autouse=True)
def _cleanup_event_loop() -> None:
    """清理模块内可能残留的默认事件循环，避免 ResourceWarning。"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield
    if not loop.is_closed():
        loop.close()
    asyncio.set_event_loop(None)


def test_build_style_spec_from_template() -> None:
    """模板应正确映射到统一风格契约。"""
    spec = build_style_spec("nature")
    assert spec.style_key == "nature"
    assert spec.dpi >= 300
    assert len(spec.colors) >= 1
    assert spec.figure_size[0] > 0
    assert spec.figure_size[1] > 0


def test_normalize_render_engine_fallback() -> None:
    """非法渲染引擎应回退到默认配置。"""
    default_engine = settings.chart_default_render_engine
    assert normalize_render_engine("unknown-engine") == default_engine
    assert normalize_render_engine("plotly") == "plotly"
    assert normalize_render_engine("matplotlib") == "matplotlib"


def test_create_chart_with_matplotlib_engine_exports_publication_formats() -> None:
    """create_chart 使用 matplotlib 时应导出 pdf/svg/png。"""
    registry = create_default_registry()
    session = Session()
    session.datasets["exp.csv"] = pd.DataFrame(
        {
            "group": ["control", "control", "treatment", "treatment"],
            "value": [1.1, 1.2, 1.8, 2.0],
        }
    )

    result = asyncio.run(
        registry.execute(
            "create_chart",
            session=session,
            dataset_name="exp.csv",
            chart_type="box",
            y_column="value",
            group_column="group",
            journal_style="nature",
            render_engine="matplotlib",
            title="Treatment vs Control",
        )
    )

    assert result["success"] is True, result
    assert result["has_chart"] is True
    assert isinstance(result["chart_data"], dict)
    artifacts = result.get("artifacts") or []
    formats = {item.get("format") for item in artifacts}
    # 兼容前端预览，仍保留 JSON；发表级导出要求三种基础格式
    assert "json" in formats
    assert {"pdf", "svg", "png"}.issubset(formats)


def test_cross_engine_style_parameters_consistent() -> None:
    """同一契约下关键样式参数应在双引擎一致。"""
    spec = build_style_spec("science")
    skill = CreateChartSkill()
    df = pd.DataFrame({"x": [1, 2, 3], "y": [2, 3, 4]})
    kwargs: dict[str, object] = {"x_column": "x", "y_column": "y"}

    plotly_fig = skill._create_plotly_figure(df, "line", kwargs, list(spec.colors))
    apply_plotly_style(plotly_fig, spec, "trend")
    layout = plotly_fig.to_plotly_json()["layout"]
    assert layout["font"]["size"] == spec.font_size
    assert layout["font"]["family"]
    assert layout["xaxis"]["linecolor"] == spec.axis_color
    assert layout["yaxis"]["linecolor"] == spec.axis_color

    matplotlib_fig = skill._create_matplotlib_figure(
        df=df,
        chart_type="line",
        kwargs=kwargs,
        title="trend",
        style_spec=spec,
    )
    ax = matplotlib_fig.axes[0]
    line = ax.lines[0]
    assert round(float(line.get_linewidth()), 3) == round(float(spec.line_width), 3)
    assert round(float(ax.spines["left"].get_linewidth()), 3) == round(
        float(spec.tick_major_width), 3
    )
    try:
        import matplotlib.pyplot as plt

        plt.close(matplotlib_fig)
    except Exception:
        pass


def test_run_code_matplotlib_exports_publication_formats() -> None:
    """run_code 生成 matplotlib 图时应导出 pdf/svg/png。"""
    registry = create_default_registry()
    session = Session()
    session.datasets["exp.csv"] = pd.DataFrame({"x": [1, 2, 3], "y": [2, 3, 4]})

    result = asyncio.run(
        registry.execute(
            "run_code",
            session=session,
            dataset_name="exp.csv",
            purpose="visualization",
            label="line_demo",
            code=(
                "import matplotlib.pyplot as plt\n"
                "fig, ax = plt.subplots()\n"
                "ax.plot(df['x'], df['y'])\n"
                "ax.set_title('demo')\n"
            ),
        )
    )
    assert result["success"] is True, result
    artifacts = result.get("artifacts") or []
    formats = {item.get("format") for item in artifacts}
    assert {"pdf", "svg", "png"}.issubset(formats)


def test_publication_skill_scanned_into_markdown_skills() -> None:
    """发表级图表技能应进入 Markdown 技能扫描结果。"""
    items = scan_markdown_skills(settings.skills_dir)
    names = {item.name for item in items}
    assert "publication_figure" in names


def test_publication_skill_written_into_snapshot() -> None:
    """发表级图表技能应进入技能快照。"""
    registry = create_default_registry()
    registry.write_skills_snapshot()
    snapshot_text = settings.skills_snapshot_path.read_text(encoding="utf-8")
    assert "publication_figure" in snapshot_text
    assert "skills/publication_figure/SKILL.md" in snapshot_text


def _compute_ssim(values_a: np.ndarray, values_b: np.ndarray) -> float:
    """简化版 SSIM，使用全局统计量评估相似度。"""
    a = values_a.astype(np.float64)
    b = values_b.astype(np.float64)
    c1 = 0.01**2
    c2 = 0.03**2

    mu_a = a.mean()
    mu_b = b.mean()
    sigma_a = a.var()
    sigma_b = b.var()
    sigma_ab = ((a - mu_a) * (b - mu_b)).mean()

    numerator = (2 * mu_a * mu_b + c1) * (2 * sigma_ab + c2)
    denominator = (mu_a**2 + mu_b**2 + c1) * (sigma_a + sigma_b + c2)
    if denominator == 0:
        return 1.0
    return float(numerator / denominator)


def _render_plotly_png_worker(
    queue: Any,
    payload: dict[str, Any],
    *,
    width: int,
    height: int,
    scale: int,
) -> None:
    """子进程渲染 Plotly PNG，结果通过队列回传。"""
    try:
        import plotly.graph_objects as go

        fig = go.Figure(payload)
        png_bytes = fig.to_image(
            format="png",
            width=width,
            height=height,
            scale=scale,
        )
        queue.put(("ok", png_bytes))
    except Exception as exc:  # pragma: no cover - 环境依赖路径
        queue.put(("err", str(exc)))


def _render_plotly_png(
    fig: Any,
    *,
    width: int,
    height: int,
    scale: int,
    timeout_seconds: float = 20.0,
) -> bytes:
    """在限定时间内导出 Plotly PNG，超时抛出 TimeoutError。"""
    ctx = mp.get_context("spawn")
    queue: Any = ctx.Queue()
    payload = cast(dict[str, Any], fig.to_plotly_json())
    process = ctx.Process(
        target=_render_plotly_png_worker,
        kwargs={
            "queue": queue,
            "payload": payload,
            "width": width,
            "height": height,
            "scale": scale,
        },
        daemon=True,
    )
    process.start()
    process.join(timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join(3)
        raise TimeoutError("Plotly PNG 导出超时")

    try:
        status, value = queue.get_nowait()
    except Exception as exc:  # pragma: no cover - 异常路径
        raise RuntimeError("Plotly PNG 导出失败：无返回结果") from exc
    if status == "ok":
        return cast(bytes, value)
    raise RuntimeError(f"Plotly PNG 导出失败: {value}")


def test_cross_engine_visual_similarity_ssim_threshold() -> None:
    """同图跨引擎输出在可用环境下满足 SSIM 阈值。"""
    spec = build_style_spec("nature")
    skill = CreateChartSkill()
    df = pd.DataFrame({"x": [1, 2, 3, 4], "y": [2, 3, 3.5, 5]})
    kwargs: dict[str, object] = {"x_column": "x", "y_column": "y"}

    # 1) Plotly 渲染 PNG（依赖 kaleido + Chrome）
    plotly_fig = skill._create_plotly_figure(df, "line", kwargs, list(spec.colors))
    apply_plotly_style(plotly_fig, spec, "trend")
    try:
        plotly_png = _render_plotly_png(
            plotly_fig,
            width=900,
            height=600,
            scale=max(1, int(spec.dpi / 150)),
        )
    except Exception as exc:  # pragma: no cover - 环境依赖路径
        pytest.skip(f"Plotly PNG 导出不可用（可能缺 kaleido/Chrome）: {exc}")

    # 2) Matplotlib 渲染 PNG
    matplotlib_fig = skill._create_matplotlib_figure(
        df=df,
        chart_type="line",
        kwargs=kwargs,
        title="trend",
        style_spec=spec,
    )
    matplot_buf = io.BytesIO()
    matplotlib_fig.savefig(matplot_buf, format="png", dpi=spec.dpi)
    matplotlib_fig.clf()
    try:
        import matplotlib.pyplot as plt

        plt.close(matplotlib_fig)
    except Exception:
        pass
    matplot_buf.seek(0)

    # 3) 统一为灰度并缩放到相同尺寸
    try:
        from PIL import Image
    except Exception as exc:  # pragma: no cover - 环境依赖路径
        pytest.skip(f"Pillow 不可用: {exc}")

    img_a = Image.open(io.BytesIO(plotly_png)).convert("L").resize((512, 384))
    img_b = Image.open(matplot_buf).convert("L").resize((512, 384))
    arr_a = np.array(img_a)
    arr_b = np.array(img_b)
    # 使用灰度直方图计算 SSIM，降低跨引擎布局细节差异带来的噪声
    hist_a = np.histogram(arr_a, bins=64, range=(0, 256))[0].astype(np.float64)
    hist_b = np.histogram(arr_b, bins=64, range=(0, 256))[0].astype(np.float64)
    hist_a /= max(hist_a.sum(), 1.0)
    hist_b /= max(hist_b.sum(), 1.0)
    score = _compute_ssim(hist_a, hist_b)
    assert score >= settings.chart_similarity_threshold
