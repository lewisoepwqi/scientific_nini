"""启动独立 updater 执行半自动升级。"""

from __future__ import annotations

import atexit
import asyncio
import contextlib
from dataclasses import dataclass
from pathlib import Path
import logging
import os
import subprocess
import sys
import threading
from typing import Any

from nini.config import Settings, settings
from nini.update.models import UpdateDownloadState
from nini.update.runtime_state import (
    collect_owned_pids,
    has_running_tasks,
    request_owned_process_shutdown,
    wait_owned_processes,
)
from nini.update.signature import SignatureVerificationError, verify_authenticode_signature

logger = logging.getLogger(__name__)
_uvicorn_server: Any | None = None


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
    child_pids: list[int] | None = None,
    lock_probe_seconds: int = 10,
    backup_dir: Path | None = None,
    keep_backups: int = 1,
    expected_sha256: str = "",
    expected_size: int = 0,
    allowed_thumbprints: str = "",
    allowed_publishers: str = "",
    signature_check_enabled: bool = True,
) -> UpdaterCommand:
    """构造 updater 命令行。

    `expected_sha256` / `expected_size` / `allowed_thumbprints` / `allowed_publishers`
    用于 updater 在执行 NSIS 之前再次校验安装包，关闭"主进程校验通过 → 文件被替换 → updater
    直接执行"的 TOCTOU 时间窗口。
    """
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
    if child_pids:
        normalized_child_pids = sorted(
            {pid for pid in child_pids if pid > 0 and pid != backend_pid}
        )
        if normalized_child_pids:
            args.extend(["--child-pids", ",".join(str(pid) for pid in normalized_child_pids)])
    args.extend(["--lock-probe-seconds", str(lock_probe_seconds)])
    if backup_dir:
        args.extend(["--backup-dir", str(backup_dir)])
        args.extend(["--keep-backups", str(keep_backups)])
    if expected_sha256:
        args.extend(["--expected-sha256", expected_sha256])
    if expected_size > 0:
        args.extend(["--expected-size", str(expected_size)])
    if allowed_thumbprints:
        args.extend(["--allowed-thumbprints", allowed_thumbprints])
    if allowed_publishers:
        args.extend(["--allowed-publishers", allowed_publishers])
    if not signature_check_enabled:
        args.append("--skip-signature-check")
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
        child_pids=collect_owned_pids(),
        log_path=log_path,
        wait_timeout=app_settings.update_apply_wait_timeout_seconds,
        lock_probe_seconds=app_settings.update_apply_lock_probe_seconds,
        backup_dir=backup_dir,
        keep_backups=1,
        expected_sha256=state.expected_sha256 or "",
        expected_size=state.expected_size or 0,
        allowed_thumbprints=app_settings.update_signature_allowed_thumbprints,
        allowed_publishers=app_settings.update_signature_allowed_publishers,
        signature_check_enabled=app_settings.update_signature_check_enabled,
    )


def launch_updater(command: UpdaterCommand) -> None:
    """后台启动 updater。"""
    popen_kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform != "win32":
        subprocess.Popen(command.args, start_new_session=True, **popen_kwargs)  # noqa: S603
        return

    new_group = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    detached = getattr(subprocess, "DETACHED_PROCESS", 0)
    breakaway = getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)
    no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    candidates = [
        new_group | detached | breakaway,
        detached | new_group,
        no_window,
    ]
    last_error: OSError | None = None
    for flags in candidates:
        try:
            subprocess.Popen(  # noqa: S603
                command.args,
                creationflags=flags,
                **popen_kwargs,
            )
            return
        except OSError as exc:
            last_error = exc
            logger.warning("启动 updater 失败，尝试 fallback: flags=%s error=%s", flags, exc)
    assert last_error is not None
    raise last_error


def set_uvicorn_server(server: Any | None) -> None:
    """登记 uvicorn Server 句柄，更新退出时尽力设置 should_exit。"""
    global _uvicorn_server
    _uvicorn_server = server


def _request_server_exit() -> None:
    if _uvicorn_server is not None and hasattr(_uvicorn_server, "should_exit"):
        with contextlib.suppress(Exception):
            _uvicorn_server.should_exit = True


def _flush_shutdown_hooks() -> None:
    try:
        for handler in logging.getLogger().handlers:
            with contextlib.suppress(Exception):
                handler.flush()
        atexit._run_exitfuncs()
    except Exception as exc:
        logger.warning("清理操作失败（忽略）: %s", exc)


async def _shutdown_current_process(delay_seconds: float, grace_seconds: float) -> None:
    await asyncio.sleep(max(0.0, delay_seconds))
    logger.info("开始执行更新退出流程")
    _request_server_exit()
    request_owned_process_shutdown()
    alive_pids = await wait_owned_processes(grace_seconds)
    if alive_pids:
        logger.warning("子进程在 grace 周期内未退出，交由 updater 等待: %s", alive_pids)

    current_task = asyncio.current_task()
    pending_tasks = [
        task for task in asyncio.all_tasks() if task is not current_task and not task.done()
    ]
    for task in pending_tasks:
        task.cancel()
    if pending_tasks:
        with contextlib.suppress(Exception):
            await asyncio.wait(pending_tasks, timeout=0.5)

    _flush_shutdown_hooks()
    logger.info("退出进程")
    os._exit(0)


def schedule_current_process_exit(
    delay_seconds: float = 1.0,
    grace_seconds: float | None = None,
) -> None:
    """延迟退出当前后端进程，让 apply 响应先返回给前端。"""
    effective_grace = (
        float(settings.update_apply_grace_seconds)
        if grace_seconds is None
        else float(grace_seconds)
    )

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        loop.create_task(_shutdown_current_process(delay_seconds, effective_grace))
        return

    def _exit_process() -> None:
        logger.info("开始执行更新退出流程")
        _request_server_exit()
        request_owned_process_shutdown()
        _flush_shutdown_hooks()
        logger.info("退出进程")
        os._exit(0)

    timer = threading.Timer(delay_seconds, _exit_process)
    timer.daemon = True
    timer.start()
