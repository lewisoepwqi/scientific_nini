"""统计工具公共基础模块。

包含各统计工具共用的工具函数和类型定义。
"""

from __future__ import annotations

import logging
import math
import warnings
from typing import Any

import pandas as pd

from nini.agent.session import Session
from nini.memory.compression import StatisticResult, get_analysis_memory

logger = logging.getLogger(__name__)

# 忽略 scipy 的 RuntimeWarning
warnings.filterwarnings("ignore", category=RuntimeWarning)


def _safe_float(value: object) -> float | None:
    """安全地将值转换为 float，处理 None 和非有限值。"""
    if value is None:
        return None
    fval = float(value)  # type: ignore[arg-type]
    if not math.isfinite(fval):
        return None
    return fval


def _ensure_finite(value: object, label: str) -> float:
    """确保值是有效的有限数值，否则抛出错误。"""
    if value is None:
        raise ValueError(f"{label} 计算结果无效，请检查数据")
    fval = float(value)  # type: ignore[arg-type]
    if not math.isfinite(fval):
        raise ValueError(f"{label} 计算结果无效，请检查数据")
    return fval


def _get_df(session: Session, name: str) -> pd.DataFrame | None:
    """从会话中获取数据集。"""
    return session.datasets.get(name)


def _record_stat_result(
    session: Session,
    dataset_name: str,
    *,
    test_name: str,
    message: str,
    test_statistic: float | None = None,
    p_value: float | None = None,
    degrees_of_freedom: int | None = None,
    effect_size: float | None = None,
    effect_type: str = "",
    significant: bool = False,
) -> None:
    """将统计结果记录到 AnalysisMemory 和 KnowledgeMemory。"""
    # AnalysisMemory
    mem = get_analysis_memory(session.id, dataset_name)
    mem.add_statistic(
        StatisticResult(
            test_name=test_name,
            test_statistic=test_statistic,
            p_value=p_value,
            degrees_of_freedom=degrees_of_freedom,
            effect_size=effect_size,
            effect_type=effect_type,
            significant=significant,
        )
    )
    # KnowledgeMemory
    session.knowledge_memory.append(test_name, message)
