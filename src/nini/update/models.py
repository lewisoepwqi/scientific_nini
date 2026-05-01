"""应用内更新数据模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

UpdateCheckStatus = Literal[
    "available",
    "up_to_date",
    "check_failed",
    "not_configured",
    "disabled",
    "channel_mismatch",
]

DownloadStatus = Literal[
    "idle",
    "checking",
    "available",
    "up_to_date",
    "check_failed",
    "downloading",
    "download_failed",
    "verifying",
    "verify_failed",
    "ready",
    "applying",
    "restarting",
]


class UpdateAsset(BaseModel):
    """单个平台的更新安装包。"""

    platform: str = Field(min_length=1)
    kind: str = Field(default="nsis-installer", min_length=1)
    url: str = Field(min_length=1)
    size: int = Field(gt=0)
    sha256: str = Field(min_length=64, max_length=64)

    @field_validator("sha256")
    @classmethod
    def _validate_sha256(cls, value: str) -> str:
        normalized = value.strip().lower()
        if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
            raise ValueError("sha256 必须是 64 位十六进制字符串")
        return normalized


class UpdateManifest(BaseModel):
    """更新服务器发布的版本清单。"""

    schema_version: int = 1
    product: str = Field(default="nini", min_length=1)
    channel: str = Field(default="stable", min_length=1)
    version: str = Field(min_length=1)
    released_at: datetime | None = None
    minimum_supported_version: str | None = None
    important: bool = False
    title: str | None = None
    notes: list[str] = Field(default_factory=list)
    assets: list[UpdateAsset] = Field(default_factory=list)
    signature_policy: str | None = None
    signature_url: str | None = None
    signature: str | None = None

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, value: int) -> int:
        if value != 1:
            raise ValueError("仅支持 schema_version=1 的更新清单")
        return value


class UpdateCheckResult(BaseModel):
    """版本检查结果。"""

    current_version: str
    latest_version: str | None = None
    update_available: bool = False
    important: bool = False
    status: UpdateCheckStatus = "up_to_date"
    title: str | None = None
    notes: list[str] = Field(default_factory=list)
    asset_size: int | None = None
    error: str | None = None


class UpdateDownloadState(BaseModel):
    """更新包下载状态。"""

    status: DownloadStatus = "idle"
    version: str | None = None
    progress: int = Field(default=0, ge=0, le=100)
    downloaded_bytes: int = Field(default=0, ge=0)
    total_bytes: int | None = Field(default=None, ge=0)
    installer_path: str | None = None
    verified: bool = False
    error: str | None = None
    # 预期 sha256 / size 由 manifest 提供，updater 在 NSIS 之前以此进行二次校验
    expected_sha256: str | None = None
    expected_size: int | None = None


class UpdateStatus(BaseModel):
    """对前端暴露的更新状态。"""

    check: UpdateCheckResult | None = None
    download: UpdateDownloadState = Field(default_factory=UpdateDownloadState)
