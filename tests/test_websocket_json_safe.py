"""WebSocket 事件 JSON 安全转换测试。"""

from __future__ import annotations

import math

import pandas as pd

from nini.api.websocket import _to_json_safe


def test_to_json_safe_converts_dataframe_nested_payload() -> None:
    """DataFrame 出现在嵌套 payload 中时应转换为可序列化预览。"""
    df = pd.DataFrame({"x": [1, 2], "y": [3.5, 4.5]})
    payload = {
        "result": {
            "table": df,
        }
    }

    converted = _to_json_safe(payload)
    table = converted["result"]["table"]

    assert table["__type__"] == "DataFrame"
    assert table["rows"] == 2
    assert table["columns"] == ["x", "y"]
    assert table["preview_rows"] == 2
    assert len(table["preview"]) == 2
    assert table["preview"][0] == {"x": 1, "y": 3.5}


def test_to_json_safe_normalizes_non_finite_float() -> None:
    """非有限浮点值应转换为 None。"""
    payload = {"value": math.inf, "nested": {"nan": math.nan}}
    converted = _to_json_safe(payload)

    assert converted["value"] is None
    assert converted["nested"]["nan"] is None
