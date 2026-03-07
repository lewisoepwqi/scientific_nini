"""模型配置管理回归测试。"""

from __future__ import annotations

from pathlib import Path
import asyncio

import pytest

from nini.app import create_app
from nini.config import settings
from nini.config_manager import (
    get_builtin_usage,
    get_effective_config,
    get_model_priorities,
    get_model_purpose_routes,
    increment_builtin_usage,
    get_purpose_provider_routes,
    save_model_config,
    set_model_priorities,
    set_model_purpose_routes,
    set_purpose_provider_routes,
)
from nini.models.database import init_db
from tests.client_utils import LocalASGIClient


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


@pytest.mark.asyncio
async def test_get_effective_config_supports_minimax_provider() -> None:
    """应支持读取 MiniMax 的有效配置。"""
    await init_db()

    await save_model_config(
        provider="minimax",
        api_key="sk-minimax-test-12345678",
        model="MiniMax-M2.5",
        base_url="https://api.minimax.chat/v1",
    )
    cfg = await get_effective_config("minimax")

    assert cfg["api_key"] == "sk-minimax-test-12345678"
    assert cfg["model"] == "MiniMax-M2.5"
    assert cfg["base_url"] == "https://api.minimax.chat/v1"


@pytest.mark.asyncio
async def test_increment_builtin_usage_is_atomic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """并发递增时不应丢失计数。"""
    usage_file = tmp_path / "builtin_usage.json"
    monkeypatch.setattr("nini.config_manager._get_system_usage_path", lambda: usage_file)
    await init_db()

    await asyncio.gather(*(increment_builtin_usage("fast") for _ in range(20)))

    usage = await get_builtin_usage()
    assert usage["fast"] == 20


def _configure_ollama_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    explicit_env_fields: set[str],
) -> None:
    """配置测试环境中的 Ollama 设置。"""
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "ollama_base_url", "http://localhost:11434")
    monkeypatch.setattr(settings, "ollama_model", "qwen2.5:7b")
    monkeypatch.setattr(
        "nini.api.models_routes._is_settings_field_explicit",
        lambda field: field in explicit_env_fields,
    )


def _get_ollama_entry(client: LocalASGIClient) -> dict[str, object]:
    """请求 `/api/models` 并返回 Ollama 条目。"""
    response = client.get("/api/models")
    assert response.status_code == 200
    payload = response.json()
    return next(item for item in payload["data"] if item["id"] == "ollama")


@pytest.mark.parametrize(
    ("explicit_env_fields", "expected_configured", "expected_source"),
    [
        (
            {"ollama_base_url", "ollama_model"},
            True,
            "env",
        ),
        (
            set(),
            False,
            "none",
        ),
    ],
    ids=[
        "env-explicit-configured",
        "defaults-only-not-configured",
    ],
)
def test_list_models_ollama_env_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    explicit_env_fields: set[str],
    expected_configured: bool,
    expected_source: str,
) -> None:
    """Ollama 的 env/default 配置状态应符合预期。"""
    _configure_ollama_settings(
        tmp_path,
        monkeypatch,
        explicit_env_fields=explicit_env_fields,
    )

    app = create_app()
    client = LocalASGIClient(app)
    try:
        ollama = _get_ollama_entry(client)
    finally:
        client.close()

    assert ollama["configured"] is expected_configured
    assert ollama["config_source"] == expected_source


@pytest.mark.parametrize(
    ("explicit_env_fields", "expected_configured", "expected_source"),
    [
        (
            set(),
            False,
            "none",
        ),
        (
            {"ollama_base_url", "ollama_model"},
            True,
            "env",
        ),
    ],
    ids=[
        "delete-db-falls-back-to-none",
        "delete-db-falls-back-to-env",
    ],
)
def test_list_models_ollama_status_after_delete_db_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    explicit_env_fields: set[str],
    expected_configured: bool,
    expected_source: str,
) -> None:
    """删除 Ollama DB 配置后，应按 env 显式性回退状态。"""
    _configure_ollama_settings(
        tmp_path,
        monkeypatch,
        explicit_env_fields=explicit_env_fields,
    )
    asyncio.run(init_db())

    app = create_app()
    client = LocalASGIClient(app)
    try:
        save_response = client.post(
            "/api/models/config",
            json={
                "provider_id": "ollama",
                "model": "llama3.1:8b",
                "base_url": "http://127.0.0.1:11434",
                "is_active": True,
            },
        )
        assert save_response.status_code == 200
        assert save_response.json()["success"] is True

        configured_ollama = _get_ollama_entry(client)
        assert configured_ollama["configured"] is True
        assert configured_ollama["config_source"] == "db"

        delete_response = client.delete("/api/models/ollama/config")
        assert delete_response.status_code == 200
        assert delete_response.json()["success"] is True

        final_ollama = _get_ollama_entry(client)
    finally:
        client.close()

    assert final_ollama["configured"] is expected_configured
    assert final_ollama["config_source"] == expected_source
