"""独立升级器入口。"""

from __future__ import annotations

import argparse
import hashlib
import shutil
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys
import time

# 退出码（区分失败原因，便于运维定位）
EXIT_OK = 0
EXIT_PARSE = 1
EXIT_INSTALLER_MISSING = 2
EXIT_PROCESS_WAIT_TIMEOUT = 3
EXIT_VERIFICATION_FAILED = 4
EXIT_BACKUP_FAILED = 5
EXIT_LOCK_PROBE_FAILED = 6
EXIT_RESTORE_FAILED = 10


def _process_exists(pid: int) -> bool:
    if pid <= 0 or pid == os.getpid():
        return False
    if sys.platform == "win32":
        import ctypes

        process = ctypes.windll.kernel32.OpenProcess(0x100000, False, pid)
        if not process:
            error_code = ctypes.GetLastError()
            if error_code == 5:  # ERROR_ACCESS_DENIED
                logger.warning("OpenProcess 权限不足 pid=%d，视为进程存活", pid)
                return True
            # ERROR_INVALID_PARAMETER(87) 等其他错误码视为进程已退出
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


def _parse_pid_csv(value: str) -> list[int]:
    """解析逗号分隔 PID 列表。"""
    result: list[int] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            pid = int(item)
        except ValueError:
            continue
        if pid > 0 and pid != os.getpid():
            result.append(pid)
    return result


def _probe_install_dir_unlocked(
    install_dir: Path,
    *,
    timeout: float,
    log_path: Path,
) -> bool:
    """通过独占重命名探测安装目录是否仍被文件锁占用。"""
    if timeout <= 0 or not install_dir.exists():
        return True

    probe_path = install_dir.with_name(f"{install_dir.name}.lockprobe-{os.getpid()}")
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    try:
        while time.monotonic() < deadline:
            try:
                os.rename(install_dir, probe_path)
                # rename 成功，立即尝试恢复原位
                try:
                    os.rename(probe_path, install_dir)
                except Exception as restore_exc:
                    _write_log(log_path, f"文件锁探测 rename-back 失败: {restore_exc}")
                    # 二次尝试恢复
                    try:
                        os.rename(probe_path, install_dir)
                    except Exception as retry_exc:
                        _write_log(log_path, f"文件锁探测二次恢复失败: {retry_exc}")
                        return False
                _write_log(log_path, "文件锁探测通过")
                return True
            except Exception as exc:
                last_error = exc
                # 确保 rename 成功后如果 rename-back 没执行，探测文件不会残留
                if probe_path.exists() and not install_dir.exists():
                    try:
                        os.rename(probe_path, install_dir)
                    except Exception as restore_exc:
                        _write_log(log_path, f"文件锁探测恢复失败: {restore_exc}")
                        return False
                _write_log(log_path, f"文件锁探测等待中: {exc}")
                time.sleep(1)
    finally:
        # 确保任何退出路径上探测文件不残留
        if probe_path.exists() and not install_dir.exists():
            try:
                os.rename(probe_path, install_dir)
            except Exception:
                pass

    _write_log(log_path, f"文件锁探测超时，取消安装: {last_error}")
    return False


def _hardlink_copytree(src: Path, dst: Path) -> None:
    """递归使用硬链接克隆目录。"""
    dst.mkdir(parents=True, exist_ok=False)
    for root, dirs, files in os.walk(src):
        root_path = Path(root)
        relative_root = root_path.relative_to(src)
        target_root = dst / relative_root
        for dirname in dirs:
            (target_root / dirname).mkdir(exist_ok=True)
        for filename in files:
            source_file = root_path / filename
            target_file = target_root / filename
            os.link(source_file, target_file)


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
        try:
            _hardlink_copytree(install_dir, backup_path)
            _write_log(log_path, f"硬链接备份完成: {backup_path}")
        except Exception as link_exc:
            _write_log(log_path, f"硬链接备份失败，回退完整复制: {link_exc}")
            if backup_path.exists():
                shutil.rmtree(backup_path)
            shutil.copytree(install_dir, backup_path)
            _write_log(log_path, f"复制备份完成: {backup_path}")
        return backup_path
    except Exception as exc:
        _write_log(log_path, f"备份失败，取消安装: {exc}")
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


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """流式计算文件 SHA256，避免整文件读入内存。"""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_installer_before_install(
    installer: Path,
    *,
    expected_sha256: str,
    expected_size: int,
    allowed_thumbprints: str,
    allowed_publishers: str,
    signature_check_enabled: bool,
    log_path: Path,
) -> str | None:
    """在执行 NSIS 之前对安装包做二次校验。

    返回 None 表示通过，否则返回失败原因（已记录日志）。
    关闭"主进程校验通过 → 文件被替换 → updater 直接执行"的 TOCTOU 时间窗口。
    """
    if not installer.exists() or not installer.is_file():
        msg = f"二次校验：安装包不存在 {installer}"
        _write_log(log_path, msg)
        return msg

    if expected_size > 0:
        actual_size = installer.stat().st_size
        if actual_size != expected_size:
            msg = f"二次校验：大小不匹配，预期={expected_size}，实际={actual_size}"
            _write_log(log_path, msg)
            return msg

    if expected_sha256:
        start = time.monotonic()
        actual_sha = _sha256_file(installer)
        elapsed = time.monotonic() - start
        if actual_sha.lower() != expected_sha256.lower():
            msg = f"二次校验：SHA256 不匹配，预期={expected_sha256}，实际={actual_sha}"
            _write_log(log_path, msg)
            return msg
        _write_log(log_path, f"二次校验：SHA256 通过（耗时 {elapsed:.2f}s）")

    # Authenticode 签名校验（仅 Windows）
    if signature_check_enabled and sys.platform == "win32":
        try:
            from nini.update.signature import (
                SignatureVerificationError,
                verify_authenticode_signature,
            )
        except Exception as exc:
            msg = f"二次校验：无法加载签名校验模块: {exc}"
            _write_log(log_path, msg)
            return msg
        try:
            verify_authenticode_signature(
                installer,
                allowed_thumbprints=allowed_thumbprints,
                allowed_publishers=allowed_publishers,
                enabled=True,
            )
        except SignatureVerificationError as exc:
            msg = f"二次校验：签名失败 {exc}"
            _write_log(log_path, msg)
            return msg
        _write_log(log_path, "二次校验：Authenticode 通过")

    return None


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
    parser.add_argument("--keep-backups", type=int, default=1, help="保留的备份数量")
    parser.add_argument("--child-pids", default="", help="Nini 派生子进程 PID（逗号分隔）")
    parser.add_argument("--lock-probe-seconds", type=float, default=10.0, help="文件锁探测超时")
    # 二次校验参数（关闭 TOCTOU 时间窗口）
    parser.add_argument("--expected-sha256", default="", help="安装包预期 SHA256（小写）")
    parser.add_argument("--expected-size", type=int, default=0, help="安装包预期大小（字节）")
    parser.add_argument("--allowed-thumbprints", default="", help="允许的签名指纹（逗号分隔）")
    parser.add_argument("--allowed-publishers", default="", help="允许的签名发布者（逗号分隔）")
    parser.add_argument(
        "--skip-signature-check",
        action="store_true",
        help="跳过 Authenticode 签名校验（仅测试构建，正式发布禁用）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    installer = Path(args.installer).expanduser().resolve()
    install_dir = Path(args.install_dir).expanduser().resolve()
    app_exe = Path(args.app_exe).expanduser().resolve()
    log_path = Path(args.log_path).expanduser().resolve()
    pids = [
        pid
        for pid in [args.backend_pid, args.gui_pid, *_parse_pid_csv(args.child_pids)]
        if pid > 0 and pid != os.getpid()
    ]

    # 解析备份目录
    backup_dir = Path(args.backup_dir).expanduser().resolve() if args.backup_dir else None

    _write_log(log_path, "updater 启动")
    if not installer.exists():
        _write_log(log_path, f"安装包不存在: {installer}")
        return EXIT_INSTALLER_MISSING
    if not _wait_for_processes(pids, args.wait_timeout, log_path):
        _write_log(log_path, "等待 Nini 进程退出超时，取消安装")
        return EXIT_PROCESS_WAIT_TIMEOUT

    if not _probe_install_dir_unlocked(
        install_dir,
        timeout=float(args.lock_probe_seconds),
        log_path=log_path,
    ):
        return EXIT_LOCK_PROBE_FAILED

    # 二次校验：在 NSIS 执行前重新比对大小/SHA256/签名，
    # 关闭"主进程校验通过 → 文件被替换 → updater 直接执行"的 TOCTOU 时间窗口
    verify_failure = _verify_installer_before_install(
        installer,
        expected_sha256=args.expected_sha256,
        expected_size=args.expected_size,
        allowed_thumbprints=args.allowed_thumbprints,
        allowed_publishers=args.allowed_publishers,
        signature_check_enabled=not args.skip_signature_check,
        log_path=log_path,
    )
    if verify_failure is not None:
        _write_log(log_path, "二次校验未通过，取消安装")
        return EXIT_VERIFICATION_FAILED

    # 备份当前安装目录
    backup_path = None
    if backup_dir:
        backup_path = _backup_install_dir(install_dir, backup_dir, log_path)
        if install_dir.exists() and backup_path is None:
            return EXIT_BACKUP_FAILED

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
                    try:
                        subprocess.Popen(  # noqa: S603
                            [str(app_exe)],
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                        )
                        _write_log(log_path, f"已启动旧版本: {app_exe}")
                    except OSError as start_exc:
                        _write_log(log_path, f"启动旧版本失败: {start_exc}")
            else:
                _write_log(log_path, "回滚失败，安装目录可能已损坏")
                return EXIT_RESTORE_FAILED

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
