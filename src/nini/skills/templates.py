"""出版级模板定义。"""

from __future__ import annotations

from typing import Any

from nini.utils.chart_fonts import CJK_FONT_FAMILY

TEMPLATES: dict[str, dict[str, Any]] = {
    "default": {
        "name": "默认模板",
        "font": CJK_FONT_FAMILY,
        "font_size": 12,
        "line_width": 1.5,
        "dpi": 300,
    },
    "nature": {
        "name": "Nature",
        "font": CJK_FONT_FAMILY,
        "font_size": 11,
        "line_width": 1.2,
        "dpi": 300,
    },
    "science": {
        "name": "Science",
        "font": CJK_FONT_FAMILY,
        "font_size": 12,
        "line_width": 1.2,
        "dpi": 300,
    },
    "cell": {
        "name": "Cell",
        "font": CJK_FONT_FAMILY,
        "font_size": 11,
        "line_width": 1.0,
        "dpi": 300,
    },
    "nejm": {
        "name": "NEJM",
        "font": CJK_FONT_FAMILY,
        "font_size": 10,
        "line_width": 1.0,
        "dpi": 300,
    },
    "lancet": {
        "name": "Lancet",
        "font": CJK_FONT_FAMILY,
        "font_size": 10,
        "line_width": 1.0,
        "dpi": 300,
    },
}


def get_template(style: str) -> dict[str, Any]:
    """获取模板配置，不存在时回退 default。"""
    key = style.lower().strip()
    return TEMPLATES.get(key, TEMPLATES["default"])
