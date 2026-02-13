"""模型配置管理回归测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from nini.config import settings
from nini.config_manager import get_effective_config, save_model_config
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
