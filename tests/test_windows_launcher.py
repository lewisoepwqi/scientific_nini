"""Windows GUI 启动器测试。"""

from __future__ import annotations

import socket
from pathlib import Path
from unittest.mock import patch

from nini.windows_launcher import (
    _acquire_single_instance_mutex,
    _build_parser,
    _build_server_command,
    _find_webview2_runtime,
    _is_local_base_url,
    _pick_free_port,
    _resolve_runtime_port,
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


def test_parser_defaults_to_loopback_and_random_port() -> None:
    args = _build_parser().parse_args([])
    assert args.host == "127.0.0.1"
    assert args.port == 0
    assert args.startup_timeout == 30.0
    assert args.log_level == "warning"
    assert args.external_browser is False


def test_parser_accepts_explicit_port() -> None:
    args = _build_parser().parse_args(["--port", "9090"])
    assert args.port == 9090


def test_parser_accepts_external_browser_flag() -> None:
    args = _build_parser().parse_args(["--external-browser"])
    assert args.external_browser is True


def test_resolve_runtime_port_uses_explicit_port_when_given() -> None:
    port = _resolve_runtime_port("127.0.0.1", 8500)
    assert port == 8500


def test_resolve_runtime_port_picks_free_port_when_zero() -> None:
    port = _resolve_runtime_port("127.0.0.1", 0)
    assert 1024 < port < 65536


def test_pick_free_port_returns_usable_port() -> None:
    port = _pick_free_port("127.0.0.1")
    assert 1024 < port < 65536
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", port))


def test_find_webview2_runtime_returns_none_when_no_dirs_exist(tmp_path) -> None:
    """所有 Program Files 环境变量指向空目录时返回 None。"""
    env_overrides = {
        "ProgramFiles(x86)": str(tmp_path),
        "ProgramFiles": str(tmp_path),
        "LOCALAPPDATA": str(tmp_path),
    }
    with patch.dict("os.environ", env_overrides, clear=False):
        result = _find_webview2_runtime()
    assert result is None


def test_find_webview2_runtime_returns_path_when_msedge_exists(tmp_path) -> None:
    """存在 msedgewebview2.exe 时返回其路径。"""
    edge_path = tmp_path / "Microsoft" / "EdgeWebView" / "Application" / "120.0.0.0"
    edge_path.mkdir(parents=True)
    exe = edge_path / "msedgewebview2.exe"
    exe.touch()

    env_overrides = {
        "ProgramFiles(x86)": str(tmp_path),
        "ProgramFiles": "",
        "LOCALAPPDATA": "",
    }
    with patch.dict("os.environ", env_overrides, clear=False):
        result = _find_webview2_runtime()
    assert result == exe


def test_acquire_single_instance_mutex_returns_non_none_first_time() -> None:
    """非 Windows 平台上，函数总返回非 None（视为第一实例）。"""
    import sys
    if sys.platform == "win32":
        handle = _acquire_single_instance_mutex()
        assert handle is not None
    else:
        handle = _acquire_single_instance_mutex()
        assert handle == -1  # 非 Windows 平台哨兵值
