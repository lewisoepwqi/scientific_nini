"""校验 Nini 发布配置文件格式与必填项。"""

from __future__ import annotations

import argparse
import configparser
import sys
from pathlib import Path
from urllib.parse import urlparse


def _error(message: str) -> None:
    print(f"[FAIL] {message}", file=sys.stderr)


def verify_release_conf(config_path: Path) -> list[str]:
    """返回发现的问题列表；为空表示通过。"""
    errors: list[str] = []

    if not config_path.exists():
        errors.append(f"配置文件不存在: {config_path}")
        return errors

    parser = configparser.ConfigParser()
    try:
        parser.read(config_path, encoding="utf-8")
    except configparser.Error as exc:
        errors.append(f"配置文件解析失败: {exc}")
        return errors

    # 校验必需的 section
    if "server" not in parser.sections():
        errors.append("缺少 [server] 配置段")
        return errors

    server = parser["server"]

    # 校验必填字段
    required_fields = [
        ("url", "服务器 URL"),
        ("channel", "更新渠道"),
        ("ssh_user", "SSH 用户名"),
        ("ssh_host", "SSH 主机地址"),
        ("upload_path", "服务器上传目录"),
    ]
    for field, label in required_fields:
        value = server.get(field, "").strip()
        if not value:
            errors.append(f"[server] 缺少必填项: {field} ({label})")

    # 校验 URL 格式
    url = server.get("url", "").strip()
    if url:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            errors.append(f"服务器 URL 协议必须是 http 或 https: {url}")
        if not url.endswith("/"):
            errors.append(f"服务器 URL 必须以 / 结尾: {url}")

    # 校验渠道
    channel = server.get("channel", "").strip().lower()
    if channel and channel not in ("stable", "beta"):
        errors.append(f"更新渠道必须是 stable 或 beta: {channel}")

    # 校验 allow_insecure_http（如果是布尔值）
    allow_insecure = server.get("allow_insecure_http", "false").strip().lower()
    if allow_insecure not in ("true", "false", "1", "0", "yes", "no"):
        errors.append(
            f"allow_insecure_http 必须是布尔值 (true/false): {allow_insecure}"
        )

    # 校验 release 段（可选，有就校验）
    if "release" in parser.sections():
        release = parser["release"]
        default_notes = release.get("default_notes", "").strip()
        if default_notes and "|" not in default_notes:
            # 单条说明也是允许的，只做警告级提示
            pass  # 不报错，允许单条

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="校验 Nini 发布配置文件")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/release.conf"),
        help="配置文件路径（默认: config/release.conf）",
    )
    args = parser.parse_args(argv)

    errors = verify_release_conf(args.config)
    if errors:
        for error in errors:
            _error(error)
        return 1

    print("[OK] release.conf 校验通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
