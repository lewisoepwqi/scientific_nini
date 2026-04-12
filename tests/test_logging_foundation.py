"""日志基础设施回归测试。"""

from __future__ import annotations

from contextlib import suppress
import json
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import httpx
import pytest

from nini.agent.session import session_manager
from nini.app import create_app
from nini.config import settings
from nini.logging_config import setup_logging
from tests.client_utils import live_websocket_connect


def _prepare_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    log_level: str = "INFO",
) -> None:
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "api_key", "")
    monkeypatch.setattr(settings, "log_level", log_level)
    settings.ensure_dirs()
    session_manager._sessions.clear()


def _flush_managed_handlers() -> None:
    for handler in logging.getLogger().handlers:
        with suppress(Exception):
            handler.flush()


def _get_file_handler() -> TimedRotatingFileHandler:
    for handler in logging.getLogger().handlers:
        if isinstance(handler, TimedRotatingFileHandler):
            return handler
    raise AssertionError("未找到 TimedRotatingFileHandler")


def test_setup_logging_writes_file_and_supports_rotation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _prepare_runtime(tmp_path, monkeypatch)

    log_path = setup_logging(log_level="info")
    logger = logging.getLogger("nini.tests.logging_foundation")

    logger.info("日志写入验证")
    file_handler = _get_file_handler()
    file_handler.doRollover()
    logger.info("轮转后仍可写入")
    _flush_managed_handlers()

    assert log_path == settings.log_file_path
    assert log_path is not None
    assert log_path.exists()
    assert "轮转后仍可写入" in log_path.read_text(encoding="utf-8")
    rotated_files = list(log_path.parent.glob(f"{settings.log_file_name}.*"))
    assert rotated_files


def test_setup_logging_is_idempotent_and_compatible_with_stdlib_logger(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _prepare_runtime(tmp_path, monkeypatch)

    setup_logging(log_level="debug")
    setup_logging(log_level="debug")
    logger = logging.getLogger("nini.tests.stdlib_compat")
    logger.warning("stdlib logger 兼容性验证")
    _flush_managed_handlers()

    managed_handlers = [
        handler
        for handler in logging.getLogger().handlers
        if isinstance(handler, (logging.StreamHandler, TimedRotatingFileHandler))
    ]
    assert len(managed_handlers) >= 2
    assert "stdlib logger 兼容性验证" in settings.log_file_path.read_text(encoding="utf-8")


def test_setup_logging_quiets_httpx_request_logs_outside_debug(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _prepare_runtime(tmp_path, monkeypatch, log_level="INFO")

    setup_logging(log_level="info")

    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING


def test_setup_logging_normalizes_uvicorn_error_logger_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _prepare_runtime(tmp_path, monkeypatch, log_level="INFO")

    setup_logging(log_level="info")
    logging.getLogger("uvicorn.error").info("uvicorn logger 名称归一化验证")
    _flush_managed_handlers()

    log_text = settings.log_file_path.read_text(encoding="utf-8")
    assert "INFO uvicorn " in log_text
    assert "INFO uvicorn.error " not in log_text


@pytest.mark.asyncio
async def test_http_logs_bind_request_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _prepare_runtime(tmp_path, monkeypatch, log_level="DEBUG")
    caplog.set_level(logging.INFO)

    app = create_app()
    transport = httpx.ASGITransport(app=app)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.get("/api/health", headers={"X-Request-ID": "req-http-123"})

    assert response.headers["X-Request-ID"] == "req-http-123"
    request_logs = [record for record in caplog.records if "HTTP 请求" in record.message]
    assert request_logs
    assert all(getattr(record, "request_id", "-") == "req-http-123" for record in request_logs)


def test_websocket_logs_bind_connection_id_and_session_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _prepare_runtime(tmp_path, monkeypatch, log_level="DEBUG")
    caplog.set_level(logging.INFO)

    app = create_app()
    requested_session_id = "session-log-test"

    with live_websocket_connect(app, "/ws", receive_timeout=2.0) as ws:
        ws.send_text(json.dumps({"type": "stop", "session_id": requested_session_id}))
        ws.receive_json()

    connected_log = next(
        record for record in caplog.records if record.message == "WebSocket 连接已建立"
    )
    stop_logs = [
        record for record in caplog.records if record.message == "处理 WebSocket 消息: type=stop"
    ]

    assert getattr(connected_log, "connection_id", "-") != "-"
    assert stop_logs
    assert any(getattr(record, "session_id", "-") == requested_session_id for record in stop_logs)
    assert all(
        getattr(record, "connection_id", "-") == getattr(connected_log, "connection_id", "-")
        for record in stop_logs
    )
