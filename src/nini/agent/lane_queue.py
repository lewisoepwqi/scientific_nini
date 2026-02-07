"""Lane Queue：技能串行执行队列。

保证同一会话内的技能调用按顺序执行，避免并发操作同一数据集。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


class LaneQueue:
    """每个会话一个 lane，确保技能串行执行。"""

    def __init__(self):
        self._locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, session_id: str) -> asyncio.Lock:
        if session_id not in self._locks:
            self._locks[session_id] = asyncio.Lock()
        return self._locks[session_id]

    async def execute(
        self,
        session_id: str,
        coro: Coroutine[Any, Any, Any],
    ) -> Any:
        """在指定会话的 lane 中串行执行协程。"""
        lock = self._get_lock(session_id)
        async with lock:
            return await coro

    def remove_lane(self, session_id: str) -> None:
        """清理会话 lane。"""
        self._locks.pop(session_id, None)


# 全局单例
lane_queue = LaneQueue()
