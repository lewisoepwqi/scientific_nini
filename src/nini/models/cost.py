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
    total_tokens: int = 0
    cost_cny: float = 0.0
    cost_usd: float = 0.0
    call_count: int = 0


class TokenUsage(BaseModel):
    """会话级别的 Token 使用统计。"""

    session_id: str
    input_tokens: int = 0
    output_tokens: int = 0
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


class PricingConfig(BaseModel):
    """定价配置集合。"""

    models: dict[str, ModelPricing] = Field(default_factory=dict)
    usd_to_cny_rate: float = 7.2
    default_model: str = "gpt-4o"

    def get_model_pricing(self, model_id: str) -> Optional[ModelPricing]:
        """获取指定模型的定价配置。"""
        # 尝试精确匹配
        if model_id in self.models:
            return self.models[model_id]

        # 尝试前缀匹配
        for key, pricing in self.models.items():
            if model_id.startswith(key) or key.startswith(model_id.split("-")[0]):
                return pricing

        return None

    def calculate_cost_cny(self, model_id: str, input_tokens: int, output_tokens: int) -> float:
        """计算人民币成本。"""
        pricing = self.get_model_pricing(model_id)
        if not pricing:
            return 0.0

        cost_usd = pricing.calculate_cost(input_tokens, output_tokens)
        return cost_usd * self.usd_to_cny_rate

    def calculate_cost_usd(self, model_id: str, input_tokens: int, output_tokens: int) -> float:
        """计算美元成本。"""
        pricing = self.get_model_pricing(model_id)
        if not pricing:
            return 0.0
        return pricing.calculate_cost(input_tokens, output_tokens)


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
