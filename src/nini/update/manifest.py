"""更新清单拉取与校验。"""

from __future__ import annotations

import ipaddress
from urllib.parse import urljoin, urlparse

import httpx

from nini.update.models import UpdateAsset, UpdateManifest
from nini.update.versioning import parse_version

DEFAULT_PRODUCT = "nini"
DEFAULT_PLATFORM = "windows-x64"


class ManifestError(ValueError):
    """更新清单无效。"""


class UpdateSourceNotConfigured(ManifestError):
    """未配置更新源。"""


def _is_ip_or_localhost(hostname: str | None) -> bool:
    """判断主机是否为 localhost 或字面量 IP 地址。"""
    if not hostname:
        return False
    normalized = hostname.strip().lower()
    if normalized == "localhost":
        return True
    try:
        ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return True


def _validate_update_url_security(
    parsed_url,
    *,
    allow_insecure_http: bool,
    label: str,
) -> None:
    """校验更新 URL 协议；HTTP 仅允许显式开启的 IP 地址。"""
    if parsed_url.scheme == "https":
        return
    if (
        parsed_url.scheme == "http"
        and allow_insecure_http
        and _is_ip_or_localhost(parsed_url.hostname)
    ):
        return
    if parsed_url.scheme == "http":
        raise ManifestError(f"{label} 必须使用 HTTPS；HTTP 仅允许显式开启的 IP 地址或 localhost")
    raise ManifestError(f"{label} 必须使用 HTTPS")


def build_manifest_url(
    base_url: str,
    channel: str,
    *,
    allow_insecure_http: bool = False,
) -> str:
    """根据基础 URL 与渠道生成 latest.json 地址。"""
    base = base_url.strip()
    if not base:
        raise UpdateSourceNotConfigured("未配置更新服务器 URL")
    parsed = urlparse(base)
    _validate_update_url_security(
        parsed,
        allow_insecure_http=allow_insecure_http,
        label="更新服务器 URL",
    )
    if base.endswith(".json"):
        return base
    return urljoin(base.rstrip("/") + "/", f"{channel.strip() or 'stable'}/latest.json")


def validate_asset_url(
    asset: UpdateAsset,
    *,
    base_url: str,
    allow_insecure_http: bool = False,
) -> None:
    """校验安装包 URL 的协议与来源。"""
    asset_url = urlparse(asset.url)
    source_url = urlparse(base_url)
    _validate_update_url_security(
        asset_url,
        allow_insecure_http=allow_insecure_http,
        label="更新包 URL",
    )
    if source_url.netloc and asset_url.netloc != source_url.netloc:
        raise ManifestError("更新包 URL 必须与更新源同域")


def select_asset(
    manifest: UpdateManifest,
    *,
    product: str = DEFAULT_PRODUCT,
    channel: str,
    platform: str = DEFAULT_PLATFORM,
    base_url: str,
    allow_insecure_http: bool = False,
) -> UpdateAsset:
    """校验清单并选出当前平台安装包。"""
    if manifest.product != product:
        raise ManifestError("更新清单 product 与当前产品不匹配")
    if manifest.channel != channel:
        raise ManifestError("更新清单 channel 与当前渠道不匹配")
    parse_version(manifest.version)
    if manifest.minimum_supported_version:
        parse_version(manifest.minimum_supported_version)

    for asset in manifest.assets:
        if asset.platform == platform:
            validate_asset_url(
                asset,
                base_url=base_url,
                allow_insecure_http=allow_insecure_http,
            )
            return asset
    raise ManifestError("更新清单不包含当前平台安装包")


async def fetch_manifest(
    base_url: str,
    *,
    channel: str = "stable",
    timeout: float = 10.0,
    allow_insecure_http: bool = False,
    client: httpx.AsyncClient | None = None,
) -> UpdateManifest:
    """从更新服务器获取清单。"""
    url = build_manifest_url(
        base_url,
        channel,
        allow_insecure_http=allow_insecure_http,
    )
    if client is None:
        async with httpx.AsyncClient(timeout=timeout) as owned_client:
            response = await owned_client.get(url)
    else:
        response = await client.get(url)
    response.raise_for_status()
    return UpdateManifest.model_validate(response.json())
