"""更新版本比较工具。"""

from __future__ import annotations

from packaging.version import InvalidVersion, Version


def parse_version(value: str) -> Version:
    """解析 PEP 440 版本号。"""
    raw = value.strip()
    if not raw:
        raise InvalidVersion("版本号不能为空")
    return Version(raw)


def is_newer_version(candidate: str, current: str) -> bool:
    """判断候选版本是否高于当前版本。"""
    return parse_version(candidate) > parse_version(current)
