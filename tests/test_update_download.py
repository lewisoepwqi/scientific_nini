"""更新包下载与续传相关测试。

§3.2 redirect 拒绝；后续 §7 续传 sha256 比对将在此文件追加。
"""

from __future__ import annotations

from pathlib import Path
import hashlib

import httpx
import pytest

from nini.update.download import download_asset
from nini.update.models import UpdateAsset, UpdateDownloadState
from nini.update.state import UpdateStateStore


def _make_asset() -> UpdateAsset:
    return UpdateAsset(
        platform="windows-x64",
        kind="nsis-installer",
        url="https://updates.example.com/releases/Nini-0.1.2-Setup.exe",
        size=10,
        sha256="a" * 64,
    )


@pytest.mark.asyncio
async def test_download_asset_rejects_redirect(tmp_path: Path) -> None:
    """服务器返回 302 时下载被拒绝并报可读错误。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302,
            headers={"Location": "https://evil.example.com/installer.exe"},
        )

    state_store = UpdateStateStore(tmp_path / "state.json")
    asset = _make_asset()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await download_asset(
            asset,
            version="0.1.2",
            updates_dir=tmp_path,
            state_store=state_store,
            timeout=5.0,
            client=client,
        )

    assert result.status == "download_failed"
    assert result.error is not None and "重定向" in result.error


@pytest.mark.asyncio
async def test_download_asset_discards_resume_when_sha256_changes(tmp_path: Path) -> None:
    """同 version 重发布导致 sha256 变化时，删除旧 .download 并从头下载。"""
    payload = b"new-installer"
    asset = UpdateAsset(
        platform="windows-x64",
        kind="nsis-installer",
        url="https://updates.example.com/releases/Nini-0.1.2-Setup.exe",
        size=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
    )
    version_dir = tmp_path / "0.1.2"
    version_dir.mkdir()
    temp_file = version_dir / "Nini-0.1.2-Setup.exe.download"
    temp_file.write_bytes(b"old-partial")
    state_store = UpdateStateStore(tmp_path / "state.json")
    state_store.save(
        UpdateDownloadState(
            status="downloading",
            version="0.1.2",
            progress=50,
            downloaded_bytes=len(b"old-partial"),
            total_bytes=999,
            installer_path=str(version_dir / "Nini-0.1.2-Setup.exe"),
            expected_sha256="b" * 64,
            expected_size=999,
        )
    )
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await download_asset(
            asset,
            version="0.1.2",
            updates_dir=tmp_path,
            state_store=state_store,
            timeout=5.0,
            client=client,
        )

    assert result.status == "ready"
    assert result.downloaded_bytes == len(payload)
    assert requests[0].headers.get("Range") is None
    assert (version_dir / "Nini-0.1.2-Setup.exe").read_bytes() == payload
