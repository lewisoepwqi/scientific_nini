"""
数据处理和管理服务。
"""
from typing import Optional, List, Dict, Any, Tuple
import math
import pandas as pd
import numpy as np

from app.core.exceptions import DataProcessingException
from app.services.file_service import file_service
from app.schemas.dataset import ColumnInfo, ColumnStats
from app.utils.dataframe_utils import dataframe_to_json_safe


# 数据处理常量
DEFAULT_PREVIEW_ROWS = 10  # 默认预览行数
SAMPLE_VALUES_COUNT = 5  # 列样本值数量
TOP_VALUES_COUNT = 10  # 分类列显示的前 N 个值
CATEGORICAL_UNIQUE_RATIO = 0.05  # 判定为分类列的唯一值比例阈值
CATEGORICAL_MAX_UNIQUE = 20  # 判定为分类列的最大唯一值数量


class DataService:
    """数据处理和统计服务。"""

    def __init__(self):
        self.preview_rows = DEFAULT_PREVIEW_ROWS

    @staticmethod
    def _safe_float(value: Optional[float]) -> Optional[float]:
        """将非有限数值转换为 None。"""
        if value is None:
            return None
        if not math.isfinite(value):
            return None
        return float(value)

    def load_dataset(self, file_path: str) -> pd.DataFrame:
        """从文件加载数据集。"""
        return file_service.read_dataframe(file_path)

    def get_column_info(self, df: pd.DataFrame) -> List[ColumnInfo]:
        """获取每列的信息。"""
        columns = []
        for col in df.columns:
            dtype = str(df[col].dtype)
            unique_count = df[col].nunique()

            # 获取样本值（非空）
            sample_values = df[col].dropna().head(SAMPLE_VALUES_COUNT).tolist()

            columns.append(ColumnInfo(
                name=str(col),
                dtype=dtype,
                nullable=df[col].isnull().any(),
                unique_count=unique_count,
                sample_values=sample_values
            ))
        return columns

    def get_preview(self, df: pd.DataFrame, n_rows: int = None) -> Dict[str, Any]:
        """获取数据集预览。"""
        n_rows = n_rows or self.preview_rows

        columns = self.get_column_info(df)

        # 转换 DataFrame 为字典以便 JSON 序列化
        preview_df = df.head(n_rows).copy()

        # 统一处理 NaN、Inf 和不可序列化的类型
        data = dataframe_to_json_safe(preview_df)

        return {
            "columns": columns,
            "data": data,
            "total_rows": len(df),
            "preview_rows": min(n_rows, len(df))
        }

    def compute_column_stats(self, df: pd.DataFrame, column: str) -> ColumnStats:
        """计算单列的统计信息。"""
        series = df[column]
        dtype = str(series.dtype)

        stats = ColumnStats(
            column=column,
            dtype=dtype,
            count=len(series),
            null_count=series.isnull().sum(),
            unique_count=series.nunique()
        )

        # 数值统计
        if pd.api.types.is_numeric_dtype(series):
            non_null = series.dropna()
            if len(non_null) > 0:
                stats.mean = self._safe_float(non_null.mean())
                stats.std = self._safe_float(non_null.std())
                stats.min = self._safe_float(non_null.min())
                stats.max = self._safe_float(non_null.max())
                stats.q25 = self._safe_float(non_null.quantile(0.25))
                stats.q50 = self._safe_float(non_null.quantile(0.50))
                stats.q75 = self._safe_float(non_null.quantile(0.75))

        # 分类统计
        elif pd.api.types.is_object_dtype(series) or pd.api.types.is_categorical_dtype(series):
            value_counts = series.value_counts().head(TOP_VALUES_COUNT)
            stats.top_values = [
                {"value": str(k), "count": int(v)}
                for k, v in value_counts.items()
            ]

        return stats

    def compute_all_stats(self, df: pd.DataFrame) -> List[ColumnStats]:
        """计算所有列的统计信息。"""
        return [self.compute_column_stats(df, col) for col in df.columns]

    def filter_data(
        self,
        df: pd.DataFrame,
        filters: Dict[str, Any]
    ) -> pd.DataFrame:
        """根据条件过滤 DataFrame。"""
        result = df.copy()

        for column, condition in filters.items():
            if column not in result.columns:
                continue

            if isinstance(condition, dict):
                # 范围过滤
                if "min" in condition:
                    result = result[result[column] >= condition["min"]]
                if "max" in condition:
                    result = result[result[column] <= condition["max"]]

                # 值过滤
                if "values" in condition:
                    result = result[result[column].isin(condition["values"])]

            elif isinstance(condition, list):
                result = result[result[column].isin(condition)]

        return result

    def transform_data(
        self,
        df: pd.DataFrame,
        transformations: List[Dict[str, Any]]
    ) -> pd.DataFrame:
        """对 DataFrame 应用转换。"""
        result = df.copy()

        for transform in transformations:
            operation = transform.get("operation")
            column = transform.get("column")

            if operation == "log":
                result[f"{column}_log"] = np.log10(result[column].replace(0, np.nan))

            elif operation == "ln":
                result[f"{column}_ln"] = np.log(result[column].replace(0, np.nan))

            elif operation == "sqrt":
                result[f"{column}_sqrt"] = np.sqrt(result[column].clip(lower=0))

            elif operation == "zscore":
                result[f"{column}_zscore"] = (
                    (result[column] - result[column].mean()) / result[column].std()
                )

            elif operation == "normalize":
                min_val = result[column].min()
                max_val = result[column].max()
                if max_val > min_val:
                    result[f"{column}_norm"] = (
                        (result[column] - min_val) / (max_val - min_val)
                    )

            elif operation == "drop_na":
                result = result.dropna(subset=[column])

            elif operation == "fill_na":
                fill_value = transform.get("value", 0)
                result[column] = result[column].fillna(fill_value)

        return result

    def get_data_summary(self, df: pd.DataFrame) -> Dict[str, Any]:
        """获取全面的数据摘要。"""
        return {
            "shape": {"rows": len(df), "columns": len(df.columns)},
            "memory_usage": df.memory_usage(deep=True).sum(),
            "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
            "missing_values": df.isnull().sum().to_dict(),
            "missing_percentage": (
                (df.isnull().sum() / len(df) * 100).round(2).to_dict()
            )
        }

    def detect_column_types(self, df: pd.DataFrame) -> Dict[str, str]:
        """自动检测列类型。"""
        types = {}
        for col in df.columns:
            series = df[col]

            if pd.api.types.is_datetime64_any_dtype(series):
                types[col] = "datetime"
            elif pd.api.types.is_numeric_dtype(series):
                unique_ratio = series.nunique() / len(series.dropna())
                if unique_ratio < CATEGORICAL_UNIQUE_RATIO and series.nunique() < CATEGORICAL_MAX_UNIQUE:
                    types[col] = "categorical_numeric"
                else:
                    types[col] = "continuous"
            elif pd.api.types.is_categorical_dtype(series) or series.nunique() < CATEGORICAL_MAX_UNIQUE:
                types[col] = "categorical"
            else:
                types[col] = "text"

        return types


# 单例实例
data_service = DataService()
