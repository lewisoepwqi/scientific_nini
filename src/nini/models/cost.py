"""成本与 Token 使用模型。

包含 Token 统计、成本计算和模型定价相关的 Pydantic 模型。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ModelTokenUsage(BaseModel):
    """单个模型的 Token 使用统计。"""

    model_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0
    cost_cny: float = 0.0
    cost_usd: float = 0.0
    call_count: int = 0


class TokenUsage(BaseModel):
    """会话级别的 Token 使用统计。"""

    session_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_cny: float = 0.0
    estimated_cost_usd: float = 0.0
    model_breakdown: dict[str, ModelTokenUsage] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "session_id": self.session_id,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost_cny": round(self.estimated_cost_cny, 6),
            "estimated_cost_usd": round(self.estimated_cost_usd, 6),
            "model_breakdown": {k: v.model_dump() for k, v in self.model_breakdown.items()},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ModelPricing(BaseModel):
    """模型定价配置。"""

    input_price: float  # 每 1K tokens 的价格
    output_price: float
    currency: str = "USD"
    tier: str = "standard"  # economy, standard, premium

    def calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """计算指定 token 数量的成本。"""
        return (input_tokens * self.input_price + output_tokens * self.output_price) / 1000


class TierDefinition(BaseModel):
    """模型层级定义。"""

    name: str  # 层级名称
    description: str = ""  # 层级描述
    max_input_tokens: int = 0  # 最大输入 token 数
    max_output_tokens: int = 0  # 最大输出 token 数
    models: list[str] = Field(default_factory=list)  # 该层级包含的模型


class CostWarning(BaseModel):
    """成本警告配置。"""

    threshold_percent: float = 80.0  # 警告阈值百分比
    message: str = "成本已超过阈值的 {percent}%"
    notification_type: str = "warning"  # info, warning, critical


class PricingConfig(BaseModel):
    """定价配置集合。"""

    models: dict[str, ModelPricing] = Field(default_factory=dict)
    usd_to_cny_rate: float = 7.2
    default_model: str = "gpt-4o"
    tier_definitions: dict[str, TierDefinition] = Field(default_factory=dict)  # 层级定义
    cost_warnings: list[CostWarning] = Field(default_factory=list)  # 成本警告配置

    # 兜底价格配置（当模型无定价时使用）
    fallback_pricing: ModelPricing = Field(
        default_factory=lambda: ModelPricing(
            input_price=0.001,  # $0.001 per 1K tokens
            output_price=0.002,  # $0.002 per 1K tokens
            currency="USD",
            tier="standard",
        )
    )
    enable_fallback_pricing: bool = True  # 是否启用兜底价格

    def get_model_pricing(self, model_id: str) -> tuple[Optional[ModelPricing], str]:
        """获取指定模型的定价配置。

        支持精确匹配和模糊匹配：
        1. 先尝试精确匹配
        2. 再尝试去掉版本日期后缀
        3. 最后尝试前缀匹配和包含匹配
        4. 使用兜底价格（如果启用）

        Returns:
            tuple: (ModelPricing, 状态信息)
                  状态信息包括："exact"(精确匹配), "fuzzy"(模糊匹配), "fallback"(兜底价格), "unknown"(未知)
        """
        if not model_id or model_id == "unknown":
            if self.enable_fallback_pricing:
                return self.fallback_pricing, "fallback"
            return None, "unknown"

        # 1. 尝试精确匹配
        if model_id in self.models:
            return self.models[model_id], "exact"

        # 2. 尝试去掉版本日期后缀（如 -20250514）
        import re

        base_model = re.sub(r"-\d{8}$", "", model_id)
        if base_model != model_id and base_model in self.models:
            return self.models[base_model], "fuzzy"

        # 3. 尝试前缀匹配（按 key 长度降序，优先匹配长的）
        for key in sorted(self.models.keys(), key=len, reverse=True):
            if model_id.startswith(key) or key.startswith(
                model_id.split("-")[0] if "-" in model_id else model_id
            ):
                return self.models[key], "fuzzy"

        # 4. 特殊处理：包含匹配（大小写不敏感）
        model_lower = model_id.lower()
        for key in self.models:
            if key.lower() in model_lower or model_lower in key.lower():
                return self.models[key], "fuzzy"

        # 5. 使用兜底价格
        if self.enable_fallback_pricing:
            return self.fallback_pricing, "fallback"

        return None, "unknown"

    def calculate_cost_cny(
        self, model_id: str, input_tokens: int, output_tokens: int
    ) -> tuple[float, str]:
        """计算人民币成本。

        Returns:
            tuple: (成本 CNY, 状态信息)
        """
        pricing, status = self.get_model_pricing(model_id)
        if not pricing:
            return 0.0, "unknown"

        cost_usd = pricing.calculate_cost(input_tokens, output_tokens)
        return cost_usd * self.usd_to_cny_rate, status

    def calculate_cost_usd(
        self, model_id: str, input_tokens: int, output_tokens: int
    ) -> tuple[float, str]:
        """计算美元成本。

        Returns:
            tuple: (成本 USD, 状态信息)
        """
        pricing, status = self.get_model_pricing(model_id)
        if not pricing:
            return 0.0, "unknown"
        return pricing.calculate_cost(input_tokens, output_tokens), status


class SessionCostSummary(BaseModel):
    """会话成本摘要（用于会话列表展示）。"""

    session_id: str
    title: str
    total_tokens: int
    estimated_cost_cny: float
    model_count: int
    created_at: Optional[datetime] = None


class AggregateCostSummary(BaseModel):
    """聚合成本摘要。"""

    total_sessions: int
    total_tokens: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost_cny: float
    total_cost_usd: float
    average_cost_per_session: float
    most_used_model: Optional[str] = None
