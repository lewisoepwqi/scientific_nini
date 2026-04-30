"""应用内更新 API 测试。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from nini.update.models import UpdateCheckResult, UpdateDownloadState, UpdateStatus


class _FakeUpdateService:
    def __init__(self) -> None:
        self.download_state = UpdateDownloadState()

    async def check_update(self) -> UpdateCheckResult:
        return UpdateCheckResult(
            current_version="0.1.1",
            latest_version="0.1.2",
            update_available=True,
            status="available",
            notes=["更新"],
            asset_size=10,
        )

    async def download_update(self) -> UpdateDownloadState:
        return self.download_state

    def status(self) -> UpdateStatus:
        return UpdateStatus(
            check=UpdateCheckResult(current_version="0.1.1", status="available"),
            download=self.download_state,
        )


@pytest.fixture
async def client(monkeypatch: pytest.MonkeyPatch):
    import httpx
    import nini.api.update_routes as update_routes
    from nini.app import create_app

    fake = _FakeUpdateService()
    monkeypatch.setattr(update_routes, "update_service", fake)
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client


def test_update_router_registered() -> None:
    from fastapi.routing import APIRoute
    from nini.app import create_app

    app: FastAPI = create_app()
    paths = {route.path for route in app.routes if isinstance(route, APIRoute)}
    assert "/api/update/check" in paths
    assert "/api/update/download" in paths
    assert "/api/update/status" in paths
    assert "/api/update/apply" in paths


@pytest.mark.asyncio
async def test_update_check_endpoint(client) -> None:
    response = await client.get("/api/update/check")
    payload = response.json()

    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["data"]["update_available"] is True


@pytest.mark.asyncio
async def test_update_download_failure_endpoint(client) -> None:
    response = await client.post("/api/update/download")
    payload = response.json()

    assert response.status_code == 200
    assert payload["success"] is False
    assert payload["data"]["status"] == "idle"


@pytest.mark.asyncio
async def test_update_apply_requires_ready_package(client) -> None:
    response = await client.post("/api/update/apply")

    assert response.status_code == 409
    assert "源码开发环境" in response.text


@pytest.mark.asyncio
async def test_update_apply_reports_signature_failure(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nini.api.update_routes as update_routes
    from nini.update.signature import SignatureVerificationError

    update_routes.update_service.download_state = UpdateDownloadState(
        status="ready",
        version="0.1.2",
        progress=100,
        installer_path="C:/tmp/setup.exe",
        verified=True,
    )

    def fake_prepare(_state):
        raise SignatureVerificationError("签名不可信")

    monkeypatch.setattr(update_routes, "prepare_apply_update", fake_prepare)
    response = await client.post("/api/update/apply")

    assert response.status_code == 409
    assert "签名不可信" in response.text


@pytest.mark.asyncio
async def test_update_apply_launches_updater_and_schedules_exit(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nini.api.update_routes as update_routes

    update_routes.update_service.download_state = UpdateDownloadState(
        status="ready",
        version="0.1.2",
        progress=100,
        installer_path="C:/tmp/setup.exe",
        verified=True,
    )
    events: list[str] = []

    monkeypatch.setattr(update_routes, "prepare_apply_update", lambda _state: object())
    monkeypatch.setattr(update_routes, "launch_updater", lambda _command: events.append("launch"))
    monkeypatch.setattr(
        update_routes,
        "schedule_current_process_exit",
        lambda: events.append("exit"),
    )

    response = await client.post("/api/update/apply")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "restarting"
    assert events == ["launch", "exit"]
