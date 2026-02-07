"""代码执行技能：在受限沙箱中运行 Python 代码。"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from nini.agent.session import Session
from nini.sandbox.executor import sandbox_executor
from nini.sandbox.policy import SandboxPolicyError
from nini.skills.base import Skill, SkillResult


def _json_safe_records(df: pd.DataFrame, n_rows: int = 20) -> list[dict[str, Any]]:
    """DataFrame 预览转 JSON 安全结构。"""
    preview = df.head(n_rows)
    rows = preview.to_dict(orient="records")
    safe_rows: list[dict[str, Any]] = []
    for row in rows:
        safe_row: dict[str, Any] = {}
        for key, value in row.items():
            if isinstance(value, (np.integer, np.floating, float)):
                if isinstance(value, (np.floating, float)) and not math.isfinite(value):
                    safe_row[key] = None
                else:
                    safe_row[key] = float(value)
            elif pd.isna(value):
                safe_row[key] = None
            else:
                safe_row[key] = value
        safe_rows.append(safe_row)
    return safe_rows


class RunCodeSkill(Skill):
    """运行用户提供的 Python 代码。"""

    @property
    def name(self) -> str:
        return "run_code"

    @property
    def description(self) -> str:
        return (
            "在受限沙箱中运行 Python 代码。"
            "可使用变量：datasets（所有数据集字典）、df（指定 dataset_name 时可用）。"
            "可通过 result 返回结果，或通过 output_df 返回 DataFrame。"
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
            },
            "required": ["code"],
        }

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        code = str(kwargs.get("code", "")).strip()
        dataset_name = kwargs.get("dataset_name")
        persist_df = bool(kwargs.get("persist_df", False))
        save_as = kwargs.get("save_as")

        if not code:
            return SkillResult(success=False, message="代码不能为空")
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
            )

        # 回写被持久化的数据集
        persisted = payload.get("datasets") or {}
        if isinstance(persisted, dict):
            for name, df in persisted.items():
                if isinstance(name, str) and isinstance(df, pd.DataFrame):
                    session.datasets[name] = df

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
            )

        msg = "代码执行成功"
        if stdout:
            msg += f"\nstdout:\n{stdout}"
        if stderr:
            msg += f"\nstderr:\n{stderr}"

        return SkillResult(
            success=True,
            message=msg,
            data={"result": result_obj, "result_type": type(result_obj).__name__},
        )
