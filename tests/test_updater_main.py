"""独立 updater CLI 测试。"""

from __future__ import annotations

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
        ]
    )

    assert ret == 0
    assert calls[0] == [str(installer.resolve()), "/S", f"/D={app_dir.resolve()}"]
    assert calls[1] == [str(app.resolve())]
