"""更新包下载与完整性校验。"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from urllib.parse import urlparse

import httpx

from nini.update.models import UpdateAsset, UpdateDownloadState
from nini.update.state import UpdateStateStore

logger = logging.getLogger(__name__)

# 流式下载的块大小（1MB）
_CHUNK_SIZE = 1024 * 1024

# 状态保存间隔（每 5% 保存一次）
_PROGRESS_SAVE_INTERVAL = 5


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
        for chunk in iter(lambda: file.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_downloaded_file(path: Path, asset: UpdateAsset) -> None:
    """校验文件大小和 SHA256。"""
    if not path.exists() or not path.is_file():
        raise DownloadError("更新包不存在")
    size = path.stat().st_size
    if size != asset.size:
        raise DownloadError(f"更新包大小与 manifest 不一致: 实际={size}, 预期={asset.size}")
    digest = sha256_file(path)
    if digest != asset.sha256:
        raise DownloadError("更新包 SHA256 校验失败")


async def _stream_download(
    url: str,
    target: Path,
    expected_size: int,
    state: UpdateDownloadState,
    state_store: UpdateStateStore,
    timeout: float,
    client: httpx.AsyncClient | None = None,
    resume_from: int = 0,
) -> int:
    """流式下载文件，支持断点续传。

    Args:
        url: 下载 URL
        target: 目标文件路径
        expected_size: 预期文件大小
        state: 下载状态对象
        state_store: 状态存储
        timeout: 超时时间
        client: httpx 客户端（可选）
        resume_from: 从哪个字节位置继续下载（0 表示从头开始）

    Returns:
        实际下载的总字节数

    Raises:
        DownloadError: 下载失败或校验异常
    """
    downloaded = resume_from
    last_saved_progress = state.progress if resume_from > 0 else 0

    # 构建请求头
    headers = {}
    if resume_from > 0:
        headers["Range"] = f"bytes={resume_from}-"
        logger.info("断点续传: 从 %d 字节位置继续下载", resume_from)

    async def _download_with_client(c: httpx.AsyncClient) -> int:
        nonlocal downloaded, last_saved_progress
        async with c.stream("GET", url, headers=headers) as response:
            # 拒绝任何 3xx 重定向：当前发布架构无 CDN redirect 需求，
            # 跟随重定向可能让安装包来源偏离 manifest 同源校验
            if 300 <= response.status_code < 400:
                raise DownloadError(
                    f"更新包 URL 返回重定向（status={response.status_code}），出于安全考虑已拒绝跟随"
                )
            # 检查服务器是否支持 Range 请求
            if resume_from > 0:
                if response.status_code == 200:
                    # 服务器不支持 Range 请求，从头开始下载
                    logger.warning("服务器不支持 Range 请求，从头开始下载")
                    downloaded = 0
                    state.downloaded_bytes = 0
                    state.progress = 0
                elif response.status_code == 206:
                    # 服务器支持 Range 请求，继续下载
                    logger.info("服务器支持 Range 请求，继续下载")
                else:
                    response.raise_for_status()

            # 选择写入模式
            mode = "ab" if resume_from > 0 and response.status_code == 206 else "wb"

            with target.open(mode) as f:
                async for chunk in response.aiter_bytes(chunk_size=_CHUNK_SIZE):
                    f.write(chunk)
                    downloaded += len(chunk)

                    # 实时校验大小
                    if downloaded > expected_size:
                        raise DownloadError(
                            f"下载大小超过 manifest 声明: 已下载={downloaded}, 预期={expected_size}"
                        )

                    # 更新进度
                    state.downloaded_bytes = downloaded
                    state.progress = (
                        int(downloaded * 100 / expected_size) if expected_size > 0 else 0
                    )

                    # 定期保存状态（避免频繁 IO）
                    if state.progress - last_saved_progress >= _PROGRESS_SAVE_INTERVAL:
                        state_store.save(state)
                        last_saved_progress = state.progress

        return downloaded

    if client is None:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as owned_client:
            return await _download_with_client(owned_client)
    else:
        return await _download_with_client(client)


async def download_asset(
    asset: UpdateAsset,
    *,
    version: str,
    updates_dir: Path,
    state_store: UpdateStateStore,
    timeout: float,
    client: httpx.AsyncClient | None = None,
) -> UpdateDownloadState:
    """下载更新安装包；同版本下载请求保持幂等。

    改进：
    - 流式下载：避免将整个文件读入内存
    - 实时大小校验：下载过程中检测异常
    - 进度上报：定期更新下载进度
    - 断点续传：支持从上次中断位置继续下载
    """
    existing = state_store.load()

    # 检查是否已完成
    if existing.version == version and existing.status == "ready":
        logger.info("跳过已完成的下载: version=%s", version)
        return existing

    # 检查是否可以断点续传
    can_resume = (
        existing.version == version
        and existing.status == "downloading"
        and existing.downloaded_bytes > 0
        and existing.installer_path is not None
    )

    version_dir = updates_dir / version
    version_dir.mkdir(parents=True, exist_ok=True)
    filename = _safe_filename_from_url(asset.url, fallback=f"Nini-{version}-Setup.exe")
    target = version_dir / filename
    temp_target = target.with_suffix(target.suffix + ".download")

    if can_resume and (existing.expected_sha256 or "").lower() != asset.sha256.lower():
        logger.warning(
            "检测到同版本 manifest 重发布，丢弃旧下载字节: version=%s old_sha=%s new_sha=%s",
            version,
            existing.expected_sha256,
            asset.sha256,
        )
        if temp_target.exists():
            temp_target.unlink()
        existing.status = "idle"
        existing.downloaded_bytes = 0
        existing.progress = 0
        existing.verified = False
        existing.error = "manifest sha256 已变化，已从头重新下载"
        state_store.save(existing)
        can_resume = False

    # 初始化或恢复状态
    if can_resume:
        logger.info(
            "尝试断点续传: version=%s, 已下载=%d bytes",
            version,
            existing.downloaded_bytes,
        )
        state = existing
        state.expected_sha256 = asset.sha256
        state.expected_size = asset.size
        state.total_bytes = asset.size
        resume_from = existing.downloaded_bytes
    else:
        state = UpdateDownloadState(
            status="downloading",
            version=version,
            progress=0,
            downloaded_bytes=0,
            total_bytes=asset.size,
            installer_path=str(target),
            expected_sha256=asset.sha256,
            expected_size=asset.size,
        )
        state_store.save(state)
        resume_from = 0

    logger.info(
        "开始流式下载: version=%s, size=%d bytes, resume_from=%d, url=%s",
        version,
        asset.size,
        resume_from,
        asset.url,
    )

    try:
        # 流式下载（支持断点续传）
        total_downloaded = await _stream_download(
            asset.url,
            temp_target,
            asset.size,
            state,
            state_store,
            timeout,
            client,
            resume_from,
        )

        # 下载完成，更新状态
        state.downloaded_bytes = temp_target.stat().st_size
        state.progress = 100
        state.status = "verifying"
        state_store.save(state)

        logger.info("下载完成，开始校验: downloaded=%d bytes", state.downloaded_bytes)

        # 校验文件
        verify_downloaded_file(temp_target, asset)
        temp_target.replace(target)

        state.status = "ready"
        state.installer_path = str(target)
        state.verified = True
        state.error = None
        state.expected_sha256 = asset.sha256
        state.expected_size = asset.size
        state_store.save(state)

        logger.info("更新包校验通过: path=%s", target)
        return state
    except Exception as exc:
        logger.error("下载或校验失败: %s", exc)
        # 清理临时文件（但保留部分下载的文件以便续传）
        if "不支持 Range" in str(exc) or resume_from == 0:
            # 如果是全新下载失败，清理临时文件
            if temp_target.exists():
                temp_target.unlink()
        else:
            # 断点续传失败，保留已下载的部分
            logger.info("保留部分下载文件以便续传: %s", temp_target)

        state.status = "download_failed" if state.status == "downloading" else "verify_failed"
        state.verified = False
        state.error = str(exc)
        state_store.save(state)
        return state
