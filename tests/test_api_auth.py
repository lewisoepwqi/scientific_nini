"""API Key 鉴权链路测试。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from nini.app import create_app
from nini.api.auth_utils import (
    AUTH_SESSION_COOKIE_NAME,
    build_auth_session_cookie_value,
    is_websocket_authenticated,
)
from nini.api.websocket import websocket_agent
from nini.agent.session import session_manager
from nini.config import settings
from tests.client_utils import LocalASGIClient


@pytest.fixture(autouse=True)
def isolate_auth_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()
    session_manager._sessions.clear()
    yield
    session_manager._sessions.clear()


def test_api_key_middleware_only_protects_api_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "api_key", "test-key")
    app = create_app()

    with LocalASGIClient(app) as client:
        root_resp = client.get("/")
        assert root_resp.status_code == 200

        status_resp = client.get("/api/auth/status")
        assert status_resp.status_code == 200
        assert status_resp.json()["api_key_required"] is True
        assert status_resp.json()["authenticated"] is False

        health_resp = client.get("/api/health")
        assert health_resp.status_code == 200

        unauthorized_resp = client.get("/api/sessions")
        assert unauthorized_resp.status_code == 401

        bearer_resp = client.get(
            "/api/sessions",
            headers={"Authorization": "Bearer test-key"},
        )
        assert bearer_resp.status_code == 200

        header_resp = client.get(
            "/api/sessions",
            headers={"X-API-Key": "test-key"},
        )
        assert header_resp.status_code == 200

        query_resp = client.get("/api/sessions?token=test-key")
        assert query_resp.status_code == 401


def test_auth_session_cookie_can_authenticate_subsequent_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "api_key", "test-key")
    app = create_app()

    with LocalASGIClient(app) as client:
        session_resp = client.post(
            "/api/auth/session",
            headers={"Authorization": "Bearer test-key"},
        )
        assert session_resp.status_code == 200
        cookie_header = session_resp.headers.get("set-cookie", "")
        assert AUTH_SESSION_COOKIE_NAME in cookie_header

        authed_resp = client.get(
            "/api/sessions",
            cookies={AUTH_SESSION_COOKIE_NAME: build_auth_session_cookie_value("test-key")},
        )
        assert authed_resp.status_code == 200


class _UnauthorizedWebSocket:
    """用于验证鉴权拒绝行为的最小 WebSocket 仿真。"""

    def __init__(
        self, *, headers: dict[str, str] | None = None, cookies: dict[str, str] | None = None
    ) -> None:
        self.headers = headers or {}
        self.cookies = cookies or {}
        self.closed: tuple[int, str] | None = None

    async def close(self, code: int, reason: str = "") -> None:
        self.closed = (code, reason)

    async def accept(self) -> None:
        raise AssertionError("未授权连接不应进入 accept")


def test_websocket_rejects_missing_auth_when_api_key_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "api_key", "test-key")
    ws = _UnauthorizedWebSocket()

    asyncio.run(websocket_agent(ws))

    assert ws.closed == (4401, "未授权：需要有效的 API Key")


def test_websocket_cookie_session_is_treated_as_authenticated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "api_key", "test-key")
    ws = _UnauthorizedWebSocket(
        cookies={AUTH_SESSION_COOKIE_NAME: build_auth_session_cookie_value("test-key")}
    )
    assert is_websocket_authenticated(ws, settings.api_key) is True
