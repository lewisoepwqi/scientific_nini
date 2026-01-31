"""
出版级模板定义。
"""
from typing import Dict, Any

TEMPLATES: Dict[str, Dict[str, Any]] = {
    "default": {
        "name": "默认模板",
        "font": "Arial",
        "font_size": 12,
        "line_width": 1.5,
        "dpi": 300,
    },
    "nature": {
        "name": "Nature",
        "font": "Helvetica",
        "font_size": 11,
        "line_width": 1.2,
        "dpi": 300,
    },
    "science": {
        "name": "Science",
        "font": "Arial",
        "font_size": 12,
        "line_width": 1.2,
        "dpi": 300,
    },
}
