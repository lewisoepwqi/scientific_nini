"""代码执行技能：在受限沙箱中运行 Python 代码。"""

from __future__ import annotations

import base64
import concurrent.futures
import logging
import math
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from nini.agent.session import Session
from nini.config import settings
from nini.memory.storage import ArtifactStorage
from nini.sandbox.executor import sandbox_executor
from nini.sandbox.policy import SandboxPolicyError
from nini.skills.base import Skill, SkillResult
from nini.utils.chart_fonts import apply_plotly_cjk_font_fallback
from nini.utils.dataframe_io import dataframe_to_json_safe
from nini.workspace import WorkspaceManager

logger = logging.getLogger(__name__)


def _json_safe_records(df: pd.DataFrame, n_rows: int = 20) -> list[dict[str, Any]]:
    """DataFrame 预览转 JSON 安全结构。

    注意：此函数已迁移到 nini.utils.dataframe_io.dataframe_to_json_safe，
    保留此包装函数以保持向后兼容。
    """
    return dataframe_to_json_safe(df, n_rows=n_rows)


class RunCodeSkill(Skill):
    """运行用户提供的 Python 代码。"""

    @property
    def name(self) -> str:
        return "run_code"

    @property
    def category(self) -> str:
        return "code"

    @property
    def description(self) -> str:
        return (
            "在受限沙箱中运行 Python 代码。支持 matplotlib/plotly 绘图，图表会自动检测并保存为产物。"
            "可使用变量：datasets（所有数据集字典）、df（指定 dataset_name 时可用）。"
            "可通过 result 返回结果，或通过 output_df 返回 DataFrame。"
            "绘制复杂自定义图表、子图布局、统计标注时，优先使用此工具而非 create_chart。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "要执行的 Python 代码片段",
                },
                "dataset_name": {
                    "type": "string",
                    "description": "可选。绑定为变量 df 的数据集名称",
                },
                "persist_df": {
                    "type": "boolean",
                    "default": False,
                    "description": "当 dataset_name 存在时，是否将修改后的 df 覆盖回原数据集",
                },
                "save_as": {
                    "type": "string",
                    "description": "可选。若 result/output_df 是 DataFrame，则另存为该数据集名",
                },
                "purpose": {
                    "type": "string",
                    "enum": ["exploration", "visualization", "export", "transformation"],
                    "default": "exploration",
                    "description": "代码用途：exploration=探索性分析，visualization=绘图，export=导出，transformation=数据变换",
                },
                "label": {
                    "type": "string",
                    "description": "简短描述代码用途，如'绘制组间箱线图'，用于产物命名",
                },
                "intent": {
                    "type": "string",
                    "description": "执行意图摘要（建议 8-30 字），用于记录本次 run_code 的分析目的",
                },
            },
            "required": ["code"],
        }

    def _save_figures(
        self,
        session: Session,
        figures: list[dict[str, Any]],
        label: str | None = None,
    ) -> list[dict[str, Any]]:
        """将沙箱序列化的图表保存为工件产物。

        返回产物记录列表，供 SkillResult.artifacts 使用。
        """
        if not figures:
            return []

        storage = ArtifactStorage(session.id)
        ws = WorkspaceManager(session.id)
        artifacts: list[dict[str, Any]] = []
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        for idx, fig_info in enumerate(figures):
            var_name = fig_info.get("var_name", f"fig_{idx}")
            library = fig_info.get("library", "unknown")
            title = fig_info.get("title", "")
            # 优先使用 label 命名，其次 title，最后回退 var_name_ts
            if label:
                base_name = ws.sanitize_filename(label, default_name=f"fig_{idx}")[:40]
            elif title:
                base_name = title.replace(" ", "_")[:40]
            else:
                base_name = f"{var_name}_{ts}"

            if library == "matplotlib":
                # 保存 SVG
                svg_b64 = fig_info.get("svg_data", "")
                if svg_b64:
                    try:
                        svg_bytes = base64.b64decode(svg_b64)
                        svg_name = f"{base_name}.svg"
                        path = storage.save(svg_bytes, svg_name)
                        record = ws.add_artifact_record(
                            name=svg_name,
                            artifact_type="chart",
                            file_path=path,
                            format_hint="svg",
                        )
                        artifacts.append(
                            {
                                "name": svg_name,
                                "type": "chart",
                                "format": "svg",
                                "path": str(path),
                                "download_url": record.get("download_url", ""),
                            }
                        )
                    except Exception:
                        logger.debug("保存 matplotlib SVG 失败", exc_info=True)

                # 保存 PNG
                png_b64 = fig_info.get("png_data", "")
                if png_b64:
                    try:
                        png_bytes = base64.b64decode(png_b64)
                        png_name = f"{base_name}.png"
                        path = storage.save(png_bytes, png_name)
                        record = ws.add_artifact_record(
                            name=png_name,
                            artifact_type="chart",
                            file_path=path,
                            format_hint="png",
                        )
                        artifacts.append(
                            {
                                "name": png_name,
                                "type": "chart",
                                "format": "png",
                                "path": str(path),
                                "download_url": record.get("download_url", ""),
                            }
                        )
                    except Exception:
                        logger.debug("保存 matplotlib PNG 失败", exc_info=True)

            elif library == "plotly":
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

                # 保存 JSON
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

                # 生成 HTML（始终可用）
                try:
                    import plotly.graph_objects as go
                    import json as json_mod

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

                # 尝试 SVG/PNG（需要 kaleido + Chrome），带超时保护
                export_timeout = settings.sandbox_image_export_timeout
                try:
                    import plotly.graph_objects as go
                    import json as json_mod

                    fig = go.Figure(json_mod.loads(normalized_plotly_json))
                    apply_plotly_cjk_font_fallback(fig)
                    for fmt in ("svg", "png"):
                        img_name = f"{base_name}.{fmt}"
                        img_path = storage.get_path(img_name)
                        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                            future = pool.submit(
                                fig.write_image,
                                str(img_path),
                                format=fmt,
                                width=1200,
                                height=800,
                                scale=2,
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
                            }
                        )
                except concurrent.futures.TimeoutError:
                    logger.warning(
                        "Plotly 图片导出超时（>%ds），跳过 SVG/PNG 导出。"
                        "请运行 `nini doctor` 检查 kaleido/Chrome 状态。",
                        export_timeout,
                    )
                except Exception:
                    # kaleido/Chrome 不可用时静默跳过图片导出
                    logger.debug("Plotly 图片导出跳过（kaleido/Chrome 不可用）", exc_info=True)

                # 写入 session.artifacts，使 export_chart 可复用
                try:
                    import json as json_mod

                    session.artifacts["latest_chart"] = {
                        "chart_data": normalized_chart_data
                        or json_mod.loads(normalized_plotly_json),
                        "chart_type": "plotly_auto",
                    }
                except Exception:
                    pass

        return artifacts

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        code = str(kwargs.get("code", "")).strip()
        dataset_name = kwargs.get("dataset_name")
        persist_df = bool(kwargs.get("persist_df", False))
        save_as = kwargs.get("save_as")
        purpose = str(kwargs.get("purpose", "exploration")).strip()
        label = kwargs.get("label") or None
        intent = str(kwargs.get("intent") or label or "").strip()
        metadata = {
            "intent": intent,
            "purpose": purpose,
            "label": str(label).strip() if isinstance(label, str) else "",
        }

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
                metadata={"intent": intent} if intent else {},
            )

        # 回写被持久化的数据集
        persisted = payload.get("datasets") or {}
        if isinstance(persisted, dict):
            for name, df in persisted.items():
                if isinstance(name, str) and isinstance(df, pd.DataFrame):
                    session.datasets[name] = df

        # 处理自动检测到的图表
        figures = payload.get("figures") or []
        saved_artifacts = self._save_figures(session, figures, label=label)

        stdout = str(payload.get("stdout", "")).strip()
        stderr = str(payload.get("stderr", "")).strip()
        result_obj = payload.get("result")

        if isinstance(result_obj, pd.DataFrame):
            if save_as:
                session.datasets[save_as] = result_obj
            preview = {
                "data": _json_safe_records(result_obj),
                "columns": [
                    {"name": c, "dtype": str(result_obj[c].dtype)} for c in result_obj.columns
                ],
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
                metadata={"intent": intent} if intent else {},
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
            metadata={"intent": intent} if intent else {},
        )
