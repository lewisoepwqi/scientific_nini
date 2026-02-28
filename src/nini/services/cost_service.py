"""成本计算服务。

提供 Token 使用统计、成本计算和模型定价查询功能。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from nini.config import settings
from nini.models.cost import (
    AggregateCostSummary,
    ModelPricing,
    ModelTokenUsage,
    PricingConfig,
    SessionCostSummary,
    TokenUsage,
)
from nini.utils.token_counter import get_tracker

logger = logging.getLogger(__name__)

# 缓存定价配置
_pricing_config: PricingConfig | None = None


def load_pricing_config() -> PricingConfig:
    """加载定价配置。"""
    global _pricing_config
    if _pricing_config is not None:
        return _pricing_config

    pricing_file = Path(__file__).parent.parent / "config" / "pricing.yaml"
    try:
        with open(pricing_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        models = {}
        for model_id, model_data in data.get("models", {}).items():
            if isinstance(model_data, dict) and "input_price" in model_data:
                models[model_id] = ModelPricing(**model_data)

        _pricing_config = PricingConfig(
            models=models,
            usd_to_cny_rate=data.get("usd_to_cny_rate", 7.2),
            default_model=data.get("default_model", "gpt-4o"),
        )
        return _pricing_config
    except Exception as e:
        logger.warning(f"Failed to load pricing config: {e}")
        # 返回默认配置
        _pricing_config = PricingConfig()
        return _pricing_config


def calculate_cost_cny(model_id: str, input_tokens: int, output_tokens: int) -> float:
    """计算人民币成本。

    Args:
        model_id: 模型 ID
        input_tokens: 输入 token 数量
        output_tokens: 输出 token 数量

    Returns:
        预估成本（人民币）
    """
    pricing = load_pricing_config()
    return pricing.calculate_cost_cny(model_id, input_tokens, output_tokens)


def calculate_cost_usd(model_id: str, input_tokens: int, output_tokens: int) -> float:
    """计算美元成本。

    Args:
        model_id: 模型 ID
        input_tokens: 输入 token 数量
        output_tokens: 输出 token 数量

    Returns:
        预估成本（美元）
    """
    pricing = load_pricing_config()
    return pricing.calculate_cost_usd(model_id, input_tokens, output_tokens)


def get_session_token_usage(session_id: str) -> TokenUsage | None:
    """获取会话的 Token 使用统计。

    Args:
        session_id: 会话 ID

    Returns:
        Token 使用统计，如果没有则返回 None
    """
    try:
        tracker = get_tracker(session_id)
        pricing = load_pricing_config()

        # 计算成本
        total_cost_usd = tracker.total_cost_usd
        total_cost_cny = total_cost_usd * pricing.usd_to_cny_rate

        # 构建模型分解
        model_breakdown: dict[str, dict[str, Any]] = {}
        for record in tracker.records:
            if record.model not in model_breakdown:
                model_breakdown[record.model] = {
                    "model_id": record.model,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                    "cost_cny": 0.0,
                    "cost_usd": 0.0,
                    "call_count": 0,
                }

            model_data = model_breakdown[record.model]
            model_data["input_tokens"] = int(model_data["input_tokens"]) + record.input_tokens
            model_data["output_tokens"] = int(model_data["output_tokens"]) + record.output_tokens
            model_data["total_tokens"] = (
                int(model_data["total_tokens"]) + record.input_tokens + record.output_tokens
            )
            model_data["cost_usd"] = float(model_data["cost_usd"]) + (record.cost_usd or 0.0)
            model_data["call_count"] = int(model_data["call_count"]) + 1

        # 转换 USD 到 CNY
        model_usage: dict[str, ModelTokenUsage] = {}
        for model_id, data in model_breakdown.items():
            data["cost_cny"] = float(data["cost_usd"]) * pricing.usd_to_cny_rate
            model_usage[model_id] = ModelTokenUsage(
                model_id=str(data["model_id"]),
                input_tokens=int(data["input_tokens"]),
                output_tokens=int(data["output_tokens"]),
                total_tokens=int(data["total_tokens"]),
                cost_cny=float(data["cost_cny"]),
                cost_usd=float(data["cost_usd"]),
                call_count=int(data["call_count"]),
            )

        return TokenUsage(
            session_id=session_id,
            input_tokens=tracker.total_input_tokens,
            output_tokens=tracker.total_output_tokens,
            total_tokens=tracker.total_tokens,
            estimated_cost_cny=total_cost_cny,
            estimated_cost_usd=total_cost_usd,
            model_breakdown=model_usage,
        )
    except Exception as e:
        logger.warning(f"Failed to get token usage for session {session_id}: {e}")
        return None


def get_all_sessions_cost_summary() -> tuple[list[SessionCostSummary], AggregateCostSummary]:
    """获取所有会话的成本统计。

    Returns:
        (会话列表, 聚合摘要)
    """
    sessions_dir = Path(settings.data_dir) / "sessions"
    if not sessions_dir.exists():
        return [], AggregateCostSummary(
            total_sessions=0,
            total_tokens=0,
            total_input_tokens=0,
            total_output_tokens=0,
            total_cost_cny=0.0,
            total_cost_usd=0.0,
            average_cost_per_session=0.0,
        )

    pricing = load_pricing_config()
    sessions = []
    total_input = 0
    total_output = 0
    total_cost_cny = 0.0
    total_cost_usd = 0.0
    model_usage: dict[str, int] = {}

    for session_dir in sorted(
        sessions_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True
    ):
        if not session_dir.is_dir():
            continue

        session_id = session_dir.name
        meta_file = session_dir / "meta.json"

        # 获取会话标题
        title = "新会话"
        if meta_file.exists():
            try:
                import json

                with open(meta_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                    title = meta.get("title", "新会话")
            except Exception:
                pass

        # 获取 token 使用
        usage = get_session_token_usage(session_id)
        if usage and usage.total_tokens > 0:
            sessions.append(
                SessionCostSummary(
                    session_id=session_id,
                    title=title,
                    total_tokens=usage.total_tokens,
                    estimated_cost_cny=round(usage.estimated_cost_cny, 6),
                    model_count=len(usage.model_breakdown),
                )
            )
            total_input += usage.input_tokens
            total_output += usage.output_tokens
            total_cost_cny += usage.estimated_cost_cny
            total_cost_usd += usage.estimated_cost_usd

            # 统计模型使用
            for model_id, model_data in usage.model_breakdown.items():
                model_usage[model_id] = model_usage.get(model_id, 0) + model_data.call_count

    # 找出使用最多的模型
    most_used_model: str | None = None
    if model_usage:
        most_used_model = max(model_usage.items(), key=lambda x: x[1])[0]

    # 构建聚合摘要
    aggregate = AggregateCostSummary(
        total_sessions=len(sessions),
        total_tokens=total_input + total_output,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        total_cost_cny=round(total_cost_cny, 6),
        total_cost_usd=round(total_cost_usd, 6),
        average_cost_per_session=round(total_cost_cny / len(sessions), 6) if sessions else 0.0,
        most_used_model=most_used_model,
    )

    return sessions, aggregate


def get_pricing_info() -> dict[str, Any]:
    """获取定价信息。

    Returns:
        定价配置字典
    """
    pricing = load_pricing_config()

    # 加载 tier 定义
    pricing_file = Path(__file__).parent.parent / "config" / "pricing.yaml"
    tier_definitions = {}
    cost_warnings = {}

    try:
        with open(pricing_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            tier_definitions = data.get("tier_definitions", {})
            cost_warnings = data.get("cost_warnings", {})
    except Exception as e:
        logger.warning(f"Failed to load tier definitions: {e}")

    return {
        "models": {
            model_id: {
                "input_price": p.input_price,
                "output_price": p.output_price,
                "currency": p.currency,
                "tier": p.tier,
            }
            for model_id, p in pricing.models.items()
        },
        "usd_to_cny_rate": pricing.usd_to_cny_rate,
        "default_model": pricing.default_model,
        "tier_definitions": tier_definitions,
        "cost_warnings": cost_warnings,
    }


def get_model_pricing(model_id: str) -> ModelPricing | None:
    """获取指定模型的定价信息。

    Args:
        model_id: 模型 ID

    Returns:
        模型定价信息，如果没有则返回 None
    """
    pricing = load_pricing_config()
    return pricing.get_model_pricing(model_id)


def is_high_cost_model(model_id: str, base_model: str | None = None) -> tuple[bool, float]:
    """检查模型是否为高成本模型。

    Args:
        model_id: 要检查的模型 ID
        base_model: 基准模型 ID，默认为配置中的默认模型

    Returns:
        (是否高成本, 成本倍数)
    """
    pricing = load_pricing_config()

    if base_model is None:
        base_model = pricing.default_model

    model_pricing = pricing.get_model_pricing(model_id)
    base_pricing = pricing.get_model_pricing(base_model)

    if not model_pricing or not base_pricing:
        return False, 1.0

    # 计算平均成本倍数（输入和输出的平均值）
    model_avg_price = (model_pricing.input_price + model_pricing.output_price) / 2
    base_avg_price = (base_pricing.input_price + base_pricing.output_price) / 2

    if base_avg_price == 0:
        return False, 1.0

    multiplier = model_avg_price / base_avg_price

    # 加载警告阈值
    pricing_file = Path(__file__).parent.parent / "config" / "pricing.yaml"
    try:
        with open(pricing_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            threshold = data.get("cost_warnings", {}).get("high_cost_multiplier", 2.0)
            return multiplier >= threshold, multiplier
    except Exception:
        return multiplier >= 2.0, multiplier
