"""校验应用内更新 manifest 与安装包是否一致。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_manifest(manifest_path: Path, installer_path: Path) -> list[str]:
    """返回发现的问题列表；为空表示通过。"""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assets = manifest.get("assets")
    if not isinstance(assets, list) or not assets:
        return ["manifest 缺少 assets"]
    asset = assets[0]
    if not isinstance(asset, dict):
        return ["manifest asset 格式错误"]

    errors: list[str] = []
    actual_size = installer_path.stat().st_size
    actual_sha = _sha256(installer_path)
    if int(asset.get("size", -1)) != actual_size:
        errors.append(f"size 不一致: manifest={asset.get('size')} actual={actual_size}")
    if str(asset.get("sha256", "")).lower() != actual_sha:
        errors.append("sha256 不一致")
    return errors


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="校验 Nini 更新 manifest")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--installer", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    errors = verify_manifest(args.manifest, args.installer)
    if errors:
        for error in errors:
            print(f"[FAIL] {error}")
        return 1
    print("manifest 校验通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
