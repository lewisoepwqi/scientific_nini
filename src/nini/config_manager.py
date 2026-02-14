"""模型配置管理器。

负责将用户通过 Web 界面保存的模型配置持久化到数据库，
并在启动时合并 DB 配置与 .env 环境变量配置。

优先级：DB 用户配置 > .env 环境变量 > 默认值。
"""

from __future__ import annotations

import logging
from typing import Any

from nini.config import settings
from nini.models.database import get_db
from nini.utils.crypto import decrypt_api_key, encrypt_api_key, mask_api_key

logger = logging.getLogger(__name__)

# 支持的 provider 列表
VALID_PROVIDERS = {
    "openai",
    "anthropic",
    "moonshot",
    "kimi_coding",
    "zhipu",
    "deepseek",
    "dashscope",
    "ollama",
}


async def save_model_config(
    provider: str,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    is_active: bool = True,
) -> dict[str, Any]:
    """保存模型配置到数据库。

    Args:
        provider: 模型提供商 ID
        api_key: 明文 API Key（将加密存储）
        model: 模型名称
        base_url: 自定义 API 端点
        is_active: 是否启用

    Returns:
        保存后的配置信息（脱敏）
    """
    if provider not in VALID_PROVIDERS:
        raise ValueError(f"不支持的模型提供商: {provider}")

    # 统一规范：None / 空字符串 / 全空白均视为“未提供新 Key”
    normalized_api_key = api_key.strip() if isinstance(api_key, str) else None
    if normalized_api_key == "":
        normalized_api_key = None
    has_new_key = normalized_api_key is not None

    encrypted_key = encrypt_api_key(normalized_api_key) if normalized_api_key is not None else None
    key_hint = mask_api_key(normalized_api_key) if normalized_api_key is not None else ""

    db = await get_db()
    try:
        # 先查询是否已存在该 provider 的记录
        cursor = await db.execute(
            "SELECT id, encrypted_api_key, api_key_hint FROM model_configs WHERE provider = ?",
            (provider,),
        )
        existing = await cursor.fetchone()

        if existing:
            # 更新：如果未提供新 Key 则保留旧值
            final_encrypted_key = encrypted_key if has_new_key else existing[1]
            final_key_hint = key_hint if has_new_key else (existing[2] or "")
            await db.execute(
                """
                UPDATE model_configs
                SET model = ?, encrypted_api_key = ?, api_key_hint = ?,
                    base_url = ?, is_active = ?, updated_at = datetime('now')
                WHERE provider = ?
                """,
                (
                    model or "",
                    final_encrypted_key,
                    final_key_hint,
                    base_url,
                    int(is_active),
                    provider,
                ),
            )
        else:
            # 插入新记录
            final_key_hint = key_hint
            await db.execute(
                """
                INSERT INTO model_configs (provider, model, encrypted_api_key, api_key_hint, base_url, is_active, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    provider,
                    model or "",
                    encrypted_key,
                    key_hint,
                    base_url,
                    int(is_active),
                ),
            )
        await db.commit()
        logger.info("已保存模型配置: provider=%s, model=%s", provider, model)

        return {
            "provider": provider,
            "model": model or "",
            "api_key_hint": final_key_hint,
            "base_url": base_url,
            "is_active": is_active,
        }
    finally:
        await db.close()


async def load_all_model_configs() -> dict[str, dict[str, Any]]:
    """从数据库加载所有模型配置。

    Returns:
        以 provider 为键的配置字典，值包含解密后的 api_key、model、base_url 等
    """
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT provider, model, encrypted_api_key, api_key_hint, base_url, is_active "
            "FROM model_configs WHERE is_active = 1"
        )
        rows = await cursor.fetchall()

        configs: dict[str, dict[str, Any]] = {}
        for row in rows:
            provider = row[0]
            encrypted_key = row[2]
            api_key = decrypt_api_key(encrypted_key) if encrypted_key else None

            configs[provider] = {
                "provider": provider,
                "model": row[1],
                "api_key": api_key,
                "api_key_hint": row[3] or "",
                "base_url": row[4],
                "is_active": bool(row[5]),
            }
        return configs
    finally:
        await db.close()


async def get_effective_config(provider: str) -> dict[str, Any]:
    """获取指定 provider 的有效配置（DB 优先，.env 兜底）。

    Args:
        provider: 模型提供商 ID

    Returns:
        包含 api_key、model、base_url 的配置字典
    """
    # 从 DB 加载
    db_configs = await load_all_model_configs()
    db_cfg = db_configs.get(provider, {})

    # .env 配置映射
    env_map: dict[str, dict[str, str | None]] = {
        "openai": {
            "api_key": settings.openai_api_key,
            "model": settings.openai_model,
            "base_url": settings.openai_base_url,
        },
        "anthropic": {
            "api_key": settings.anthropic_api_key,
            "model": settings.anthropic_model,
            "base_url": None,
        },
        "moonshot": {
            "api_key": settings.moonshot_api_key,
            "model": settings.moonshot_model,
            "base_url": None,
        },
        "kimi_coding": {
            "api_key": settings.kimi_coding_api_key,
            "model": settings.kimi_coding_model,
            "base_url": settings.kimi_coding_base_url,
        },
        "zhipu": {
            "api_key": settings.zhipu_api_key,
            "model": settings.zhipu_model,
            "base_url": settings.zhipu_base_url,
        },
        "deepseek": {
            "api_key": settings.deepseek_api_key,
            "model": settings.deepseek_model,
            "base_url": None,
        },
        "dashscope": {
            "api_key": settings.dashscope_api_key,
            "model": settings.dashscope_model,
            "base_url": None,
        },
        "ollama": {
            "api_key": None,
            "model": settings.ollama_model,
            "base_url": settings.ollama_base_url,
        },
    }

    env_cfg = env_map.get(provider, {})

    # DB 优先，.env 兜底
    return {
        "api_key": db_cfg.get("api_key") or env_cfg.get("api_key"),
        "model": db_cfg.get("model") or env_cfg.get("model") or "",
        "base_url": db_cfg.get("base_url") or env_cfg.get("base_url"),
    }


async def get_all_effective_configs() -> dict[str, dict[str, Any]]:
    """获取所有 provider 的有效配置。"""
    result: dict[str, dict[str, Any]] = {}
    for provider in VALID_PROVIDERS:
        result[provider] = await get_effective_config(provider)
    return result


async def get_default_provider() -> str | None:
    """获取用户设置的默认模型提供商。

    Returns:
        默认提供商 ID，如果未设置则返回 None
    """
    db = await get_db()
    try:
        cursor = await db.execute("SELECT value FROM app_settings WHERE key = 'default_provider'")
        row = await cursor.fetchone()
        if row and row[0]:
            provider_id = row[0] if isinstance(row[0], str) else None
            if provider_id in VALID_PROVIDERS:
                return provider_id
        return None
    finally:
        await db.close()


async def set_default_provider(provider_id: str | None) -> bool:
    """设置默认模型提供商。

    Args:
        provider_id: 提供商 ID，None 表示清除默认设置

    Returns:
        是否设置成功
    """
    db = await get_db()
    try:
        if provider_id is None:
            # 清除默认设置
            await db.execute("DELETE FROM app_settings WHERE key = 'default_provider'")
            await db.commit()
            logger.info("已清除默认模型提供商设置")
            return True

        if provider_id not in VALID_PROVIDERS:
            logger.warning("尝试设置无效的默认提供商: %s", provider_id)
            return False

        # 保存到 app_settings
        await db.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES ('default_provider', ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = excluded.updated_at
            """,
            (provider_id,),
        )
        await db.commit()
        logger.info("默认模型提供商已设置为: %s", provider_id)
        return True
    except Exception as e:
        logger.error("设置默认提供商失败: %s", e)
        return False
    finally:
        await db.close()
