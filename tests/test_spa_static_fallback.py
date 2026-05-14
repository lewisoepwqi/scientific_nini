"""前端静态资源与 SPA 回退测试。"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from nini import app as app_module


def _write_web_dist(path: Path, script_name: str = "app.js") -> None:
    """写入最小前端构建产物。"""
    (path / "assets").mkdir(parents=True, exist_ok=True)
    (path / "index.html").write_text(
        '<!doctype html><div id="root"></div>'
        f'<script type="module" src="/assets/{script_name}"></script>',
        encoding="utf-8",
    )
    (path / "assets" / script_name).write_text("console.log('ok')", encoding="utf-8")


@pytest.mark.asyncio
async def test_spa_fallback_keeps_missing_static_asset_404(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """缺失静态资源不应回退为 HTML。"""
    web_dist = tmp_path / "dist"
    _write_web_dist(web_dist)
    monkeypatch.setattr(app_module, "_WEB_DIST", web_dist)
    monkeypatch.setattr(app_module.settings, "api_key", "")

    app = app_module.create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/assets/missing.js", headers={"accept": "*/*"})

    assert response.status_code == 404
    assert "text/html" not in response.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_spa_fallback_still_serves_client_route(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """客户端路由刷新时仍应返回 SPA 入口页。"""
    web_dist = tmp_path / "dist"
    _write_web_dist(web_dist)
    monkeypatch.setattr(app_module, "_WEB_DIST", web_dist)
    monkeypatch.setattr(app_module.settings, "api_key", "")

    app = app_module.create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/sessions/demo", headers={"accept": "text/html"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "/assets/app.js" in response.text


@pytest.mark.asyncio
async def test_spa_fallback_reads_latest_index_html(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """后端运行期间重建前端后，应返回最新入口页。"""
    web_dist = tmp_path / "dist"
    _write_web_dist(web_dist, "old.js")
    monkeypatch.setattr(app_module, "_WEB_DIST", web_dist)
    monkeypatch.setattr(app_module.settings, "api_key", "")

    app = app_module.create_app()
    _write_web_dist(web_dist, "new.js")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/sessions/demo", headers={"accept": "text/html"})

    assert response.status_code == 200
    assert "/assets/new.js" in response.text
    assert "/assets/old.js" not in response.text
