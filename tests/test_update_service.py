"""更新服务与下载状态测试。"""

from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
import pytest

from nini.config import Settings
from nini.update.download import download_asset
from nini.update.models import UpdateAsset
from nini.update.service import UpdateService
from nini.update.state import build_state_store


def _asset_for_content(
    content: bytes, url: str = "https://updates.example.com/app.exe"
) -> UpdateAsset:
    return UpdateAsset(
        platform="windows-x64",
        kind="nsis-installer",
        url=url,
        size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
    )


@pytest.mark.asyncio
async def test_check_update_no_source_is_not_configured(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path, update_base_url="")
    service = UpdateService(settings)

    result = await service.check_update()

    assert result.status == "not_configured"
    assert result.update_available is False


@pytest.mark.asyncio
async def test_check_update_available(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path,
        update_base_url="https://updates.example.com/releases",
    )
    monkeypatch.setattr("nini.update.service.get_current_version", lambda: "0.1.1")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "schema_version": 1,
                "product": "nini",
                "channel": "stable",
                "version": "0.1.2",
                "important": True,
                "notes": ["修复问题"],
                "assets": [
                    {
                        "platform": "windows-x64",
                        "kind": "nsis-installer",
                        "url": "https://updates.example.com/releases/Nini-0.1.2-Setup.exe",
                        "size": 123,
                        "sha256": "b" * 64,
                    }
                ],
            },
        )

    service = UpdateService(settings)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await service.check_update(client=client)

    assert result.status == "available"
    assert result.update_available is True
    assert result.important is True
    assert result.asset_size == 123


@pytest.mark.asyncio
async def test_download_asset_success_and_idempotent(tmp_path: Path) -> None:
    content = b"installer"
    asset = _asset_for_content(content)
    store = build_state_store(tmp_path)
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=content)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        first = await download_asset(
            asset,
            version="0.1.2",
            updates_dir=tmp_path,
            state_store=store,
            timeout=1,
            client=client,
        )
        second = await download_asset(
            asset,
            version="0.1.2",
            updates_dir=tmp_path,
            state_store=store,
            timeout=1,
            client=client,
        )

    assert first.status == "ready"
    assert first.verified is True
    assert second.status == "ready"
    assert calls == 1


@pytest.mark.asyncio
async def test_download_asset_sha256_failure(tmp_path: Path) -> None:
    asset = UpdateAsset(
        platform="windows-x64",
        kind="nsis-installer",
        url="https://updates.example.com/app.exe",
        size=3,
        sha256="0" * 64,
    )
    store = build_state_store(tmp_path)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"bad")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        state = await download_asset(
            asset,
            version="0.1.2",
            updates_dir=tmp_path,
            state_store=store,
            timeout=1,
            client=client,
        )

    assert state.status == "verify_failed"
    assert state.verified is False
    assert "SHA256" in (state.error or "")
