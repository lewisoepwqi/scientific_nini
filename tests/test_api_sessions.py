"""会话 API 端点测试。"""

from __future__ import annotations

import httpx
import pytest


async def _create_session(async_client: httpx.AsyncClient) -> tuple[httpx.Response, str]:
    """创建测试会话并返回响应与会话 ID。"""
    response = await async_client.post("/api/sessions")
    session_id = response.json()["data"]["session_id"]
    return response, session_id


@pytest.mark.asyncio
async def test_async_client_fixture_can_create_app_and_send_requests(
    async_client: httpx.AsyncClient,
) -> None:
    """异步客户端 fixture 应可直接访问应用。"""
    response = await async_client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_create_session_returns_201(async_client: httpx.AsyncClient) -> None:
    """创建会话接口应返回 201 和会话元数据。"""
    response, session_id = await _create_session(async_client)
    payload = response.json()

    assert response.status_code == 201
    assert payload["success"] is True
    assert payload["data"]["session_id"] == session_id
    assert payload["data"]["message_count"] == 0


@pytest.mark.asyncio
async def test_list_sessions_returns_created_sessions(async_client: httpx.AsyncClient) -> None:
    """会话列表接口应包含新创建的会话。"""
    _, first_session_id = await _create_session(async_client)
    _, second_session_id = await _create_session(async_client)

    response = await async_client.get("/api/sessions")
    payload = response.json()
    session_ids = {item["id"] for item in payload["data"]}

    assert response.status_code == 200
    assert isinstance(payload["data"], list)
    assert {first_session_id, second_session_id}.issubset(session_ids)


@pytest.mark.asyncio
async def test_get_missing_session_returns_404(async_client: httpx.AsyncClient) -> None:
    """获取不存在的会话应返回 404。"""
    response = await async_client.get("/api/sessions/missing-session")

    assert response.status_code == 404
    assert response.json()["detail"] == "会话不存在"


@pytest.mark.asyncio
async def test_delete_session_removes_it_from_follow_up_requests(
    async_client: httpx.AsyncClient,
) -> None:
    """删除会话后应无法再次访问。"""
    _, session_id = await _create_session(async_client)

    delete_response = await async_client.delete(f"/api/sessions/{session_id}")
    fetch_response = await async_client.get(f"/api/sessions/{session_id}")

    assert delete_response.status_code == 200
    assert delete_response.json()["success"] is True
    assert fetch_response.status_code == 404
