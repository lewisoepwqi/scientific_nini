"""Capability 实现模块。

包含具体的 Capability 实现。
"""

from __future__ import annotations

from nini.capabilities.implementations.correlation_analysis import (
    CorrelationAnalysisCapability,
    CorrelationAnalysisResult,
)
from nini.capabilities.implementations.difference_analysis import (
    DifferenceAnalysisCapability,
    DifferenceAnalysisResult,
)

__all__ = [
    "CorrelationAnalysisCapability",
    "CorrelationAnalysisResult",
    "DifferenceAnalysisCapability",
    "DifferenceAnalysisResult",
]
