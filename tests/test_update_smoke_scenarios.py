"""§11.8 Windows 打包烟测模拟。

以自动化测试覆盖手动验证的五个场景：
1. 升级成功：完整 updater 流程（二次校验 → 备份 → NSIS → 重启新版）
2. 升级失败回滚：NSIS 失败 → 从备份恢复 → 启动旧版本
3. 续传：断点续传下载，Range header 正确发送
4. 重发布丢字节：manifest sha256 变化 → 丢弃旧 .download → 从头下载
5. 文件锁超时：安装目录被锁 → 探测超时 → 取消安装、保留安装包
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

import nini.updater_main as updater
from nini.update.download import download_asset
from nini.update.models import UpdateAsset, UpdateDownloadState
from nini.update.state import UpdateStateStore


# ---------- 场景 1：升级成功 ----------


def test_smoke_upgrade_success(monkeypatch, tmp_path: Path) -> None:
    """升级成功：二次校验通过 → 硬链接备份 → NSIS 静默安装 → 重启新版本。"""
    # 准备安装包（计算真实 sha256）
    installer_payload = b"nini-0.2.0-setup-payload"
    installer = tmp_path / "Nini-0.2.0-Setup.exe"
    installer.write_bytes(installer_payload)
    expected_sha = hashlib.sha256(installer_payload).hexdigest()

    # 准备安装目录（模拟当前版本）
    install_dir = tmp_path / "install"
    install_dir.mkdir()
    app_exe = install_dir / "nini.exe"
    app_exe.write_bytes(b"nini-0.1.0-binary")

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    log_path = tmp_path / "updater.log"

    # 记录 subprocess 调用
    calls: list[list[str]] = []

    monkeypatch.setattr(updater, "_process_exists", lambda _pid: False)
    monkeypatch.setattr(updater.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        updater.subprocess,
        "run",
        lambda command, **_kw: calls.append(("run", command)) or SimpleNamespace(returncode=0),
    )
    monkeypatch.setattr(
        updater.subprocess,
        "Popen",
        lambda command, **_kw: calls.append(("Popen", command)) or SimpleNamespace(),
    )

    ret = updater.main(
        [
            "--installer",
            str(installer),
            "--install-dir",
            str(install_dir),
            "--app-exe",
            str(app_exe),
            "--backend-pid",
            "123",
            "--log-path",
            str(log_path),
            "--backup-dir",
            str(backup_dir),
            "--expected-sha256",
            expected_sha,
            "--expected-size",
            str(len(installer_payload)),
            "--skip-signature-check",
        ]
    )

    log = log_path.read_text(encoding="utf-8")

    # 退出码成功
    assert ret == 0

    # 二次校验通过
    assert "SHA256 通过" in log

    # 备份完成（硬链接或复制）
    assert "备份完成" in log

    # NSIS 静默安装被执行
    assert calls[0] == ("run", [str(installer.resolve()), "/S", f"/D={install_dir.resolve()}"])

    # 新版本被启动
    assert calls[1] == ("Popen", [str(app_exe.resolve())])
    assert "安装成功" in log
    assert "已启动新版本" in log


# ---------- 场景 2：升级失败回滚 ----------


def test_smoke_upgrade_failure_rollback(monkeypatch, tmp_path: Path) -> None:
    """升级失败回滚：NSIS 返回非零 → 从备份恢复安装目录 → 启动旧版本。"""
    installer_payload = b"nini-0.2.0-setup-broken"
    installer = tmp_path / "Nini-0.2.0-Setup.exe"
    installer.write_bytes(installer_payload)
    expected_sha = hashlib.sha256(installer_payload).hexdigest()

    # 模拟当前安装目录（含可执行文件和配置）
    install_dir = tmp_path / "install"
    install_dir.mkdir()
    old_exe = install_dir / "nini.exe"
    old_exe.write_bytes(b"nini-0.1.0-binary")
    (install_dir / "config.json").write_text('{"version": "0.1.0"}')

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    log_path = tmp_path / "updater.log"

    popen_commands: list[list[str]] = []

    monkeypatch.setattr(updater, "_process_exists", lambda _pid: False)
    monkeypatch.setattr(updater.time, "sleep", lambda _seconds: None)
    # NSIS 安装失败
    monkeypatch.setattr(
        updater.subprocess,
        "run",
        lambda command, **_kw: SimpleNamespace(returncode=1),
    )
    monkeypatch.setattr(
        updater.subprocess,
        "Popen",
        lambda command, **_kw: popen_commands.append(command) or SimpleNamespace(),
    )

    ret = updater.main(
        [
            "--installer",
            str(installer),
            "--install-dir",
            str(install_dir),
            "--app-exe",
            str(old_exe),
            "--backend-pid",
            "123",
            "--log-path",
            str(log_path),
            "--backup-dir",
            str(backup_dir),
            "--expected-sha256",
            expected_sha,
            "--expected-size",
            str(len(installer_payload)),
            "--skip-signature-check",
        ]
    )

    log = log_path.read_text(encoding="utf-8")

    # NSIS 退出码非零
    assert ret != 0
    assert "安装失败" in log

    # 回滚成功
    assert "回滚成功" in log

    # 旧版本被启动
    assert len(popen_commands) == 1
    assert popen_commands[0] == [str(old_exe.resolve())]
    assert "已启动旧版本" in log

    # 安装目录恢复为旧版本内容
    assert install_dir.exists()
    assert (install_dir / "nini.exe").read_bytes() == b"nini-0.1.0-binary"
    assert (install_dir / "config.json").read_text() == '{"version": "0.1.0"}'


# ---------- 场景 3：续传 ----------


@pytest.mark.asyncio
async def test_smoke_resume_download(tmp_path: Path) -> None:
    """断点续传：已有部分下载，发送 Range header，从断点继续下载完成。"""
    full_payload = b"A" * 100 + b"B" * 100  # 200 字节
    asset = UpdateAsset(
        platform="windows-x64",
        kind="nsis-installer",
        url="https://updates.example.com/releases/Nini-0.2.0-Setup.exe",
        size=len(full_payload),
        sha256=hashlib.sha256(full_payload).hexdigest(),
    )

    version_dir = tmp_path / "0.2.0"
    version_dir.mkdir()
    temp_file = version_dir / "Nini-0.2.0-Setup.exe.download"

    # 模拟已下载前 100 字节
    first_half = full_payload[:100]
    temp_file.write_bytes(first_half)

    state_store = UpdateStateStore(tmp_path / "state.json")
    state_store.save(
        UpdateDownloadState(
            status="downloading",
            version="0.2.0",
            progress=50,
            downloaded_bytes=100,
            total_bytes=len(full_payload),
            installer_path=str(version_dir / "Nini-0.2.0-Setup.exe"),
            expected_sha256=asset.sha256,
            expected_size=asset.size,
        )
    )

    captured_range: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_range.append(request.headers.get("Range"))
        # 返回 206 Partial Content，仅发送后半段
        return httpx.Response(
            206,
            content=full_payload[100:],
            headers={"Content-Range": f"bytes 100-199/{len(full_payload)}"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await download_asset(
            asset,
            version="0.2.0",
            updates_dir=tmp_path,
            state_store=state_store,
            timeout=5.0,
            client=client,
        )

    # 发送了 Range header
    assert captured_range[0] == "bytes=100-"

    # 下载完成
    assert result.status == "ready"
    assert result.downloaded_bytes == len(full_payload)
    assert result.verified is True

    # 文件内容完整
    final_file = version_dir / "Nini-0.2.0-Setup.exe"
    assert final_file.read_bytes() == full_payload


# ---------- 场景 4：重发布丢字节 ----------


@pytest.mark.asyncio
async def test_smoke_republish_discards_old_bytes(tmp_path: Path) -> None:
    """重发布丢字节：同版本但 manifest sha256 变化 → 旧 .download 被删除 → 从头下载。"""
    new_payload = b"nini-0.2.0-republished-installer"
    new_sha = hashlib.sha256(new_payload).hexdigest()

    asset = UpdateAsset(
        platform="windows-x64",
        kind="nsis-installer",
        url="https://updates.example.com/releases/Nini-0.2.0-Setup.exe",
        size=len(new_payload),
        sha256=new_sha,
    )

    version_dir = tmp_path / "0.2.0"
    version_dir.mkdir()
    temp_file = version_dir / "Nini-0.2.0-Setup.exe.download"

    # 模拟旧的半下载文件（sha256 与新 manifest 不同）
    old_bytes = b"old-partial-download-data-from-previous-publish"
    temp_file.write_bytes(old_bytes)

    state_store = UpdateStateStore(tmp_path / "state.json")
    state_store.save(
        UpdateDownloadState(
            status="downloading",
            version="0.2.0",
            progress=40,
            downloaded_bytes=len(old_bytes),
            total_bytes=500,
            installer_path=str(version_dir / "Nini-0.2.0-Setup.exe"),
            expected_sha256="c" * 64,  # 旧 manifest sha256，与新 sha256 不同
            expected_size=500,
        )
    )

    requests_log: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_log.append(request)
        return httpx.Response(200, content=new_payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await download_asset(
            asset,
            version="0.2.0",
            updates_dir=tmp_path,
            state_store=state_store,
            timeout=5.0,
            client=client,
        )

    # 旧 .download 被删除
    assert not temp_file.exists()

    # 没有发送 Range header（从头下载）
    assert requests_log[0].headers.get("Range") is None

    # 下载完成且校验通过
    assert result.status == "ready"
    assert result.downloaded_bytes == len(new_payload)
    assert result.verified is True

    # 最终文件内容是新 manifest 对应的安装包
    final_file = version_dir / "Nini-0.2.0-Setup.exe"
    assert final_file.read_bytes() == new_payload


# ---------- 场景 5：文件锁超时 ----------


def test_smoke_file_lock_timeout(monkeypatch, tmp_path: Path) -> None:
    """文件锁超时：安装目录被占用 → 探测超时 → 取消安装 → 保留安装包。"""
    installer_payload = b"nini-0.2.0-setup"
    installer = tmp_path / "Nini-0.2.0-Setup.exe"
    installer.write_bytes(installer_payload)
    expected_sha = hashlib.sha256(installer_payload).hexdigest()

    install_dir = tmp_path / "install"
    install_dir.mkdir()
    app_exe = install_dir / "nini.exe"
    app_exe.write_bytes(b"nini-0.1.0-binary")

    log_path = tmp_path / "updater.log"

    # 模拟所有进程已退出
    monkeypatch.setattr(updater, "_process_exists", lambda _pid: False)
    monkeypatch.setattr(updater.time, "sleep", lambda _seconds: None)

    # 模拟文件锁：os.rename 总是失败
    monkeypatch.setattr(
        updater.os,
        "rename",
        lambda *_args: (_ for _ in ()).throw(PermissionError("文件被其他进程占用")),
    )

    # NSIS 不应被调用
    runs: list[list[str]] = []
    monkeypatch.setattr(
        updater.subprocess,
        "run",
        lambda command, **_kw: runs.append(command) or SimpleNamespace(returncode=0),
    )

    ret = updater.main(
        [
            "--installer",
            str(installer),
            "--install-dir",
            str(install_dir),
            "--app-exe",
            str(app_exe),
            "--backend-pid",
            "123",
            "--log-path",
            str(log_path),
            "--expected-sha256",
            expected_sha,
            "--expected-size",
            str(len(installer_payload)),
            "--lock-probe-seconds",
            "0.001",
            "--skip-signature-check",
        ]
    )

    log = log_path.read_text(encoding="utf-8")

    # 特定退出码：文件锁探测失败
    assert ret == updater.EXIT_LOCK_PROBE_FAILED

    # 日志包含探测超时信息
    assert "文件锁探测超时" in log
    assert "取消安装" in log

    # NSIS 未被执行
    assert runs == []

    # 安装包仍保留（可供重试）
    assert installer.exists()
    assert installer.read_bytes() == installer_payload
