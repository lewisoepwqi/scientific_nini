"""文件上传与下载 API 测试。"""

from __future__ import annotations

import httpx
import pytest

from nini.config import settings


async def _create_session(async_client: httpx.AsyncClient) -> str:
    """通过 API 创建测试会话。"""
    response = await async_client.post("/api/sessions")
    return response.json()["data"]["session_id"]


@pytest.mark.asyncio
async def test_upload_csv_file_returns_metadata(async_client: httpx.AsyncClient) -> None:
    """上传 CSV 后应返回数据集与工作区文件元数据。"""
    session_id = await _create_session(async_client)

    response = await async_client.post(
        "/api/upload",
        data={"session_id": session_id},
        files={"file": ("sample.csv", b"a,b\n1,2\n3,4\n", "text/csv")},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["dataset"]["session_id"] == session_id
    assert payload["dataset"]["file_type"] == "csv"
    assert payload["dataset"]["row_count"] == 2
    assert payload["dataset"]["column_count"] == 2
    assert payload["workspace_file"]["kind"] == "dataset"
    assert payload["workspace_file"]["meta"]["file_type"] == "csv"


@pytest.mark.asyncio
async def test_download_missing_workspace_file_returns_404(
    async_client: httpx.AsyncClient,
) -> None:
    """下载不存在的工作区文件应返回 404。"""
    session_id = await _create_session(async_client)

    response = await async_client.get(f"/api/workspace/{session_id}/download/missing.csv")

    assert response.status_code == 404
    assert "文件不存在" in response.json()["detail"]


@pytest.mark.asyncio
async def test_upload_oversized_file_returns_413(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """超出上传上限的文件应被拒绝。"""
    monkeypatch.setattr(settings, "max_upload_size", 8)
    session_id = await _create_session(async_client)

    response = await async_client.post(
        "/api/upload",
        data={"session_id": session_id},
        files={"file": ("large.csv", b"col\n123456789\n", "text/csv")},
    )

    assert response.status_code == 413
    assert "文件过大" in response.json()["detail"]
