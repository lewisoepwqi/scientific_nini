"""应用内更新业务服务。"""

from __future__ import annotations

import logging

import httpx

from nini.config import Settings, settings
from nini.update.download import download_asset
from nini.update.manifest import (
    DEFAULT_PLATFORM,
    ManifestError,
    UpdateSourceNotConfigured,
    fetch_manifest,
    select_asset,
)
from nini.update.models import UpdateAsset, UpdateCheckResult, UpdateManifest, UpdateStatus
from nini.update.state import UpdateStateStore, build_state_store
from nini.update.versioning import is_newer_version
from nini.version import get_current_version

logger = logging.getLogger(__name__)


class UpdateService:
    """协调版本检查、下载和本地状态。"""

    def __init__(self, app_settings: Settings = settings) -> None:
        self.settings = app_settings
        self.state_store: UpdateStateStore = build_state_store(app_settings.updates_dir)
        self._manifest: UpdateManifest | None = None
        self._asset: UpdateAsset | None = None
        self._check_result: UpdateCheckResult | None = None

    async def check_update(
        self,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> UpdateCheckResult:
        """检查是否存在可用更新。"""
        current = get_current_version()
        if self.settings.update_disabled:
            result = UpdateCheckResult(current_version=current, status="disabled")
            self._check_result = result
            return result
        if not self.settings.update_base_url.strip():
            result = UpdateCheckResult(current_version=current, status="not_configured")
            self._check_result = result
            return result

        try:
            manifest = await fetch_manifest(
                self.settings.update_base_url,
                channel=self.settings.update_channel,
                timeout=float(self.settings.update_download_timeout_seconds),
                client=client,
            )
            asset = select_asset(
                manifest,
                channel=self.settings.update_channel,
                platform=DEFAULT_PLATFORM,
                base_url=self.settings.update_base_url,
            )
            available = is_newer_version(manifest.version, current)
            result = UpdateCheckResult(
                current_version=current,
                latest_version=manifest.version,
                update_available=available,
                important=manifest.important,
                status="available" if available else "up_to_date",
                title=manifest.title,
                notes=manifest.notes,
                asset_size=asset.size,
            )
            self._manifest = manifest
            self._asset = asset
        except UpdateSourceNotConfigured:
            result = UpdateCheckResult(current_version=current, status="not_configured")
        except (ManifestError, httpx.HTTPError, ValueError) as exc:
            logger.warning("检查更新失败: %s", exc)
            result = UpdateCheckResult(
                current_version=current,
                status="check_failed",
                error=str(exc),
            )
        self._check_result = result
        return result

    async def download_update(
        self,
        *,
        client: httpx.AsyncClient | None = None,
    ):
        """下载当前检查到的更新包。"""
        if self._manifest is None or self._asset is None:
            check = await self.check_update(client=client)
            if not check.update_available:
                state = self.state_store.load()
                state.status = "download_failed"
                state.error = check.error or "当前没有可下载的更新"
                self.state_store.save(state)
                return state
        assert self._manifest is not None
        assert self._asset is not None
        return await download_asset(
            self._asset,
            version=self._manifest.version,
            updates_dir=self.settings.updates_dir,
            state_store=self.state_store,
            timeout=float(self.settings.update_download_timeout_seconds),
            client=client,
        )

    def status(self) -> UpdateStatus:
        """返回当前更新状态。"""
        return UpdateStatus(check=self._check_result, download=self.state_store.load())


update_service = UpdateService()
