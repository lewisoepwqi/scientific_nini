"""Windows GUI 启动器：静默拉起后台服务，仅打开浏览器。"""

from __future__ import annotations

import argparse
from contextlib import suppress
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import webbrowser
from urllib.parse import urlparse


def _is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    """检测目标端口是否已监听。"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _wait_for_port(host: str, port: int, timeout: float) -> bool:
    """等待目标端口就绪。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _is_port_open(host, port):
            return True
        time.sleep(0.5)
    return False


def _is_local_base_url(base_url: str) -> bool:
    """仅对本机 Ollama 地址启用自动拉起。"""
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"}:
        return False
    return (parsed.hostname or "").lower() in {"127.0.0.1", "localhost"}


def _build_server_command(
    cli_path: Path,
    *,
    host: str,
    port: int,
    log_level: str,
) -> list[str]:
    """构建后台服务启动命令。"""
    return [
        str(cli_path),
        "start",
        "--host",
        host,
        "--port",
        str(port),
        "--log-level",
        log_level,
        "--no-open",
    ]


def _get_windows_creationflags() -> int:
    """返回 Windows 无感后台启动所需 flags。"""
    detached = getattr(subprocess, "DETACHED_PROCESS", 0)
    new_group = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return detached | new_group | no_window


def _spawn_detached(command: list[str], *, env: dict[str, str] | None = None) -> None:
    """以脱离当前 GUI 进程的方式启动后台子进程。"""
    kwargs: dict[str, object] = {
        "args": command,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "env": env,
        "close_fds": True,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = _get_windows_creationflags()
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(**kwargs)  # noqa: S603


def _show_error(message: str, title: str = "Nini") -> None:
    """在 GUI 模式下展示错误信息。"""
    if sys.platform == "win32":
        with suppress(Exception):
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)
            return
    print(message, file=sys.stderr)


def _start_bundled_ollama(install_root: Path, ollama_base_url: str) -> None:
    """若安装包包含便携版 Ollama，则静默拉起。"""
    if not _is_local_base_url(ollama_base_url):
        return

    parsed = urlparse(ollama_base_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 11434
    if _is_port_open(host, port):
        return

    ollama_exe = install_root / "runtime" / "ollama" / "ollama.exe"
    if not ollama_exe.exists():
        return

    env = dict(os.environ)
    env["OLLAMA_HOST"] = f"{host}:{port}"

    bundled_models = install_root / "runtime" / "ollama-models"
    if bundled_models.exists():
        env["OLLAMA_MODELS"] = str(bundled_models)

    _spawn_detached([str(ollama_exe), "serve"], env=env)


def _open_browser(host: str, port: int) -> None:
    """打开前端页面。"""
    webbrowser.open(f"http://{host}:{port}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Nini Windows 启动器")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=8000, help="监听端口")
    parser.add_argument(
        "--startup-timeout",
        type=float,
        default=30.0,
        help="等待后端启动成功的秒数",
    )
    parser.add_argument(
        "--log-level",
        default="warning",
        choices=["critical", "error", "warning", "info", "debug", "trace"],
        help="后台服务日志级别",
    )
    parser.add_argument(
        "--ollama-base-url",
        default="http://127.0.0.1:11434",
        help="便携版 Ollama 自动拉起地址",
    )
    parser.add_argument(
        "--cli-name",
        default="nini-cli.exe" if sys.platform == "win32" else "nini-cli",
        help="后台 CLI 可执行文件名",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    install_root = Path(sys.executable).resolve().parent
    cli_path = install_root / args.cli_name

    if _is_port_open(args.host, args.port):
        _open_browser(args.host, args.port)
        return 0

    if not cli_path.exists():
        _show_error(f"未找到后台启动文件：{cli_path}")
        return 1

    _start_bundled_ollama(install_root, args.ollama_base_url)

    try:
        _spawn_detached(
            _build_server_command(
                cli_path,
                host=args.host,
                port=args.port,
                log_level=args.log_level,
            )
        )
    except OSError as exc:
        _show_error(f"启动后台服务失败：{exc}")
        return 1

    if not _wait_for_port(args.host, args.port, args.startup_timeout):
        _show_error(
            "Nini 后台服务未在预期时间内就绪。\n"
            "可手动运行 nini-cli.exe start 查看日志并排查问题。"
        )
        return 1

    _open_browser(args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
