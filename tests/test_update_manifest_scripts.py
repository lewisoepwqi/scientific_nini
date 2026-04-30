"""更新 manifest 生成与校验脚本测试。"""

from __future__ import annotations

import json

import pytest

from scripts.generate_update_manifest import build_manifest
from scripts.verify_update_manifest import verify_manifest


def test_build_manifest_contains_installer_metadata(tmp_path) -> None:
    installer = tmp_path / "Nini-0.1.1-Setup.exe"
    installer.write_bytes(b"nini-installer")

    manifest = build_manifest(
        installer=installer,
        version="0.1.1",
        channel="stable",
        base_url="https://updates.example.com/nini/stable/",
        notes="修复问题|优化体验",
        important=True,
    )

    asset = manifest["assets"][0]
    assert manifest["product"] == "nini"
    assert manifest["version"] == "0.1.1"
    assert manifest["important"] is True
    assert manifest["notes"] == ["修复问题", "优化体验"]
    assert manifest["signature_policy"]
    assert asset["url"] == "https://updates.example.com/nini/stable/Nini-0.1.1-Setup.exe"
    assert asset["size"] == len(b"nini-installer")
    assert len(asset["sha256"]) == 64


def test_build_manifest_rejects_insecure_base_url(tmp_path) -> None:
    installer = tmp_path / "Nini-0.1.1-Setup.exe"
    installer.write_bytes(b"nini-installer")

    with pytest.raises(ValueError, match="HTTPS"):
        build_manifest(
            installer=installer,
            version="0.1.1",
            channel="stable",
            base_url="http://updates.example.com/nini/stable/",
            notes="",
            important=False,
        )


def test_build_manifest_allows_ip_http_when_explicitly_enabled(tmp_path) -> None:
    installer = tmp_path / "Nini-0.1.1-Setup.exe"
    installer.write_bytes(b"nini-installer")

    manifest = build_manifest(
        installer=installer,
        version="0.1.1",
        channel="stable",
        base_url="http://121.41.97.123:1116/nini/stable/",
        notes="",
        important=False,
        allow_insecure_http=True,
    )

    asset = manifest["assets"][0]
    assert asset["url"] == "http://121.41.97.123:1116/nini/stable/Nini-0.1.1-Setup.exe"


def test_build_manifest_rejects_http_domain_even_when_enabled(tmp_path) -> None:
    installer = tmp_path / "Nini-0.1.1-Setup.exe"
    installer.write_bytes(b"nini-installer")

    with pytest.raises(ValueError, match="IP"):
        build_manifest(
            installer=installer,
            version="0.1.1",
            channel="stable",
            base_url="http://updates.example.com/nini/stable/",
            notes="",
            important=False,
            allow_insecure_http=True,
        )


def test_verify_manifest_detects_mismatch(tmp_path) -> None:
    installer = tmp_path / "Nini-0.1.1-Setup.exe"
    installer.write_bytes(b"nini-installer")
    manifest = build_manifest(
        installer=installer,
        version="0.1.1",
        channel="stable",
        base_url="https://updates.example.com/nini/stable/",
        notes="",
        important=False,
    )
    manifest_path = tmp_path / "latest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    assert verify_manifest(manifest_path, installer) == []

    installer.write_bytes(b"tampered")
    errors = verify_manifest(manifest_path, installer)
    assert any("size 不一致" in error for error in errors)
    assert "sha256 不一致" in errors
