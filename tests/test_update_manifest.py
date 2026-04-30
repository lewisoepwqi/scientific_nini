"""应用内更新清单与版本比较测试。"""

from __future__ import annotations

import pytest
import httpx
from packaging.version import InvalidVersion

from nini.config import Settings
from nini.update.manifest import (
    ManifestError,
    UpdateSourceNotConfigured,
    build_manifest_url,
    fetch_manifest,
    select_asset,
)
from nini.update.models import UpdateManifest
from nini.update.versioning import is_newer_version, parse_version


_SHA = "a" * 64


def _manifest_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "product": "nini",
        "channel": "stable",
        "version": "0.1.2",
        "important": False,
        "notes": ["更新说明"],
        "assets": [
            {
                "platform": "windows-x64",
                "kind": "nsis-installer",
                "url": "https://updates.example.com/releases/Nini-0.1.2-Setup.exe",
                "size": 1024,
                "sha256": _SHA,
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_pep440_version_comparison() -> None:
    assert is_newer_version("0.1.2", "0.1.1") is True
    assert is_newer_version("0.1.2rc1", "0.1.2b1") is True
    assert is_newer_version("0.1.2", "0.1.2rc1") is True
    assert is_newer_version("0.1.1", "0.1.2") is False


def test_invalid_version_is_rejected() -> None:
    with pytest.raises(InvalidVersion):
        parse_version("not a version")


def test_build_manifest_url_requires_configured_source() -> None:
    with pytest.raises(UpdateSourceNotConfigured):
        build_manifest_url("", "stable")


def test_build_manifest_url_requires_https() -> None:
    with pytest.raises(ManifestError, match="HTTPS"):
        build_manifest_url("http://updates.example.com", "stable")


def test_build_manifest_url_allows_ip_http_when_explicitly_enabled() -> None:
    assert (
        build_manifest_url(
            "http://121.41.97.123:1116/releases",
            "stable",
            allow_insecure_http=True,
        )
        == "http://121.41.97.123:1116/releases/stable/latest.json"
    )


def test_build_manifest_url_rejects_http_domain_even_when_enabled() -> None:
    with pytest.raises(ManifestError, match="IP"):
        build_manifest_url(
            "http://updates.example.com/releases",
            "stable",
            allow_insecure_http=True,
        )


def test_build_manifest_url_uses_channel_path() -> None:
    assert (
        build_manifest_url("https://updates.example.com/releases", "beta")
        == "https://updates.example.com/releases/beta/latest.json"
    )


def test_manifest_normalizes_sha256() -> None:
    payload = _manifest_payload(
        assets=[
            {
                "platform": "windows-x64",
                "kind": "nsis-installer",
                "url": "https://updates.example.com/releases/Nini-0.1.2-Setup.exe",
                "size": 1024,
                "sha256": "A" * 64,
            }
        ]
    )
    manifest = UpdateManifest.model_validate(payload)
    assert manifest.assets[0].sha256 == _SHA


def test_manifest_rejects_missing_sha256() -> None:
    payload = _manifest_payload(
        assets=[
            {
                "platform": "windows-x64",
                "kind": "nsis-installer",
                "url": "https://updates.example.com/releases/Nini-0.1.2-Setup.exe",
                "size": 1024,
            }
        ]
    )
    with pytest.raises(ValueError):
        UpdateManifest.model_validate(payload)


def test_select_asset_rejects_product_mismatch() -> None:
    manifest = UpdateManifest.model_validate(_manifest_payload(product="other"))
    with pytest.raises(ManifestError, match="product"):
        select_asset(
            manifest,
            channel="stable",
            base_url="https://updates.example.com/releases",
        )


def test_select_asset_rejects_unsupported_platform() -> None:
    manifest = UpdateManifest.model_validate(_manifest_payload())
    with pytest.raises(ManifestError, match="平台"):
        select_asset(
            manifest,
            channel="stable",
            platform="linux-x64",
            base_url="https://updates.example.com/releases",
        )


def test_select_asset_rejects_insecure_asset_url() -> None:
    manifest = UpdateManifest.model_validate(
        _manifest_payload(
            assets=[
                {
                    "platform": "windows-x64",
                    "kind": "nsis-installer",
                    "url": "http://updates.example.com/releases/Nini-0.1.2-Setup.exe",
                    "size": 1024,
                    "sha256": _SHA,
                }
            ]
        )
    )
    with pytest.raises(ManifestError, match="HTTPS"):
        select_asset(
            manifest,
            channel="stable",
            base_url="https://updates.example.com/releases",
        )


def test_select_asset_allows_ip_http_when_explicitly_enabled() -> None:
    manifest = UpdateManifest.model_validate(
        _manifest_payload(
            assets=[
                {
                    "platform": "windows-x64",
                    "kind": "nsis-installer",
                    "url": "http://121.41.97.123:1116/releases/Nini-0.1.2-Setup.exe",
                    "size": 1024,
                    "sha256": _SHA,
                }
            ]
        )
    )

    asset = select_asset(
        manifest,
        channel="stable",
        base_url="http://121.41.97.123:1116/releases",
        allow_insecure_http=True,
    )

    assert asset.url.startswith("http://121.41.97.123:1116/")


def test_select_asset_rejects_cross_domain_asset_url() -> None:
    manifest = UpdateManifest.model_validate(
        _manifest_payload(
            assets=[
                {
                    "platform": "windows-x64",
                    "kind": "nsis-installer",
                    "url": "https://evil.example.net/Nini-0.1.2-Setup.exe",
                    "size": 1024,
                    "sha256": _SHA,
                }
            ]
        )
    )
    with pytest.raises(ManifestError, match="同域"):
        select_asset(
            manifest,
            channel="stable",
            base_url="https://updates.example.com/releases",
        )


@pytest.mark.asyncio
async def test_fetch_manifest_parses_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://updates.example.com/releases/stable/latest.json"
        return httpx.Response(200, json=_manifest_payload())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        manifest = await fetch_manifest(
            "https://updates.example.com/releases",
            channel="stable",
            client=client,
        )

    assert manifest.version == "0.1.2"
    assert manifest.notes == ["更新说明"]


@pytest.mark.asyncio
async def test_fetch_manifest_allows_ip_http_when_explicitly_enabled() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://121.41.97.123:1116/releases/stable/latest.json"
        return httpx.Response(200, json=_manifest_payload())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        manifest = await fetch_manifest(
            "http://121.41.97.123:1116/releases",
            channel="stable",
            allow_insecure_http=True,
            client=client,
        )

    assert manifest.version == "0.1.2"


def test_update_settings_default_to_no_real_source() -> None:
    settings = Settings(_env_file=None)
    assert settings.update_base_url == ""
    assert settings.update_channel == "stable"
    assert settings.update_allow_insecure_http is False
    assert settings.update_auto_check_enabled is True
    assert settings.update_disabled is False
