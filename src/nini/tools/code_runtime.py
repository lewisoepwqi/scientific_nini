"""脚本执行共享运行时。"""

from __future__ import annotations

import base64
import concurrent.futures
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import uuid

import pandas as pd

from nini.agent.session import Session
from nini.charts import build_style_spec
from nini.config import settings
from nini.memory.storage import ArtifactStorage
from nini.models import ResourceType
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


def _persist_runtime_dataset(
    session: Session,
    *,
    dataset_name: str,
    df: pd.DataFrame,
    temporary: bool,
) -> dict[str, Any]:
    """将运行时 DataFrame 落盘并注册为可复用资源。"""
    normalized_name = str(dataset_name or "").strip() or f"dataset_{uuid.uuid4().hex[:8]}"
    session.datasets[normalized_name] = df

    manager = WorkspaceManager(session.id)
    resource_type = ResourceType.TEMP_DATASET if temporary else ResourceType.DATASET
    source_kind = "temp_datasets" if temporary else "datasets"
    retention = "session" if temporary else "persistent"
    dataset_id = ("tmp_" if temporary else "ds_") + uuid.uuid4().hex[:12]
    path = manager.build_managed_resource_path(
        resource_type,
        f"{normalized_name}.csv",
        default_name=f"{dataset_id}.csv",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    record = manager.add_dataset_record(
        dataset_id=dataset_id,
        name=normalized_name,
        file_path=path,
        file_type="csv",
        file_size=path.stat().st_size,
        row_count=len(df),
        column_count=len(df.columns),
        resource_type=resource_type,
        source_kind=source_kind,
        retention=retention,
    )
    resource = manager.get_resource_summary(str(record.get("id", "")).strip())
    if isinstance(resource, dict):
        return resource
    return {
        "id": record.get("id", dataset_id),
        "resource_type": resource_type.value,
        "name": normalized_name,
        "source_kind": source_kind,
        "metadata": {"retention": retention},
    }


def _build_output_resource_refs(resources: list[dict[str, Any]]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in resources:
        if not isinstance(item, dict):
            continue
        resource_id = str(item.get("id", "")).strip()
        resource_type = str(item.get("resource_type", "")).strip()
        if not resource_id or not resource_type or resource_id in seen:
            continue
        seen.add(resource_id)
        refs.append(
            {
                "resource_id": resource_id,
                "resource_type": resource_type,
                "name": str(item.get("name", "")).strip() or resource_id,
            }
        )
    return refs


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

        raw_plotly_json = fig_info.get("plotly_json")
        if not isinstance(raw_plotly_json, str) or not raw_plotly_json:
            continue
        normalized_plotly_json: str = raw_plotly_json
        normalized_chart_data: dict[str, Any] | None = None

        try:
            import json as json_mod
            import plotly.graph_objects as go

            normalized_fig = go.Figure(json_mod.loads(raw_plotly_json))
            apply_plotly_cjk_font_fallback(normalized_fig)
            normalized_plotly_json = str(normalized_fig.to_json())
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

    output_resources: list[dict[str, Any]] = []
    persisted = payload.get("datasets") or {}
    if isinstance(persisted, dict):
        for name, df in persisted.items():
            if not isinstance(name, str) or not isinstance(df, pd.DataFrame):
                continue
            normalized_name = name.strip()
            is_persistent_dataset = bool(
                (save_as and normalized_name == str(save_as).strip())
                or (persist_df and dataset_name and normalized_name == str(dataset_name).strip())
            )
            output_resources.append(
                _persist_runtime_dataset(
                    session,
                    dataset_name=normalized_name,
                    df=df,
                    temporary=not is_persistent_dataset,
                )
            )

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
        output_dataset_name = (
            str(save_as).strip() if isinstance(save_as, str) and save_as.strip() else ""
        )
        if not output_dataset_name:
            output_dataset_name = (
                f"tmp_python_output_{datetime.now(timezone.utc).strftime('%H%M%S')}"
            )
        output_resources.append(
            _persist_runtime_dataset(
                session,
                dataset_name=output_dataset_name,
                df=result_obj,
                temporary=not bool(save_as),
            )
        )
        output_refs = _build_output_resource_refs(output_resources)
        primary_ref = output_refs[-1] if output_refs else None
        preview = {
            "data": _json_safe_records(result_obj),
            "columns": [{"name": c, "dtype": str(result_obj[c].dtype)} for c in result_obj.columns],
            "total_rows": len(result_obj),
            "preview_rows": min(20, len(result_obj)),
        }
        extra = f"，已保存为数据集 '{output_dataset_name}'"
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
            data={
                "result_type": "dataframe",
                "output_dataset_name": output_dataset_name,
                "output_resources": output_refs,
                "resource_id": (
                    primary_ref.get("resource_id") if isinstance(primary_ref, dict) else None
                ),
                "resource_type": (
                    primary_ref.get("resource_type") if isinstance(primary_ref, dict) else None
                ),
            },
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

    output_refs = _build_output_resource_refs(output_resources)
    return SkillResult(
        success=True,
        message=msg,
        data={
            "result": result_obj,
            "result_type": type(result_obj).__name__,
            "output_resources": output_refs,
        },
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

    output_resources: list[dict[str, Any]] = []
    persisted = payload.get("datasets") or {}
    if isinstance(persisted, dict):
        for name, df in persisted.items():
            if not isinstance(name, str) or not isinstance(df, pd.DataFrame):
                continue
            normalized_name = name.strip()
            is_persistent_dataset = bool(
                (save_as and normalized_name == str(save_as).strip())
                or (persist_df and dataset_name and normalized_name == str(dataset_name).strip())
            )
            output_resources.append(
                _persist_runtime_dataset(
                    session,
                    dataset_name=normalized_name,
                    df=df,
                    temporary=not is_persistent_dataset,
                )
            )

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
        output_dataset_name = (
            str(save_as).strip() if isinstance(save_as, str) and save_as.strip() else ""
        )
        if not output_dataset_name:
            output_dataset_name = f"tmp_r_output_{datetime.now(timezone.utc).strftime('%H%M%S')}"
        output_resources.append(
            _persist_runtime_dataset(
                session,
                dataset_name=output_dataset_name,
                df=output_df,
                temporary=not bool(save_as),
            )
        )
        output_refs = _build_output_resource_refs(output_resources)
        primary_ref = output_refs[-1] if output_refs else None

        preview_rows = min(20, len(output_df))
        preview = {
            "data": dataframe_to_json_safe(output_df, n_rows=preview_rows),
            "columns": [{"name": c, "dtype": str(output_df[c].dtype)} for c in output_df.columns],
            "total_rows": len(output_df),
            "preview_rows": preview_rows,
        }
        extra = f"，已保存为数据集 '{output_dataset_name}'"
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
            data={
                "result_type": "dataframe",
                "output_dataset_name": output_dataset_name,
                "output_resources": output_refs,
                "resource_id": (
                    primary_ref.get("resource_id") if isinstance(primary_ref, dict) else None
                ),
                "resource_type": (
                    primary_ref.get("resource_type") if isinstance(primary_ref, dict) else None
                ),
            },
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
    data["output_resources"] = _build_output_resource_refs(output_resources)

    return SkillResult(
        success=True,
        message=msg,
        data=data,
        artifacts=saved_artifacts,
        metadata={"intent": metadata["intent"]} if metadata["intent"] else {},
    )
