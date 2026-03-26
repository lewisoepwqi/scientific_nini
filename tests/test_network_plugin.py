"""NetworkPlugin 测试：可用性检测（mock 网络）、降级信息生成、配置读取。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nini.plugins.network import NetworkPlugin

# ---- 可用性检测测试 ----


@pytest.mark.asyncio
async def test_network_available_when_probe_succeeds() -> None:
    """网络连通时 is_available() 返回 True。"""
    plugin = NetworkPlugin()

    # Mock httpx.AsyncClient，通用探测和 Semantic Scholar 探测都返回 200
    mock_probe_response = MagicMock()
    mock_probe_response.status_code = 200
    mock_semantic_response = MagicMock()
    mock_semantic_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.head = AsyncMock(return_value=mock_probe_response)
    mock_client.get = AsyncMock(return_value=mock_semantic_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("nini.plugins.network.httpx") as mock_httpx:
        mock_httpx.AsyncClient.return_value = mock_client
        result = await plugin.is_available()

    assert result is True


@pytest.mark.asyncio
async def test_network_unavailable_when_connection_error() -> None:
    """网络连接失败时 is_available() 返回 False。"""
    import httpx

    plugin = NetworkPlugin()

    mock_client = AsyncMock()
    mock_client.head = AsyncMock(side_effect=httpx.ConnectError("连接失败"))
    mock_client.get = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("nini.plugins.network.httpx") as mock_httpx:
        mock_httpx.AsyncClient.return_value = mock_client
        mock_httpx.ConnectError = httpx.ConnectError
        result = await plugin.is_available()

    assert result is False


@pytest.mark.asyncio
async def test_network_unavailable_when_httpx_not_installed() -> None:
    """httpx 未安装时 is_available() 返回 False 而不是抛出异常。"""
    import nini.plugins.network as net_module

    plugin = NetworkPlugin()

    with patch.object(net_module, "_HTTPX_AVAILABLE", False):
        result = await plugin.is_available()

    assert result is False


@pytest.mark.asyncio
async def test_network_unavailable_when_server_error() -> None:
    """服务端 5xx 响应时 is_available() 返回 False。"""
    plugin = NetworkPlugin()

    mock_probe_response = MagicMock()
    mock_probe_response.status_code = 503

    mock_client = AsyncMock()
    mock_client.head = AsyncMock(return_value=mock_probe_response)
    mock_client.get = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("nini.plugins.network.httpx") as mock_httpx:
        mock_httpx.AsyncClient.return_value = mock_client
        result = await plugin.is_available()

    assert result is False


# ---- 初始化测试 ----


@pytest.mark.asyncio
async def test_initialize_creates_http_client() -> None:
    """initialize() 成功后 _client 不为 None。"""
    plugin = NetworkPlugin()

    mock_client_instance = AsyncMock()

    with patch("nini.plugins.network.httpx") as mock_httpx:
        mock_httpx.AsyncClient.return_value = mock_client_instance
        await plugin.initialize()

    assert plugin._client is mock_client_instance


@pytest.mark.asyncio
async def test_initialize_skips_gracefully_when_httpx_missing() -> None:
    """httpx 未安装时 initialize() 不抛出异常。"""
    import nini.plugins.network as net_module

    plugin = NetworkPlugin()

    with patch.object(net_module, "_HTTPX_AVAILABLE", False):
        await plugin.initialize()  # 不应抛出


# ---- shutdown 测试 ----


@pytest.mark.asyncio
async def test_shutdown_closes_http_client() -> None:
    """shutdown() 调用 client.aclose() 并将 _client 置 None。"""
    import httpx

    plugin = NetworkPlugin()
    # 使用真实的 httpx.AsyncClient spec，确保 isinstance 检测通过
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    plugin._client = mock_client

    await plugin.shutdown()

    mock_client.aclose.assert_called_once()
    assert plugin._client is None


@pytest.mark.asyncio
async def test_shutdown_noop_when_no_client() -> None:
    """未初始化时调用 shutdown() 不报错。"""
    plugin = NetworkPlugin()
    await plugin.shutdown()  # 不应抛出


# ---- 降级信息测试 ----


def test_get_degradation_info_structure() -> None:
    """get_degradation_info() 返回包含完整字段的 DegradationInfo。"""
    plugin = NetworkPlugin()
    info = plugin.get_degradation_info()

    assert info is not None
    assert info.plugin_name == "network"
    assert "网络" in info.reason
    assert info.impact != ""
    assert len(info.alternatives) > 0


def test_get_degradation_info_includes_offline_alternatives() -> None:
    """降级信息的 alternatives 包含离线替代建议。"""
    plugin = NetworkPlugin()
    info = plugin.get_degradation_info()

    assert info is not None
    # 至少有一条建议提到手动上传或粘贴
    has_offline_option = any(
        "上传" in alt or "粘贴" in alt or "手动" in alt for alt in info.alternatives
    )
    assert has_offline_option, f"缺少离线替代建议，当前 alternatives: {info.alternatives}"


# ---- 配置读取测试 ----


@pytest.mark.asyncio
async def test_network_uses_configured_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """NetworkPlugin 使用 settings.network_timeout 配置值。"""
    from nini import config as cfg_module

    # 临时修改配置
    monkeypatch.setattr(cfg_module.settings, "network_timeout", 3)

    plugin = NetworkPlugin()
    mock_probe_response = MagicMock()
    mock_probe_response.status_code = 200
    mock_semantic_response = MagicMock()
    mock_semantic_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.head = AsyncMock(return_value=mock_probe_response)
    mock_client.get = AsyncMock(return_value=mock_semantic_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("nini.plugins.network.httpx") as mock_httpx:
        mock_httpx.AsyncClient.return_value = mock_client
        await plugin.is_available()
        # 验证 AsyncClient 使用了 timeout=3
        _, kwargs = mock_httpx.AsyncClient.call_args
        assert kwargs.get("timeout") == 3


@pytest.mark.asyncio
async def test_network_uses_configured_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    """NetworkPlugin 在设置代理时将代理传给 httpx.AsyncClient。"""
    from nini import config as cfg_module

    monkeypatch.setattr(cfg_module.settings, "network_proxy", "http://proxy.example.com:8080")

    plugin = NetworkPlugin()
    mock_probe_response = MagicMock()
    mock_probe_response.status_code = 200
    mock_semantic_response = MagicMock()
    mock_semantic_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.head = AsyncMock(return_value=mock_probe_response)
    mock_client.get = AsyncMock(return_value=mock_semantic_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("nini.plugins.network.httpx") as mock_httpx:
        mock_httpx.AsyncClient.return_value = mock_client
        await plugin.is_available()
        _, kwargs = mock_httpx.AsyncClient.call_args
        proxies = kwargs.get("proxies")
        assert proxies is not None
        assert "http://proxy.example.com:8080" in proxies.values()


@pytest.mark.asyncio
async def test_network_unavailable_when_semantic_scholar_probe_fails() -> None:
    """Semantic Scholar 端点不可达时 is_available() 返回 False。"""
    plugin = NetworkPlugin()

    mock_probe_response = MagicMock()
    mock_probe_response.status_code = 200
    mock_semantic_response = MagicMock()
    mock_semantic_response.status_code = 503

    mock_client = AsyncMock()
    mock_client.head = AsyncMock(return_value=mock_probe_response)
    mock_client.get = AsyncMock(return_value=mock_semantic_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("nini.plugins.network.httpx") as mock_httpx:
        mock_httpx.AsyncClient.return_value = mock_client
        result = await plugin.is_available()

    assert result is False
