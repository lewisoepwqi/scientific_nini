"""进程隔离代码执行器。"""

from __future__ import annotations

import base64
import builtins as py_builtins
import io
import logging
import multiprocessing
from multiprocessing.connection import Connection
import os
import pickle
import time
import traceback
from typing import Any

import pandas as pd

from nini.charts import build_style_spec
from nini.charts.renderers import apply_matplotlib_rc_style
from nini.config import settings
from nini.sandbox.capture import capture_stdio
from nini.sandbox.policy import validate_code
from nini.utils.chart_fonts import (
    CJK_FONT_CANDIDATES,
    CJK_FONT_FAMILY,
    apply_plotly_cjk_font_fallback,
    get_available_cjk_fonts,
    get_matplotlib_font_list,
)

try:
    import resource  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - Windows 等平台可能不存在
    resource = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


def _safe_import(name: str, *args: Any, **kwargs: Any) -> Any:
    """白名单版本的 __import__ 函数。

    只允许导入 ALLOWED_IMPORT_ROOTS 中的模块。
    由于模块已预加载到 globals，此函数主要用于兼容 import 语句。
    """
    from nini.sandbox.policy import ALLOWED_IMPORT_ROOTS

    # 提取根模块名
    root_module = name.split(".", 1)[0]

    # 检查白名单
    if root_module not in ALLOWED_IMPORT_ROOTS:
        raise ImportError(
            f"模块 '{name}' 不在沙箱白名单中。允许的模块: {', '.join(sorted(ALLOWED_IMPORT_ROOTS))}"
        )

    # 调用真正的 __import__
    import builtins

    return builtins.__import__(name, *args, **kwargs)


SAFE_BUILTINS: dict[str, Any] = {
    # 受限的 __import__（只允许白名单模块）
    "__import__": _safe_import,
    # 标准内建函数
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "isinstance": isinstance,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "print": print,
    "range": range,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
    "Exception": Exception,
    "ValueError": ValueError,
    "TypeError": TypeError,
}


def _apply_matplotlib_cjk_font_fallback(fig: Any) -> None:
    """在导出前统一覆盖文本字体，降低中文方框字概率。"""
    try:
        from matplotlib.text import Text

        for text_obj in fig.findobj(match=Text):
            text_obj.set_fontfamily(get_available_cjk_fonts() or CJK_FONT_CANDIDATES)
    except ImportError:
        logger.debug("Matplotlib 不可用，跳过中文字体回退配置。")
        return
    except Exception as exc:
        logger.debug("应用 Matplotlib 中文字体回退失败: %s", exc)
        return


def _configure_chart_defaults() -> None:
    """统一绘图默认风格，优先保证中文显示和科研风格可读性。"""
    style = build_style_spec()

    # Matplotlib 默认样式
    try:
        import matplotlib
        from cycler import cycler
        from matplotlib import rcParams

        matplotlib.use("Agg", force=True)
        apply_matplotlib_rc_style(rcParams, style)
        # 仅配置系统实际存在的字体，避免大量 'Font family not found' 警告
        sans_serif = get_matplotlib_font_list()
        if sans_serif:
            rcParams["font.sans-serif"] = sans_serif
        rcParams["axes.unicode_minus"] = False
        rcParams["axes.prop_cycle"] = cycler(color=list(style.colors))
        rcParams["lines.linewidth"] = style.line_width
    except ImportError as exc:
        logger.debug("Matplotlib 相关依赖不可用，跳过默认样式配置: %s", exc)
    except Exception as exc:
        logger.warning("配置 Matplotlib 默认样式失败，使用库默认配置: %s", exc)

    # Plotly 默认样式
    try:
        import plotly.express as px
        import plotly.graph_objects as go
        import plotly.io as pio

        template = go.layout.Template(pio.templates["plotly_white"])
        template.layout.font = {
            "family": CJK_FONT_FAMILY,
            "size": style.font_size,
            "color": style.text_color,
        }
        template.layout.colorway = list(style.colors)
        template.layout.paper_bgcolor = style.background_color
        template.layout.plot_bgcolor = style.background_color
        template.layout.xaxis = {
            "showline": True,
            "linecolor": style.axis_color,
            "ticks": "outside",
            "tickcolor": style.axis_color,
            "gridcolor": style.grid_color,
            "zeroline": False,
        }
        template.layout.yaxis = {
            "showline": True,
            "linecolor": style.axis_color,
            "ticks": "outside",
            "tickcolor": style.axis_color,
            "gridcolor": style.grid_color,
            "zeroline": False,
        }

        pio.templates["nini_science"] = template
        pio.templates.default = "nini_science"
        px.defaults.template = "nini_science"
        px.defaults.color_discrete_sequence = list(style.colors)
    except ImportError as exc:
        logger.debug("Plotly 相关依赖不可用，跳过默认样式配置: %s", exc)
    except Exception as exc:
        logger.warning("配置 Plotly 默认样式失败，使用库默认配置: %s", exc)


def _safe_copy_datasets(datasets: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    copied: dict[str, pd.DataFrame] = {}
    for name, df in datasets.items():
        copied[name] = df.copy(deep=True)
    return copied


def _set_resource_limits(timeout_seconds: int, max_memory_mb: int) -> None:
    """对子进程施加资源限制。"""
    if resource is None:
        return
    try:
        if hasattr(resource, "RLIMIT_CPU"):
            cpu_limit = max(1, int(timeout_seconds))
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_limit))
        if hasattr(resource, "RLIMIT_AS") and int(max_memory_mb) > 0:
            usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            # Linux ru_maxrss 单位是 KB，macOS 是 Byte；统一转换为 MB
            usage_mb = usage / 1024 if usage > 10_000 else usage / (1024 * 1024)
            # 给运行时和序列化留出缓冲，避免进程尚未执行业务代码就触发 OOM。
            # 低于 1GB 的配置也应生效：当请求上限较小时，至少保证当前占用 + 256MB 缓冲。
            if int(max_memory_mb) < 1024:
                effective_limit_mb = max(int(max_memory_mb), int(usage_mb) + 256)
            else:
                effective_limit_mb = max(int(max_memory_mb), int(usage_mb) + 512)
            mem_limit = effective_limit_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (mem_limit, mem_limit))
    except Exception:
        # 某些环境不允许设置 rlimit，降级为仅使用超时终止
        pass


def _try_pickleable(value: Any) -> Any:
    """确保结果可跨进程传输。"""
    try:
        pickle.dumps(value)
        return value
    except Exception:
        return repr(value)


def _build_exec_globals(datasets: dict[str, pd.DataFrame]) -> dict[str, Any]:
    """构建沙箱执行环境的全局命名空间。

    预加载常用科学计算模块，避免用户代码 import 失败（SAFE_BUILTINS 中已移除 __import__）。
    """
    # 预加载常用模块（避免 import 失败）
    import numpy as np
    import datetime
    from datetime import datetime as dt, timedelta
    from collections import Counter, defaultdict, deque
    from itertools import combinations, permutations, product
    from functools import reduce, partial
    import re
    import json

    # 尝试导入可视化库（可能未安装）
    plt: Any | None = None
    matplotlib: Any | None = None
    try:
        import matplotlib.pyplot as plt
        import matplotlib
    except ImportError:
        pass

    sns: Any | None = None
    try:
        import seaborn as _sns

        sns = _sns
    except ImportError:
        pass

    go: Any | None = None
    px: Any | None = None
    try:
        import plotly.graph_objects as _go
        import plotly.express as _px

        go = _go
        px = _px
    except ImportError:
        pass

    globals_dict: dict[str, Any] = {
        "__builtins__": SAFE_BUILTINS,
        # 数据框架（预加载）
        "pd": pd,
        "datasets": datasets,
        # 数值计算
        "np": np,
        "numpy": np,
        # 日期时间
        "datetime": datetime,
        "dt": dt,
        "timedelta": timedelta,
        # 数据结构
        "Counter": Counter,
        "defaultdict": defaultdict,
        "deque": deque,
        # 迭代器工具
        "combinations": combinations,
        "permutations": permutations,
        "product": product,
        # 函数式工具
        "reduce": reduce,
        "partial": partial,
        # 文本处理
        "re": re,
        "json": json,
    }

    # 可视化库（如果可用）
    if plt is not None:
        globals_dict["plt"] = plt
        globals_dict["matplotlib"] = matplotlib
    if sns is not None:
        globals_dict["sns"] = sns
    if go is not None:
        globals_dict["go"] = go
        globals_dict["px"] = px

    return globals_dict


def _collect_figures(
    exec_globals: dict[str, Any], exec_locals: dict[str, Any]
) -> list[dict[str, Any]]:
    """遍历执行环境，检测并序列化 Plotly/Matplotlib 图表对象。

    - Plotly Figure: 通过 to_json() 序列化为 JSON 字符串
    - Matplotlib Figure: 通过 savefig() 序列化为 base64 编码的 SVG 和 PNG
    - 自动去重（同一对象不重复收集）
    - 跳过空白图表和序列化失败的对象
    """
    figures: list[dict[str, Any]] = []
    style = build_style_spec()
    seen_ids: set[int] = set()

    # 尝试导入图表库（子进程启动代码不受 AST 白名单限制）
    plotly_figure_cls = None
    mpl_figure_cls = None
    try:
        import plotly.graph_objects as go

        plotly_figure_cls = go.Figure
    except Exception:
        pass
    try:
        import matplotlib.figure

        mpl_figure_cls = matplotlib.figure.Figure
    except Exception:
        pass

    if plotly_figure_cls is None and mpl_figure_cls is None:
        return figures

    # 合并两个命名空间，优先 exec_locals
    combined: dict[str, Any] = {}
    combined.update(exec_globals)
    combined.update(exec_locals)

    # 也检测 matplotlib.pyplot.gcf()
    mpl_gcf_fig = None
    if mpl_figure_cls is not None:
        try:
            import matplotlib.pyplot as plt

            gcf = plt.gcf()
            if gcf.get_axes():
                mpl_gcf_fig = gcf
        except Exception:
            pass

    for var_name, obj in combined.items():
        if var_name.startswith("_"):
            continue

        obj_id = id(obj)
        if obj_id in seen_ids:
            continue

        # Plotly Figure
        if plotly_figure_cls is not None and isinstance(obj, plotly_figure_cls):
            seen_ids.add(obj_id)
            try:
                apply_plotly_cjk_font_fallback(obj)
                json_str = obj.to_json()
                title = ""
                if obj.layout and hasattr(obj.layout, "title") and obj.layout.title:
                    title_obj = obj.layout.title
                    if hasattr(title_obj, "text") and title_obj.text:
                        title = str(title_obj.text)
                figures.append(
                    {
                        "var_name": var_name,
                        "library": "plotly",
                        "plotly_json": json_str,
                        "title": title,
                    }
                )
            except Exception as exc:
                logger.debug("Plotly 图表序列化失败（变量 %s）: %s", var_name, exc)
            continue

        # Matplotlib Figure
        if mpl_figure_cls is not None and isinstance(obj, mpl_figure_cls):
            seen_ids.add(obj_id)
            if not obj.get_axes():
                continue
            try:
                _apply_matplotlib_cjk_font_fallback(obj)
                entry: dict[str, Any] = {
                    "var_name": var_name,
                    "library": "matplotlib",
                    "title": "",
                }
                # 提取标题
                title_text = (
                    obj._suptitle.get_text() if hasattr(obj, "_suptitle") and obj._suptitle else ""
                )
                if not title_text and obj.get_axes():
                    title_text = obj.get_axes()[0].get_title()
                entry["title"] = title_text or ""

                # SVG
                svg_buf = io.BytesIO()
                obj.savefig(svg_buf, format="svg", bbox_inches="tight")
                entry["svg_data"] = base64.b64encode(svg_buf.getvalue()).decode("ascii")

                # PDF
                pdf_buf = io.BytesIO()
                obj.savefig(pdf_buf, format="pdf", bbox_inches="tight")
                entry["pdf_data"] = base64.b64encode(pdf_buf.getvalue()).decode("ascii")

                # PNG
                png_buf = io.BytesIO()
                obj.savefig(png_buf, format="png", bbox_inches="tight", dpi=style.dpi)
                entry["png_data"] = base64.b64encode(png_buf.getvalue()).decode("ascii")

                figures.append(entry)
            except Exception as exc:
                logger.debug("Matplotlib 图表序列化失败（变量 %s）: %s", var_name, exc)
            continue

    # 检测 gcf（当前活跃图表），如果尚未被收集
    if mpl_gcf_fig is not None and id(mpl_gcf_fig) not in seen_ids:
        try:
            _apply_matplotlib_cjk_font_fallback(mpl_gcf_fig)
            entry = {
                "var_name": "__gcf__",
                "library": "matplotlib",
                "title": "",
            }
            title_text = (
                mpl_gcf_fig._suptitle.get_text()
                if hasattr(mpl_gcf_fig, "_suptitle") and mpl_gcf_fig._suptitle
                else ""
            )
            if not title_text and mpl_gcf_fig.get_axes():
                title_text = mpl_gcf_fig.get_axes()[0].get_title()
            entry["title"] = title_text or ""

            svg_buf = io.BytesIO()
            mpl_gcf_fig.savefig(svg_buf, format="svg", bbox_inches="tight")
            entry["svg_data"] = base64.b64encode(svg_buf.getvalue()).decode("ascii")

            pdf_buf = io.BytesIO()
            mpl_gcf_fig.savefig(pdf_buf, format="pdf", bbox_inches="tight")
            entry["pdf_data"] = base64.b64encode(pdf_buf.getvalue()).decode("ascii")

            png_buf = io.BytesIO()
            mpl_gcf_fig.savefig(png_buf, format="png", bbox_inches="tight", dpi=style.dpi)
            entry["png_data"] = base64.b64encode(png_buf.getvalue()).decode("ascii")

            figures.append(entry)
        except Exception as exc:
            logger.debug("Matplotlib 当前活动图表序列化失败: %s", exc)

    return figures


def _sandbox_worker(
    conn: Connection,
    code: str,
    datasets: dict[str, pd.DataFrame],
    working_dir: str,
    timeout_seconds: int,
    max_memory_mb: int,
    dataset_name: str | None,
    persist_df: bool,
) -> None:
    """子进程执行入口。"""
    stdout_text = ""
    stderr_text = ""

    try:
        _set_resource_limits(timeout_seconds, max_memory_mb)
        os.chdir(working_dir)
        _configure_chart_defaults()

        local_datasets = _safe_copy_datasets(datasets)
        exec_globals = _build_exec_globals(local_datasets)

        # 使用单命名空间：避免 exec(code, globals, locals) 双命名空间导致
        # 用户在代码中定义的函数无法被 lambda/闭包引用（NameError）。
        # 单命名空间下所有定义统一存储在 exec_globals 中。
        if dataset_name:
            if dataset_name not in local_datasets:
                raise ValueError(f"数据集 '{dataset_name}' 不存在")
            exec_globals["df"] = local_datasets[dataset_name].copy(deep=True)

        with capture_stdio() as (stdout_buf, stderr_buf):
            compiled = compile(code, "<sandbox>", "exec")
            # 注意：这里使用 Python 内置的 exec() 函数执行沙箱代码，
            # 不是 child_process.exec，代码已通过 validate_code() 策略校验。
            exec(compiled, exec_globals)  # noqa: S102
            stdout_text = stdout_buf.getvalue()
            stderr_text = stderr_buf.getvalue()

        result_obj = exec_globals.get("result")
        output_df = exec_globals.get("output_df")

        if persist_df and dataset_name and isinstance(exec_globals.get("df"), pd.DataFrame):
            local_datasets[dataset_name] = exec_globals["df"]

        if isinstance(output_df, pd.DataFrame):
            result_obj = output_df

        # 自动检测并序列化图表对象（单命名空间，exec_locals 传空字典）
        figures = _collect_figures(exec_globals, {})

        payload = {
            "success": True,
            "stdout": stdout_text,
            "stderr": stderr_text,
            "result": _try_pickleable(result_obj),
            "datasets": local_datasets if persist_df else {},
            "figures": figures,
        }
        conn.send(payload)
    except Exception as exc:
        tb = traceback.format_exc()
        conn.send(
            {
                "success": False,
                "stdout": stdout_text,
                "stderr": stderr_text,
                "error": str(exc),
                "traceback": tb,
            }
        )
    finally:
        conn.close()


class SandboxExecutor:
    """沙箱执行器（进程隔离 + 策略校验 + 超时控制）。"""

    def __init__(self, timeout_seconds: int | None = None, max_memory_mb: int | None = None):
        self.timeout_seconds = timeout_seconds or settings.sandbox_timeout
        self.max_memory_mb = max_memory_mb or settings.sandbox_max_memory_mb

    async def execute(
        self,
        *,
        code: str,
        session_id: str,
        datasets: dict[str, pd.DataFrame],
        dataset_name: str | None = None,
        persist_df: bool = False,
    ) -> dict[str, Any]:
        """异步执行入口。"""
        return self._execute_sync(
            code=code,
            session_id=session_id,
            datasets=datasets,
            dataset_name=dataset_name,
            persist_df=persist_df,
        )

    def _execute_sync(
        self,
        *,
        code: str,
        session_id: str,
        datasets: dict[str, pd.DataFrame],
        dataset_name: str | None,
        persist_df: bool,
    ) -> dict[str, Any]:
        validate_code(code)

        working_dir = settings.sessions_dir / session_id / "sandbox_tmp"
        working_dir.mkdir(parents=True, exist_ok=True)

        ctx = multiprocessing.get_context("spawn")
        parent_conn, child_conn = ctx.Pipe(duplex=False)
        process = ctx.Process(
            target=_sandbox_worker,
            args=(
                child_conn,
                code,
                datasets,
                str(working_dir),
                self.timeout_seconds,
                self.max_memory_mb,
                dataset_name,
                persist_df,
            ),
            daemon=True,
        )

        process.start()
        child_conn.close()
        deadline = time.monotonic() + self.timeout_seconds
        payload: dict[str, Any] | None = None

        # 注意：不能先 join 再 recv。若子进程发送 payload 较大（例如 output_df），
        # 可能阻塞在 conn.send()，父进程若在 join 等待会形成死锁直到超时。
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break

            if parent_conn.poll(min(0.05, remaining)):
                try:
                    payload = parent_conn.recv()
                except EOFError:
                    payload = None
                break

            if not process.is_alive():
                # 进程已退出但可能还有最后一条消息尚未被读取
                if parent_conn.poll(0.05):
                    try:
                        payload = parent_conn.recv()
                    except EOFError:
                        payload = None
                break

        if payload is not None:
            process.join(timeout=1)
            if process.is_alive():
                process.terminate()
                process.join(timeout=1)
            parent_conn.close()
            return payload

        if process.is_alive():
            process.terminate()
            process.join(timeout=1)
            parent_conn.close()
            return {
                "success": False,
                "error": f"代码执行超时（>{self.timeout_seconds}s）",
                "stdout": "",
                "stderr": "",
            }

        process.join(timeout=0.2)
        parent_conn.close()
        return {
            "success": False,
            "error": "沙箱进程异常退出，未返回结果",
            "stdout": "",
            "stderr": "",
        }


sandbox_executor = SandboxExecutor()
