"""回归测试：MultiIndex 列名不应导致 JSON 序列化崩溃。

根因：dataset_transform.group_aggregate 在 metrics 包含多个聚合函数时
产生 MultiIndex 列（tuple 类型），后续 json.dumps 无法序列化 tuple key 的 dict。
"""
import json

import pandas as pd
import pytest

from nini.agent.components.tool_executor import (
    serialize_tool_result_for_memory,
    summarize_tool_result_dict,
    _summarize_dataset_profile,
)


def _make_multiindex_df() -> pd.DataFrame:
    """构造一个模拟 groupby().agg() 产生的 MultiIndex 列 DataFrame。"""
    df = pd.DataFrame({
        "月份": ["1月", "1月", "2月", "2月"],
        "收缩压": [120, 130, 140, 135],
        "舒张压": [80, 85, 90, 88],
    })
    metrics = {"收缩压": ["mean", "std"], "舒张压": ["mean", "std"]}
    result = df.groupby("月份", dropna=False).agg(metrics).reset_index()
    return result


class TestMultiIndexColumnSerialization:
    """MultiIndex 列名的 DataFrame 不应导致 JSON 序列化崩溃。"""

    def test_data_ops_info_stringifies_multiindex_columns(self):
        """data_ops 提取的列名和 dtypes key 应为字符串。"""
        df = _make_multiindex_df()
        column_names = df.columns.tolist()
        dtypes = {col: str(dtype) for col, dtype in df.dtypes.items()}

        for name in column_names:
            assert isinstance(name, str), f"列名 {name!r} 不是字符串而是 {type(name)}"

        for key in dtypes:
            assert isinstance(key, str), f"dtypes key {key!r} 不是字符串而是 {type(key)}"

    def test_data_ops_info_is_json_serializable(self):
        """data_ops 返回的数据应可直接 JSON 序列化。"""
        df = _make_multiindex_df()
        info = {
            "name": "test",
            "rows": len(df),
            "columns": len(df.columns),
            "column_names": df.columns.tolist(),
            "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        }
        json.dumps(info, ensure_ascii=False)

    def test_summarize_dataset_profile_handles_tuple_keys(self):
        """_summarize_dataset_profile 应正确处理含 tuple key 的 dtypes dict。"""
        data_obj = {
            "dataset_name": "test",
            "basic": {
                "rows": 4,
                "columns": 5,
                "column_names": [("月份", ""), ("收缩压", "mean"), ("收缩压", "std")],
                "dtypes": {
                    ("月份", ""): "object",
                    ("收缩压", "mean"): "float64",
                    ("收缩压", "std"): "float64",
                },
            },
        }
        summary = _summarize_dataset_profile(data_obj)
        json.dumps(summary, ensure_ascii=False)
        if "dtypes" in summary:
            for key in summary["dtypes"]:
                assert isinstance(key, str), f"dtypes key {key!r} 不是字符串"

    def test_serialize_tool_result_handles_multiindex_profile(self):
        """serialize_tool_result_for_memory 应能序列化含 MultiIndex 列信息的工具结果。"""
        tool_result = {
            "success": True,
            "message": "已生成数据集概况",
            "has_dataframe": True,
            "data": {
                "dataset_name": "月度统计",
                "basic": {
                    "rows": 12,
                    "columns": 5,
                    "column_names": [("月份", ""), ("收缩压", "mean"), ("收缩压", "std")],
                    "dtypes": {
                        ("月份", ""): "object",
                        ("收缩压", "mean"): "float64",
                        ("收缩压", "std"): "float64",
                    },
                },
            },
        }
        result_str = serialize_tool_result_for_memory(tool_result, tool_name="dataset_catalog")
        assert isinstance(result_str, str)
        parsed = json.loads(result_str)
        assert parsed["success"] is True
