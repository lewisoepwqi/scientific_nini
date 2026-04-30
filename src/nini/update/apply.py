"""启动独立 updater 执行半自动升级。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import logging
import os
import subprocess
import sys
import threading

from nini.config import Settings, settings
from nini.update.models import UpdateDownloadState
from nini.update.runtime_state import has_running_tasks
from nini.update.signature import SignatureVerificationError, verify_authenticode_signature

logger = logging.getLogger(__name__)


class ApplyUpdateError(RuntimeError):
    """无法进入安装阶段。"""


@dataclass(frozen=True)
class UpdaterCommand:
    """独立 updater 启动命令。"""

    args: list[str]


def is_packaged_app() -> bool:
    """当前是否为 PyInstaller 打包环境。"""
    return bool(getattr(sys, "frozen", False))


def resolve_install_dir() -> Path:
    """解析当前安装目录。"""
    return Path(sys.executable).resolve().parent


def resolve_updater_path(install_dir: Path) -> Path:
    """解析 updater 可执行文件路径。"""
    return install_dir / ("nini-updater.exe" if sys.platform == "win32" else "nini-updater")


def build_updater_command(
    *,
    updater_path: Path,
    installer_path: Path,
    install_dir: Path,
    app_exe: Path,
    backend_pid: int,
    gui_pid: int | None,
    log_path: Path,
    wait_timeout: int,
    backup_dir: Path | None = None,
    keep_backups: int = 3,
) -> UpdaterCommand:
    """构造 updater 命令行。"""
    args = [
        str(updater_path),
        "--installer",
        str(installer_path),
        "--install-dir",
        str(install_dir),
        "--app-exe",
        str(app_exe),
        "--backend-pid",
        str(backend_pid),
        "--log-path",
        str(log_path),
        "--wait-timeout",
        str(wait_timeout),
    ]
    if gui_pid and gui_pid > 0:
        args.extend(["--gui-pid", str(gui_pid)])
    if backup_dir:
        args.extend(["--backup-dir", str(backup_dir)])
        args.extend(["--keep-backups", str(keep_backups)])
    return UpdaterCommand(args=args)


def prepare_apply_update(
    state: UpdateDownloadState,
    *,
    app_settings: Settings = settings,
    packaged: bool | None = None,
) -> UpdaterCommand:
    """校验安装前置条件并生成 updater 命令。"""
    if packaged is None:
        packaged = is_packaged_app()
    if not packaged:
        raise ApplyUpdateError("源码开发环境不支持应用内安装升级")
    if state.status != "ready" or not state.verified or not state.installer_path:
        raise ApplyUpdateError("更新包尚未下载或校验通过")
    if has_running_tasks():
        raise ApplyUpdateError("当前存在正在运行的 Agent 任务，请等待任务完成后再升级")

    installer_path = Path(state.installer_path).expanduser().resolve()
    verify_authenticode_signature(
        installer_path,
        allowed_thumbprints=app_settings.update_signature_allowed_thumbprints,
        allowed_publishers=app_settings.update_signature_allowed_publishers,
        enabled=app_settings.update_signature_check_enabled,
    )

    install_dir = resolve_install_dir()
    updater_path = resolve_updater_path(install_dir)
    if not updater_path.exists():
        raise ApplyUpdateError(f"未找到升级器: {updater_path}")
    app_exe = install_dir / ("nini.exe" if sys.platform == "win32" else "nini")
    log_path = app_settings.logs_dir / "updater.log"

    # 备份目录：在 updates 目录下创建 backup 子目录
    backup_dir = app_settings.updates_dir / "backup"

    return build_updater_command(
        updater_path=updater_path,
        installer_path=installer_path,
        install_dir=install_dir,
        app_exe=app_exe,
        backend_pid=os.getpid(),
        gui_pid=os.getppid() if os.getppid() > 0 else None,
        log_path=log_path,
        wait_timeout=app_settings.update_apply_wait_timeout_seconds,
        backup_dir=backup_dir,
        keep_backups=3,
    )


def launch_updater(command: UpdaterCommand) -> None:
    """后台启动 updater。"""
    subprocess.Popen(  # noqa: S603
        command.args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def schedule_current_process_exit(delay_seconds: float = 1.0) -> None:
    """延迟退出当前后端进程，让 apply 响应先返回给前端。

    退出流程：
    1. 等待 delay_seconds 秒（让 HTTP 响应返回给前端）
    2. 尝试执行关键清理操作（保存日志等）
    3. 使用 os._exit(0) 强制退出（确保进程终止）
    """

    def _exit_process() -> None:
        logger.info("开始执行更新退出流程")

        # 尝试执行关键清理操作
        try:
            # 刷新日志
            import logging
            for handler in logging.getLogger().handlers:
                try:
                    handler.flush()
                except Exception:
                    pass

            # 执行 atexit 注册的清理函数
            import atexit
            atexit._run_exitfuncs()
        except Exception as exc:
            logger.warning("清理操作失败（忽略）: %s", exc)

        # 强制退出进程
        logger.info("退出进程")
        os._exit(0)

    timer = threading.Timer(delay_seconds, _exit_process)
    timer.daemon = True
    timer.start()
