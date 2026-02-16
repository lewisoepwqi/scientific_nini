"""模型配置管理器。

负责将用户通过 Web 界面保存的模型配置持久化到数据库，
并在启动时合并 DB 配置与 .env 环境变量配置。

优先级：DB 用户配置 > .env 环境变量 > 默认值。
"""

from __future__ import annotations

import json
import logging
from typing import Any, TypedDict

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

# 默认提供商优先级（数值越小优先级越高）
PROVIDER_PRIORITY_ORDER: tuple[str, ...] = (
    "openai",
    "anthropic",
    "moonshot",
    "kimi_coding",
    "zhipu",
    "deepseek",
    "dashscope",
    "ollama",
)

# 支持的模型用途
MODEL_PURPOSES: tuple[str, ...] = ("chat", "title_generation", "image_analysis")
VALID_MODEL_PURPOSES = set(MODEL_PURPOSES)

_PURPOSE_ROUTING_KEY = "preferred_provider_by_purpose"


class ModelPurposeRoute(TypedDict):
    """用途模型路由配置。"""

    provider_id: str | None
    model: str | None
    base_url: str | None


async def save_model_config(
    provider: str,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    priority: int | None = None,
    is_active: bool = True,
) -> dict[str, Any]:
    """保存模型配置到数据库。

    Args:
        provider: 模型提供商 ID
        api_key: 明文 API Key（将加密存储）
        model: 模型名称
        base_url: 自定义 API 端点
        priority: 优先级（数值越小越优先）
        is_active: 是否启用

    Returns:
        保存后的配置信息（脱敏）
    """
    if provider not in VALID_PROVIDERS:
        raise ValueError(f"不支持的模型提供商: {provider}")
    if priority is not None and priority < 0:
        raise ValueError("优先级不能小于 0")

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
            "SELECT id, encrypted_api_key, api_key_hint, priority FROM model_configs WHERE provider = ?",
            (provider,),
        )
        existing = await cursor.fetchone()

        if existing:
            # 更新：如果未提供新 Key 则保留旧值
            final_encrypted_key = encrypted_key if has_new_key else existing[1]
            final_key_hint = key_hint if has_new_key else (existing[2] or "")
            final_priority = priority if priority is not None else int(existing[3] or 0)
            await db.execute(
                """
                UPDATE model_configs
                SET model = ?, encrypted_api_key = ?, api_key_hint = ?,
                    base_url = ?, priority = ?, is_active = ?, updated_at = datetime('now')
                WHERE provider = ?
                """,
                (
                    model or "",
                    final_encrypted_key,
                    final_key_hint,
                    base_url,
                    final_priority,
                    int(is_active),
                    provider,
                ),
            )
        else:
            # 插入新记录
            final_key_hint = key_hint
            default_priorities = {pid: idx for idx, pid in enumerate(PROVIDER_PRIORITY_ORDER)}
            final_priority = priority if priority is not None else default_priorities.get(provider, 0)
            await db.execute(
                """
                INSERT INTO model_configs (
                    provider, model, encrypted_api_key, api_key_hint, base_url, priority, is_active, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    provider,
                    model or "",
                    encrypted_key,
                    key_hint,
                    base_url,
                    final_priority,
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
            "priority": final_priority,
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
            "SELECT provider, model, encrypted_api_key, api_key_hint, base_url, priority, is_active "
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
                "priority": int(row[5] or 0),
                "is_active": bool(row[6]),
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
    for provider in PROVIDER_PRIORITY_ORDER:
        result[provider] = await get_effective_config(provider)
    return result


async def get_model_priorities() -> dict[str, int]:
    """读取所有提供商优先级（数值越小越优先）。"""
    priorities = {provider: idx for idx, provider in enumerate(PROVIDER_PRIORITY_ORDER)}

    db = await get_db()
    try:
        cursor = await db.execute("SELECT provider, priority FROM model_configs")
        rows = await cursor.fetchall()
        for row in rows:
            provider = row[0]
            if provider not in VALID_PROVIDERS:
                continue
            try:
                parsed = int(row[1])
            except (TypeError, ValueError):
                continue
            priorities[provider] = max(0, parsed)
        return priorities
    finally:
        await db.close()


async def set_model_priorities(priorities: dict[str, int]) -> dict[str, int]:
    """批量设置提供商优先级。"""
    if not priorities:
        return await get_model_priorities()

    for provider, priority in priorities.items():
        if provider not in VALID_PROVIDERS:
            raise ValueError(f"不支持的模型提供商: {provider}")
        if priority < 0:
            raise ValueError("优先级不能小于 0")

    db = await get_db()
    try:
        for provider, priority in priorities.items():
            await db.execute(
                """
                INSERT INTO model_configs (provider, model, priority, is_active, updated_at)
                VALUES (?, '', ?, 1, datetime('now'))
                ON CONFLICT(provider) DO UPDATE SET
                    priority = excluded.priority,
                    updated_at = excluded.updated_at
                """,
                (provider, int(priority)),
            )
        await db.commit()
    finally:
        await db.close()

    return await get_model_priorities()


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


def _empty_route() -> ModelPurposeRoute:
    return {"provider_id": None, "model": None, "base_url": None}


def _normalize_route_item(item: Any) -> ModelPurposeRoute:
    """兼容旧格式（字符串 provider）与新格式（对象）。"""
    route = _empty_route()

    # 旧格式：{"chat": "zhipu"}
    if isinstance(item, str):
        provider_id = item.strip()
        if provider_id and provider_id in VALID_PROVIDERS:
            route["provider_id"] = provider_id
        return route

    # 新格式：{"provider_id": "...", "model": "...", "base_url": "..."}
    if not isinstance(item, dict):
        return route

    provider_raw = item.get("provider_id")
    provider_id = provider_raw.strip() if isinstance(provider_raw, str) else ""
    if provider_id and provider_id in VALID_PROVIDERS:
        route["provider_id"] = provider_id

    model_raw = item.get("model")
    model = model_raw.strip() if isinstance(model_raw, str) else ""
    if model:
        route["model"] = model

    base_url_raw = item.get("base_url")
    base_url = base_url_raw.strip() if isinstance(base_url_raw, str) else ""
    if base_url:
        route["base_url"] = base_url

    # provider 缺失时，model/base_url 无意义，自动清空
    if not route["provider_id"]:
        route["model"] = None
        route["base_url"] = None
    return route


def _normalize_purpose_routes(value: Any) -> dict[str, ModelPurposeRoute]:
    """清洗并校验用途路由映射。"""
    normalized: dict[str, ModelPurposeRoute] = {
        purpose: _empty_route() for purpose in MODEL_PURPOSES
    }
    if not isinstance(value, dict):
        return normalized

    for purpose, raw in value.items():
        if purpose not in VALID_MODEL_PURPOSES:
            continue
        normalized[purpose] = _normalize_route_item(raw)
    return normalized


async def get_model_purpose_routes() -> dict[str, ModelPurposeRoute]:
    """读取用途级别的模型路由映射。"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT value FROM app_settings WHERE key = ?",
            (_PURPOSE_ROUTING_KEY,),
        )
        row = await cursor.fetchone()
        if not row or not row[0]:
            return {purpose: _empty_route() for purpose in MODEL_PURPOSES}
        try:
            loaded = json.loads(row[0])
        except json.JSONDecodeError:
            logger.warning("用途模型路由配置解析失败，已回退为空映射")
            loaded = {}
        return _normalize_purpose_routes(loaded)
    finally:
        await db.close()


async def set_model_purpose_routes(
    updates: dict[str, dict[str, str | None]],
) -> dict[str, ModelPurposeRoute]:
    """保存用途级别的模型路由映射（增量更新）。"""
    for purpose in updates:
        if purpose not in VALID_MODEL_PURPOSES:
            raise ValueError(f"不支持的模型用途: {purpose}")

    current = await get_model_purpose_routes()
    merged: dict[str, ModelPurposeRoute] = {
        purpose: {
            "provider_id": current[purpose]["provider_id"],
            "model": current[purpose]["model"],
            "base_url": current[purpose]["base_url"],
        }
        for purpose in MODEL_PURPOSES
    }

    for purpose, payload in updates.items():
        route = merged[purpose]
        if "provider_id" in payload:
            provider_id = payload.get("provider_id")
            normalized_provider = provider_id.strip() if isinstance(provider_id, str) else None
            route["provider_id"] = normalized_provider or None
        if "model" in payload:
            model = payload.get("model")
            normalized_model = model.strip() if isinstance(model, str) else None
            route["model"] = normalized_model or None
        if "base_url" in payload:
            base_url = payload.get("base_url")
            normalized_base_url = base_url.strip() if isinstance(base_url, str) else None
            route["base_url"] = normalized_base_url or None

        if route["provider_id"] and route["provider_id"] not in VALID_PROVIDERS:
            raise ValueError(f"不支持的模型提供商: {route['provider_id']}")
        if not route["provider_id"] and (route["model"] or route["base_url"]):
            raise ValueError(f"用途 {purpose} 配置了 model/base_url，但缺少 provider_id")

    to_store: dict[str, dict[str, str]] = {}
    for purpose, route in merged.items():
        provider_id = route.get("provider_id")
        if not provider_id:
            continue
        item: dict[str, str] = {"provider_id": provider_id}
        if route.get("model"):
            item["model"] = str(route["model"])
        if route.get("base_url"):
            item["base_url"] = str(route["base_url"])
        to_store[purpose] = item

    db = await get_db()
    try:
        if to_store:
            await db.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (?, ?, datetime('now'))
                ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
                """,
                (_PURPOSE_ROUTING_KEY, json.dumps(to_store, ensure_ascii=False)),
            )
        else:
            await db.execute(
                "DELETE FROM app_settings WHERE key = ?",
                (_PURPOSE_ROUTING_KEY,),
            )
        await db.commit()
        logger.info("用途模型路由已更新: %s", to_store)
        return merged
    finally:
        await db.close()


async def get_purpose_provider_routes() -> dict[str, str | None]:
    """读取用途级别的首选提供商映射（兼容接口）。"""
    routes = await get_model_purpose_routes()
    return {purpose: routes[purpose].get("provider_id") for purpose in MODEL_PURPOSES}


async def set_purpose_provider_routes(
    updates: dict[str, str | None],
) -> dict[str, str | None]:
    """保存用途级别的首选提供商映射（兼容接口）。"""
    transformed: dict[str, dict[str, str | None]] = {}
    for purpose, provider in updates.items():
        transformed[purpose] = {
            "provider_id": provider,
            "model": None,
            "base_url": None,
        }
    merged = await set_model_purpose_routes(transformed)
    return {purpose: merged[purpose].get("provider_id") for purpose in MODEL_PURPOSES}
