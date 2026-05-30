"""发布上传脚本生成器测试。"""

from __future__ import annotations

from pathlib import Path

from scripts.generate_upload_script import generate_upload_scripts


def test_generated_upload_scripts_run_from_script_directory(tmp_path: Path) -> None:
    """生成的上传脚本应可从任意当前目录执行。"""
    config_path = tmp_path / "release.conf"
    config_path.write_text(
        "\n".join(
            [
                "[server]",
                "ssh_user = lewis",
                "ssh_host = 121.41.97.123",
                "upload_path = /opt/nini-updates/public/nini/updates/stable",
                "url = https://update.lewisoepwqi.com/nini/updates/",
                "channel = stable",
            ]
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "dist" / "v0.1.9"

    generate_upload_scripts(
        version="0.1.9",
        installer_dir=output_dir,
        config_path=config_path,
        output_dir=output_dir,
    )

    ps1_text = (output_dir / "upload.ps1").read_text(encoding="utf-8")
    bat_text = (output_dir / "upload.bat").read_text(encoding="utf-8")

    assert "Set-Location -LiteralPath $ScriptDir" in ps1_text
    assert "Join-Path $ScriptDir $File" in ps1_text
    assert 'cd /d "%~dp0"' in bat_text


def test_generated_powershell_upload_fails_on_scp_exit_code(tmp_path: Path) -> None:
    """PowerShell 上传脚本必须显式检查 scp 退出码。"""
    config_path = tmp_path / "release.conf"
    config_path.write_text(
        "\n".join(
            [
                "[server]",
                "ssh_user = lewis",
                "ssh_host = 121.41.97.123",
                "upload_path = /opt/nini-updates/public/nini/updates/stable",
                "url = https://update.lewisoepwqi.com/nini/updates/",
                "channel = stable",
            ]
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "dist" / "v0.1.9"

    generate_upload_scripts(
        version="0.1.9",
        installer_dir=output_dir,
        config_path=config_path,
        output_dir=output_dir,
    )

    ps1_text = (output_dir / "upload.ps1").read_text(encoding="utf-8")

    assert "if ($LASTEXITCODE -ne 0)" in ps1_text
    assert 'throw "scp failed with exit code $LASTEXITCODE"' in ps1_text
