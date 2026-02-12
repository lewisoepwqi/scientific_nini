"""图表字体工具：统一中文字体链和兜底逻辑。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from nini.config import settings

CJK_FONT_CANDIDATES = [
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "Microsoft YaHei",
    "PingFang SC",
    "Hiragino Sans GB",
    "WenQuanYi Micro Hei",
    "SimHei",
    "Arial Unicode MS",
    "DejaVu Sans",
]

CJK_FONT_FAMILY = ", ".join(CJK_FONT_CANDIDATES)

_PRIMARY_CJK_CANDIDATES = CJK_FONT_CANDIDATES[:-1]
_FALLBACK_FONT_URL = (
    "https://raw.githubusercontent.com/notofonts/noto-cjk/main/"
    "Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf"
)
_FALLBACK_FONT_PATH = settings.data_dir / "fonts" / "NotoSansCJKsc-Regular.otf"
_download_attempted = False
_downloaded_font_name: str | None = None
logger = logging.getLogger(__name__)


def _split_font_tokens(family: str) -> list[str]:
    return [part.strip() for part in family.split(",") if part.strip()]


def with_cjk_font_fallback(family: str | None) -> str:
    """补齐字体回退链，避免中文字符渲染为方框。"""
    tokens = _split_font_tokens(family or "")
    if not tokens:
        return CJK_FONT_FAMILY

    normalized: set[str] = set()
    merged: list[str] = []
    for token in tokens:
        key = token.strip("'\" ").lower()
        if key and key not in normalized:
            normalized.add(key)
            merged.append(token)

    for candidate in CJK_FONT_CANDIDATES:
        key = candidate.lower()
        if key not in normalized:
            normalized.add(key)
            merged.append(candidate)
    return ", ".join(merged)


def pick_available_matplotlib_font() -> str | None:
    """选择系统中可用的首个中文候选字体。"""
    try:
        from matplotlib import font_manager

        available = {
            entry.name.lower()
            for entry in font_manager.fontManager.ttflist
            if getattr(entry, "name", None)
        }
        for candidate in _PRIMARY_CJK_CANDIDATES:
            if candidate.lower() in available:
                return candidate
        fallback_name = _ensure_downloaded_matplotlib_cjk_font()
        if fallback_name:
            return fallback_name
        if CJK_FONT_CANDIDATES[-1].lower() in available:
            return CJK_FONT_CANDIDATES[-1]
    except Exception:
        return None
    return None


def get_available_cjk_fonts() -> list[str]:
    """返回系统中实际可用的 CJK 候选字体列表（用于 rcParams 配置）。

    仅返回 matplotlib 能找到的字体，避免大量 'Font family not found' 警告。
    如果没有任何真正的 CJK 字体可用，会尝试下载 Noto CJK 作为兜底。
    """
    try:
        from matplotlib import font_manager

        available = {
            entry.name.lower()
            for entry in font_manager.fontManager.ttflist
            if getattr(entry, "name", None)
        }
        # 先检查真正的 CJK 字体（排除 DejaVu Sans 等通用兜底）
        cjk_found: list[str] = []
        for candidate in _PRIMARY_CJK_CANDIDATES:
            if candidate.lower() in available:
                cjk_found.append(candidate)
        # 没有真正的 CJK 字体时，尝试下载 Noto CJK
        if not cjk_found:
            fallback_name = _ensure_downloaded_matplotlib_cjk_font()
            if fallback_name:
                cjk_found.append(fallback_name)
        if not cjk_found:
            logger.warning(
                "未找到任何中文字体，图表中文可能显示为方框。"
                "建议安装中文字体：apt install fonts-noto-cjk 或 yum install google-noto-sans-cjk-sc-fonts"
            )
        # 最后追加通用兜底字体（如 DejaVu Sans）
        generic_fallback = CJK_FONT_CANDIDATES[-1]  # DejaVu Sans
        if generic_fallback.lower() in available and generic_fallback not in cjk_found:
            cjk_found.append(generic_fallback)
        return cjk_found
    except Exception:
        return []


def apply_plotly_cjk_font_fallback(fig: Any) -> None:
    """给 Plotly Figure 应用中文字体回退链。"""
    try:
        layout_font: dict[str, Any] = {}
        if getattr(fig.layout, "font", None) is not None:
            layout_font = fig.layout.font.to_plotly_json()
        family = layout_font.get("family") if isinstance(layout_font, dict) else None
        fig.update_layout(
            font={
                **layout_font,
                "family": with_cjk_font_fallback(family if isinstance(family, str) else ""),
            }
        )
    except Exception:
        return

    try:
        annotations = getattr(fig.layout, "annotations", None)
        if not annotations:
            return
        patched: list[dict[str, Any]] = []
        for ann in annotations:
            ann_dict = ann.to_plotly_json() if hasattr(ann, "to_plotly_json") else dict(ann)
            font_obj = ann_dict.get("font", {})
            if not isinstance(font_obj, dict):
                font_obj = {}
            family = font_obj.get("family")
            ann_dict["font"] = {
                **font_obj,
                "family": with_cjk_font_fallback(family if isinstance(family, str) else ""),
            }
            patched.append(ann_dict)
        fig.update_layout(annotations=patched)
    except Exception:
        return


def _ensure_downloaded_matplotlib_cjk_font() -> str | None:
    """在系统缺少中文字体时，尝试下载并注册 Noto CJK 字体。"""
    global _download_attempted, _downloaded_font_name

    if _downloaded_font_name:
        return _downloaded_font_name
    if _download_attempted:
        return None
    _download_attempted = True

    try:
        from matplotlib import font_manager

        if _FALLBACK_FONT_PATH.exists():
            font_manager.fontManager.addfont(str(_FALLBACK_FONT_PATH))
            _downloaded_font_name = font_manager.FontProperties(
                fname=str(_FALLBACK_FONT_PATH)
            ).get_name()
            return _downloaded_font_name
    except Exception:
        return None

    try:
        _FALLBACK_FONT_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = Path(f"{_FALLBACK_FONT_PATH}.tmp")
        with urlopen(_FALLBACK_FONT_URL, timeout=20) as resp, tmp_path.open("wb") as dst:
            dst.write(resp.read())
        tmp_path.replace(_FALLBACK_FONT_PATH)

        from matplotlib import font_manager

        font_manager.fontManager.addfont(str(_FALLBACK_FONT_PATH))
        _downloaded_font_name = font_manager.FontProperties(
            fname=str(_FALLBACK_FONT_PATH)
        ).get_name()
        return _downloaded_font_name
    except Exception:
        logger.warning("中文字体自动引导失败：将继续使用系统默认字体", exc_info=True)
        return None
