"""更新包下载与完整性校验。"""

from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import urlparse

import httpx

from nini.update.models import UpdateAsset, UpdateDownloadState
from nini.update.state import UpdateStateStore


class DownloadError(RuntimeError):
    """更新包下载失败。"""


def _safe_filename_from_url(url: str, *, fallback: str) -> str:
    name = Path(urlparse(url).path).name
    if not name or name in {".", ".."}:
        return fallback
    return name


def sha256_file(path: Path) -> str:
    """计算文件 SHA256。"""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_downloaded_file(path: Path, asset: UpdateAsset) -> None:
    """校验文件大小和 SHA256。"""
    if not path.exists() or not path.is_file():
        raise DownloadError("更新包不存在")
    size = path.stat().st_size
    if size != asset.size:
        raise DownloadError("更新包大小与 manifest 不一致")
    digest = sha256_file(path)
    if digest != asset.sha256:
        raise DownloadError("更新包 SHA256 校验失败")


async def download_asset(
    asset: UpdateAsset,
    *,
    version: str,
    updates_dir: Path,
    state_store: UpdateStateStore,
    timeout: float,
    client: httpx.AsyncClient | None = None,
) -> UpdateDownloadState:
    """下载更新安装包；同版本下载请求保持幂等。"""
    existing = state_store.load()
    if existing.version == version and existing.status in {"downloading", "ready"}:
        return existing

    version_dir = updates_dir / version
    version_dir.mkdir(parents=True, exist_ok=True)
    filename = _safe_filename_from_url(asset.url, fallback=f"Nini-{version}-Setup.exe")
    target = version_dir / filename
    temp_target = target.with_suffix(target.suffix + ".download")

    state = UpdateDownloadState(
        status="downloading",
        version=version,
        progress=0,
        downloaded_bytes=0,
        total_bytes=asset.size,
        installer_path=str(target),
    )
    state_store.save(state)

    try:
        if client is None:
            async with httpx.AsyncClient(timeout=timeout) as owned_client:
                response = await owned_client.get(asset.url)
        else:
            response = await client.get(asset.url)
        response.raise_for_status()
        content = response.content
        temp_target.write_bytes(content)

        state.downloaded_bytes = len(content)
        state.progress = 100
        state.status = "verifying"
        state_store.save(state)

        verify_downloaded_file(temp_target, asset)
        temp_target.replace(target)

        state.status = "ready"
        state.installer_path = str(target)
        state.verified = True
        state.error = None
        state_store.save(state)
        return state
    except Exception as exc:
        if temp_target.exists():
            temp_target.unlink()
        state.status = "download_failed" if state.status == "downloading" else "verify_failed"
        state.verified = False
        state.error = str(exc)
        state_store.save(state)
        return state
