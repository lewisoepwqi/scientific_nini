"""独立 updater CLI 测试。"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from types import SimpleNamespace

import nini.updater_main as updater


def test_updater_wait_timeout_returns_error(monkeypatch, tmp_path: Path) -> None:
    installer = tmp_path / "setup.exe"
    installer.write_bytes(b"installer")
    log_path = tmp_path / "updater.log"
    monkeypatch.setattr(updater, "_process_exists", lambda _pid: True)
    monkeypatch.setattr(updater.time, "sleep", lambda _seconds: None)

    ret = updater.main(
        [
            "--installer",
            str(installer),
            "--install-dir",
            str(tmp_path / "app"),
            "--app-exe",
            str(tmp_path / "app" / "nini.exe"),
            "--backend-pid",
            "123",
            "--log-path",
            str(log_path),
            "--wait-timeout",
            "0",
        ]
    )

    assert ret == 3
    assert "超时" in log_path.read_text(encoding="utf-8")


def test_updater_runs_installer_and_starts_app(monkeypatch, tmp_path: Path) -> None:
    installer = tmp_path / "setup.exe"
    installer.write_bytes(b"installer")
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    app = app_dir / "nini.exe"
    app.write_bytes(b"app")
    log_path = tmp_path / "updater.log"
    calls: list[list[str]] = []

    monkeypatch.setattr(updater, "_process_exists", lambda _pid: False)
    monkeypatch.setattr(updater.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        updater.subprocess,
        "run",
        lambda command, **_kwargs: calls.append(command) or SimpleNamespace(returncode=0),
    )
    monkeypatch.setattr(
        updater.subprocess,
        "Popen",
        lambda command, **_kwargs: calls.append(command) or SimpleNamespace(),
    )

    ret = updater.main(
        [
            "--installer",
            str(installer),
            "--install-dir",
            str(app_dir),
            "--app-exe",
            str(app),
            "--backend-pid",
            "123",
            "--log-path",
            str(log_path),
            "--skip-signature-check",
        ]
    )

    assert ret == 0
    assert calls[0] == [str(installer.resolve()), "/S", f"/D={app_dir.resolve()}"]
    assert calls[1] == [str(app.resolve())]


def test_updater_waits_for_child_pids(monkeypatch, tmp_path: Path) -> None:
    installer = tmp_path / "setup.exe"
    installer.write_bytes(b"installer")
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    log_path = tmp_path / "updater.log"
    waited: list[int] = []

    monkeypatch.setattr(
        updater,
        "_wait_for_processes",
        lambda pids, _timeout, _log_path: waited.extend(pids) or True,
    )
    monkeypatch.setattr(updater, "_probe_install_dir_unlocked", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        updater.subprocess,
        "run",
        lambda _command, **_kwargs: SimpleNamespace(returncode=0),
    )

    ret = updater.main(
        _build_args(
            installer,
            app_dir,
            log_path,
            child_pids="456,789,not-a-pid",
            lock_probe_seconds="0",
        )
    )

    assert ret == 0
    assert waited == [123, 456, 789]


def test_lock_probe_timeout_returns_false(monkeypatch, tmp_path: Path) -> None:
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    log_path = tmp_path / "updater.log"

    monkeypatch.setattr(
        updater.os, "rename", lambda *_args: (_ for _ in ()).throw(PermissionError("locked"))
    )
    monkeypatch.setattr(updater.time, "sleep", lambda _seconds: None)

    ok = updater._probe_install_dir_unlocked(app_dir, timeout=0.001, log_path=log_path)

    assert ok is False
    assert "文件锁探测超时" in log_path.read_text(encoding="utf-8")


def test_backup_install_dir_uses_hardlinks(tmp_path: Path) -> None:
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    source = app_dir / "nini.exe"
    source.write_bytes(b"app")
    log_path = tmp_path / "updater.log"

    backup = updater._backup_install_dir(app_dir, tmp_path / "backup", log_path)

    assert backup is not None
    copied = backup / "nini.exe"
    assert copied.read_bytes() == b"app"
    assert copied.stat().st_ino == source.stat().st_ino


def test_backup_install_dir_falls_back_to_copy(monkeypatch, tmp_path: Path) -> None:
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "nini.exe").write_bytes(b"app")
    log_path = tmp_path / "updater.log"

    monkeypatch.setattr(
        updater.os, "link", lambda *_args: (_ for _ in ()).throw(OSError("no link"))
    )

    backup = updater._backup_install_dir(app_dir, tmp_path / "backup", log_path)

    assert backup is not None
    assert (backup / "nini.exe").read_bytes() == b"app"
    assert "回退完整复制" in log_path.read_text(encoding="utf-8")


def test_backup_failure_aborts_before_installer(monkeypatch, tmp_path: Path) -> None:
    installer = tmp_path / "setup.exe"
    installer.write_bytes(b"installer")
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    log_path = tmp_path / "updater.log"
    runs: list[list[str]] = []

    monkeypatch.setattr(updater, "_process_exists", lambda _pid: False)
    monkeypatch.setattr(updater, "_probe_install_dir_unlocked", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(updater, "_backup_install_dir", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        updater.subprocess,
        "run",
        lambda command, **_kwargs: runs.append(command) or SimpleNamespace(returncode=0),
    )

    ret = updater.main(
        [
            *_build_args(installer, app_dir, log_path, lock_probe_seconds="0"),
            "--backup-dir",
            str(tmp_path / "backup"),
        ]
    )

    assert ret == updater.EXIT_BACKUP_FAILED
    assert runs == []


# ---------- 二次校验（§2） ----------


def _build_args(installer: Path, app_dir: Path, log_path: Path, **extras: str) -> list[str]:
    args = [
        "--installer",
        str(installer),
        "--install-dir",
        str(app_dir),
        "--app-exe",
        str(app_dir / "nini.exe"),
        "--backend-pid",
        "123",
        "--log-path",
        str(log_path),
        "--skip-signature-check",
    ]
    for key, value in extras.items():
        args.extend([f"--{key.replace('_', '-')}", value])
    return args


def test_updater_rejects_sha256_mismatch(monkeypatch, tmp_path: Path) -> None:
    """安装包在主进程校验后被替换（sha256 不一致）时，updater 拒绝执行。"""
    installer = tmp_path / "setup.exe"
    installer.write_bytes(b"replaced-by-attacker")
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    log_path = tmp_path / "updater.log"

    monkeypatch.setattr(updater, "_process_exists", lambda _pid: False)
    monkeypatch.setattr(updater.time, "sleep", lambda _seconds: None)
    fake_run = lambda *_args, **_kwargs: SimpleNamespace(returncode=0)  # noqa: E731
    monkeypatch.setattr(updater.subprocess, "run", fake_run)

    expected_sha = "0" * 64  # 与文件实际内容不一致
    ret = updater.main(_build_args(installer, app_dir, log_path, expected_sha256=expected_sha))

    assert ret == updater.EXIT_VERIFICATION_FAILED
    log = log_path.read_text(encoding="utf-8")
    assert "SHA256 不匹配" in log
    assert "取消安装" in log


def test_updater_rejects_size_mismatch(monkeypatch, tmp_path: Path) -> None:
    """size 不匹配时 updater 拒绝执行（大小校验先于 sha256，节省时间）。"""
    installer = tmp_path / "setup.exe"
    installer.write_bytes(b"installer")
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    log_path = tmp_path / "updater.log"

    monkeypatch.setattr(updater, "_process_exists", lambda _pid: False)
    monkeypatch.setattr(updater.time, "sleep", lambda _seconds: None)

    ret = updater.main(_build_args(installer, app_dir, log_path, expected_size="999999"))

    assert ret == updater.EXIT_VERIFICATION_FAILED
    assert "大小不匹配" in log_path.read_text(encoding="utf-8")


def test_updater_passes_when_sha256_matches(monkeypatch, tmp_path: Path) -> None:
    """sha256 一致时进入 NSIS。"""
    installer = tmp_path / "setup.exe"
    payload = b"installer-bytes"
    installer.write_bytes(payload)
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    app_exe = app_dir / "nini.exe"
    app_exe.write_bytes(b"app")
    log_path = tmp_path / "updater.log"
    calls: list[list[str]] = []

    monkeypatch.setattr(updater, "_process_exists", lambda _pid: False)
    monkeypatch.setattr(updater.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        updater.subprocess,
        "run",
        lambda command, **_kwargs: calls.append(command) or SimpleNamespace(returncode=0),
    )
    monkeypatch.setattr(
        updater.subprocess,
        "Popen",
        lambda command, **_kwargs: calls.append(command) or SimpleNamespace(),
    )

    expected_sha = hashlib.sha256(payload).hexdigest()
    ret = updater.main(
        _build_args(
            installer,
            app_dir,
            log_path,
            expected_sha256=expected_sha,
            expected_size=str(len(payload)),
        )
    )

    assert ret == 0
    log = log_path.read_text(encoding="utf-8")
    assert "SHA256 通过" in log
    # 第一个 subprocess 调用必须是 NSIS
    assert calls[0][0] == str(installer.resolve())


def test_updater_sha256_throughput_smoke(tmp_path: Path) -> None:
    """SHA256 二次校验吞吐量烟测。

    676MB 安装包要求 ≤5s（任务 §2.5）。676MB / 5s ≈ 135MB/s。
    本测试用 ~16MB 数据快速验证：常见硬件下吞吐 > 200MB/s（hashlib SHA256），
    完整 676MB 性能门由 §11.8 Windows 打包烟测覆盖。
    """
    installer = tmp_path / "big.bin"
    payload = b"x" * (16 * 1024 * 1024)
    installer.write_bytes(payload)

    start = time.monotonic()
    digest = updater._sha256_file(installer)
    elapsed = time.monotonic() - start

    assert len(digest) == 64
    # 16MB 在合理 CI 环境下应 < 1s（充足裕量）；本断言主要防止实现回退到逐字节
    assert elapsed < 2.0, f"SHA256 吞吐异常低（16MB 用时 {elapsed:.2f}s）"


def test_updater_records_size_check_before_sha256(tmp_path: Path) -> None:
    """直接调用 _verify_installer_before_install 验证短路顺序与日志。"""
    installer = tmp_path / "setup.exe"
    installer.write_bytes(b"installer")
    log_path = tmp_path / "updater.log"

    msg = updater._verify_installer_before_install(
        installer,
        expected_sha256="a" * 64,
        expected_size=999999,
        allowed_thumbprints="",
        allowed_publishers="",
        signature_check_enabled=False,
        log_path=log_path,
    )

    assert msg is not None
    assert "大小不匹配" in msg
    # 大小先失败，sha256 不应被记录
    assert "SHA256" not in log_path.read_text(encoding="utf-8")
