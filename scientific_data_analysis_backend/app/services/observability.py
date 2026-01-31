"""
可观测性辅助工具。
"""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator

logger = logging.getLogger(__name__)


def _compact_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """移除空值字段，避免日志噪音。"""
    return {key: value for key, value in payload.items() if value is not None}


def _log_event(event: str, payload: Dict[str, Any]) -> None:
    """记录事件日志。"""
    logger.info("观测事件", extra=_compact_payload({"event": event, **payload}))


def log_task_event(action: str, task_id: str | None = None, owner_id: str | None = None, **extra: Any) -> None:
    """记录任务相关事件。"""
    _log_event(f"task.{action}", {"task_id": task_id, "owner_id": owner_id, **extra})


def log_suggestion_event(action: str, task_id: str | None = None, suggestion_id: str | None = None, **extra: Any) -> None:
    """记录建议相关事件。"""
    _log_event(f"suggestion.{action}", {"task_id": task_id, "suggestion_id": suggestion_id, **extra})


def log_export_event(action: str, export_id: str | None = None, visualization_id: str | None = None, **extra: Any) -> None:
    """记录导出相关事件。"""
    _log_event(f"export.{action}", {"export_id": export_id, "visualization_id": visualization_id, **extra})


@contextmanager
def observe_duration(event: str, **payload: Any) -> Iterator[None]:
    """统计耗时并记录事件。"""
    start = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        _log_event(event, {"duration_ms": round(duration_ms, 2), **payload})
