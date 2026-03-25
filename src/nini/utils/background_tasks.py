"""异步后台任务生命周期管理。

通过持有强引用防止 asyncio.Task 被 GC 回收（fire-and-forget 模式）。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Coroutine

logger = logging.getLogger(__name__)

# 模块级集合，持有所有后台任务的强引用
_background_tasks: set[asyncio.Task] = set()  # type: ignore[type-arg]


def track_background_task(coro: Coroutine) -> asyncio.Task:  # type: ignore[type-arg]
    """创建并追踪一个后台异步任务。

    任务完成（正常或异常）后自动从集合中移除。
    异常会被记录为 warning 级别日志，不会传播。
    """
    task = asyncio.create_task(coro)
    _background_tasks.add(task)

    def _on_done(t: asyncio.Task) -> None:  # type: ignore[type-arg]
        _background_tasks.discard(t)
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            logger.warning("后台任务异常: %s", exc, exc_info=exc)

    task.add_done_callback(_on_done)
    return task
