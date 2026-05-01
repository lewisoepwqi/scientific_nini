"""根据发布配置生成上传脚本和运维说明文档。"""

from __future__ import annotations

import argparse
import configparser
from datetime import datetime, timezone
from pathlib import Path


def _generate_bat_script(
    *,
    version: str,
    ssh_user: str,
    ssh_host: str,
    upload_path: str,
    server_url: str,
    channel: str,
    installer_name: str,
) -> str:
    """生成 Windows CMD 上传脚本。"""
    return f'''@echo off
chcp 65001 >nul 2>nul
echo === Nini v{version} 发布上传 ===
echo.
echo 服务器: {ssh_host}
echo 渠道: {channel}
echo 上传目录: {upload_path}
echo.

echo [1/3] 上传 latest.json...
scp latest.json {ssh_user}@{ssh_host}:{upload_path}/
if %errorlevel% neq 0 (
    echo [FAIL] latest.json 上传失败
    pause
    exit /b 1
)

echo [2/3] 上传 {installer_name}...
scp {installer_name} {ssh_user}@{ssh_host}:{upload_path}/
if %errorlevel% neq 0 (
    echo [FAIL] {installer_name} 上传失败
    pause
    exit /b 1
)

echo [3/3] 上传 {installer_name}.sha256...
if exist "{installer_name}.sha256" (
    scp {installer_name}.sha256 {ssh_user}@{ssh_host}:{upload_path}/
)

echo.
echo === 上传完成 ===
echo 验证地址: {server_url}{channel}/latest.json
echo.
pause
'''


def _generate_ps1_script(
    *,
    version: str,
    ssh_user: str,
    ssh_host: str,
    upload_path: str,
    server_url: str,
    channel: str,
    installer_name: str,
) -> str:
    """生成 PowerShell 上传脚本。"""
    return f'''#Requires -Version 5.1
# Nini v{version} 发布上传脚本（PowerShell）
# 推荐方式：右键选择"使用 PowerShell 运行"

$ErrorActionPreference = "Stop"

$Server = "{ssh_host}"
$User = "{ssh_user}"
$RemotePath = "{upload_path}"
$Channel = "{channel}"
$VerifyUrl = "{server_url}{channel}/latest.json"

Write-Host "=== Nini v{version} 发布上传 ===" -ForegroundColor Cyan
Write-Host "服务器: $Server" -ForegroundColor Gray
Write-Host "渠道: $Channel" -ForegroundColor Gray
Write-Host "上传目录: $RemotePath" -ForegroundColor Gray
Write-Host ""

$Files = @(
    "latest.json",
    "{installer_name}"
)

# 可选文件
if (Test-Path "{installer_name}.sha256") {{
    $Files += "{installer_name}.sha256"
}}

$Index = 0
foreach ($File in $Files) {{
    $Index++
    Write-Host "[$Index/$($Files.Count)] 上传 $File..." -ForegroundColor Yellow -NoNewline
    try {{
        scp $File "$User@${{Server}}:$RemotePath/"
        Write-Host " 完成" -ForegroundColor Green
    }} catch {{
        Write-Host " 失败" -ForegroundColor Red
        Write-Error "上传失败: $_"
        exit 1
    }}
}}

Write-Host ""
Write-Host "=== 上传完成 ===" -ForegroundColor Cyan
Write-Host "验证地址: $VerifyUrl" -ForegroundColor Green
Write-Host ""

# 尝试验证
Write-Host "正在验证..." -ForegroundColor Yellow -NoNewline
try {{
    $Response = Invoke-RestMethod -Uri $VerifyUrl -TimeoutSec 10
    if ($Response.version -eq "{version}") {{
        Write-Host " 版本号验证通过 ($($Response.version))" -ForegroundColor Green
    }} else {{
        Write-Host " 版本号不匹配: 期望 {version}, 实际 $($Response.version)" -ForegroundColor Red
    }}
}} catch {{
    Write-Host " 无法访问验证地址" -ForegroundColor Yellow
}}

Write-Host ""
Read-Host "按 Enter 键退出"
'''


def _generate_instructions(
    *,
    version: str,
    ssh_user: str,
    ssh_host: str,
    upload_path: str,
    server_url: str,
    channel: str,
    installer_name: str,
    allow_insecure_http: bool,
) -> str:
    """生成运维人员操作说明文档。"""
    http_note = ""
    if allow_insecure_http:
        http_note = """
【HTTP 说明】
当前配置使用 HTTP，客户端 .env 需要额外配置：
  NINI_UPDATE_ALLOW_INSECURE_HTTP=true
"""

    return f'''================================================================================
Nini v{version} 发布文件上传说明
================================================================================
生成时间: {datetime.now(timezone.utc).isoformat()}

【需上传的文件】（共 3 个）
  1. latest.json
  2. {installer_name}
  3. {installer_name}.sha256（可选，但建议上传）

【服务器配置】
  基础 URL: {server_url}
  渠道: {channel}
  SSH 主机: {ssh_host}
  SSH 用户: {ssh_user}
  上传目录: {upload_path}

【方式一：PowerShell 上传（推荐）】
  1. 打开 PowerShell
  2. 进入目录: cd dist/v{version}
  3. 执行: .\\upload.ps1
  或右键 upload.ps1 → "使用 PowerShell 运行"

【方式二：CMD 一键上传】
  直接双击运行: upload.bat

【方式三：手动上传】
  scp latest.json {ssh_user}@{ssh_host}:{upload_path}/
  scp {installer_name} {ssh_user}@{ssh_host}:{upload_path}/
  scp {installer_name}.sha256 {ssh_user}@{ssh_host}:{upload_path}/

【验证】
  浏览器访问: {server_url}{channel}/latest.json
  应能看到:
    - "version": "{version}"
    - "assets"[0]."sha256": 64 位十六进制字符串
    - "assets"[0]."size": 与本地文件大小一致

【客户端配置】
  NINI_UPDATE_BASE_URL={server_url}
  NINI_UPDATE_CHANNEL={channel}
  {f"NINI_UPDATE_ALLOW_INSECURE_HTTP=true" if allow_insecure_http else "NINI_UPDATE_ALLOW_INSECURE_HTTP=false"}

【注意事项】
  1. latest.json 和 {installer_name} 必须一起上传，不可只传其一
  2. 上传后务必通过浏览器验证 latest.json 内容正确
  3. 如果客户端已运行，需要重启客户端才能检测到更新
{http_note}
================================================================================
'''


def generate_upload_scripts(
    *,
    version: str,
    installer_dir: Path,
    config_path: Path,
    output_dir: Path,
) -> list[Path]:
    """生成上传脚本和说明文档，返回生成的文件列表。"""
    # 读取配置
    parser = configparser.ConfigParser()
    parser.read(config_path, encoding="utf-8")

    server = parser["server"]
    release = parser["release"] if "release" in parser.sections() else {}

    ssh_user = server.get("ssh_user", "").strip()
    ssh_host = server.get("ssh_host", "").strip()
    upload_path = server.get("upload_path", "").strip()
    server_url = server.get("url", "").strip()
    channel = server.get("channel", "stable").strip()
    allow_insecure_http = server.get("allow_insecure_http", "false").strip().lower() in (
        "true",
        "1",
        "yes",
    )

    installer_name = f"Nini-{version}-Setup.exe"

    # 确保输出目录存在
    output_dir.mkdir(parents=True, exist_ok=True)

    generated: list[Path] = []

    # 生成 upload.bat
    bat_content = _generate_bat_script(
        version=version,
        ssh_user=ssh_user,
        ssh_host=ssh_host,
        upload_path=upload_path,
        server_url=server_url,
        channel=channel,
        installer_name=installer_name,
    )
    bat_path = output_dir / "upload.bat"
    bat_path.write_text(bat_content, encoding="utf-8")
    generated.append(bat_path)

    # 生成 upload.ps1
    ps1_content = _generate_ps1_script(
        version=version,
        ssh_user=ssh_user,
        ssh_host=ssh_host,
        upload_path=upload_path,
        server_url=server_url,
        channel=channel,
        installer_name=installer_name,
    )
    ps1_path = output_dir / "upload.ps1"
    ps1_path.write_text(ps1_content, encoding="utf-8")
    generated.append(ps1_path)

    # 生成 UPLOAD_INSTRUCTIONS.txt
    instructions_content = _generate_instructions(
        version=version,
        ssh_user=ssh_user,
        ssh_host=ssh_host,
        upload_path=upload_path,
        server_url=server_url,
        channel=channel,
        installer_name=installer_name,
        allow_insecure_http=allow_insecure_http,
    )
    instructions_path = output_dir / "UPLOAD_INSTRUCTIONS.txt"
    instructions_path.write_text(instructions_content, encoding="utf-8")
    generated.append(instructions_path)

    return generated


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="生成 Nini 发布上传脚本")
    parser.add_argument("--version", required=True, help="版本号（如 0.1.3）")
    parser.add_argument(
        "--installer-dir",
        type=Path,
        required=True,
        help="安装包所在目录（如 dist/v0.1.3）",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/release.conf"),
        help="配置文件路径（默认: config/release.conf）",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="输出目录（默认与 --installer-dir 相同）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    output_dir = args.output_dir or args.installer_dir

    if not args.config.exists():
        print(f"[SKIP] 配置文件不存在: {args.config}，跳过上传脚本生成")
        return 0

    try:
        generated = generate_upload_scripts(
            version=args.version,
            installer_dir=args.installer_dir,
            config_path=args.config,
            output_dir=output_dir,
        )
        for path in generated:
            print(f"已生成: {path}")
        return 0
    except Exception as exc:
        print(f"[FAIL] 生成上传脚本失败: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
