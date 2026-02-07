"""数据清洗技能。"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from nini.agent.session import Session
from nini.skills.base import Skill, SkillResult


def _safe_preview(df: pd.DataFrame, n_rows: int = 20) -> dict[str, Any]:
    preview = df.head(n_rows)
    rows = preview.to_dict(orient="records")
    safe_rows: list[dict[str, Any]] = []
    for row in rows:
        safe_row: dict[str, Any] = {}
        for key, value in row.items():
            if isinstance(value, np.bool_):
                safe_row[key] = bool(value)
            elif isinstance(value, np.integer):
                safe_row[key] = int(value)
            elif isinstance(value, (np.floating, float)):
                if not math.isfinite(value):
                    safe_row[key] = None
                else:
                    safe_row[key] = float(value)
            elif pd.isna(value):
                safe_row[key] = None
            else:
                safe_row[key] = value
        safe_rows.append(safe_row)

    return {
        "data": safe_rows,
        "columns": [{"name": c, "dtype": str(df[c].dtype)} for c in df.columns],
        "total_rows": len(df),
        "preview_rows": min(n_rows, len(df)),
    }


class CleanDataSkill(Skill):
    """对数据集进行缺失值处理、异常值过滤与标准化。"""

    _missing_strategies = ["drop", "mean", "median", "mode", "zero", "ffill", "bfill"]
    _outlier_methods = ["none", "iqr", "zscore"]

    @property
    def name(self) -> str:
        return "clean_data"

    @property
    def description(self) -> str:
        return (
            "执行数据清洗：缺失值处理、异常值过滤、标准化。"
            "支持 inplace 覆盖原数据，或输出为新数据集。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "dataset_name": {"type": "string", "description": "输入数据集名称"},
                "missing_strategy": {
                    "type": "string",
                    "enum": self._missing_strategies,
                    "default": "mean",
                    "description": "缺失值处理策略",
                },
                "outlier_method": {
                    "type": "string",
                    "enum": self._outlier_methods,
                    "default": "none",
                    "description": "异常值处理方法",
                },
                "outlier_threshold": {
                    "type": "number",
                    "default": 3.0,
                    "description": "zscore 阈值（仅 outlier_method=zscore）",
                },
                "normalize_numeric": {
                    "type": "boolean",
                    "default": False,
                    "description": "是否对数值列做 Z-score 标准化",
                },
                "normalize_columns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "指定要标准化的列（为空则默认所有数值列）",
                },
                "inplace": {
                    "type": "boolean",
                    "default": False,
                    "description": "是否覆盖原数据集",
                },
                "output_dataset_name": {
                    "type": "string",
                    "description": "输出数据集名称（inplace=false 时可选）",
                },
            },
            "required": ["dataset_name"],
        }

    @property
    def is_idempotent(self) -> bool:
        return False

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        dataset_name = kwargs["dataset_name"]
        missing_strategy = str(kwargs.get("missing_strategy", "mean")).lower().strip()
        outlier_method = str(kwargs.get("outlier_method", "none")).lower().strip()
        outlier_threshold = float(kwargs.get("outlier_threshold", 3.0))
        normalize_numeric = bool(kwargs.get("normalize_numeric", False))
        normalize_columns = kwargs.get("normalize_columns") or []
        inplace = bool(kwargs.get("inplace", False))
        output_dataset_name = kwargs.get("output_dataset_name")

        df = session.datasets.get(dataset_name)
        if df is None:
            return SkillResult(success=False, message=f"数据集 '{dataset_name}' 不存在")
        if missing_strategy not in self._missing_strategies:
            return SkillResult(
                success=False, message=f"不支持的 missing_strategy: {missing_strategy}"
            )
        if outlier_method not in self._outlier_methods:
            return SkillResult(success=False, message=f"不支持的 outlier_method: {outlier_method}")

        cleaned = df.copy(deep=True)
        before_rows = len(cleaned)
        before_missing = int(cleaned.isna().sum().sum())

        self._handle_missing(cleaned, missing_strategy)
        removed_outliers = self._handle_outliers(cleaned, outlier_method, outlier_threshold)
        self._normalize(cleaned, normalize_numeric, normalize_columns)

        after_rows = len(cleaned)
        after_missing = int(cleaned.isna().sum().sum())

        if inplace:
            target_name = dataset_name
        else:
            target_name = output_dataset_name or self._default_output_name(dataset_name)
        session.datasets[target_name] = cleaned

        summary = {
            "input_dataset": dataset_name,
            "output_dataset": target_name,
            "inplace": inplace,
            "missing_strategy": missing_strategy,
            "outlier_method": outlier_method,
            "rows_before": before_rows,
            "rows_after": after_rows,
            "rows_removed_by_outlier": removed_outliers,
            "missing_before": before_missing,
            "missing_after": after_missing,
        }

        msg = (
            f"数据清洗完成：{dataset_name} -> {target_name}，"
            f"行数 {before_rows}->{after_rows}，缺失值 {before_missing}->{after_missing}"
        )

        preview = _safe_preview(cleaned)
        return SkillResult(
            success=True,
            message=msg,
            data=summary,
            has_dataframe=True,
            dataframe_preview=preview,
        )

    def _handle_missing(self, df: pd.DataFrame, strategy: str) -> None:
        if strategy == "drop":
            df.dropna(inplace=True)
            df.reset_index(drop=True, inplace=True)
            return

        if strategy == "ffill":
            df.fillna(method="ffill", inplace=True)
            return
        if strategy == "bfill":
            df.fillna(method="bfill", inplace=True)
            return

        numeric_cols = df.select_dtypes(include="number").columns.tolist()
        non_numeric_cols = [c for c in df.columns if c not in numeric_cols]

        if strategy == "mean":
            for col in numeric_cols:
                df[col] = df[col].fillna(df[col].mean())
            for col in non_numeric_cols:
                mode = df[col].mode(dropna=True)
                if len(mode) > 0:
                    df[col] = df[col].fillna(mode.iloc[0])
            return

        if strategy == "median":
            for col in numeric_cols:
                df[col] = df[col].fillna(df[col].median())
            for col in non_numeric_cols:
                mode = df[col].mode(dropna=True)
                if len(mode) > 0:
                    df[col] = df[col].fillna(mode.iloc[0])
            return

        if strategy == "mode":
            for col in df.columns:
                mode = df[col].mode(dropna=True)
                if len(mode) > 0:
                    df[col] = df[col].fillna(mode.iloc[0])
            return

        if strategy == "zero":
            for col in numeric_cols:
                df[col] = df[col].fillna(0)
            for col in non_numeric_cols:
                df[col] = df[col].fillna("")

    def _handle_outliers(self, df: pd.DataFrame, method: str, threshold: float) -> int:
        if method == "none":
            return 0

        numeric_cols = df.select_dtypes(include="number").columns.tolist()
        if not numeric_cols:
            return 0

        before = len(df)
        mask = pd.Series([True] * len(df), index=df.index)

        if method == "iqr":
            for col in numeric_cols:
                q1 = df[col].quantile(0.25)
                q3 = df[col].quantile(0.75)
                iqr = q3 - q1
                if pd.isna(iqr) or iqr == 0:
                    continue
                low = q1 - 1.5 * iqr
                high = q3 + 1.5 * iqr
                mask &= df[col].between(low, high) | df[col].isna()

        if method == "zscore":
            for col in numeric_cols:
                std = df[col].std()
                if pd.isna(std) or std == 0:
                    continue
                z = (df[col] - df[col].mean()) / std
                mask &= z.abs().le(threshold) | df[col].isna()

        filtered = df[mask].copy()
        df.drop(df.index, inplace=True)
        if len(filtered) > 0:
            df[filtered.columns] = filtered
        df.reset_index(drop=True, inplace=True)
        return before - len(df)

    def _normalize(self, df: pd.DataFrame, normalize_numeric: bool, columns: list[str]) -> None:
        if not normalize_numeric:
            return
        if columns:
            target_cols = [col for col in columns if col in df.columns]
        else:
            target_cols = df.select_dtypes(include="number").columns.tolist()

        for col in target_cols:
            if not pd.api.types.is_numeric_dtype(df[col]):
                continue
            std = df[col].std()
            if pd.isna(std) or std == 0:
                continue
            df[col] = (df[col] - df[col].mean()) / std

    def _default_output_name(self, dataset_name: str) -> str:
        if "." in dataset_name:
            base, ext = dataset_name.rsplit(".", 1)
            return f"{base}_cleaned.{ext}"
        return f"{dataset_name}_cleaned"
