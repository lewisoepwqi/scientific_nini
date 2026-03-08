"""Windows GUI 启动器测试。"""

from __future__ import annotations

from pathlib import Path

from nini.windows_launcher import (
    _build_server_command,
    _is_local_base_url,
)


def test_build_server_command_always_disables_browser_opening() -> None:
    command = _build_server_command(
        Path("C:/Nini/nini-cli.exe"),
        host="127.0.0.1",
        port=8010,
        log_level="warning",
    )

    assert command == [
        "C:/Nini/nini-cli.exe",
        "start",
        "--host",
        "127.0.0.1",
        "--port",
        "8010",
        "--log-level",
        "warning",
        "--no-open",
    ]


def test_is_local_base_url_only_accepts_loopback_addresses() -> None:
    assert _is_local_base_url("http://127.0.0.1:11434") is True
    assert _is_local_base_url("http://localhost:11434") is True
    assert _is_local_base_url("http://192.168.1.8:11434") is False
    assert _is_local_base_url("not-a-url") is False
