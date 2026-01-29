"""
DataFrame 操作工具函数。
"""
import re
import math
from datetime import datetime, date
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np


# 预编译的正则表达式
WHITESPACE_PATTERN = re.compile(r'^\s*$')

# 数据类型推断常量
NUMERIC_CONVERSION_THRESHOLD = 0.5  # 数值转换成功率阈值
DISCRETE_UNIQUE_RATIO = 0.05  # 判定为离散数值的唯一值比例阈值
DISCRETE_MAX_UNIQUE = 20  # 判定为离散数值的最大唯一值数量
CATEGORICAL_UNIQUE_RATIO = 0.1  # 判定为分类列的唯一值比例阈值
CATEGORICAL_MAX_UNIQUE = 10  # 判定为分类列的最大唯一值数量
IQR_MULTIPLIER = 1.5  # IQR 异常值检测乘数
ZSCORE_THRESHOLD = 3  # Z-score 异常值阈值


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    清理 DataFrame，处理常见问题。

    - 去除列名空白
    - 将空字符串替换为 NaN
    - 转换数值列
    """
    df = df.copy()

    # 清理列名
    df.columns = df.columns.str.strip()

    # 将空字符串替换为 NaN（使用预编译的正则表达式）
    for col in df.select_dtypes(include=['object']).columns:
        mask = df[col].astype(str).str.match(WHITESPACE_PATTERN)
        df.loc[mask, col] = np.nan

    # 尝试将 object 列转换为数值
    for col in df.select_dtypes(include=['object']).columns:
        # 尝试数值转换
        numeric_col = pd.to_numeric(df[col], errors='coerce')
        # 如果超过阈值的值转换成功，则使用数值类型
        if numeric_col.notna().sum() / len(df) > NUMERIC_CONVERSION_THRESHOLD:
            df[col] = numeric_col

    return df


def detect_outliers(
    df: pd.DataFrame,
    column: str,
    method: str = "iqr"
) -> pd.Series:
    """
    检测列中的异常值。

    参数:
        df: DataFrame
        column: 要检查的列
        method: "iqr" 或 "zscore"

    返回:
        指示异常值的布尔 Series
    """
    data = df[column].dropna()

    if method == "iqr":
        Q1 = data.quantile(0.25)
        Q3 = data.quantile(0.75)
        IQR = Q3 - Q1
        lower_bound = Q1 - IQR_MULTIPLIER * IQR
        upper_bound = Q3 + IQR_MULTIPLIER * IQR
        return (df[column] < lower_bound) | (df[column] > upper_bound)

    elif method == "zscore":
        z_scores = np.abs((df[column] - data.mean()) / data.std())
        return z_scores > ZSCORE_THRESHOLD

    return pd.Series(False, index=df.index)


def safe_json_serialize(obj: Any) -> Any:
    """
    安全地将对象序列化为 JSON。

    处理:
    - NaN、Inf 值
    - NumPy 类型
    - Pandas 类型
    """
    if isinstance(obj, (np.integer, np.floating, float)):
        if isinstance(obj, (np.floating, float)) and not math.isfinite(obj):
            return None
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, pd.Series):
        return obj.to_list()
    elif isinstance(obj, pd.DataFrame):
        return obj.to_dict(orient='records')
    elif isinstance(obj, np.datetime64):
        return pd.Timestamp(obj).isoformat()
    elif isinstance(obj, (pd.Timestamp, datetime, date)):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: safe_json_serialize(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [safe_json_serialize(item) for item in obj]
    elif isinstance(obj, tuple):
        return [safe_json_serialize(item) for item in obj]
    elif pd.isna(obj):
        return None
    return obj


def dataframe_to_json_safe(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """将 DataFrame 转换为 JSON 安全的字典列表。"""
    records = df.to_dict(orient='records')
    return [safe_json_serialize(record) for record in records]


def infer_column_types(df: pd.DataFrame) -> Dict[str, str]:
    """
    推断列的语义类型。

    返回列名到类型的映射字典:
    - "continuous": 连续数值
    - "discrete": 离散数值
    - "categorical": 分类
    - "ordinal": 有序
    - "identifier": ID 列
    - "text": 文本数据
    - "datetime": 日期/时间
    """
    types = {}

    for col in df.columns:
        series = df[col]

        # 检查 ID 模式
        if col.lower() in ['id', 'index', 'key', 'uuid']:
            types[col] = "identifier"
            continue

        # 检查日期时间
        if pd.api.types.is_datetime64_any_dtype(series):
            types[col] = "datetime"
            continue

        # 检查数值
        if pd.api.types.is_numeric_dtype(series):
            non_null_count = len(series.dropna())
            if non_null_count == 0:
                types[col] = "continuous"
                continue

            unique_ratio = series.nunique() / non_null_count

            if unique_ratio < DISCRETE_UNIQUE_RATIO and series.nunique() < DISCRETE_MAX_UNIQUE:
                types[col] = "discrete"
            else:
                types[col] = "continuous"
            continue

        # 检查分类
        unique_count = series.nunique()
        total_count = len(series.dropna())

        if total_count == 0:
            types[col] = "text"
        elif unique_count / total_count < CATEGORICAL_UNIQUE_RATIO or unique_count < CATEGORICAL_MAX_UNIQUE:
            types[col] = "categorical"
        else:
            types[col] = "text"

    return types


def get_data_summary(df: pd.DataFrame) -> Dict[str, Any]:
    """获取全面的数据摘要。"""
    return {
        "shape": {"rows": len(df), "columns": len(df.columns)},
        "memory_usage_mb": df.memory_usage(deep=True).sum() / 1024 / 1024,
        "column_types": infer_column_types(df),
        "missing_values": df.isnull().sum().to_dict(),
        "missing_percentage": (
            (df.isnull().sum() / len(df) * 100).round(2).to_dict()
        ),
        "numeric_columns": df.select_dtypes(include=[np.number]).columns.tolist(),
        "categorical_columns": df.select_dtypes(include=['object', 'category']).columns.tolist(),
        "unique_counts": {col: df[col].nunique() for col in df.columns}
    }
