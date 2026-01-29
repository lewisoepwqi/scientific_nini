"""
Tests for health check endpoints.
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(async_client: AsyncClient):
    """Test health check endpoint."""
    response = await async_client.get("/api/v1/health/")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["status"] == "healthy"


@pytest.mark.asyncio
async def test_ping(async_client: AsyncClient):
    """Test ping endpoint."""
    response = await async_client.get("/api/v1/health/ping")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"] == "pong"


@pytest.mark.asyncio
async def test_root(async_client: AsyncClient):
    """Test root endpoint."""
    response = await async_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    assert "version" in data
