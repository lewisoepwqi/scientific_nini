"""模型配置管理回归测试。"""

from __future__ import annotations

from pathlib import Path
import asyncio

import pytest

from nini.app import create_app
from nini.config import settings
from nini.config_manager import (
    API_MODE_CODING_PLAN,
    API_MODE_STANDARD,
    get_builtin_usage,
    get_effective_config,
    get_model_priorities,
    get_model_purpose_routes,
    increment_builtin_usage,
    infer_api_mode_from_base_url,
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
    settings.ensure_dirs()


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
        "planning": None,
        "verification": None,
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
    assert first["planning"] is None
    assert first["verification"] is None
    assert second["title_generation"] is None
    assert second["image_analysis"] == "openai"
    assert second["planning"] is None
    assert second["verification"] is None
    assert loaded["title_generation"] is None
    assert loaded["image_analysis"] == "openai"
    assert loaded["planning"] is None
    assert loaded["verification"] is None


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
        api_mode=API_MODE_STANDARD,
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
@pytest.mark.parametrize(
    ("provider", "api_mode", "expected_base_url"),
    [
        (
            "zhipu",
            API_MODE_STANDARD,
            "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        ),
        (
            "zhipu",
            API_MODE_CODING_PLAN,
            "https://open.bigmodel.cn/api/coding/paas/v4",
        ),
        (
            "dashscope",
            API_MODE_STANDARD,
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ),
        (
            "dashscope",
            API_MODE_CODING_PLAN,
            "https://coding.dashscope.aliyuncs.com/v1",
        ),
    ],
)
async def test_save_model_config_sets_mode_default_base_url(
    provider: str,
    api_mode: str,
    expected_base_url: str,
) -> None:
    """双模式供应商保存时应写入模式对应的默认端点。"""
    await init_db()

    await save_model_config(
        provider=provider,
        api_key=f"sk-{provider}-test-12345678",
        model="test-model",
        api_mode=api_mode,
    )
    cfg = await get_effective_config(provider)

    assert cfg["api_mode"] == api_mode
    assert cfg["base_url"] == expected_base_url


@pytest.mark.asyncio
async def test_dashscope_coding_plan_uses_mode_default_model() -> None:
    """阿里 Coding Plan 在未显式指定模型时，应使用模式默认模型。"""
    await init_db()

    result = await save_model_config(
        provider="dashscope",
        api_key="sk-dashscope-test-12345678",
        api_mode=API_MODE_CODING_PLAN,
    )
    cfg = await get_effective_config("dashscope")

    assert result["model"] == "qwen3-coder-plus"
    assert cfg["model"] == "qwen3-coder-plus"


@pytest.mark.asyncio
async def test_dashscope_env_coding_plan_uses_mode_default_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`.env` 仅切换到 Coding Plan 端点时，应回退模式默认模型而非普通默认模型。"""
    await init_db()

    monkeypatch.setattr(settings, "dashscope_api_key", "sk-dashscope-env-12345678")
    monkeypatch.setattr(settings, "dashscope_base_url", "https://coding.dashscope.aliyuncs.com/v1")
    monkeypatch.setattr(settings, "dashscope_model", "qwen-plus")

    cfg = await get_effective_config("dashscope")

    assert cfg["api_mode"] == API_MODE_CODING_PLAN
    assert cfg["model"] == "qwen3-coder-plus"


@pytest.mark.asyncio
async def test_save_model_config_requires_api_mode_for_dual_mode_provider() -> None:
    """智谱和阿里在首次保存时必须显式选择模式。"""
    await init_db()

    with pytest.raises(ValueError, match="必须选择 API 模式"):
        await save_model_config(
            provider="zhipu",
            api_key="sk-zhipu-test-12345678",
            model="glm-4.5",
        )


@pytest.mark.asyncio
async def test_dual_mode_provider_must_delete_before_reconfigure() -> None:
    """双模式供应商保存后不允许原位修改。"""
    await init_db()

    await save_model_config(
        provider="dashscope",
        api_key="sk-dashscope-test-12345678",
        model="qwen-plus",
        api_mode=API_MODE_STANDARD,
    )

    with pytest.raises(ValueError, match="请先删除当前配置后重新配置"):
        await save_model_config(
            provider="dashscope",
            api_key="sk-dashscope-test-87654321",
            model="qwen-max",
            api_mode=API_MODE_CODING_PLAN,
        )


@pytest.mark.asyncio
async def test_priority_placeholder_does_not_block_first_dual_mode_config() -> None:
    """仅有优先级占位记录时，双模式供应商仍应允许首次配置。"""
    await init_db()
    await set_model_priorities({"dashscope": 2})

    result = await save_model_config(
        provider="dashscope",
        api_key="sk-dashscope-test-12345678",
        api_mode=API_MODE_CODING_PLAN,
    )
    cfg = await get_effective_config("dashscope")

    assert result["provider"] == "dashscope"
    assert cfg["api_key"] == "sk-dashscope-test-12345678"
    assert cfg["api_mode"] == API_MODE_CODING_PLAN
    assert cfg["model"] == "qwen3-coder-plus"


def test_infer_api_mode_from_base_url() -> None:
    """应能根据已知端点反推双模式供应商的模式。"""
    assert (
        infer_api_mode_from_base_url(
            "zhipu",
            "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        )
        == API_MODE_STANDARD
    )
    assert (
        infer_api_mode_from_base_url(
            "dashscope",
            "https://coding.dashscope.aliyuncs.com/v1",
        )
        == API_MODE_CODING_PLAN
    )
    assert (
        infer_api_mode_from_base_url(
            "dashscope",
            "https://example.com/custom",
        )
        is None
    )


@pytest.mark.asyncio
async def test_increment_builtin_usage_is_atomic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """并发递增时不应丢失计数。"""
    usage_file = tmp_path / "builtin_usage.json"
    monkeypatch.setattr("nini._config_usage._get_system_usage_path", lambda: usage_file)
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
    settings.ensure_dirs()
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


def test_list_models_returns_dual_mode_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`/api/models` 应返回双模式供应商的模式与锁定状态。"""
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()
    asyncio.run(init_db())

    app = create_app()
    client = LocalASGIClient(app)
    try:
        save_response = client.post(
            "/api/models/config",
            json={
                "provider_id": "zhipu",
                "api_key": "sk-zhipu-test-12345678",
                "model": "glm-4.5",
                "api_mode": "coding_plan",
                "is_active": True,
            },
        )
        assert save_response.status_code == 200
        assert save_response.json()["success"] is True

        response = client.get("/api/models")
        assert response.status_code == 200
        payload = response.json()
        zhipu = next(item for item in payload["data"] if item["id"] == "zhipu")
    finally:
        client.close()

    assert zhipu["api_mode"] == "coding_plan"
    assert zhipu["can_edit_in_place"] is False
    assert zhipu["can_delete_config"] is True
    assert zhipu["supported_api_modes"] == ["standard", "coding_plan"]


def test_list_models_dashscope_coding_plan_uses_mode_aware_available_models(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """阿里 Coding Plan 的可选模型不应混入普通模式静态列表。"""
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()
    asyncio.run(init_db())

    app = create_app()
    client = LocalASGIClient(app)
    try:
        save_response = client.post(
            "/api/models/config",
            json={
                "provider_id": "dashscope",
                "api_key": "sk-dashscope-test-12345678",
                "api_mode": "coding_plan",
                "is_active": True,
            },
        )
        assert save_response.status_code == 200
        assert save_response.json()["success"] is True

        response = client.get("/api/models")
        assert response.status_code == 200
        payload = response.json()
        dashscope = next(item for item in payload["data"] if item["id"] == "dashscope")
    finally:
        client.close()

    assert dashscope["api_mode"] == "coding_plan"
    assert "qwen3-coder-plus" in dashscope["available_models"]
    assert "qwen-plus" not in dashscope["available_models"]
    assert "qwen-turbo" not in dashscope["available_models"]
    assert "qwen-max" not in dashscope["available_models"]


def test_list_models_dashscope_env_coding_plan_uses_mode_default_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`/api/models` 在 env Coding Plan 场景下应展示模式默认模型。"""
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()
    monkeypatch.setattr(settings, "dashscope_api_key", "sk-dashscope-env-12345678")
    monkeypatch.setattr(settings, "dashscope_base_url", "https://coding.dashscope.aliyuncs.com/v1")
    monkeypatch.setattr(settings, "dashscope_model", "qwen-plus")
    asyncio.run(init_db())

    app = create_app()
    client = LocalASGIClient(app)
    try:
        response = client.get("/api/models")
        assert response.status_code == 200
        payload = response.json()
        dashscope = next(item for item in payload["data"] if item["id"] == "dashscope")
    finally:
        client.close()

    assert dashscope["configured"] is True
    assert dashscope["config_source"] == "env"
    assert dashscope["api_mode"] == "coding_plan"
    assert dashscope["current_model"] == "qwen3-coder-plus"


def test_dual_mode_provider_can_reconfigure_after_delete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """删除后应允许双模式供应商重新按另一种模式配置。"""
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()
    asyncio.run(init_db())

    app = create_app()
    client = LocalASGIClient(app)
    try:
        first = client.post(
            "/api/models/config",
            json={
                "provider_id": "dashscope",
                "api_key": "sk-dashscope-test-12345678",
                "model": "qwen-plus",
                "api_mode": "standard",
                "is_active": True,
            },
        )
        assert first.status_code == 200
        assert first.json()["success"] is True

        rejected = client.post(
            "/api/models/config",
            json={
                "provider_id": "dashscope",
                "api_key": "sk-dashscope-test-87654321",
                "model": "qwen-max",
                "api_mode": "coding_plan",
                "is_active": True,
            },
        )
        assert rejected.status_code == 200
        assert rejected.json()["success"] is False

        deleted = client.delete("/api/models/dashscope/config")
        assert deleted.status_code == 200
        assert deleted.json()["success"] is True

        recreated = client.post(
            "/api/models/config",
            json={
                "provider_id": "dashscope",
                "api_key": "sk-dashscope-test-87654321",
                "model": "qwen-max",
                "api_mode": "coding_plan",
                "is_active": True,
            },
        )
    finally:
        client.close()

    assert recreated.status_code == 200
    assert recreated.json()["success"] is True


def test_test_connection_with_inline_config_does_not_persist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """临时测试连接成功后，不应把供应商标记为已配置。"""
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()
    asyncio.run(init_db())

    async def _fake_test_connection(self, provider_id: str, **kwargs):  # type: ignore[no-untyped-def]
        return {
            "success": True,
            "provider": provider_id,
            "model": kwargs.get("model") or "qwen-plus",
            "message": "连接成功",
        }

    monkeypatch.setattr(
        "nini.agent.model_resolver.ModelResolver.test_connection",
        _fake_test_connection,
    )

    app = create_app()
    client = LocalASGIClient(app)
    try:
        response = client.post(
            "/api/models/dashscope/test",
            json={
                "provider_id": "dashscope",
                "api_key": "sk-dashscope-test-12345678",
                "api_mode": "coding_plan",
                "base_url": "https://coding.dashscope.aliyuncs.com/v1",
            },
        )
        assert response.status_code == 200
        assert response.json()["success"] is True

        models_response = client.get("/api/models")
        assert models_response.status_code == 200
        payload = models_response.json()
        dashscope = next(item for item in payload["data"] if item["id"] == "dashscope")
    finally:
        client.close()

    assert dashscope["configured"] is False
    assert dashscope["config_source"] == "none"
