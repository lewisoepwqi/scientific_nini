"""Nini 版本读取工具。"""

from __future__ import annotations

from importlib import metadata

PACKAGE_NAME = "nini"
FALLBACK_VERSION = "0.1.6"


def get_current_version() -> str:
    """返回当前安装的 Nini 版本。"""
    try:
        import nini

        value = getattr(nini, "__version__", "")
    except Exception:
        value = ""
    if isinstance(value, str) and value.strip():
        return value.strip()

    try:
        return metadata.version(PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        pass
    return FALLBACK_VERSION
