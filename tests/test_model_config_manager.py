"""模型配置管理回归测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from nini.config import settings
from nini.config_manager import (
    get_effective_config,
    get_model_priorities,
    get_model_purpose_routes,
    get_purpose_provider_routes,
    save_model_config,
    set_model_priorities,
    set_model_purpose_routes,
    set_purpose_provider_routes,
)
from nini.models.database import init_db


@pytest.fixture(autouse=True)
def isolate_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """隔离测试数据目录，避免污染真实数据。"""
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")


@pytest.mark.asyncio
async def test_save_model_without_new_key_keeps_existing_api_key() -> None:
    """已有 key 时仅切换模型，不应覆盖原 key。"""
    await init_db()

    first = await save_model_config(
        provider="deepseek",
        api_key="sk-test-keep-12345678",
        model="deepseek-chat",
    )
    updated = await save_model_config(
        provider="deepseek",
        model="deepseek-reasoner",
    )
    cfg = await get_effective_config("deepseek")

    assert cfg["api_key"] == "sk-test-keep-12345678"
    assert cfg["model"] == "deepseek-reasoner"
    assert updated["api_key_hint"] == first["api_key_hint"]


@pytest.mark.asyncio
async def test_save_model_with_blank_key_does_not_override_existing_key() -> None:
    """传入空白 key 应视为未填写，保留原 key。"""
    await init_db()

    first = await save_model_config(
        provider="deepseek",
        api_key="sk-test-blank-87654321",
        model="deepseek-chat",
    )
    updated = await save_model_config(
        provider="deepseek",
        api_key="   \n\t  ",
        model="deepseek-reasoner",
    )
    cfg = await get_effective_config("deepseek")

    assert cfg["api_key"] == "sk-test-blank-87654321"
    assert cfg["model"] == "deepseek-reasoner"
    assert updated["api_key_hint"] == first["api_key_hint"]


@pytest.mark.asyncio
async def test_purpose_provider_routes_default_to_none() -> None:
    """用途路由未配置时应返回空映射（值为 None）。"""
    await init_db()

    routes = await get_purpose_provider_routes()

    assert routes == {
        "chat": None,
        "title_generation": None,
        "image_analysis": None,
    }


@pytest.mark.asyncio
async def test_set_purpose_provider_routes_merges_updates() -> None:
    """用途路由应支持增量更新并持久化。"""
    await init_db()

    first = await set_purpose_provider_routes(
        {
            "title_generation": "zhipu",
            "image_analysis": "openai",
        }
    )
    second = await set_purpose_provider_routes(
        {
            "title_generation": None,
        }
    )
    loaded = await get_purpose_provider_routes()

    assert first["title_generation"] == "zhipu"
    assert first["image_analysis"] == "openai"
    assert second["title_generation"] is None
    assert second["image_analysis"] == "openai"
    assert loaded["title_generation"] is None
    assert loaded["image_analysis"] == "openai"


@pytest.mark.asyncio
async def test_set_model_purpose_routes_supports_model_override() -> None:
    """用途路由应支持 provider+model 组合配置。"""
    await init_db()

    await set_model_purpose_routes(
        {
            "chat": {
                "provider_id": "zhipu",
                "model": "glm-5",
                "base_url": None,
            },
            "title_generation": {
                "provider_id": "zhipu",
                "model": "glm-4.7-flash",
                "base_url": None,
            },
        }
    )
    routes = await get_model_purpose_routes()

    assert routes["chat"]["provider_id"] == "zhipu"
    assert routes["chat"]["model"] == "glm-5"
    assert routes["title_generation"]["provider_id"] == "zhipu"
    assert routes["title_generation"]["model"] == "glm-4.7-flash"


@pytest.mark.asyncio
async def test_save_model_config_supports_priority() -> None:
    """保存模型配置时应支持优先级。"""
    await init_db()

    await save_model_config(
        provider="zhipu",
        model="glm-5",
        priority=1,
    )
    priorities = await get_model_priorities()

    assert priorities["zhipu"] == 1


@pytest.mark.asyncio
async def test_set_model_priorities_batch_update() -> None:
    """应支持批量更新提供商优先级。"""
    await init_db()

    await set_model_priorities(
        {
            "deepseek": 0,
            "openai": 6,
        }
    )
    priorities = await get_model_priorities()

    assert priorities["deepseek"] == 0
    assert priorities["openai"] == 6
