"""生成应用内更新 manifest 草稿。"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

from packaging.version import InvalidVersion, Version


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _notes(raw: str) -> list[str]:
    return [item.strip() for item in raw.split("|") if item.strip()]


def _is_local_or_private_host(hostname: str | None) -> bool:
    """判断主机是否为本机或私有地址。"""
    if not hostname:
        return False
    normalized = hostname.strip().lower()
    if normalized == "localhost":
        return True
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return address.is_loopback or address.is_private or address.is_link_local


def build_manifest(
    *,
    installer: Path,
    version: str,
    channel: str,
    base_url: str,
    notes: str,
    important: bool,
    allow_insecure_http: bool = False,
) -> dict[str, object]:
    """根据安装包生成 manifest 内容。"""
    installer = installer.resolve()
    if not installer.exists():
        raise FileNotFoundError(installer)
    try:
        Version(version)
    except InvalidVersion as exc:
        raise ValueError(f"版本号不符合 PEP 440: {version}") from exc
    parsed_base_url = urlparse(base_url)
    if parsed_base_url.scheme == "http":
        if not allow_insecure_http or not _is_local_or_private_host(parsed_base_url.hostname):
            raise ValueError(
                "更新安装包下载 URL 必须使用 HTTPS；HTTP 仅允许显式开启的内网 IP 或 localhost"
            )
    elif parsed_base_url.scheme != "https":
        raise ValueError("更新安装包下载 URL 必须使用 HTTPS")
    url = urljoin(base_url.rstrip("/") + "/", installer.name)
    return {
        "schema_version": 1,
        "product": "nini",
        "channel": channel,
        "version": version,
        "released_at": datetime.now(timezone.utc).isoformat(),
        "minimum_supported_version": "0.1.0",
        "important": important,
        "title": f"Nini {version}",
        "notes": _notes(notes),
        "assets": [
            {
                "platform": "windows-x64",
                "kind": "nsis-installer",
                "url": url,
                "size": installer.stat().st_size,
                "sha256": _sha256(installer),
            }
        ],
        "signature_policy": "正式发布必须对 nini.exe、nini-cli.exe、nini-updater.exe 和安装包进行 Authenticode 签名",
        "signature": None,
        "signature_url": None,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="生成 Nini 更新 manifest")
    parser.add_argument("--installer", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--channel", default="stable")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--notes", default="")
    parser.add_argument("--important", action="store_true")
    parser.add_argument(
        "--allow-insecure-http",
        action="store_true",
        help="仅测试或内网发布使用：允许 localhost / 私有 IP 的 HTTP 下载 URL",
    )
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    manifest = build_manifest(
        installer=args.installer,
        version=args.version,
        channel=args.channel,
        base_url=args.base_url,
        notes=args.notes,
        important=args.important,
        allow_insecure_http=args.allow_insecure_http,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"已生成更新 manifest: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
