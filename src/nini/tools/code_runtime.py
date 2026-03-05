"""脚本执行共享运行时。"""

from __future__ import annotations

import base64
import concurrent.futures
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from nini.agent.session import Session
from nini.charts import build_style_spec
from nini.config import settings
from nini.memory.storage import ArtifactStorage
from nini.sandbox.executor import sandbox_executor
from nini.sandbox.policy import SandboxPolicyError
from nini.sandbox.r_executor import RSandboxPolicyError
from nini.sandbox.r_router import r_sandbox_executor
from nini.tools.base import SkillResult
from nini.utils.chart_fonts import apply_plotly_cjk_font_fallback
from nini.utils.dataframe_io import dataframe_to_json_safe
from nini.workspace import WorkspaceManager

logger = logging.getLogger(__name__)


def _json_safe_records(df: pd.DataFrame, n_rows: int = 20) -> list[dict[str, Any]]:
    """DataFrame 预览转 JSON 安全结构。"""
    return dataframe_to_json_safe(df, n_rows=n_rows)


def _build_metadata(
    *,
    purpose: Any,
    label: Any,
    intent: Any,
) -> dict[str, str]:
    return {
        "intent": str(intent or label or "").strip(),
        "purpose": str(purpose or "exploration").strip(),
        "label": str(label).strip() if isinstance(label, str) else "",
    }


def _save_python_figures(
    session: Session,
    figures: list[dict[str, Any]],
    label: str | None = None,
) -> list[dict[str, Any]]:
    """将 Python 沙箱序列化的图表保存为工件产物。"""
    if not figures:
        return []

    storage = ArtifactStorage(session.id)
    ws = WorkspaceManager(session.id)
    artifacts: list[dict[str, Any]] = []
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    style_spec = build_style_spec()

    for idx, fig_info in enumerate(figures):
        var_name = fig_info.get("var_name", f"fig_{idx}")
        library = fig_info.get("library", "unknown")
        title = fig_info.get("title", "")
        if label:
            base_name = ws.sanitize_filename(label, default_name=f"fig_{idx}")[:40]
        elif title:
            base_name = title.replace(" ", "_")[:40]
        else:
            base_name = f"{var_name}_{ts}"

        if library == "matplotlib":
            for fmt_key in ("pdf", "svg", "png"):
                encoded = fig_info.get(f"{fmt_key}_data", "")
                if not encoded:
                    continue
                try:
                    data = base64.b64decode(encoded)
                    filename = f"{base_name}.{fmt_key}"
                    path = storage.save(data, filename)
                    record = ws.add_artifact_record(
                        name=filename,
                        artifact_type="chart",
                        file_path=path,
                        format_hint=fmt_key,
                    )
                    artifacts.append(
                        {
                            "name": filename,
                            "type": "chart",
                            "format": fmt_key,
                            "path": str(path),
                            "download_url": record.get("download_url", ""),
                            "render_engine": "matplotlib",
                            "style_key": style_spec.style_key,
                        }
                    )
                except Exception:
                    logger.debug("保存 matplotlib %s 失败", fmt_key, exc_info=True)
            continue

        if library != "plotly":
            continue

        plotly_json = fig_info.get("plotly_json", "")
        if not plotly_json:
            continue
        normalized_plotly_json = plotly_json
        normalized_chart_data: dict[str, Any] | None = None

        try:
            import json as json_mod
            import plotly.graph_objects as go

            normalized_fig = go.Figure(json_mod.loads(plotly_json))
            apply_plotly_cjk_font_fallback(normalized_fig)
            normalized_plotly_json = normalized_fig.to_json()
            normalized_chart_data = normalized_fig.to_plotly_json()
        except Exception:
            logger.debug("标准化 Plotly 中文字体失败，回退原始图表", exc_info=True)

        try:
            json_name = f"{base_name}.json"
            path = storage.save_text(normalized_plotly_json, json_name)
            ws.add_artifact_record(
                name=json_name,
                artifact_type="chart",
                file_path=path,
                format_hint="json",
            )
        except Exception:
            logger.debug("保存 Plotly JSON 失败", exc_info=True)

        try:
            import json as json_mod
            import plotly.graph_objects as go

            fig = go.Figure(json_mod.loads(normalized_plotly_json))
            apply_plotly_cjk_font_fallback(fig)
            html_name = f"{base_name}.html"
            html_path = storage.get_path(html_name)
            fig.write_html(str(html_path))
            record = ws.add_artifact_record(
                name=html_name,
                artifact_type="chart",
                file_path=html_path,
                format_hint="html",
            )
            artifacts.append(
                {
                    "name": html_name,
                    "type": "chart",
                    "format": "html",
                    "path": str(html_path),
                    "download_url": record.get("download_url", ""),
                }
            )
        except Exception:
            logger.debug("保存 Plotly HTML 失败", exc_info=True)

        export_timeout = settings.sandbox_image_export_timeout
        try:
            import json as json_mod
            import plotly.graph_objects as go

            fig = go.Figure(json_mod.loads(normalized_plotly_json))
            apply_plotly_cjk_font_fallback(fig)
            export_formats = [
                fmt for fmt in style_spec.export_formats if fmt in {"pdf", "svg", "png"}
            ] or ["pdf", "svg", "png"]
            for fmt in export_formats:
                img_name = f"{base_name}.{fmt}"
                img_path = storage.get_path(img_name)
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(
                        fig.write_image,
                        str(img_path),
                        format=fmt,
                        width=1200,
                        height=800,
                        scale=max(1, int(style_spec.dpi / 150)),
                    )
                    future.result(timeout=export_timeout)
                record = ws.add_artifact_record(
                    name=img_name,
                    artifact_type="chart",
                    file_path=img_path,
                    format_hint=fmt,
                )
                artifacts.append(
                    {
                        "name": img_name,
                        "type": "chart",
                        "format": fmt,
                        "path": str(img_path),
                        "download_url": record.get("download_url", ""),
                        "render_engine": "plotly",
                        "style_key": style_spec.style_key,
                    }
                )
        except concurrent.futures.TimeoutError:
            logger.warning(
                "Plotly 图片导出超时（>%ds），跳过 SVG/PNG 导出。",
                export_timeout,
            )
        except Exception:
            logger.debug("Plotly 图片导出跳过（kaleido/Chrome 不可用）", exc_info=True)

        try:
            import json as json_mod

            session.artifacts["latest_chart"] = {
                "chart_data": normalized_chart_data or json_mod.loads(normalized_plotly_json),
                "chart_type": "plotly_auto",
                "render_engine": "plotly",
                "style_key": style_spec.style_key,
            }
        except Exception:
            logger.debug("写入 latest_chart 失败", exc_info=True)

    return artifacts


def _save_r_figures(
    session: Session,
    figures: list[dict[str, Any]],
    label: str | None = None,
) -> list[dict[str, Any]]:
    if not figures:
        return []

    storage = ArtifactStorage(session.id)
    ws = WorkspaceManager(session.id)
    artifacts: list[dict[str, Any]] = []
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    for idx, fig in enumerate(figures, start=1):
        path_str = fig.get("path")
        if not isinstance(path_str, str) or not path_str:
            continue
        src_path = Path(path_str)
        if not src_path.exists() or not src_path.is_file():
            continue

        fmt = str(fig.get("format") or src_path.suffix.lstrip(".") or "bin").lower()
        if label:
            stem = ws.sanitize_filename(label, default_name=f"r_plot_{idx}")[:40]
        else:
            stem = ws.sanitize_filename(src_path.stem, default_name=f"r_plot_{idx}")[:40]
        filename = f"{stem}_{ts}_{idx:02d}.{fmt}"

        try:
            saved_path = storage.save(src_path.read_bytes(), filename)
            record = ws.add_artifact_record(
                name=filename,
                artifact_type="chart",
                file_path=saved_path,
                format_hint=fmt,
            )
            artifacts.append(
                {
                    "name": filename,
                    "type": "chart",
                    "format": fmt,
                    "path": str(saved_path),
                    "download_url": record.get("download_url", ""),
                    "render_engine": "r",
                }
            )
        except Exception:
            logger.debug("保存 R 图表产物失败: %s", src_path, exc_info=True)

    return artifacts


async def execute_python_code(
    session: Session,
    **kwargs: Any,
) -> SkillResult:
    """执行 Python 代码并返回统一结果。"""
    code = str(kwargs.get("code", "")).strip()
    dataset_name = kwargs.get("dataset_name")
    persist_df = bool(kwargs.get("persist_df", False))
    save_as = kwargs.get("save_as")
    metadata = _build_metadata(
        purpose=kwargs.get("purpose", "exploration"),
        label=kwargs.get("label"),
        intent=kwargs.get("intent"),
    )

    if not code:
        return SkillResult(
            success=False,
            message="代码不能为空",
            data={"metadata": metadata},
            metadata=metadata,
        )
    if dataset_name and dataset_name not in session.datasets:
        return SkillResult(success=False, message=f"数据集 '{dataset_name}' 不存在")

    try:
        payload = await sandbox_executor.execute(
            code=code,
            session_id=session.id,
            datasets=session.datasets,
            dataset_name=dataset_name,
            persist_df=persist_df,
        )
    except SandboxPolicyError as exc:
        return SkillResult(success=False, message=f"沙箱策略拦截: {exc}")

    if not payload.get("success"):
        err = payload.get("error") or "代码执行失败"
        return SkillResult(
            success=False,
            message=f"代码执行失败: {err}",
            data={
                "stdout": payload.get("stdout", ""),
                "stderr": payload.get("stderr", ""),
                "traceback": payload.get("traceback", ""),
            },
            metadata={"intent": metadata["intent"]} if metadata["intent"] else {},
        )

    persisted = payload.get("datasets") or {}
    if isinstance(persisted, dict):
        for name, df in persisted.items():
            if isinstance(name, str) and isinstance(df, pd.DataFrame):
                session.datasets[name] = df

    figures = payload.get("figures") or []
    saved_artifacts = _save_python_figures(
        session,
        figures,
        label=str(kwargs.get("label") or "").strip() or None,
    )

    stdout = str(payload.get("stdout", "")).strip()
    stderr = str(payload.get("stderr", "")).strip()
    result_obj = payload.get("result")

    if isinstance(result_obj, pd.DataFrame):
        if save_as:
            session.datasets[save_as] = result_obj
        preview = {
            "data": _json_safe_records(result_obj),
            "columns": [{"name": c, "dtype": str(result_obj[c].dtype)} for c in result_obj.columns],
            "total_rows": len(result_obj),
            "preview_rows": min(20, len(result_obj)),
        }
        extra = f"，已保存为数据集 '{save_as}'" if save_as else ""
        msg = f"代码执行成功，返回 DataFrame（{len(result_obj)} 行 × {len(result_obj.columns)} 列）{extra}"
        if saved_artifacts:
            msg += f"\n自动导出了 {len(saved_artifacts)} 个图表产物"
        if stdout:
            msg += f"\nstdout:\n{stdout}"
        if stderr:
            msg += f"\nstderr:\n{stderr}"
        return SkillResult(
            success=True,
            message=msg,
            data={"result_type": "dataframe"},
            has_dataframe=True,
            dataframe_preview=preview,
            artifacts=saved_artifacts,
            metadata={"intent": metadata["intent"]} if metadata["intent"] else {},
        )

    msg = "代码执行成功"
    if saved_artifacts:
        msg += f"\n自动导出了 {len(saved_artifacts)} 个图表产物"
    if stdout:
        msg += f"\nstdout:\n{stdout}"
    if stderr:
        msg += f"\nstderr:\n{stderr}"

    return SkillResult(
        success=True,
        message=msg,
        data={"result": result_obj, "result_type": type(result_obj).__name__},
        artifacts=saved_artifacts,
        metadata={"intent": metadata["intent"]} if metadata["intent"] else {},
    )


async def execute_r_code(
    session: Session,
    **kwargs: Any,
) -> SkillResult:
    """执行 R 代码并返回统一结果。"""
    code = str(kwargs.get("code", "")).strip()
    dataset_name = kwargs.get("dataset_name")
    persist_df = bool(kwargs.get("persist_df", False))
    save_as = kwargs.get("save_as")
    metadata = _build_metadata(
        purpose=kwargs.get("purpose", "exploration"),
        label=kwargs.get("label"),
        intent=kwargs.get("intent"),
    )

    if not code:
        return SkillResult(
            success=False,
            message="代码不能为空",
            data={"metadata": metadata},
            metadata=metadata,
        )
    if dataset_name and dataset_name not in session.datasets:
        return SkillResult(success=False, message=f"数据集 '{dataset_name}' 不存在")

    try:
        payload = await r_sandbox_executor.execute(
            code=code,
            session_id=session.id,
            datasets=session.datasets,
            dataset_name=dataset_name,
            persist_df=persist_df,
        )
    except RSandboxPolicyError as exc:
        return SkillResult(success=False, message=f"R 沙箱策略拦截: {exc}")

    if not payload.get("success"):
        err = payload.get("error") or "R 代码执行失败"
        return SkillResult(
            success=False,
            message=f"R 代码执行失败: {err}",
            data={
                "stdout": payload.get("stdout", ""),
                "stderr": payload.get("stderr", ""),
                "traceback": payload.get("traceback", ""),
            },
            metadata={"intent": metadata["intent"]} if metadata["intent"] else {},
        )

    persisted = payload.get("datasets") or {}
    if isinstance(persisted, dict):
        for name, df in persisted.items():
            if isinstance(name, str) and isinstance(df, pd.DataFrame):
                session.datasets[name] = df

    figures = payload.get("figures") or []
    saved_artifacts = _save_r_figures(
        session,
        figures,
        label=str(kwargs.get("label") or "").strip() or None,
    )

    stdout = str(payload.get("stdout", "")).strip()
    stderr = str(payload.get("stderr", "")).strip()
    output_df = payload.get("output_df")

    if isinstance(output_df, pd.DataFrame):
        if save_as:
            session.datasets[save_as] = output_df

        preview = {
            "data": dataframe_to_json_safe(output_df),
            "columns": [{"name": c, "dtype": str(output_df[c].dtype)} for c in output_df.columns],
            "total_rows": len(output_df),
            "preview_rows": min(20, len(output_df)),
        }
        extra = f"，已保存为数据集 '{save_as}'" if save_as else ""
        msg = f"R 代码执行成功，返回 DataFrame（{len(output_df)} 行 × {len(output_df.columns)} 列）{extra}"
        if saved_artifacts:
            msg += f"\n自动导出了 {len(saved_artifacts)} 个图表产物"
        if stdout:
            msg += f"\nstdout:\n{stdout}"
        if stderr:
            msg += f"\nstderr:\n{stderr}"

        return SkillResult(
            success=True,
            message=msg,
            data={"result_type": "dataframe"},
            has_dataframe=True,
            dataframe_preview=preview,
            artifacts=saved_artifacts,
            metadata={"intent": metadata["intent"]} if metadata["intent"] else {},
        )

    result_obj = payload.get("result")
    result_repr = payload.get("result_repr")
    msg = "R 代码执行成功"
    if saved_artifacts:
        msg += f"\n自动导出了 {len(saved_artifacts)} 个图表产物"
    if stdout:
        msg += f"\nstdout:\n{stdout}"
    if stderr:
        msg += f"\nstderr:\n{stderr}"

    data: dict[str, Any] = {
        "result": result_obj,
        "result_type": payload.get("result_type", type(result_obj).__name__),
    }
    if result_repr:
        data["result_repr"] = result_repr

    return SkillResult(
        success=True,
        message=msg,
        data=data,
        artifacts=saved_artifacts,
        metadata={"intent": metadata["intent"]} if metadata["intent"] else {},
    )
