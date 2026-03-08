"""模型配置管理器。

负责将用户通过 Web 界面保存的模型配置持久化到数据库，
并在启动时合并 DB 配置与 .env 环境变量配置。

优先级：DB 用户配置 > .env 环境变量 > 默认值。
"""

from __future__ import annotations

import json
import logging
import os
import platform
from datetime import timezone, datetime
from pathlib import Path
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
    "minimax",
    "ollama",
}

BUILTIN_PROVIDER_ID = "builtin"
VALID_ROUTE_PROVIDERS = VALID_PROVIDERS | {BUILTIN_PROVIDER_ID}

API_MODE_STANDARD = "standard"
API_MODE_CODING_PLAN = "coding_plan"
SUPPORTED_API_MODES_BY_PROVIDER: dict[str, tuple[str, ...]] = {
    "zhipu": (API_MODE_STANDARD, API_MODE_CODING_PLAN),
    "dashscope": (API_MODE_STANDARD, API_MODE_CODING_PLAN),
}
DEFAULT_BASE_URLS_BY_PROVIDER_MODE: dict[str, dict[str, str]] = {
    "zhipu": {
        API_MODE_STANDARD: "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        API_MODE_CODING_PLAN: "https://open.bigmodel.cn/api/coding/paas/v4",
    },
    "dashscope": {
        API_MODE_STANDARD: "https://dashscope.aliyuncs.com/compatible-mode/v1",
        API_MODE_CODING_PLAN: "https://coding.dashscope.aliyuncs.com/v1",
    },
}
DEFAULT_MODELS_BY_PROVIDER_MODE: dict[str, dict[str, str]] = {
    "zhipu": {
        API_MODE_STANDARD: "glm-4",
        API_MODE_CODING_PLAN: "glm-4.7",
    },
    "dashscope": {
        API_MODE_STANDARD: "qwen-plus",
        API_MODE_CODING_PLAN: "qwen3-coder-plus",
    },
}


def normalize_api_mode(provider: str, api_mode: str | None) -> str | None:
    """归一化 API 模式，仅对支持双模式的供应商生效。"""
    if provider not in SUPPORTED_API_MODES_BY_PROVIDER:
        return None
    normalized = api_mode.strip().lower() if isinstance(api_mode, str) else ""
    if normalized in SUPPORTED_API_MODES_BY_PROVIDER[provider]:
        return normalized
    return None


def get_default_base_url_for_mode(provider: str, api_mode: str) -> str:
    """根据供应商与模式返回默认端点。"""
    try:
        return DEFAULT_BASE_URLS_BY_PROVIDER_MODE[provider][api_mode]
    except KeyError as exc:
        raise ValueError(f"不支持的 API 模式: {provider}/{api_mode}") from exc


def get_default_model_for_mode(provider: str, api_mode: str) -> str | None:
    """根据供应商与模式返回默认模型。"""
    return DEFAULT_MODELS_BY_PROVIDER_MODE.get(provider, {}).get(api_mode)


def infer_api_mode_from_base_url(provider: str, base_url: str | None) -> str | None:
    """根据端点反推 API 模式。"""
    normalized = base_url.strip().rstrip("/") if isinstance(base_url, str) else ""
    if not normalized:
        return None
    for api_mode, default_base_url in DEFAULT_BASE_URLS_BY_PROVIDER_MODE.get(provider, {}).items():
        if normalized == default_base_url.rstrip("/"):
            return api_mode
    return None

# 默认提供商优先级（数值越小优先级越高）
PROVIDER_PRIORITY_ORDER: tuple[str, ...] = (
    "openai",
    "anthropic",
    "moonshot",
    "kimi_coding",
    "zhipu",
    "deepseek",
    "dashscope",
    "minimax",
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


async def _ensure_app_settings_table(db: Any) -> None:
    """确保 app_settings 表存在。

    某些测试场景不会触发应用 lifespan（不会先执行 init_db），
    这里做就地兜底，避免路由直接读写配置时报 no such table。
    """
    await db.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """)


async def save_model_config(
    provider: str,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_mode: str | None = None,
    priority: int | None = None,
    is_active: bool = True,
) -> dict[str, Any]:
    """保存模型配置到数据库。

    Args:
        provider: 模型提供商 ID
        api_key: 明文 API Key（将加密存储）
        model: 模型名称
        base_url: 自定义 API 端点
        api_mode: API 模式，仅部分供应商支持
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
    normalized_base_url = base_url.strip() if isinstance(base_url, str) else None
    if normalized_base_url == "":
        normalized_base_url = None

    normalized_api_mode = normalize_api_mode(provider, api_mode)
    normalized_model = model.strip() if isinstance(model, str) else None
    if normalized_model == "":
        normalized_model = None
    if provider in SUPPORTED_API_MODES_BY_PROVIDER:
        if not normalized_api_mode:
            raise ValueError(f"{provider} 必须选择 API 模式")
        final_base_url = normalized_base_url or get_default_base_url_for_mode(
            provider, normalized_api_mode
        )
        final_model = normalized_model or get_default_model_for_mode(provider, normalized_api_mode)
    else:
        final_base_url = normalized_base_url
        final_model = normalized_model

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
            if provider in SUPPORTED_API_MODES_BY_PROVIDER:
                raise ValueError("该供应商已配置，如需修改请先删除当前配置后重新配置")
            # 更新：如果未提供新 Key 则保留旧值
            final_encrypted_key = encrypted_key if has_new_key else existing[1]
            final_key_hint = key_hint if has_new_key else (existing[2] or "")
            final_priority = priority if priority is not None else int(existing[3] or 0)
            await db.execute(
                """
                UPDATE model_configs
                SET model = ?, encrypted_api_key = ?, api_key_hint = ?,
                    base_url = ?, api_mode = ?, priority = ?, is_active = ?, updated_at = datetime('now')
                WHERE provider = ?
                """,
                (
                    final_model or "",
                    final_encrypted_key,
                    final_key_hint,
                    final_base_url,
                    normalized_api_mode,
                    final_priority,
                    int(is_active),
                    provider,
                ),
            )
        else:
            # 插入新记录
            final_key_hint = key_hint
            default_priorities = {pid: idx for idx, pid in enumerate(PROVIDER_PRIORITY_ORDER)}
            final_priority = (
                priority if priority is not None else default_priorities.get(provider, 0)
            )
            await db.execute(
                """
                INSERT INTO model_configs (
                    provider, model, encrypted_api_key, api_key_hint, api_mode, base_url, priority, is_active, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    provider,
                    final_model or "",
                    encrypted_key,
                    key_hint,
                    normalized_api_mode,
                    final_base_url,
                    final_priority,
                    int(is_active),
                ),
            )
        await db.commit()
        logger.info("已保存模型配置: provider=%s, model=%s", provider, final_model)

        return {
            "provider": provider,
            "model": final_model or "",
            "api_key_hint": final_key_hint,
            "api_mode": normalized_api_mode,
            "base_url": final_base_url,
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
            "SELECT provider, model, encrypted_api_key, api_key_hint, api_mode, base_url, priority, is_active "
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
                "api_mode": normalize_api_mode(provider, row[4]),
                "base_url": row[5],
                "priority": int(row[6] or 0),
                "is_active": bool(row[7]),
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
    db_api_mode = normalize_api_mode(provider, db_cfg.get("api_mode"))

    # .env 配置映射
    env_map: dict[str, dict[str, str | None]] = {
        "openai": {
            "api_key": settings.openai_api_key,
            "model": settings.openai_model,
            "base_url": settings.openai_base_url,
            "api_mode": None,
        },
        "anthropic": {
            "api_key": settings.anthropic_api_key,
            "model": settings.anthropic_model,
            "base_url": None,
            "api_mode": None,
        },
        "moonshot": {
            "api_key": settings.moonshot_api_key,
            "model": settings.moonshot_model,
            "base_url": None,
            "api_mode": None,
        },
        "kimi_coding": {
            "api_key": settings.kimi_coding_api_key,
            "model": settings.kimi_coding_model,
            "base_url": settings.kimi_coding_base_url,
            "api_mode": None,
        },
        "zhipu": {
            "api_key": settings.zhipu_api_key,
            "model": settings.zhipu_model,
            "base_url": settings.zhipu_base_url,
            "api_mode": infer_api_mode_from_base_url("zhipu", settings.zhipu_base_url),
        },
        "deepseek": {
            "api_key": settings.deepseek_api_key,
            "model": settings.deepseek_model,
            "base_url": None,
            "api_mode": None,
        },
        "dashscope": {
            "api_key": settings.dashscope_api_key,
            "model": settings.dashscope_model,
            "base_url": settings.dashscope_base_url,
            "api_mode": infer_api_mode_from_base_url("dashscope", settings.dashscope_base_url),
        },
        "minimax": {
            "api_key": settings.minimax_api_key,
            "model": settings.minimax_model,
            "base_url": settings.minimax_base_url,
            "api_mode": None,
        },
        "ollama": {
            "api_key": None,
            "model": settings.ollama_model,
            "base_url": settings.ollama_base_url,
            "api_mode": None,
        },
    }

    env_cfg = env_map.get(provider, {})
    env_api_mode = normalize_api_mode(provider, env_cfg.get("api_mode"))
    effective_api_mode = db_api_mode or env_api_mode
    effective_model = db_cfg.get("model") or env_cfg.get("model") or ""
    if not effective_model and effective_api_mode:
        effective_model = get_default_model_for_mode(provider, effective_api_mode) or ""

    # DB 优先，.env 兜底
    return {
        "api_key": db_cfg.get("api_key") or env_cfg.get("api_key"),
        "model": effective_model,
        "api_mode": effective_api_mode,
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
        await _ensure_app_settings_table(db)
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
        await _ensure_app_settings_table(db)
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
        await _ensure_app_settings_table(db)
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

        if route["provider_id"] and route["provider_id"] not in VALID_ROUTE_PROVIDERS:
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
        await _ensure_app_settings_table(db)
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


def _is_settings_field_explicit(field_name: str) -> bool:
    """判断 settings 字段是否由环境变量或 .env 显式提供。"""
    try:
        return field_name in settings.model_fields_set
    except Exception:
        return False


async def list_user_configured_provider_ids() -> list[str]:
    """返回用户已配置的提供商列表。

    说明：
    - 仅统计用户自行配置的供应商，不包含系统内置试用模型。
    - API Key 型供应商要求 DB 或环境中存在密钥。
    - Ollama 仅在用户显式配置 DB 或环境字段时才计入，避免把默认值误判为已配置。
    """
    db_configs = await load_all_model_configs()
    configured: list[str] = []

    env_key_fields = {
        "openai": "openai_api_key",
        "anthropic": "anthropic_api_key",
        "moonshot": "moonshot_api_key",
        "kimi_coding": "kimi_coding_api_key",
        "zhipu": "zhipu_api_key",
        "deepseek": "deepseek_api_key",
        "dashscope": "dashscope_api_key",
        "minimax": "minimax_api_key",
    }

    for provider_id in PROVIDER_PRIORITY_ORDER:
        db_cfg = db_configs.get(provider_id, {})
        if provider_id == "ollama":
            db_base = str(db_cfg.get("base_url") or "").strip()
            db_model = str(db_cfg.get("model") or "").strip()
            has_env_base = _is_settings_field_explicit("ollama_base_url") and bool(
                str(settings.ollama_base_url or "").strip()
            )
            has_env_model = _is_settings_field_explicit("ollama_model") and bool(
                str(settings.ollama_model or "").strip()
            )
            if db_base or db_model or has_env_base or has_env_model:
                configured.append(provider_id)
            continue

        env_key_field = env_key_fields.get(provider_id)
        env_key = getattr(settings, env_key_field, None) if env_key_field else None
        db_key = db_cfg.get("api_key")
        if str(db_key or "").strip() or str(env_key or "").strip():
            configured.append(provider_id)

    return configured


# ---- 试用模式 ----

_TRIAL_INSTALL_DATE_KEY = "trial_install_date"
_TRIAL_ACTIVATED_KEY = "trial_activated"
_ACTIVE_PROVIDER_KEY = "active_provider"


async def get_trial_status() -> dict[str, Any]:
    """读取试用状态并计算剩余调用次数（按次数限额）。

    Returns:
        包含 activated、expired、内置模型用量与剩余额度的字典
    """
    fast_limit = max(0, int(settings.builtin_fast_limit))
    deep_limit = max(0, int(settings.builtin_deep_limit))
    usage = await get_builtin_usage()
    fast_remaining = max(0, fast_limit - usage["fast"]) if fast_limit > 0 else 10**9
    deep_remaining = max(0, deep_limit - usage["deep"]) if deep_limit > 0 else 10**9

    # 仅当两个模式都达到上限时才视为试用耗尽
    expired = (fast_limit > 0 and fast_remaining <= 0) and (deep_limit > 0 and deep_remaining <= 0)

    db = await get_db()
    try:
        await _ensure_app_settings_table(db)
        cursor = await db.execute(
            "SELECT key, value FROM app_settings WHERE key IN (?)", (_TRIAL_ACTIVATED_KEY,)
        )
        rows = await cursor.fetchall()
        row_map = {r[0]: r[1] for r in rows}

        activated = row_map.get(_TRIAL_ACTIVATED_KEY) == "true"
        # 向后兼容：若历史数据未激活但已有调用次数，视为已激活。
        if not activated and (usage["fast"] > 0 or usage["deep"] > 0):
            activated = True

        return {
            "activated": activated,
            "expired": expired,
            "fast_calls_used": usage["fast"],
            "deep_calls_used": usage["deep"],
            "fast_calls_remaining": fast_remaining if fast_limit > 0 else None,
            "deep_calls_remaining": deep_remaining if deep_limit > 0 else None,
        }
    finally:
        await db.close()


async def activate_trial() -> None:
    """激活试用模式，记录当前日期到本地存储。"""
    today_str = datetime.now(timezone.utc).date().isoformat()
    db = await get_db()
    try:
        await _ensure_app_settings_table(db)
        await db.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(key) DO NOTHING
            """,
            (_TRIAL_INSTALL_DATE_KEY, today_str),
        )
        await db.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, 'true', datetime('now'))
            ON CONFLICT(key) DO UPDATE SET value = 'true', updated_at = datetime('now')
            """,
            (_TRIAL_ACTIVATED_KEY,),
        )
        await db.commit()
        logger.info("试用模式已激活，安装日期: %s", today_str)
    finally:
        await db.close()


async def get_active_provider_id() -> str | None:
    """读取当前激活的供应商 ID。"""
    db = await get_db()
    try:
        await _ensure_app_settings_table(db)
        cursor = await db.execute(
            "SELECT value FROM app_settings WHERE key = ?",
            (_ACTIVE_PROVIDER_KEY,),
        )
        row = await cursor.fetchone()
        if row and row[0] and row[0] in VALID_PROVIDERS:
            return row[0]
        return None
    finally:
        await db.close()


async def remove_model_config(provider: str) -> None:
    """从数据库删除指定供应商的配置行。

    Args:
        provider: 供应商 ID
    """
    if provider not in VALID_PROVIDERS:
        raise ValueError(f"不支持的模型提供商: {provider}")

    db = await get_db()
    try:
        await db.execute("DELETE FROM model_configs WHERE provider = ?", (provider,))
        await db.commit()
        logger.info("已删除供应商配置: provider=%s", provider)
    finally:
        await db.close()


# ---- 内置用量追踪 ----

_BUILTIN_FAST_USAGE_KEY = "builtin_fast_calls_used"
_BUILTIN_DEEP_USAGE_KEY = "builtin_deep_calls_used"


def _get_system_usage_path() -> Path:
    """获取系统级内置用量文件路径（跨重装持久化）。

    - macOS/Linux: ~/.config/nini/builtin_usage.json
    - Windows:     %APPDATA%\\nini\\builtin_usage.json
    """
    if platform.system() == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "nini" / "builtin_usage.json"


def _read_system_usage() -> dict[str, int]:
    """从系统文件读取内置用量计数。"""
    path = _get_system_usage_path()
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return {
                "fast": max(0, int(data.get("fast", 0))),
                "deep": max(0, int(data.get("deep", 0))),
            }
    except Exception as e:
        logger.warning("读取系统用量文件失败: %s", e)
    return {"fast": 0, "deep": 0}


def _write_system_usage(fast: int, deep: int) -> None:
    """将内置用量计数写入系统文件。"""
    path = _get_system_usage_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"fast": fast, "deep": deep}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("写入系统用量文件失败: %s", e)


async def _read_db_usage() -> dict[str, int]:
    """从数据库读取内置用量计数。"""
    db = await get_db()
    try:
        await _ensure_app_settings_table(db)
        cursor = await db.execute(
            "SELECT key, value FROM app_settings WHERE key IN (?, ?)",
            (_BUILTIN_FAST_USAGE_KEY, _BUILTIN_DEEP_USAGE_KEY),
        )
        rows = await cursor.fetchall()
        row_map = {r[0]: r[1] for r in rows}
        return {
            "fast": max(0, int(row_map.get(_BUILTIN_FAST_USAGE_KEY, 0) or 0)),
            "deep": max(0, int(row_map.get(_BUILTIN_DEEP_USAGE_KEY, 0) or 0)),
        }
    except Exception as e:
        logger.warning("读取数据库用量失败: %s", e)
        return {"fast": 0, "deep": 0}
    finally:
        await db.close()


async def get_builtin_usage() -> dict[str, int]:
    """获取内置用量（取 DB 与系统文件的最大值，防止 DB 重置绕过限额）。

    Returns:
        {"fast": <已用快速次数>, "deep": <已用深度次数>}
    """
    db_usage = await _read_db_usage()
    sys_usage = _read_system_usage()
    return {
        "fast": max(db_usage["fast"], sys_usage["fast"]),
        "deep": max(db_usage["deep"], sys_usage["deep"]),
    }


async def increment_builtin_usage(mode: str) -> None:
    """递增内置用量计数（同时写入 DB 和系统文件）。

    Args:
        mode: "fast" 或 "deep"
    """
    if mode not in ("fast", "deep"):
        return

    key = _BUILTIN_FAST_USAGE_KEY if mode == "fast" else _BUILTIN_DEEP_USAGE_KEY
    db = await get_db()
    try:
        await _ensure_app_settings_table(db)
        await db.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, '1', datetime('now'))
            ON CONFLICT(key) DO UPDATE SET
                value = CAST(COALESCE(app_settings.value, '0') AS INTEGER) + 1,
                updated_at = datetime('now')
            """,
            (key,),
        )
        cursor = await db.execute(
            "SELECT key, value FROM app_settings WHERE key IN (?, ?)",
            (_BUILTIN_FAST_USAGE_KEY, _BUILTIN_DEEP_USAGE_KEY),
        )
        rows = await cursor.fetchall()
        await db.commit()
    except Exception as e:
        logger.warning("写入数据库用量失败: %s", e)
        rows = []
    finally:
        await db.close()

    row_map = {r[0]: r[1] for r in rows}
    db_usage = {
        "fast": max(0, int(row_map.get(_BUILTIN_FAST_USAGE_KEY, 0) or 0)),
        "deep": max(0, int(row_map.get(_BUILTIN_DEEP_USAGE_KEY, 0) or 0)),
    }
    sys_usage = _read_system_usage()
    merged_fast = max(db_usage["fast"], sys_usage["fast"])
    merged_deep = max(db_usage["deep"], sys_usage["deep"])
    _write_system_usage(fast=merged_fast, deep=merged_deep)
    logger.debug(
        "内置用量更新: mode=%s, 累计=%d",
        mode,
        merged_fast if mode == "fast" else merged_deep,
    )


async def is_builtin_exhausted(mode: str) -> bool:
    """检查指定模式的内置用量是否已耗尽。

    Args:
        mode: "fast" 或 "deep"

    Returns:
        True 表示已耗尽（不可再用内置模型）
    """
    from nini.config import settings

    if mode not in ("fast", "deep"):
        return False

    usage = await get_builtin_usage()
    limit = settings.builtin_fast_limit if mode == "fast" else settings.builtin_deep_limit
    return usage[mode] >= limit


async def set_active_provider(provider_id: str | None) -> None:
    """设置唯一激活供应商（单一激活约束）。

    Args:
        provider_id: 要激活的供应商 ID，None 表示清除激活状态
    """
    if provider_id is not None and provider_id not in VALID_PROVIDERS:
        raise ValueError(f"不支持的模型提供商: {provider_id}")

    db = await get_db()
    try:
        await _ensure_app_settings_table(db)
        if provider_id is None:
            await db.execute("DELETE FROM app_settings WHERE key = ?", (_ACTIVE_PROVIDER_KEY,))
        else:
            await db.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (?, ?, datetime('now'))
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')
                """,
                (_ACTIVE_PROVIDER_KEY, provider_id),
            )
        await db.commit()
        logger.info("激活供应商已设置为: %s", provider_id)
    finally:
        await db.close()
