"""独立升级器入口。"""

from __future__ import annotations

import argparse
import shutil
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


def _backup_install_dir(install_dir: Path, backup_dir: Path, log_path: Path) -> Path | None:
    """备份安装目录。

    Args:
        install_dir: 安装目录
        backup_dir: 备份目标目录
        log_path: 日志文件路径

    Returns:
        备份目录路径，失败返回 None
    """
    if not install_dir.exists():
        _write_log(log_path, f"安装目录不存在，跳过备份: {install_dir}")
        return None

    timestamp = int(time.time())
    backup_path = backup_dir / f"backup_{timestamp}"

    try:
        _write_log(log_path, f"开始备份: {install_dir} -> {backup_path}")
        shutil.copytree(install_dir, backup_path, dirs_exist_ok=True)
        _write_log(log_path, f"备份完成: {backup_path}")
        return backup_path
    except Exception as exc:
        _write_log(log_path, f"备份失败（忽略）: {exc}")
        return None


def _restore_backup(backup_path: Path, install_dir: Path, log_path: Path) -> bool:
    """从备份恢复安装目录。

    Args:
        backup_path: 备份目录路径
        install_dir: 安装目录
        log_path: 日志文件路径

    Returns:
        是否恢复成功
    """
    if not backup_path.exists():
        _write_log(log_path, f"备份目录不存在，无法恢复: {backup_path}")
        return False

    try:
        _write_log(log_path, f"开始恢复: {backup_path} -> {install_dir}")

        # 删除当前安装目录
        if install_dir.exists():
            shutil.rmtree(install_dir)

        # 从备份恢复
        shutil.copytree(backup_path, install_dir)
        _write_log(log_path, f"恢复完成: {install_dir}")
        return True
    except Exception as exc:
        _write_log(log_path, f"恢复失败: {exc}")
        return False


def _cleanup_old_backups(backup_dir: Path, keep_count: int, log_path: Path) -> None:
    """清理旧备份，保留最近的 N 个。"""
    if not backup_dir.exists():
        return

    try:
        # 获取所有备份目录（按时间排序）
        backups = sorted(
            [d for d in backup_dir.iterdir() if d.is_dir() and d.name.startswith("backup_")],
            key=lambda d: d.name,
            reverse=True,
        )

        # 删除多余的备份
        for backup in backups[keep_count:]:
            try:
                shutil.rmtree(backup)
                _write_log(log_path, f"清理旧备份: {backup}")
            except Exception as exc:
                _write_log(log_path, f"清理备份失败（忽略）: {exc}")
    except Exception as exc:
        _write_log(log_path, f"清理备份列表失败（忽略）: {exc}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Nini 独立升级器")
    parser.add_argument("--installer", required=True)
    parser.add_argument("--install-dir", required=True)
    parser.add_argument("--app-exe", required=True)
    parser.add_argument("--backend-pid", type=int, required=True)
    parser.add_argument("--gui-pid", type=int, default=0)
    parser.add_argument("--log-path", required=True)
    parser.add_argument("--wait-timeout", type=float, default=60.0)
    parser.add_argument("--backup-dir", default="", help="备份目录（留空则不备份）")
    parser.add_argument("--keep-backups", type=int, default=3, help="保留的备份数量")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    installer = Path(args.installer).expanduser().resolve()
    install_dir = Path(args.install_dir).expanduser().resolve()
    app_exe = Path(args.app_exe).expanduser().resolve()
    log_path = Path(args.log_path).expanduser().resolve()
    pids = [pid for pid in [args.backend_pid, args.gui_pid] if pid > 0 and pid != os.getpid()]

    # 解析备份目录
    backup_dir = Path(args.backup_dir).expanduser().resolve() if args.backup_dir else None

    _write_log(log_path, "updater 启动")
    if not installer.exists():
        _write_log(log_path, f"安装包不存在: {installer}")
        return 2
    if not _wait_for_processes(pids, args.wait_timeout, log_path):
        _write_log(log_path, "等待 Nini 进程退出超时，取消安装")
        return 3

    # 备份当前安装目录
    backup_path = None
    if backup_dir:
        backup_path = _backup_install_dir(install_dir, backup_dir, log_path)

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
        _write_log(log_path, "安装失败")

        # 尝试回滚
        if backup_path:
            _write_log(log_path, "尝试回滚到备份版本...")
            if _restore_backup(backup_path, install_dir, log_path):
                _write_log(log_path, "回滚成功")
                # 尝试启动旧版本
                if app_exe.exists():
                    subprocess.Popen(  # noqa: S603
                        [str(app_exe)],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                    _write_log(log_path, f"已启动旧版本: {app_exe}")
            else:
                _write_log(log_path, "回滚失败，安装目录可能已损坏")

        return proc.returncode

    # 安装成功
    _write_log(log_path, "安装成功")

    # 清理旧备份
    if backup_dir:
        _cleanup_old_backups(backup_dir, args.keep_backups, log_path)

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
