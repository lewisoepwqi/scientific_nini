"""测试初始化。"""

from __future__ import annotations

from collections.abc import AsyncIterator
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import httpx
import pytest
import pytest_asyncio

from nini.agent.prompts.builder import clear_prompt_cache
from nini.agent.session import session_manager
from nini.app import create_app
from nini.config import settings

# Python 3.12 下在部分测试组合中会出现偶发的 asyncio 事件循环析构告警，
# 不影响功能正确性，统一在测试入口忽略该类噪声。
warnings.filterwarnings(
    "ignore",
    category=ResourceWarning,
    message=r"unclosed event loop .*",
)


@pytest.fixture(autouse=True)
def _clear_prompt_cache() -> None:
    """每个测试前清空提示词 TTL 缓存，防止跨测试污染。"""
    clear_prompt_cache()


@pytest_asyncio.fixture
async def async_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[httpx.AsyncClient]:
    """提供带隔离数据目录的异步 HTTP 客户端。"""
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "api_key", "")
    settings.ensure_dirs()
    session_manager._sessions.clear()

    app = create_app()
    transport = httpx.ASGITransport(app=app)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            yield client

    session_manager._sessions.clear()
