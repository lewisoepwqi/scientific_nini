"""R 代码执行技能：在受限 R 沙箱中运行代码。"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from nini.agent.session import Session
from nini.memory.storage import ArtifactStorage
from nini.sandbox.r_executor import RSandboxPolicyError, r_sandbox_executor
from nini.skills.base import Skill, SkillResult
from nini.utils.dataframe_io import dataframe_to_json_safe
from nini.workspace import WorkspaceManager

logger = logging.getLogger(__name__)


class RunRCodeSkill(Skill):
    """运行用户提供的 R 代码。"""

    @property
    def name(self) -> str:
        return "run_r_code"

    @property
    def category(self) -> str:
        return "utility"

    @property
    def description(self) -> str:
        return (
            "在受限沙箱中运行 R 代码。支持 datasets/df 数据集注入，"
            "可通过 result 返回结构化结果，或通过 output_df 返回数据框。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "要执行的 R 代码片段",
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
                    "description": "可选。若 result/output_df 是数据框，则另存为该数据集名",
                },
                "purpose": {
                    "type": "string",
                    "enum": ["exploration", "visualization", "export", "transformation"],
                    "default": "exploration",
                    "description": "代码用途：用于执行历史与产物命名策略",
                },
                "label": {
                    "type": "string",
                    "description": "简短描述代码用途，如‘R 绘制昼夜节律图’",
                },
                "intent": {
                    "type": "string",
                    "description": "执行意图摘要（建议 8-30 字），用于记录本次 run_r_code 的分析目的",
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

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        code = str(kwargs.get("code", "")).strip()
        dataset_name = kwargs.get("dataset_name")
        persist_df = bool(kwargs.get("persist_df", False))
        save_as = kwargs.get("save_as")
        label = kwargs.get("label") or None
        intent = str(kwargs.get("intent") or label or "").strip()
        purpose = str(kwargs.get("purpose", "exploration")).strip()

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
                metadata={"intent": intent} if intent else {},
            )

        persisted = payload.get("datasets") or {}
        if isinstance(persisted, dict):
            for name, df in persisted.items():
                if isinstance(name, str) and isinstance(df, pd.DataFrame):
                    session.datasets[name] = df

        figures = payload.get("figures") or []
        saved_artifacts = self._save_figures(session, figures, label=label)

        stdout = str(payload.get("stdout", "")).strip()
        stderr = str(payload.get("stderr", "")).strip()
        output_df = payload.get("output_df")

        if isinstance(output_df, pd.DataFrame):
            if save_as:
                session.datasets[save_as] = output_df

            preview = {
                "data": dataframe_to_json_safe(output_df),
                "columns": [
                    {"name": c, "dtype": str(output_df[c].dtype)} for c in output_df.columns
                ],
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
                metadata={"intent": intent} if intent else {},
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
            metadata={"intent": intent} if intent else {},
        )
