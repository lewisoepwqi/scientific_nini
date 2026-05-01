"""更新安装前的运行状态判定。"""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Any

from nini.agent.session import session_manager

_owned_processes: dict[int, Any] = {}


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


def register_owned_process(process: Any) -> None:
    """登记由 Nini 派生且升级前需要等待退出的子进程。"""
    pid = getattr(process, "pid", None)
    if isinstance(pid, int) and pid > 0:
        _owned_processes[pid] = process


def unregister_owned_pid(pid: int | None) -> None:
    """移除已退出或已回收的子进程 PID。"""
    if isinstance(pid, int):
        _owned_processes.pop(pid, None)


def _process_is_alive(process: Any) -> bool:
    if hasattr(process, "is_alive"):
        with contextlib.suppress(Exception):
            return bool(process.is_alive())
    if hasattr(process, "poll"):
        with contextlib.suppress(Exception):
            return process.poll() is None
    return False


def collect_owned_pids() -> list[int]:
    """收集仍由 Nini 持有的派生子进程 PID。"""
    result: list[int] = []
    for pid, process in list(_owned_processes.items()):
        if _process_is_alive(process):
            result.append(pid)
        else:
            unregister_owned_pid(pid)
    return sorted(result)


def request_owned_process_shutdown() -> None:
    """通知所有登记的子进程退出。"""
    for pid, process in list(_owned_processes.items()):
        if not _process_is_alive(process):
            unregister_owned_pid(pid)
            continue
        terminate = getattr(process, "terminate", None)
        if callable(terminate):
            with contextlib.suppress(Exception):
                terminate()


async def wait_owned_processes(timeout_seconds: float) -> list[int]:
    """等待登记的子进程退出，返回超时后仍存活的 PID。"""
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    while time.monotonic() < deadline:
        alive = collect_owned_pids()
        if not alive:
            return []
        await asyncio.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
    return collect_owned_pids()
