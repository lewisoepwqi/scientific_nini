"""更新安装前置检查与 updater 测试。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from nini.config import Settings
from nini.update.apply import (
    ApplyUpdateError,
    UpdaterCommand,
    build_updater_command,
    launch_updater,
    prepare_apply_update,
)
from nini.update.models import UpdateDownloadState
from nini.update.runtime_state import has_running_tasks, running_session_ids
from nini.update.signature import SignatureVerificationError, verify_authenticode_signature


def _ready_state(installer: Path) -> UpdateDownloadState:
    installer.write_bytes(b"installer")
    return UpdateDownloadState(
        status="ready",
        version="0.1.2",
        progress=100,
        installer_path=str(installer),
        verified=True,
        expected_sha256="abc123",
    )


def test_prepare_apply_rejects_source_environment(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path)
    state = _ready_state(tmp_path / "setup.exe")

    with pytest.raises(ApplyUpdateError, match="源码"):
        prepare_apply_update(state, app_settings=settings, packaged=False)


def test_prepare_apply_rejects_not_ready_package(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path)

    with pytest.raises(ApplyUpdateError, match="尚未下载"):
        prepare_apply_update(UpdateDownloadState(), app_settings=settings, packaged=True)


def test_prepare_apply_builds_updater_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nini.update.apply import resolve_updater_path

    install_dir = tmp_path / "app"
    install_dir.mkdir()
    updater = resolve_updater_path(install_dir)
    updater.write_text("", encoding="utf-8")
    installer = tmp_path / "setup.exe"
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        update_signature_check_enabled=False,
        update_apply_wait_timeout_seconds=12,
    )
    state = _ready_state(installer)

    monkeypatch.setattr("nini.update.apply.resolve_install_dir", lambda: install_dir)
    monkeypatch.setattr("nini.update.apply.has_running_tasks", lambda: False)
    monkeypatch.setattr("nini.update.apply.os.getpid", lambda: 111)
    monkeypatch.setattr("nini.update.apply.os.getppid", lambda: 222)
    monkeypatch.setattr("nini.update.apply.collect_owned_pids", lambda: [333, 444])

    command = prepare_apply_update(state, app_settings=settings, packaged=True)

    assert command.args[0] == str(updater)
    assert "--installer" in command.args
    assert str(installer.resolve()) in command.args
    assert "--backend-pid" in command.args
    assert "111" in command.args
    assert "--gui-pid" in command.args
    assert "222" in command.args
    assert "--wait-timeout" in command.args
    assert "12" in command.args
    assert command.args[command.args.index("--child-pids") + 1] == "333,444"


def test_build_updater_command_omits_missing_gui_pid(tmp_path: Path) -> None:
    command = build_updater_command(
        updater_path=tmp_path / "nini-updater.exe",
        installer_path=tmp_path / "setup.exe",
        install_dir=tmp_path / "app",
        app_exe=tmp_path / "app" / "nini.exe",
        backend_pid=1,
        gui_pid=None,
        log_path=tmp_path / "updater.log",
        wait_timeout=60,
    )
    assert "--gui-pid" not in command.args


def test_build_updater_command_includes_child_pids_and_lock_probe(tmp_path: Path) -> None:
    command = build_updater_command(
        updater_path=tmp_path / "nini-updater.exe",
        installer_path=tmp_path / "setup.exe",
        install_dir=tmp_path / "app",
        app_exe=tmp_path / "app" / "nini.exe",
        backend_pid=100,
        gui_pid=200,
        child_pids=[300, 100, 300],
        log_path=tmp_path / "updater.log",
        wait_timeout=60,
        lock_probe_seconds=7,
    )

    assert command.args[command.args.index("--child-pids") + 1] == "300"
    assert command.args[command.args.index("--lock-probe-seconds") + 1] == "7"


def test_launch_updater_uses_windows_detach_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    monkeypatch.setattr("nini.update.apply.sys.platform", "win32")
    monkeypatch.setattr("nini.update.apply.subprocess.CREATE_NEW_PROCESS_GROUP", 1, raising=False)
    monkeypatch.setattr("nini.update.apply.subprocess.DETACHED_PROCESS", 2, raising=False)
    monkeypatch.setattr("nini.update.apply.subprocess.CREATE_BREAKAWAY_FROM_JOB", 4, raising=False)
    monkeypatch.setattr("nini.update.apply.subprocess.CREATE_NO_WINDOW", 8, raising=False)

    def fake_popen(_args, **kwargs):
        calls.append(kwargs["creationflags"])
        if len(calls) < 3:
            raise OSError("job 不允许 breakaway")
        return SimpleNamespace()

    monkeypatch.setattr("nini.update.apply.subprocess.Popen", fake_popen)

    launch_updater(UpdaterCommand(args=["nini-updater.exe"]))

    assert calls == [7, 3, 8]


def test_launch_updater_starts_new_session_on_posix(monkeypatch: pytest.MonkeyPatch) -> None:
    kwargs_seen: dict[str, object] = {}

    monkeypatch.setattr("nini.update.apply.sys.platform", "linux")

    def fake_popen(_args, **kwargs):
        kwargs_seen.update(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr("nini.update.apply.subprocess.Popen", fake_popen)

    launch_updater(UpdaterCommand(args=["nini-updater"]))

    assert kwargs_seen["start_new_session"] is True


def test_signature_check_can_be_disabled_in_dev_environment(tmp_path: Path) -> None:
    """开发环境（源码运行）允许禁用签名校验。"""
    path = tmp_path / "setup.exe"
    path.write_bytes(b"unsigned")

    result = verify_authenticode_signature(path, enabled=False)

    assert result.trusted is True
    assert result.status == "disabled"


def test_signature_check_cannot_be_disabled_in_packaged_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """生产环境（打包构建）强制启用签名校验，忽略 enabled=False。"""
    path = tmp_path / "setup.exe"
    path.write_bytes(b"unsigned")

    # 模拟打包环境
    monkeypatch.setattr("nini.config.IS_FROZEN", True)

    # 即使传入 enabled=False，在打包环境下也会被强制启用
    # 在非 Windows 环境：签名校验会被跳过（status="skipped"）
    # 在 Windows 环境：会尝试执行 PowerShell 签名校验
    import sys

    if sys.platform != "win32":
        # 非 Windows 环境：签名校验会被跳过
        result = verify_authenticode_signature(path, enabled=False)
        assert result.trusted is True
        assert result.status == "skipped"
    else:
        # Windows 环境：会尝试校验签名
        # 由于测试文件未签名，应该抛出签名验证错误
        # 或者如果 PowerShell 执行失败，也会抛出错误
        with pytest.raises(SignatureVerificationError):
            verify_authenticode_signature(path, enabled=False)


def test_signature_check_rejects_missing_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("sys.platform", "win32")

    with pytest.raises(SignatureVerificationError, match="不存在"):
        verify_authenticode_signature(tmp_path / "missing.exe")


@pytest.mark.asyncio
async def test_running_session_ids_detects_runtime_task(monkeypatch: pytest.MonkeyPatch) -> None:
    pending = asyncio.create_task(asyncio.sleep(10))
    fake_manager = SimpleNamespace(_sessions={"s1": SimpleNamespace(runtime_chat_task=pending)})
    monkeypatch.setattr("nini.update.runtime_state.session_manager", fake_manager)
    try:
        assert running_session_ids() == ["s1"]
        assert has_running_tasks() is True
    finally:
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
