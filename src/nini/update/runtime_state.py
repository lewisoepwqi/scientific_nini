"""更新安装前的运行状态判定。"""

from __future__ import annotations

import asyncio
from typing import Any

from nini.agent.session import session_manager


def _is_task_running(task: Any) -> bool:
    return isinstance(task, asyncio.Task) and not task.done()


def running_session_ids() -> list[str]:
    """返回当前仍有 Agent 任务运行的会话 ID。"""
    result: list[str] = []
    sessions = getattr(session_manager, "_sessions", {})
    if not isinstance(sessions, dict):
        return result
    for session_id, session in list(sessions.items()):
        if _is_task_running(getattr(session, "runtime_chat_task", None)):
            result.append(str(session_id))
    return result


def has_running_tasks() -> bool:
    """是否存在正在运行的 Agent 任务。"""
    return bool(running_session_ids())
