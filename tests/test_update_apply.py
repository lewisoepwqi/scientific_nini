"""更新安装前置检查与 updater 测试。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from nini.config import Settings
from nini.update.apply import (
    ApplyUpdateError,
    build_updater_command,
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


def test_signature_check_can_be_disabled(tmp_path: Path) -> None:
    path = tmp_path / "setup.exe"
    path.write_bytes(b"unsigned")

    result = verify_authenticode_signature(path, enabled=False)

    assert result.trusted is True
    assert result.status == "disabled"


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
