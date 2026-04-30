"""独立升级器入口。"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys
import time


def _process_exists(pid: int) -> bool:
    if pid <= 0 or pid == os.getpid():
        return False
    if sys.platform == "win32":
        import ctypes

        process = ctypes.windll.kernel32.OpenProcess(0x100000, False, pid)
        if not process:
            return False
        ctypes.windll.kernel32.CloseHandle(process)
        return True
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _write_log(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat()
    with path.open("a", encoding="utf-8") as file:
        file.write(f"[{stamp}] {message}\n")


def _wait_for_processes(pids: list[int], timeout: float, log_path: Path) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        alive = [pid for pid in pids if _process_exists(pid)]
        if not alive:
            return True
        _write_log(log_path, f"等待 Nini 进程退出: {alive}")
        time.sleep(1)
    return not any(_process_exists(pid) for pid in pids)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Nini 独立升级器")
    parser.add_argument("--installer", required=True)
    parser.add_argument("--install-dir", required=True)
    parser.add_argument("--app-exe", required=True)
    parser.add_argument("--backend-pid", type=int, required=True)
    parser.add_argument("--gui-pid", type=int, default=0)
    parser.add_argument("--log-path", required=True)
    parser.add_argument("--wait-timeout", type=float, default=60.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    installer = Path(args.installer).expanduser().resolve()
    install_dir = Path(args.install_dir).expanduser().resolve()
    app_exe = Path(args.app_exe).expanduser().resolve()
    log_path = Path(args.log_path).expanduser().resolve()
    pids = [pid for pid in [args.backend_pid, args.gui_pid] if pid > 0 and pid != os.getpid()]

    _write_log(log_path, "updater 启动")
    if not installer.exists():
        _write_log(log_path, f"安装包不存在: {installer}")
        return 2
    if not _wait_for_processes(pids, args.wait_timeout, log_path):
        _write_log(log_path, "等待 Nini 进程退出超时，取消安装")
        return 3

    time.sleep(1.5)
    command = [str(installer), "/S", f"/D={install_dir}"]
    _write_log(log_path, f"开始静默安装: {' '.join(command)}")
    proc = subprocess.run(  # noqa: S603
        command,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    _write_log(log_path, f"安装器退出码: {proc.returncode}")
    if proc.returncode != 0:
        return proc.returncode

    if app_exe.exists():
        subprocess.Popen(  # noqa: S603
            [str(app_exe)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        _write_log(log_path, f"已启动新版本: {app_exe}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
