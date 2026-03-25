"""工具目录与执行错误 API 测试。"""

from __future__ import annotations

import httpx
import pytest


@pytest.mark.asyncio
async def test_list_tools_returns_tool_catalog(async_client: httpx.AsyncClient) -> None:
    """工具目录接口应返回可执行工具列表。"""
    response = await async_client.get("/api/tools")
    payload = response.json()
    tools = payload["data"]["tools"]

    assert response.status_code == 200
    assert payload["success"] is True
    assert tools
    assert all(item["type"] == "function" for item in tools)
    assert all("brief_description" in item for item in tools)


@pytest.mark.asyncio
async def test_capability_execute_error_response_uses_detail_field(
    async_client: httpx.AsyncClient,
) -> None:
    """执行入口报错时应返回标准 detail 字段。"""
    response = await async_client.post(
        "/api/capabilities/difference_analysis/execute",
        params={"session_id": "tool-error"},
        json={},
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "缺少必填参数: dataset_name"}
