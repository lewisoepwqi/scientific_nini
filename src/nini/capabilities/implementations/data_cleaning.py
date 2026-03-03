"""Capability 实现兼容入口。

重量级执行逻辑已迁移到 `nini.capabilities.executors`，此模块保留原导入路径。
"""

from __future__ import annotations

from nini.capabilities.executors.data_cleaning import (
    DataCleaningCapability,
    DataCleaningResult,
)

__all__ = [
    "DataCleaningCapability",
    "DataCleaningResult",
]
