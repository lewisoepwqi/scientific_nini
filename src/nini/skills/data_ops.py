"""数据操作技能：加载、预览、摘要。

核心逻辑来源于历史版本的数据处理实现，已适配当前 Nini 架构。
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from nini.agent.session import Session
from nini.skills.base import Skill, SkillResult


# ---- 工具函数 ----


def _safe_float(value: float | None) -> float | None:
    """将非有限数值转换为 None。"""
    if value is None:
        return None
    if not math.isfinite(value):
        return None
    return float(value)


def _dataframe_to_json_safe(df: pd.DataFrame) -> list[dict[str, Any]]:
    """将 DataFrame 转换为 JSON 安全的字典列表。"""
    records = df.to_dict(orient="records")
    result = []
    for record in records:
        safe_record = {}
        for k, v in record.items():
            if isinstance(v, np.bool_):
                safe_record[k] = bool(v)
            elif isinstance(v, np.integer):
                safe_record[k] = int(v)
            elif isinstance(v, (np.floating, float)):
                if not math.isfinite(v):
                    safe_record[k] = None
                else:
                    safe_record[k] = float(v)
            elif pd.isna(v):
                safe_record[k] = None
            else:
                safe_record[k] = v
        result.append(safe_record)
    return result


# ---- 技能实现 ----


class LoadDatasetSkill(Skill):
    """加载已上传的数据集到会话。"""

    @property
    def name(self) -> str:
        return "load_dataset"

    @property
    def description(self) -> str:
        return "加载已上传的数据集。传入数据集名称（文件名），返回数据集基本信息。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "dataset_name": {
                    "type": "string",
                    "description": "数据集名称（文件名，例如 experiment.csv）",
                },
            },
            "required": ["dataset_name"],
        }

    @property
    def is_idempotent(self) -> bool:
        return True

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        name = kwargs.get("dataset_name", "")

        if not name:
            # 如果没有指定名称，返回所有已加载数据集的列表
            datasets = list(session.datasets.keys())
            if not datasets:
                return SkillResult(
                    success=False,
                    message="当前会话没有已加载的数据集。请先上传数据文件。",
                )
            return SkillResult(
                success=True,
                data={"datasets": datasets},
                message=f"当前已加载 {len(datasets)} 个数据集: {', '.join(datasets)}",
            )

        if name not in session.datasets:
            available = list(session.datasets.keys())
            return SkillResult(
                success=False,
                message=f"数据集 '{name}' 不存在。可用数据集: {', '.join(available) or '无'}",
            )

        df = session.datasets[name]
        info = {
            "name": name,
            "rows": len(df),
            "columns": len(df.columns),
            "column_names": df.columns.tolist(),
            "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
            "memory_mb": round(df.memory_usage(deep=True).sum() / 1024 / 1024, 2),
        }

        return SkillResult(
            success=True,
            data=info,
            message=f"数据集 '{name}': {info['rows']} 行 × {info['columns']} 列",
        )


class PreviewDataSkill(Skill):
    """预览数据集的前 N 行。"""

    @property
    def name(self) -> str:
        return "preview_data"

    @property
    def description(self) -> str:
        return "预览数据集的前 N 行数据和列信息。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "dataset_name": {
                    "type": "string",
                    "description": "数据集名称",
                },
                "n_rows": {
                    "type": "integer",
                    "description": "预览行数，默认 5",
                    "default": 5,
                },
            },
            "required": ["dataset_name"],
        }

    @property
    def is_idempotent(self) -> bool:
        return True

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        name = kwargs["dataset_name"]
        n_rows = kwargs.get("n_rows", 5)

        df = session.datasets.get(name)
        if df is None:
            return SkillResult(success=False, message=f"数据集 '{name}' 不存在")

        preview_df = df.head(n_rows)
        data = _dataframe_to_json_safe(preview_df)

        # 列信息
        columns_info = []
        for col in df.columns:
            col_info: dict[str, Any] = {
                "name": col,
                "dtype": str(df[col].dtype),
                "null_count": int(df[col].isnull().sum()),
                "unique_count": int(df[col].nunique()),
            }
            # 样本值
            samples = df[col].dropna().head(3).tolist()
            col_info["sample_values"] = [str(s) for s in samples]
            columns_info.append(col_info)

        result = {
            "data": data,
            "columns": columns_info,
            "total_rows": len(df),
            "preview_rows": min(n_rows, len(df)),
        }

        return SkillResult(
            success=True,
            data=result,
            message=f"数据集 '{name}' 预览（{result['preview_rows']}/{result['total_rows']} 行）",
            has_dataframe=True,
            dataframe_preview=result,
        )


class DataSummarySkill(Skill):
    """计算数据集的描述性统计摘要。"""

    @property
    def name(self) -> str:
        return "data_summary"

    @property
    def description(self) -> str:
        return "计算数据集的全面统计摘要，包括数值列的均值、标准差、分位数，分类列的频次等。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "dataset_name": {
                    "type": "string",
                    "description": "数据集名称",
                },
            },
            "required": ["dataset_name"],
        }

    @property
    def is_idempotent(self) -> bool:
        return True

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        name = kwargs["dataset_name"]
        df = session.datasets.get(name)
        if df is None:
            return SkillResult(success=False, message=f"数据集 '{name}' 不存在")

        summary: dict[str, Any] = {
            "shape": {"rows": len(df), "columns": len(df.columns)},
            "missing_values": {
                col: int(df[col].isnull().sum())
                for col in df.columns
                if df[col].isnull().any()
            },
        }

        # 数值列统计
        numeric_stats = {}
        for col in df.select_dtypes(include=[np.number]).columns:
            series = df[col].dropna()
            if len(series) > 0:
                numeric_stats[col] = {
                    "count": len(series),
                    "mean": _safe_float(series.mean()),
                    "std": _safe_float(series.std()),
                    "min": _safe_float(series.min()),
                    "q25": _safe_float(series.quantile(0.25)),
                    "median": _safe_float(series.median()),
                    "q75": _safe_float(series.quantile(0.75)),
                    "max": _safe_float(series.max()),
                }
        summary["numeric_stats"] = numeric_stats

        # 分类列统计
        categorical_stats = {}
        for col in df.select_dtypes(include=["object", "category"]).columns:
            vc = df[col].value_counts().head(10)
            categorical_stats[col] = {
                "unique_count": int(df[col].nunique()),
                "top_values": [
                    {"value": str(k), "count": int(v)} for k, v in vc.items()
                ],
            }
        summary["categorical_stats"] = categorical_stats

        # 列类型检测
        column_types = {}
        for col in df.columns:
            series = df[col]
            if pd.api.types.is_datetime64_any_dtype(series):
                column_types[col] = "datetime"
            elif pd.api.types.is_numeric_dtype(series):
                unique_ratio = series.nunique() / max(len(series.dropna()), 1)
                if unique_ratio < 0.05 and series.nunique() < 20:
                    column_types[col] = "categorical_numeric"
                else:
                    column_types[col] = "continuous"
            elif series.nunique() < 20:
                column_types[col] = "categorical"
            else:
                column_types[col] = "text"
        summary["column_types"] = column_types

        return SkillResult(
            success=True,
            data=summary,
            message=(
                f"数据集 '{name}' 摘要: {summary['shape']['rows']} 行 × {summary['shape']['columns']} 列, "
                f"{len(numeric_stats)} 个数值列, {len(categorical_stats)} 个分类列"
            ),
        )
