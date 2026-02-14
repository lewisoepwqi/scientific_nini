"""图表载荷规范化工具。"""

from __future__ import annotations

from typing import Any


def normalize_chart_payload(payload: Any) -> dict[str, Any] | None:
    """将图表载荷规范化为 Plotly 顶层结构。

    兼容两类输入：
    - 新格式：{"data": [...], "layout": {...}, ...}
    - 旧格式：{"figure": {"data": [...], "layout": {...}}, ...}
    """
    if not isinstance(payload, dict):
        return None

    raw = payload
    figure = raw.get("figure")
    if isinstance(figure, dict):
        merged = dict(figure)
        # 保留外层元信息，避免丢失图表类型等字段。
        for key in ("chart_type", "schema_version", "config"):
            if key in raw and key not in merged:
                merged[key] = raw.get(key)
        raw = merged

    data = raw.get("data")
    if isinstance(data, tuple):
        data = list(data)

    if not isinstance(data, list):
        return None

    normalized = dict(raw)
    normalized["data"] = data

    layout = normalized.get("layout")
    if layout is None:
        normalized["layout"] = {}
    elif not isinstance(layout, dict):
        normalized["layout"] = {}

    config = normalized.get("config")
    if config is not None and not isinstance(config, dict):
        normalized.pop("config", None)

    normalized.setdefault("schema_version", "1.0")
    return normalized
