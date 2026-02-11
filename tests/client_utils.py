"""测试客户端工具：无 TestClient 依赖的 HTTP/WebSocket 访问。"""

from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager, suppress
from typing import Any, Iterator

import httpx
from fastapi import WebSocketDisconnect

from nini.api.websocket import websocket_agent


class LocalASGIClient:
    """同步 HTTP 测试客户端（基于 httpx + ASGITransport）。"""

    def __init__(self, app: Any):
        self._app = app

    def __enter__(self) -> LocalASGIClient:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        return None

    def close(self) -> None:
        return None

    def request(self, method: str, url: str, **kwargs):
        async def _run():
            transport = httpx.ASGITransport(app=self._app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                response = await client.request(method, url, **kwargs)
                await response.aread()
                return response

        return asyncio.run(_run())

    def get(self, url: str, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs):
        return self.request("POST", url, **kwargs)

    def patch(self, url: str, **kwargs):
        return self.request("PATCH", url, **kwargs)

    def delete(self, url: str, **kwargs):
        return self.request("DELETE", url, **kwargs)


class _ClientState:
    def __init__(self) -> None:
        self.name = "CONNECTED"


class _InMemoryWebSocket:
    """最小 WebSocket 仿真实现，供 websocket_agent 使用。"""

    _CLOSE_SENTINEL = object()

    def __init__(self) -> None:
        self.client_state = _ClientState()
        self._incoming: asyncio.Queue[str | object] = asyncio.Queue()
        self._outgoing: asyncio.Queue[str] = asyncio.Queue()

    async def accept(self) -> None:
        self.client_state.name = "CONNECTED"

    async def receive_text(self) -> str:
        payload = await self._incoming.get()
        if payload is self._CLOSE_SENTINEL:
            self.client_state.name = "DISCONNECTED"
            raise WebSocketDisconnect()
        return str(payload)

    async def send_text(self, text: str) -> None:
        await self._outgoing.put(text)

    async def client_send_text(self, text: str) -> None:
        await self._incoming.put(text)

    async def client_receive_json(self, timeout: float) -> dict[str, Any]:
        raw = await asyncio.wait_for(self._outgoing.get(), timeout=timeout)
        return json.loads(raw)

    async def client_close(self) -> None:
        self.client_state.name = "DISCONNECTED"
        await self._incoming.put(self._CLOSE_SENTINEL)


class LocalWebSocketClient:
    """同步 WebSocket 测试会话（应用内内存通道）。"""

    def __init__(self, app: Any, *, receive_timeout: float = 15.0):
        self._app = app
        self._receive_timeout = receive_timeout
        self._loop = asyncio.new_event_loop()
        self._ws = _InMemoryWebSocket()
        self._lifespan_cm: Any = None
        self._task: asyncio.Task[Any] | None = None
        self._closed = False
        self._loop.run_until_complete(self._start())

    async def _start(self) -> None:
        self._lifespan_cm = self._app.router.lifespan_context(self._app)
        await self._lifespan_cm.__aenter__()
        self._task = self._loop.create_task(websocket_agent(self._ws))
        await asyncio.sleep(0)

    def send_text(self, text: str) -> None:
        self._loop.run_until_complete(self._ws.client_send_text(text))
        self._loop.run_until_complete(asyncio.sleep(0))

    def receive_json(self) -> dict[str, Any]:
        return self._loop.run_until_complete(
            self._ws.client_receive_json(timeout=self._receive_timeout)
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._loop.run_until_complete(self._ws.client_close())
        if self._task is not None:
            with suppress(asyncio.TimeoutError):
                self._loop.run_until_complete(asyncio.wait_for(self._task, timeout=2.0))
        if self._lifespan_cm is not None:
            self._loop.run_until_complete(self._lifespan_cm.__aexit__(None, None, None))
        self._loop.close()


@contextmanager
def live_websocket_connect(
    app: Any,
    path: str = "/ws",
    *,
    host: str = "127.0.0.1",
    port: int | None = None,
    receive_timeout: float = 15.0,
) -> Iterator[LocalWebSocketClient]:
    """建立内存态 WebSocket 会话。

    参数与旧版保持兼容（path/host/port 可传入但这里不使用网络端口）。
    """
    _ = (path, host, port)
    client = LocalWebSocketClient(app, receive_timeout=receive_timeout)
    try:
        yield client
    finally:
        client.close()
