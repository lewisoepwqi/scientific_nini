"""Token 统计与成本监控。

基于 tiktoken 实现精确的 token 计数，支持会话级别的
token 消耗追踪和 API 成本估算。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# 延迟初始化编码器
_encoder: Any = None


def _get_encoder() -> Any:
    """获取 tiktoken 编码器（cl100k_base，适用于 GPT-4/GPT-3.5）。"""
    global _encoder
    if _encoder is not None:
        return _encoder
    try:
        import tiktoken

        _encoder = tiktoken.get_encoding("cl100k_base")
        return _encoder
    except ImportError:
        logger.info("tiktoken 未安装，token 计数将使用估算模式")
        return None
    except Exception:
        logger.warning("tiktoken 编码器初始化失败", exc_info=True)
        return None


def count_tokens(text: str) -> int:
    """统计文本的 token 数量。

    使用 tiktoken cl100k_base 编码器精确计数，
    未安装时回退到字符数估算（中文 ~1.5 token/字，英文 ~0.25 token/词）。
    """
    if not text:
        return 0
    encoder = _get_encoder()
    if encoder is not None:
        return len(encoder.encode(text))
    # 回退估算：中文按 1.5 token/字，英文按 0.25 token/词
    chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    ascii_words = len(text.encode("ascii", errors="ignore").split())
    return int(chinese_chars * 1.5 + ascii_words * 0.25 + len(text) * 0.1)


def count_messages_tokens(messages: list[dict[str, Any]]) -> int:
    """统计消息列表的总 token 数（含角色标记开销）。"""
    total = 0
    for msg in messages:
        # 每条消息有 ~4 token 的格式开销
        total += 4
        content = msg.get("content", "")
        if content:
            total += count_tokens(str(content))
        # tool_calls 参数也计入 token
        tool_calls = msg.get("tool_calls")
        if isinstance(tool_calls, list):
            for tc in tool_calls:
                if isinstance(tc, dict):
                    func = tc.get("function", {})
                    if isinstance(func, dict):
                        total += count_tokens(func.get("name", ""))
                        total += count_tokens(func.get("arguments", ""))
    # 最后一条消息的格式开销
    total += 2
    return total


# ---- 每次 API 调用的价格（USD / 1K tokens）----
# 近似值，仅供参考

_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o": {"input": 0.0025, "output": 0.01},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4-turbo": {"input": 0.01, "output": 0.03},
    "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
    "claude-sonnet-4-20250514": {"input": 0.003, "output": 0.015},
    "claude-3-5-sonnet-20241022": {"input": 0.003, "output": 0.015},
    "claude-3-haiku-20240307": {"input": 0.00025, "output": 0.00125},
    "deepseek-chat": {"input": 0.00014, "output": 0.00028},
    "deepseek-coder": {"input": 0.00014, "output": 0.00028},
    "qwen-plus": {"input": 0.0008, "output": 0.002},
    "qwen-turbo": {"input": 0.0003, "output": 0.0006},
    "glm-4": {"input": 0.001, "output": 0.001},
    "glm-4-flash": {"input": 0.0001, "output": 0.0001},
}


def estimate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float | None:
    """估算单次 API 调用成本（USD）。未知模型返回 None。"""
    pricing = _PRICING.get(model)
    if pricing is None:
        return None
    return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1000


# ---- 会话级 Token 追踪器 ----


@dataclass
class UsageRecord:
    """单次 LLM 调用的 token 用量记录。"""

    timestamp: float
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float | None = None


@dataclass
class SessionTokenTracker:
    """会话级 token 消耗追踪器。"""

    session_id: str
    records: list[UsageRecord] = field(default_factory=list)

    def record(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> UsageRecord:
        """记录一次 LLM 调用的 token 消耗。"""
        cost = estimate_cost(model, input_tokens, output_tokens)
        rec = UsageRecord(
            timestamp=time.time(),
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
        )
        self.records.append(rec)
        return rec

    @property
    def total_input_tokens(self) -> int:
        return sum(r.input_tokens for r in self.records)

    @property
    def total_output_tokens(self) -> int:
        return sum(r.output_tokens for r in self.records)

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    @property
    def total_cost_usd(self) -> float:
        return sum(r.cost_usd or 0.0 for r in self.records)

    @property
    def call_count(self) -> int:
        return len(self.records)

    def to_dict(self) -> dict[str, Any]:
        """导出为可序列化的统计摘要。"""
        return {
            "session_id": self.session_id,
            "call_count": self.call_count,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "records": [
                {
                    "timestamp": r.timestamp,
                    "model": r.model,
                    "input_tokens": r.input_tokens,
                    "output_tokens": r.output_tokens,
                    "cost_usd": round(r.cost_usd, 6) if r.cost_usd is not None else None,
                }
                for r in self.records[-50:]  # 最近 50 条
            ],
        }


# ---- 全局会话追踪器注册表 ----

_trackers: dict[str, SessionTokenTracker] = {}


def get_tracker(session_id: str) -> SessionTokenTracker:
    """获取或创建会话 token 追踪器。"""
    if session_id not in _trackers:
        _trackers[session_id] = SessionTokenTracker(session_id=session_id)
    return _trackers[session_id]


def remove_tracker(session_id: str) -> None:
    """移除会话追踪器。"""
    _trackers.pop(session_id, None)


# ---- 成本透明化增强 ----


@dataclass
class TokenUsage:
    """单次 Token 使用记录（兼容新测试）。"""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    model: str

    def estimate_cost(self) -> float:
        """估算本次使用的成本（USD）。"""
        return (
            estimate_cost(
                self.model,
                self.prompt_tokens,
                self.completion_tokens,
            )
            or 0.0
        )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "model": self.model,
            "cost_estimate": round(self.estimate_cost(), 6),
        }


class TokenTracker:
    """Token 追踪器（支持预算限制和实时更新）。"""

    def __init__(self, budget_limit: float | None = None):
        """初始化追踪器。

        Args:
            budget_limit: 预算限制（USD），None 表示无限制
        """
        self._budget_limit = budget_limit
        self._total_tokens = 0
        self._total_cost = 0.0
        self._models_used: dict[str, int] = {}
        self._usage_records: list[TokenUsage] = []

    @property
    def total_tokens(self) -> int:
        return self._total_tokens

    @property
    def total_cost(self) -> float:
        return self._total_cost

    def record_usage(self, usage: TokenUsage) -> None:
        """记录 Token 使用。"""
        self._usage_records.append(usage)
        self._total_tokens += usage.total_tokens
        self._total_cost += usage.estimate_cost()

        # 记录模型使用次数
        self._models_used[usage.model] = self._models_used.get(usage.model, 0) + 1

    def reset(self) -> None:
        """重置追踪器。"""
        self._total_tokens = 0
        self._total_cost = 0.0
        self._models_used = {}
        self._usage_records = []

    def is_over_budget(self) -> bool:
        """检查是否超出预算。"""
        if self._budget_limit is None:
            return False
        return self._total_cost >= self._budget_limit

    def get_budget_usage_percent(self) -> float:
        """获取预算使用百分比。"""
        if self._budget_limit is None or self._budget_limit == 0:
            return 0.0
        return self._total_cost / self._budget_limit

    def get_progress_info(self) -> dict[str, Any]:
        """获取进度信息（用于实时更新 UI）。"""
        return {
            "tokens_used": self._total_tokens,
            "cost_usd": round(self._total_cost, 6),
            "budget_limit": self._budget_limit,
            "budget_percent": round(self.get_budget_usage_percent() * 100, 2),
            "over_budget": self.is_over_budget(),
            "models_used": dict(self._models_used),
            "record_count": len(self._usage_records),
        }

    def get_warning_level(self) -> str:
        """获取警告级别。"""
        if self.is_over_budget():
            return "critical"
        percent = self.get_budget_usage_percent()
        if percent >= 0.9:
            return "warning"
        if percent >= 0.7:
            return "caution"
        return "normal"


# 向后兼容：使用 SessionTokenTracker 作为主要接口
class BudgetAwareTokenTracker(SessionTokenTracker):
    """支持预算限制的 Token 追踪器。"""

    def __init__(self, session_id: str, budget_limit: float | None = None):
        """初始化追踪器。

        Args:
            session_id: 会话 ID
            budget_limit: 预算限制（USD）
        """
        super().__init__(session_id=session_id)
        self._budget_limit = budget_limit

    @property
    def budget_limit(self) -> float | None:
        return self._budget_limit

    @property
    def budget_usage_percent(self) -> float:
        """获取预算使用百分比。"""
        if self._budget_limit is None or self._budget_limit == 0:
            return 0.0
        return min(self.total_cost_usd / self._budget_limit, 1.0)

    @property
    def is_over_budget(self) -> bool:
        """检查是否超出预算。"""
        if self._budget_limit is None:
            return False
        return self.total_cost_usd >= self._budget_limit

    @property
    def warning_level(self) -> str:
        """获取警告级别。"""
        if self.is_over_budget:
            return "critical"
        if self.budget_usage_percent >= 0.9:
            return "warning"
        if self.budget_usage_percent >= 0.7:
            return "caution"
        return "normal"

    def to_dict(self) -> dict[str, Any]:
        """导出统计（包含预算信息）。"""
        base = super().to_dict()
        base.update(
            {
                "budget_limit": self._budget_limit,
                "budget_usage_percent": round(self.budget_usage_percent * 100, 2),
                "warning_level": self.warning_level,
                "is_over_budget": self.is_over_budget,
            }
        )
        return base
