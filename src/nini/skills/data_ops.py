"""数据操作技能：加载、预览、摘要。

核心逻辑来源于历史版本的数据处理实现，已适配当前 Nini 架构。
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from nini.agent.session import Session
from nini.skills.base import Skill, SkillResult
from nini.utils.dataframe_io import (
    dataframe_to_json_safe,
    list_excel_sheet_names,
    read_excel_all_sheets,
    read_excel_sheet_dataframe,
)
from nini.workspace import WorkspaceManager

# ---- 工具函数 ----


def _safe_float(value: float | None) -> float | None:
    """将非有限数值转换为 None。"""
    if value is None:
        return None
    if not math.isfinite(value):
        return None
    return float(value)


def _dataframe_to_json_safe(df: pd.DataFrame) -> list[dict[str, Any]]:
    """将 DataFrame 转换为 JSON 安全的字典列表。

    注意：此函数已迁移到 nini.utils.dataframe_io.dataframe_to_json_safe，
    保留此包装函数以保持向后兼容。
    """
    return dataframe_to_json_safe(df)


def _unique_dataset_name(session: Session, preferred_name: str) -> str:
    """保证新数据集名不与会话中已有名称冲突。"""
    name = preferred_name.strip() or "dataset"
    if name not in session.datasets:
        return name
    index = 2
    while f"{name}_{index}" in session.datasets:
        index += 1
    return f"{name}_{index}"


# ---- 技能实现 ----


class LoadDatasetSkill(Skill):
    """加载已上传的数据集到会话。"""

    @property
    def name(self) -> str:
        return "load_dataset"

    @property
    def category(self) -> str:
        return "data"

    @property
    def description(self) -> str:
        return (
            "加载已上传的数据集。默认返回数据集基本信息。"
            "对于 Excel 文件，支持按 sheet 读取（sheet_mode=single）或读取全部 sheet（sheet_mode=all），"
            "并可选择将全部 sheet 合并为一个数据集（combine_sheets=true）。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "dataset_name": {
                    "type": "string",
                    "description": "数据集名称（文件名，例如 experiment.csv）",
                },
                "sheet_mode": {
                    "type": "string",
                    "enum": ["default", "single", "all"],
                    "default": "default",
                    "description": (
                        "Excel 读取模式：default=默认加载；single=仅加载指定 sheet；"
                        "all=加载全部 sheet（可选合并）"
                    ),
                },
                "sheet_name": {
                    "type": "string",
                    "description": "sheet_mode=single 时必填，目标工作表名称",
                },
                "combine_sheets": {
                    "type": "boolean",
                    "default": False,
                    "description": "sheet_mode=all 时是否将全部 sheet 合并为一个数据集",
                },
                "include_sheet_column": {
                    "type": "boolean",
                    "default": True,
                    "description": "合并模式下是否新增 `__sheet_name__` 列标记来源 sheet",
                },
                "output_dataset_name": {
                    "type": "string",
                    "description": "可选。指定输出数据集名称（用于 single/all+combine）",
                },
            },
            "required": ["dataset_name"],
        }

    @property
    def is_idempotent(self) -> bool:
        return True

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        name = kwargs.get("dataset_name", "")
        sheet_mode = str(kwargs.get("sheet_mode", "default")).strip().lower()
        sheet_name_raw = kwargs.get("sheet_name")
        combine_sheets = bool(kwargs.get("combine_sheets", False))
        include_sheet_column = bool(kwargs.get("include_sheet_column", True))
        output_dataset_name_raw = str(kwargs.get("output_dataset_name", "")).strip()

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

        if sheet_mode not in {"default", "single", "all"}:
            return SkillResult(
                success=False,
                message="sheet_mode 仅支持: default/single/all",
            )

        manager = WorkspaceManager(session.id)

        if sheet_mode == "default":
            if name not in session.datasets:
                record = manager.get_dataset_by_name(name)
                if record is not None:
                    dataset_id = str(record.get("id", "")).strip()
                    if dataset_id:
                        try:
                            _, df_loaded = manager.load_dataset_by_id(dataset_id)
                            session.datasets[name] = df_loaded
                        except Exception:
                            pass
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

        record = manager.get_dataset_by_name(name)
        if record is None:
            return SkillResult(success=False, message=f"数据集 '{name}' 未在工作区中找到")

        ext = str(record.get("file_type", "")).strip().lower()
        if ext not in {"xlsx", "xls"}:
            return SkillResult(
                success=False,
                message=f"数据集 '{name}' 不是 Excel 文件，无法使用 sheet_mode={sheet_mode}",
            )

        file_path = Path(str(record.get("file_path", "")).strip())
        if not file_path.exists():
            return SkillResult(success=False, message=f"数据集文件不存在: {file_path}")

        if sheet_mode == "single":
            try:
                available_sheets = list_excel_sheet_names(file_path, ext)
            except Exception:
                available_sheets = []
            if not isinstance(sheet_name_raw, str) or not sheet_name_raw.strip():
                extra = f"；可用 sheet: {', '.join(available_sheets)}" if available_sheets else ""
                return SkillResult(
                    success=False, message=f"sheet_mode=single 时必须提供 sheet_name{extra}"
                )
            sheet_name = sheet_name_raw.strip()
            try:
                df_sheet = read_excel_sheet_dataframe(file_path, ext, sheet_name=sheet_name)
            except Exception as exc:
                extra = f"；可用 sheet: {', '.join(available_sheets)}" if available_sheets else ""
                return SkillResult(success=False, message=f"读取 sheet 失败: {exc}{extra}")

            preferred = output_dataset_name_raw or f"{name}[{sheet_name}]"
            output_name = _unique_dataset_name(session, preferred)
            session.datasets[output_name] = df_sheet

            return SkillResult(
                success=True,
                data={
                    "source_dataset": name,
                    "sheet_mode": "single",
                    "sheet_name": sheet_name,
                    "output_dataset": output_name,
                    "rows": len(df_sheet),
                    "columns": len(df_sheet.columns),
                },
                message=f"已加载 sheet '{sheet_name}' 到数据集 '{output_name}'（{len(df_sheet)} 行 × {len(df_sheet.columns)} 列）",
            )

        try:
            sheets_map = read_excel_all_sheets(file_path, ext)
            sheet_names = list_excel_sheet_names(file_path, ext)
        except Exception as exc:
            return SkillResult(success=False, message=f"读取全部 sheet 失败: {exc}")

        if not sheets_map:
            return SkillResult(success=False, message=f"Excel 文件 '{name}' 不包含可读取的 sheet")

        if combine_sheets:
            combined_parts: list[pd.DataFrame] = []
            for s_name, s_df in sheets_map.items():
                piece = s_df.copy()
                if include_sheet_column:
                    piece["__sheet_name__"] = s_name
                combined_parts.append(piece)
            merged = pd.concat(combined_parts, ignore_index=True, sort=False)

            preferred = output_dataset_name_raw or f"{name}[all_combined]"
            output_name = _unique_dataset_name(session, preferred)
            session.datasets[output_name] = merged

            return SkillResult(
                success=True,
                data={
                    "source_dataset": name,
                    "sheet_mode": "all",
                    "combine_sheets": True,
                    "sheet_count": len(sheet_names),
                    "sheet_names": sheet_names,
                    "output_dataset": output_name,
                    "rows": len(merged),
                    "columns": len(merged.columns),
                },
                message=(
                    f"已加载并合并 {len(sheet_names)} 个 sheet 到数据集 '{output_name}'"
                    f"（{len(merged)} 行 × {len(merged.columns)} 列）"
                ),
            )

        created: list[dict[str, Any]] = []
        for s_name, s_df in sheets_map.items():
            preferred = f"{name}[{s_name}]"
            out_name = _unique_dataset_name(session, preferred)
            session.datasets[out_name] = s_df
            created.append(
                {
                    "name": out_name,
                    "sheet_name": s_name,
                    "rows": len(s_df),
                    "columns": len(s_df.columns),
                }
            )

        return SkillResult(
            success=True,
            data={
                "source_dataset": name,
                "sheet_mode": "all",
                "combine_sheets": False,
                "sheet_count": len(sheet_names),
                "sheet_names": sheet_names,
                "created_datasets": created,
            },
            message=f"已加载全部 sheet，共创建 {len(created)} 个数据集",
        )


class PreviewDataSkill(Skill):
    """预览数据集的前 N 行。"""

    @property
    def name(self) -> str:
        return "preview_data"

    @property
    def category(self) -> str:
        return "data"

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
    def category(self) -> str:
        return "data"

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
                col: int(df[col].isnull().sum()) for col in df.columns if df[col].isnull().any()
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
                "top_values": [{"value": str(k), "count": int(v)} for k, v in vc.items()],
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
