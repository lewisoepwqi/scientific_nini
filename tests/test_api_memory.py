"""长期记忆 API 契约测试。

验证 memory 端点响应结构与 OpenAPI spec 一致。
"""

from __future__ import annotations

import httpx
import pytest


@pytest.mark.asyncio
async def test_memory_stats_response_shape(async_client: httpx.AsyncClient) -> None:
    """GET /api/memory/long-term/stats 应返回符合契约的响应结构。"""
    resp = await async_client.get("/api/memory/long-term/stats")
    assert resp.status_code == 200

    data = resp.json()
    assert isinstance(data, dict)

    # 必需字段
    assert "total_memories" in data, "缺少 total_memories"
    assert "type_distribution" in data, "缺少 type_distribution"
    assert "vector_store_available" in data, "缺少 vector_store_available"

    # 类型校验
    assert isinstance(data["total_memories"], int)
    assert isinstance(data["type_distribution"], dict)
    assert isinstance(data["vector_store_available"], bool)

    # type_distribution 的值应为整数
    for key, val in data["type_distribution"].items():
        assert isinstance(key, str), f"type_distribution key 应为字符串，实际: {type(key)}"
        assert isinstance(val, int), f"type_distribution['{key}'] 应为整数，实际: {type(val)}"


@pytest.mark.asyncio
async def test_memory_list_response_shape(async_client: httpx.AsyncClient) -> None:
    """GET /api/memory/long-term 应返回符合契约的响应结构。"""
    resp = await async_client.get("/api/memory/long-term")
    assert resp.status_code == 200

    data = resp.json()
    assert isinstance(data, dict)
    assert "memories" in data
    assert "total" in data
    assert isinstance(data["memories"], list)
    assert isinstance(data["total"], int)


@pytest.mark.asyncio
async def test_memory_list_entry_shape(async_client: httpx.AsyncClient) -> None:
    """GET /api/memory/long-term 返回的每条记忆应包含所有契约字段。"""
    resp = await async_client.get("/api/memory/long-term")
    data = resp.json()

    for entry in data["memories"]:
        # 必需字段
        required_fields = [
            "id",
            "memory_type",
            "content",
            "summary",
            "source_session_id",
            "importance_score",
            "tags",
            "created_at",
            "access_count",
        ]
        for field in required_fields:
            assert field in entry, f"记忆条目缺少字段: {field}"

        # 类型校验
        assert isinstance(entry["id"], str)
        assert isinstance(entry["memory_type"], str)
        assert isinstance(entry["content"], str)
        assert isinstance(entry["tags"], list)
        assert isinstance(entry["access_count"], int)

        # 可选字段（存在时类型应正确）
        if "source_dataset" in entry and entry["source_dataset"] is not None:
            assert isinstance(entry["source_dataset"], str)
        if "metadata" in entry and entry["metadata"] is not None:
            assert isinstance(entry["metadata"], dict)


@pytest.mark.asyncio
async def test_memory_stats_empty_store(async_client: httpx.AsyncClient) -> None:
    """空存储时 stats 应返回零值而非错误。"""
    resp = await async_client.get("/api/memory/long-term/stats")
    assert resp.status_code == 200

    data = resp.json()
    assert data["total_memories"] == 0
    assert data["type_distribution"] == {}
    assert isinstance(data["vector_store_available"], bool)


@pytest.mark.asyncio
async def test_memory_delete_nonexistent_returns_error(async_client: httpx.AsyncClient) -> None:
    """删除不存在的记忆应返回错误。"""
    resp = await async_client.delete("/api/memory/long-term/nonexistent-id")
    # 404 或 500 均可接受，但不应返回 200
    assert resp.status_code in (404, 500)
