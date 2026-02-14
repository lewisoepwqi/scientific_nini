"""表格读取工具：按扩展名解析为 DataFrame，以及 DataFrame 序列化工具。"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, NoReturn

import numpy as np
import pandas as pd


def _raise_excel_parse_error(exc: Exception, ext_norm: str) -> NoReturn:
    """将底层 Excel 读取异常转换为更友好的中文错误。"""
    message = str(exc)
    lower = message.lower()

    if "workbook is encrypted" in lower or "file is encrypted" in lower:
        raise ValueError(
            f"解析 .{ext_norm} 失败：文件已加密。"
            "请先在 Excel/WPS 中取消“打开密码”后再上传，"
            "或另存为未加密的 .xlsx/.csv 文件。"
        ) from exc

    raise ValueError(message) from exc


def _missing_excel_dependency_error(ext_norm: str, exc: ImportError) -> ValueError:
    if ext_norm == "xlsx":
        return ValueError(
            "解析 .xlsx 失败：缺少 openpyxl 依赖。"
            "请执行 `pip install openpyxl`（或 `pip install -e .[dev]`）后重试。"
        )
    return ValueError(
        "解析 .xls 失败：缺少 xlrd 依赖（>=2.0.1）。"
        '请执行 `pip install "xlrd>=2.0.1"`（或 `pip install -e .[dev]`）后重试。'
    )


def _excel_engine(ext_norm: str) -> str:
    if ext_norm == "xlsx":
        return "openpyxl"
    if ext_norm == "xls":
        return "xlrd"
    raise ValueError(f"不支持的 Excel 扩展名: {ext_norm}")


def _read_excel(path: Path, ext_norm: str, *, sheet_name: Any = 0) -> Any:
    engine = _excel_engine(ext_norm)
    try:
        return pd.read_excel(path, engine=engine, sheet_name=sheet_name)
    except ImportError as exc:
        raise _missing_excel_dependency_error(ext_norm, exc) from exc
    except Exception as exc:
        _raise_excel_parse_error(exc, ext_norm)


def list_excel_sheet_names(path: Path, ext: str) -> list[str]:
    """列出 Excel 文件中的所有 sheet 名称。"""
    ext_norm = str(ext).lower().lstrip(".")
    engine = _excel_engine(ext_norm)
    try:
        with pd.ExcelFile(path, engine=engine) as excel_file:
            return [str(name) for name in excel_file.sheet_names]
    except ImportError as exc:
        raise _missing_excel_dependency_error(ext_norm, exc) from exc
    except Exception as exc:
        _raise_excel_parse_error(exc, ext_norm)


def read_excel_sheet_dataframe(path: Path, ext: str, *, sheet_name: str) -> pd.DataFrame:
    """读取 Excel 指定 sheet。"""
    ext_norm = str(ext).lower().lstrip(".")
    result = _read_excel(path, ext_norm, sheet_name=sheet_name)
    if not isinstance(result, pd.DataFrame):
        raise ValueError("读取指定 sheet 失败：返回结果不是表格数据")
    return result


def read_excel_all_sheets(path: Path, ext: str) -> dict[str, pd.DataFrame]:
    """读取 Excel 全部 sheet，返回 {sheet_name: DataFrame}。"""
    ext_norm = str(ext).lower().lstrip(".")
    result = _read_excel(path, ext_norm, sheet_name=None)
    if not isinstance(result, dict):
        raise ValueError("读取全部 sheet 失败：返回结果格式异常")

    sheets: dict[str, pd.DataFrame] = {}
    for sheet_name, df in result.items():
        if isinstance(df, pd.DataFrame):
            sheets[str(sheet_name)] = df
    return sheets


def read_dataframe(path: Path, ext: str) -> pd.DataFrame:
    """按扩展名读取 DataFrame，返回更友好的错误信息。"""
    ext_norm = str(ext).lower().lstrip(".")

    if ext_norm == "xlsx":
        result = _read_excel(path, ext_norm, sheet_name=0)
        if not isinstance(result, pd.DataFrame):
            raise ValueError("解析 .xlsx 失败：返回结果不是表格数据")
        return result

    if ext_norm == "xls":
        result = _read_excel(path, ext_norm, sheet_name=0)
        if not isinstance(result, pd.DataFrame):
            raise ValueError("解析 .xls 失败：返回结果不是表格数据")
        return result

    if ext_norm == "csv":
        return pd.read_csv(path)

    if ext_norm in ("tsv", "txt"):
        return pd.read_csv(path, sep="\t")

    raise ValueError(f"不支持的扩展名: {ext_norm}")


# ---- DataFrame JSON 序列化工具 ----


def dataframe_to_json_safe(
    df: pd.DataFrame,
    n_rows: int | None = None,
    handle_non_finite: bool = True,
) -> list[dict[str, Any]]:
    """将 DataFrame 转换为 JSON 安全的字典列表。

    处理以下类型转换：
    - numpy.bool_ -> Python bool
    - numpy.integer -> Python int
    - numpy.floating/float -> Python float (非有限值转为 None)
    - NaN/None -> None

    Args:
        df: 输入 DataFrame
        n_rows: 如果指定，只转换前 n 行（用于预览）
        handle_non_finite: 是否将非有限数值（inf, -inf, nan）转为 None

    Returns:
        JSON 安全的字典列表
    """
    if n_rows is not None:
        df = df.head(n_rows)

    records = df.to_dict(orient="records")
    result: list[dict[str, Any]] = []

    for record in records:
        safe_record: dict[str, Any] = {}
        for key, value in record.items():
            safe_record[key] = _convert_value_to_json_safe(value, handle_non_finite)
        result.append(safe_record)

    return result


def _convert_value_to_json_safe(value: Any, handle_non_finite: bool = True) -> Any:
    """将单个值转换为 JSON 安全格式。"""
    if isinstance(value, np.bool_):
        return bool(value)
    elif isinstance(value, np.integer):
        return int(value)
    elif isinstance(value, (np.floating, float)):
        if handle_non_finite and not math.isfinite(value):
            return None
        return float(value)
    elif pd.isna(value):
        return None
    else:
        return value


def series_to_json_safe(series: pd.Series) -> list[Any]:
    """将 Series 转换为 JSON 安全的列表。"""
    return [_convert_value_to_json_safe(v) for v in series]
