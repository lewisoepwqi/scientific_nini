"""更新 apply 有序退出与子进程 PID 收集测试。"""

from __future__ import annotations

import pytest

from nini.update import runtime_state


class _FakeProcess:
    def __init__(self, pid: int, alive: bool = True) -> None:
        self.pid = pid
        self.alive = alive
        self.terminated = False

    def is_alive(self) -> bool:
        return self.alive

    def terminate(self) -> None:
        self.terminated = True
        self.alive = False


def test_collect_owned_pids_filters_exited_processes() -> None:
    running = _FakeProcess(123, alive=True)
    exited = _FakeProcess(456, alive=False)

    runtime_state.register_owned_process(running)
    runtime_state.register_owned_process(exited)
    try:
        assert runtime_state.collect_owned_pids() == [123]
    finally:
        runtime_state.unregister_owned_pid(123)
        runtime_state.unregister_owned_pid(456)


@pytest.mark.asyncio
async def test_request_shutdown_waits_for_owned_processes() -> None:
    process = _FakeProcess(789, alive=True)
    runtime_state.register_owned_process(process)
    try:
        runtime_state.request_owned_process_shutdown()
        alive = await runtime_state.wait_owned_processes(0.1)
        assert process.terminated is True
        assert alive == []
    finally:
        runtime_state.unregister_owned_pid(789)
