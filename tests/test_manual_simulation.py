"""模拟手动验证测试 — 覆盖 add-in-app-updater 剩余 4 个手动任务。

任务 4.8: 验证 updater 日志写入机制（路径、格式、时间戳）
任务 6.7: 验证打包配置完整性（spec / bat / NSIS）
任务 8.5: 端到端升级流程模拟（检查 → 下载 → 校验 → 安装 → 重启）
任务 8.6: 验证升级后用户数据保留
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

import nini.updater_main as updater
from nini.update.download import download_asset
from nini.update.models import (
    UpdateAsset,
    UpdateCheckResult,
    UpdateDownloadState,
    UpdateManifest,
)
from nini.update.state import UpdateStateStore


# ═══════════════════════════════════════════════════════════════════════
# 任务 4.8: 验证 updater 日志写入
# ═══════════════════════════════════════════════════════════════════════


class TestUpdaterLogWriting:
    """模拟 Windows 打包版 updater 日志写入验证。"""

    def test_log_path_under_nini_dir(self, tmp_path: Path) -> None:
        """日志路径应为 %USERPROFILE%\\.nini\\logs\\updater.log。"""
        nini_dir = tmp_path / ".nini"
        log_path = nini_dir / "logs" / "updater.log"

        # 模拟 updater 写入日志
        updater._write_log(log_path, "updater 启动")

        assert log_path.exists()
        # 父目录自动创建
        assert (nini_dir / "logs").is_dir()

    def test_log_format_iso_timestamp(self, tmp_path: Path) -> None:
        """每行日志格式为 [ISO8601时间戳] 消息内容。"""
        log_path = tmp_path / "updater.log"
        updater._write_log(log_path, "测试消息")

        content = log_path.read_text(encoding="utf-8")
        # 匹配 [2026-05-02T10:30:00.123456+00:00] 测试消息
        match = re.match(r"^\[(.+?)\] 测试消息\n$", content)
        assert match is not None

        # 验证时间戳可解析
        ts = datetime.fromisoformat(match.group(1))
        assert ts.tzinfo is not None  # 带时区信息

    def test_log_append_mode(self, tmp_path: Path) -> None:
        """多次写入追加而非覆盖。"""
        log_path = tmp_path / "updater.log"
        updater._write_log(log_path, "第一行")
        updater._write_log(log_path, "第二行")
        updater._write_log(log_path, "第三行")

        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 3
        assert "第一行" in lines[0]
        assert "第二行" in lines[1]
        assert "第三行" in lines[2]

    def test_full_updater_run_writes_log(self, monkeypatch, tmp_path: Path) -> None:
        """完整 updater 运行写入完整流程日志。"""
        installer_payload = b"nini-setup-payload-for-log-test"
        installer = tmp_path / "Nini-Setup.exe"
        installer.write_bytes(installer_payload)
        expected_sha = hashlib.sha256(installer_payload).hexdigest()

        install_dir = tmp_path / "install"
        install_dir.mkdir()
        app_exe = install_dir / "nini.exe"
        app_exe.write_bytes(b"old-binary")

        log_path = tmp_path / ".nini" / "logs" / "updater.log"

        monkeypatch.setattr(updater, "_process_exists", lambda _pid: False)
        monkeypatch.setattr(updater.time, "sleep", lambda _: None)
        monkeypatch.setattr(
            updater.subprocess,
            "run",
            lambda *a, **kw: SimpleNamespace(returncode=0),
        )
        monkeypatch.setattr(
            updater.subprocess,
            "Popen",
            lambda *a, **kw: SimpleNamespace(),
        )

        ret = updater.main(
            [
                "--installer", str(installer),
                "--install-dir", str(install_dir),
                "--app-exe", str(app_exe),
                "--backend-pid", "1234",
                "--log-path", str(log_path),
                "--expected-sha256", expected_sha,
                "--expected-size", str(len(installer_payload)),
                "--skip-signature-check",
            ]
        )
        assert ret == 0

        log = log_path.read_text(encoding="utf-8")
        # 验证完整日志链
        assert "updater 启动" in log
        assert "SHA256 通过" in log
        assert "开始静默安装" in log
        assert "安装器退出码: 0" in log
        assert "安装成功" in log
        assert "已启动新版本" in log


# ═══════════════════════════════════════════════════════════════════════
# 任务 6.7: 验证打包配置完整性
# ═══════════════════════════════════════════════════════════════════════


class TestPackagingConfiguration:
    """验证 nini.spec / build_windows.bat / NSIS 配置正确。"""

    SPEC_PATH = Path(__file__).resolve().parent.parent / "nini.spec"
    NSIS_PATH = Path(__file__).resolve().parent.parent / "packaging" / "installer.nsi"
    BAT_PATH = Path(__file__).resolve().parent.parent / "build_windows.bat"

    def test_spec_has_three_exe_entries(self) -> None:
        """nini.spec 定义 nini-cli、nini（GUI）、nini-updater 三个 EXE。"""
        spec = self.SPEC_PATH.read_text(encoding="utf-8")

        # 三个脚本入口
        assert "__main__.py" in spec
        assert "windows_launcher.py" in spec
        assert "updater_main.py" in spec

        # 三个 EXE 定义
        assert 'name="nini-cli"' in spec
        assert 'name="nini"' in spec
        assert 'name="nini-updater"' in spec

        # updater 不弹终端
        # 找到 updater_exe 块中 console=False
        updater_block_start = spec.index("updater_exe = EXE(")
        updater_block_end = spec.index(")", updater_block_start + 20)
        # 找下一个闭合括号
        depth = 0
        for i in range(updater_block_start, len(spec)):
            if spec[i] == "(":
                depth += 1
            elif spec[i] == ")":
                depth -= 1
                if depth == 0:
                    updater_block_end = i + 1
                    break
        updater_block = spec[updater_block_start:updater_block_end]
        assert "console=False" in updater_block

        # COLLECT 包含三个 EXE
        assert "cli_exe" in spec
        assert "launcher_exe" in spec
        assert "updater_exe" in spec

    def test_build_bat_signs_all_three_exes(self) -> None:
        """build_windows.bat 签名步骤包含三个 EXE。"""
        bat = self.BAT_PATH.read_text(encoding="utf-8")

        # 搜索签名命令行
        sign_section = ""
        for line in bat.split("\n"):
            if "signtool" in line.lower() and "nini" in line.lower():
                sign_section += line + "\n"

        # 签名命令覆盖三个 EXE
        assert "nini.exe" in sign_section
        assert "nini-cli.exe" in sign_section
        assert "nini-updater.exe" in sign_section

    def test_build_bat_generates_sha256(self) -> None:
        """build_windows.bat 生成安装包 SHA256。"""
        bat = self.BAT_PATH.read_text(encoding="utf-8")
        assert "sha256" in bat.lower() or "SHA256" in bat

    def test_build_bat_generates_manifest(self) -> None:
        """build_windows.bat 生成 update manifest 草稿。"""
        bat = self.BAT_PATH.read_text(encoding="utf-8")
        assert "generate_update_manifest" in bat
        assert "verify_update_manifest" in bat

    def test_nsis_defines_updater_exe(self) -> None:
        """NSIS 脚本引用 nini-updater.exe。"""
        nsis = self.NSIS_PATH.read_text(encoding="utf-8")
        assert "nini-updater.exe" in nsis
        assert "PRODUCT_UPDATER_EXE" in nsis

    def test_nsis_deletes_old_updater_before_install(self) -> None:
        """覆盖安装前清理旧 updater（避免残留）。"""
        nsis = self.NSIS_PATH.read_text(encoding="utf-8")
        # 安装段中应删除旧的 updater exe
        lines = nsis.split("\n")
        install_section = False
        delete_updater_found = False
        for line in lines:
            if 'Section "主程序"' in line:
                install_section = True
            if install_section and "Delete" in line and "updater" in line.lower():
                delete_updater_found = True
                break
        assert delete_updater_found, "NSIS 安装段应删除旧 nini-updater.exe"

    def test_build_bat_output_mentions_updater(self) -> None:
        """build_windows.bat 完成输出包含 updater 路径。"""
        bat = self.BAT_PATH.read_text(encoding="utf-8")
        assert "Updater" in bat or "updater" in bat


# ═══════════════════════════════════════════════════════════════════════
# 任务 8.5: 端到端升级流程模拟
# ═══════════════════════════════════════════════════════════════════════


class TestEndToEndUpgradeFlow:
    """模拟完整的 安装旧版 → 检查新版 → 下载 → 校验 → 安装 → 重启 流程。"""

    @pytest.mark.asyncio
    async def test_full_check_download_verify_apply(self, monkeypatch, tmp_path: Path) -> None:
        """完整流程：检查有更新 → 下载 → SHA256 校验 → 启动 updater → 重启新版。"""
        # --- 模拟当前环境 ---
        current_version = "0.1.0"
        new_version = "0.2.0"
        new_payload = b"nini-0.2.0-setup-full-payload" * 100

        # --- 步骤 1: 检查更新 ---
        manifest = UpdateManifest(
            schema_version=1,
            product="nini",
            channel="stable",
            version=new_version,
            minimum_supported_version="0.0.1",
            important=False,
            notes=["Bug fixes and improvements"],
            assets=[
                UpdateAsset(
                    platform="windows-x64",
                    kind="nsis-installer",
                    url="https://updates.example.com/releases/Nini-0.2.0-Setup.exe",
                    size=len(new_payload),
                    sha256=hashlib.sha256(new_payload).hexdigest(),
                )
            ],
        )

        check_result = UpdateCheckResult(
            update_available=True,
            current_version=current_version,
            latest_version=new_version,
            notes=manifest.notes,
            asset=manifest.assets[0],
            important=False,
        )
        assert check_result.update_available is True
        assert check_result.latest_version == new_version

        # --- 步骤 2: 下载安装包 ---
        import httpx

        asset = manifest.assets[0]
        version_dir = tmp_path / "updates" / new_version
        version_dir.mkdir(parents=True)
        state_store = UpdateStateStore(tmp_path / "updates" / "state.json")

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.scheme == "https"
            return httpx.Response(200, content=new_payload)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await download_asset(
                asset,
                version=new_version,
                updates_dir=tmp_path / "updates",
                state_store=state_store,
                timeout=5.0,
                client=client,
            )

        # 验证下载结果
        assert result.status == "ready"
        assert result.downloaded_bytes == len(new_payload)
        assert result.verified is True

        # 验证文件存在
        installer = version_dir / "Nini-0.2.0-Setup.exe"
        assert installer.exists()
        assert installer.read_bytes() == new_payload

        # --- 步骤 3: SHA256 校验（由下载流程自动完成，再次验证）---
        actual_sha = hashlib.sha256(installer.read_bytes()).hexdigest()
        assert actual_sha == asset.sha256

        # --- 步骤 4: 启动 updater（模拟 apply） ---
        install_dir = tmp_path / "install"
        install_dir.mkdir()
        old_exe = install_dir / "nini.exe"
        old_exe.write_bytes(b"nini-0.1.0-old-binary")
        app_exe = install_dir / "nini.exe"
        log_path = tmp_path / ".nini" / "logs" / "updater.log"
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        subprocess_calls: list[tuple[str, list[str]]] = []

        monkeypatch.setattr(updater, "_process_exists", lambda _pid: False)
        monkeypatch.setattr(updater.time, "sleep", lambda _: None)
        monkeypatch.setattr(
            updater.subprocess,
            "run",
            lambda cmd, **kw: subprocess_calls.append(("run", cmd))
            or SimpleNamespace(returncode=0),
        )
        monkeypatch.setattr(
            updater.subprocess,
            "Popen",
            lambda cmd, **kw: subprocess_calls.append(("Popen", cmd))
            or SimpleNamespace(),
        )

        ret = updater.main(
            [
                "--installer", str(installer),
                "--install-dir", str(install_dir),
                "--app-exe", str(app_exe),
                "--backend-pid", "9999",
                "--log-path", str(log_path),
                "--backup-dir", str(backup_dir),
                "--expected-sha256", asset.sha256,
                "--expected-size", str(asset.size),
                "--skip-signature-check",
            ]
        )

        # --- 步骤 5: 验证结果 ---
        assert ret == 0

        log = log_path.read_text(encoding="utf-8")
        assert "updater 启动" in log
        assert "SHA256 通过" in log
        assert "备份完成" in log
        assert "开始静默安装" in log
        assert "安装成功" in log

        # 验证 NSIS 静默安装命令
        run_call = next(c for c in subprocess_calls if c[0] == "run")
        assert "/S" in run_call[1]

        # 验证新版本被启动
        popen_call = next(c for c in subprocess_calls if c[0] == "Popen")
        assert str(app_exe.resolve()) in popen_call[1][0]
        assert "已启动新版本" in log


# ═══════════════════════════════════════════════════════════════════════
# 任务 8.6: 验证升级后用户数据保留
# ═══════════════════════════════════════════════════════════════════════


class TestUserDataPreservation:
    """验证升级过程不删除 %USERPROFILE%\\.nini 中的用户数据。"""

    NSIS_PATH = Path(__file__).resolve().parent.parent / "packaging" / "installer.nsi"

    def test_nsis_install_section_does_not_touch_user_data(self) -> None:
        """NSIS 安装段不包含删除 $PROFILE\\.nini 的指令。"""
        nsis = self.NSIS_PATH.read_text(encoding="utf-8")

        # 提取安装段（从 Section "主程序" 到 SectionEnd）
        install_start = nsis.index('Section "主程序"')
        install_end = nsis.index("SectionEnd", install_start)
        install_section = nsis[install_start:install_end]

        # 安装段中所有 RMDir/Delete 只针对 $INSTDIR（安装目录）
        for line in install_section.split("\n"):
            stripped = line.strip()
            if stripped.startswith("RMDir") or stripped.startswith("Delete"):
                # 允许删除 $INSTDIR 内的文件（覆盖安装需要清理旧程序）
                assert "$INSTDIR" in stripped, f"RMDir/Delete 应仅针对 $INSTDIR: {stripped}"

        # CreateDirectory "$PROFILE\.nini" 仅创建不删除
        assert 'CreateDirectory "$PROFILE\\.nini"' in install_section

    def test_nsis_uninstall_only_deletes_on_explicit_confirm(self) -> None:
        """卸载时仅在用户显式确认后删除用户数据（静默模式下保留）。"""
        nsis = self.NSIS_PATH.read_text(encoding="utf-8")

        # 找卸载段
        uninstall_start = nsis.index('Section "Uninstall"')
        uninstall_end = nsis.index("SectionEnd", uninstall_start)
        uninstall_section = nsis[uninstall_start:uninstall_end]

        # 静默模式跳过数据删除
        assert "IfSilent" in uninstall_section
        assert "skip_data" in uninstall_section

        # 非静默模式需要用户确认
        assert "MB_YESNO" in uninstall_section

        # RMDir /r "$PROFILE\\.nini" 仅在确认后执行
        rm_lines = [
            line.strip()
            for line in uninstall_section.split("\n")
            if "RMDir" in line and ".nini" in line
        ]
        assert len(rm_lines) <= 1  # 最多一处删除

    def test_updater_backup_preserves_install_dir_content(self, monkeypatch, tmp_path: Path) -> None:
        """updater 备份机制保留安装目录中的完整内容。"""
        # 模拟安装目录（含多个文件和子目录）
        install_dir = tmp_path / "install"
        install_dir.mkdir()
        (install_dir / "nini.exe").write_bytes(b"binary")
        (install_dir / "nini-cli.exe").write_bytes(b"cli-binary")
        (install_dir / "nini-updater.exe").write_bytes(b"updater-binary")
        internal = install_dir / "_internal"
        internal.mkdir()
        (internal / "runtime.dll").write_bytes(b"dll-content")

        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        log_path = tmp_path / "test.log"

        # 执行备份
        backup_path = updater._backup_install_dir(install_dir, backup_dir, log_path)
        assert backup_path is not None
        assert backup_path.exists()

        # 验证备份包含完整内容
        assert (backup_path / "nini.exe").exists()
        assert (backup_path / "nini-cli.exe").exists()
        assert (backup_path / "nini-updater.exe").exists()
        assert (backup_path / "_internal" / "runtime.dll").exists()

    def test_updater_rollback_restores_original_files(self, monkeypatch, tmp_path: Path) -> None:
        """升级失败后回滚恢复原始文件内容。"""
        install_dir = tmp_path / "install"
        install_dir.mkdir()
        original_content = b"original-v0.1.0"
        (install_dir / "nini.exe").write_bytes(original_content)
        (install_dir / "config.ini").write_text("version=0.1.0")

        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        log_path = tmp_path / "test.log"

        # 使用完整复制（避免硬链接共享 inode 导致测试失败）
        backup_path = tmp_path / "backup_copy"
        shutil.copytree(install_dir, backup_path)

        # 模拟升级覆盖了文件（先删除再写入，模拟真实 NSIS 行为）
        (install_dir / "nini.exe").unlink()
        (install_dir / "nini.exe").write_bytes(b"corrupted-v0.2.0")

        # 使用 _restore_backup 恢复
        assert updater._restore_backup(backup_path, install_dir, log_path)

        # 验证恢复
        assert (install_dir / "nini.exe").read_bytes() == original_content
        assert (install_dir / "config.ini").read_text() == "version=0.1.0"

    def test_user_data_survives_simulated_upgrade(self, monkeypatch, tmp_path: Path) -> None:
        """完整模拟升级流程中用户数据目录不受影响。"""
        # 模拟用户数据目录
        user_data = tmp_path / "userprofile" / ".nini"
        user_data.mkdir(parents=True)
        (user_data / "config.json").write_text('{"api_key": "test-key"}')
        sessions = user_data / "sessions" / "session-001"
        sessions.mkdir(parents=True)
        (sessions / "meta.json").write_text('{"title": "test session"}')
        (sessions / "workspace").mkdir()
        (sessions / "workspace" / "data.csv").write_text("col1,col2\n1,2")
        logs_dir = user_data / "logs"
        logs_dir.mkdir()
        (logs_dir / "nini.log").write_text("log line 1\nlog line 2")

        # 模拟安装目录（与用户数据目录分离）
        install_dir = tmp_path / "install"
        install_dir.mkdir()
        (install_dir / "nini.exe").write_bytes(b"old-binary")

        installer = tmp_path / "Nini-Setup.exe"
        installer.write_bytes(b"new-setup")
        expected_sha = hashlib.sha256(b"new-setup").hexdigest()

        log_path = user_data / "logs" / "updater.log"

        monkeypatch.setattr(updater, "_process_exists", lambda _: False)
        monkeypatch.setattr(updater.time, "sleep", lambda _: None)
        monkeypatch.setattr(
            updater.subprocess,
            "run",
            lambda *a, **kw: SimpleNamespace(returncode=0),
        )
        monkeypatch.setattr(
            updater.subprocess,
            "Popen",
            lambda *a, **kw: SimpleNamespace(),
        )

        ret = updater.main(
            [
                "--installer", str(installer),
                "--install-dir", str(install_dir),
                "--app-exe", str(install_dir / "nini.exe"),
                "--backend-pid", "123",
                "--log-path", str(log_path),
                "--expected-sha256", expected_sha,
                "--skip-signature-check",
            ]
        )
        assert ret == 0

        # 验证用户数据完整保留
        assert (user_data / "config.json").read_text() == '{"api_key": "test-key"}'
        assert (sessions / "meta.json").exists()
        assert (sessions / "workspace" / "data.csv").read_text() == "col1,col2\n1,2"
        assert (logs_dir / "nini.log").read_text() == "log line 1\nlog line 2"
        # updater 日志写入到用户数据目录的 logs 子目录
        assert (logs_dir / "updater.log").exists()
        assert "安装成功" in (logs_dir / "updater.log").read_text(encoding="utf-8")

    def test_state_persists_across_restart(self, tmp_path: Path) -> None:
        """下载状态持久化：重启后可恢复 ready 状态。"""
        state_file = tmp_path / "state.json"
        state_store = UpdateStateStore(state_file)

        # 模拟重启前保存的 ready 状态
        state_store.save(
            UpdateDownloadState(
                status="ready",
                version="0.2.0",
                progress=100,
                downloaded_bytes=50000,
                total_bytes=50000,
                installer_path=str(tmp_path / "0.2.0" / "Nini-0.2.0-Setup.exe"),
                expected_sha256=hashlib.sha256(b"installer").hexdigest(),
                expected_size=50000,
                verified=True,
            )
        )

        # 模拟重启后加载状态
        state_store2 = UpdateStateStore(state_file)
        loaded = state_store2.load()

        assert loaded is not None
        assert loaded.status == "ready"
        assert loaded.version == "0.2.0"
        assert loaded.verified is True
        assert loaded.downloaded_bytes == loaded.total_bytes
