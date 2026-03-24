"""Token 统计与成本监控。

基于 tiktoken 实现精确的 token 计数，支持会话级别的
token 消耗追踪和 API 成本估算。
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nini.config import settings

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
# 价格来源：官方定价，保持与 pricing.yaml 一致
# 汇率：1 USD = 7.2 CNY（2025年参考）

# 兜底价格配置（当模型无定价时使用）
FALLBACK_PRICING = {"input": 0.001, "output": 0.002}  # 默认 $0.001/$0.002 per 1K tokens
FALLBACK_MODEL_NAME = "default"

_PRICING: dict[str, dict[str, float]] = {
    # ==================== OpenAI 模型 ====================
    # GPT-4o 系列
    "gpt-4o": {"input": 0.0025, "output": 0.01},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4o-latest": {"input": 0.0025, "output": 0.01},
    # GPT-4 系列
    "gpt-4-turbo": {"input": 0.01, "output": 0.03},
    "gpt-4": {"input": 0.03, "output": 0.06},
    "gpt-4-32k": {"input": 0.06, "output": 0.12},
    # GPT-3.5 系列
    "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
    "gpt-3.5-turbo-16k": {"input": 0.001, "output": 0.002},
    # O1 系列 (推理模型)
    "o1": {"input": 0.015, "output": 0.06},
    "o1-mini": {"input": 0.0011, "output": 0.0044},
    "o3-mini": {"input": 0.0011, "output": 0.0044},
    # ==================== Anthropic 模型 ====================
    # Claude 3.5 系列
    "claude-sonnet-4-20250514": {"input": 0.003, "output": 0.015},
    "claude-3-5-sonnet-20241022": {"input": 0.003, "output": 0.015},
    "claude-3-5-sonnet-latest": {"input": 0.003, "output": 0.015},
    # Claude 3 系列
    "claude-3-opus-20240229": {"input": 0.015, "output": 0.075},
    "claude-3-sonnet-20240229": {"input": 0.003, "output": 0.015},
    "claude-3-haiku-20240307": {"input": 0.00025, "output": 0.00125},
    "claude-3-haiku-latest": {"input": 0.00025, "output": 0.00125},
    # Claude 2 系列
    "claude-2": {"input": 0.008, "output": 0.024},
    "claude-2-1": {"input": 0.008, "output": 0.024},
    "claude-instant-1": {"input": 0.0008, "output": 0.0024},
    # ==================== Google Gemini 模型 ====================
    "gemini-2-0-flash": {"input": 0.0001, "output": 0.0004},
    "gemini-2-0-flash-lite": {"input": 0.000075, "output": 0.0003},
    "gemini-1-5-flash": {"input": 0.000075, "output": 0.0003},
    "gemini-1-5-pro": {"input": 0.00125, "output": 0.005},
    "gemini-1-0-pro": {"input": 0.0005, "output": 0.0015},
    "gemini-pro": {"input": 0.0005, "output": 0.0015},
    # ==================== DeepSeek 模型 ====================
    "deepseek-chat": {"input": 0.00014, "output": 0.00028},
    "deepseek-v3": {"input": 0.00014, "output": 0.00028},
    "deepseek-coder": {"input": 0.00014, "output": 0.00028},
    "deepseek-coder-v2": {"input": 0.00014, "output": 0.00028},
    "deepseek-reasoner": {"input": 0.00055, "output": 0.00219},
    "deepseek-r1": {"input": 0.00055, "output": 0.00219},
    # ==================== 百度文心一言 ====================
    "ernie-4-0": {"input": 0.0167, "output": 0.0167},
    "ernie-bot-4": {"input": 0.0167, "output": 0.0167},
    "ernie-3-5": {"input": 0.00167, "output": 0.00167},
    "ernie-bot": {"input": 0.00167, "output": 0.00167},
    "ernie-speed": {"input": 0.0, "output": 0.0},
    "ernie-lite": {"input": 0.0, "output": 0.0},
    # ==================== 字节豆包 ====================
    "doubao-pro": {"input": 0.00011, "output": 0.00028},
    "doubao-pro-32k": {"input": 0.00011, "output": 0.00028},
    "doubao-pro-128k": {"input": 0.00011, "output": 0.00028},
    "doubao-lite": {"input": 0.000042, "output": 0.000084},
    "doubao-lite-32k": {"input": 0.000042, "output": 0.000084},
    # ==================== 讯飞星火 ====================
    "spark-4-0": {"input": 0.00417, "output": 0.00417},
    "spark-4": {"input": 0.00417, "output": 0.00417},
    "spark-3-5": {"input": 0.00208, "output": 0.00208},
    "spark-3-5-max": {"input": 0.00208, "output": 0.00208},
    "spark-pro": {"input": 0.00111, "output": 0.00111},
    "spark-lite": {"input": 0.0, "output": 0.0},
    # ==================== 阿里百炼 (Qwen) ====================
    "qwen-plus": {"input": 0.0008, "output": 0.002},
    "qwen-turbo": {"input": 0.0003, "output": 0.0006},
    "qwen-max": {"input": 0.0024, "output": 0.0096},
    "qwen-max-latest": {"input": 0.0024, "output": 0.0096},
    # Qwen3 系列
    "qwen3-235b-a22b": {"input": 0.0, "output": 0.0},
    "qwen3-32b": {"input": 0.00007, "output": 0.00028},
    "qwen3-30b-a3b": {"input": 0.0, "output": 0.0},
    "qwen3-14b": {"input": 0.000028, "output": 0.00014},
    "qwen3-8b": {"input": 0.0, "output": 0.00007},
    "qwen3-4b": {"input": 0.0, "output": 0.0},
    "qwen3-1-5b": {"input": 0.0, "output": 0.0},
    "qwen3-0-5b": {"input": 0.0, "output": 0.0},
    # ==================== 智谱 (GLM) ====================
    "glm-4": {"input": 0.001, "output": 0.001},
    "glm-4-flash": {"input": 0.0001, "output": 0.0001},
    "glm-4-plus": {"input": 0.005, "output": 0.005},
    "glm-4.5": {"input": 0.005, "output": 0.005},
    "glm-4.6": {"input": 0.008, "output": 0.008},
    "glm-4.7": {"input": 0.012, "output": 0.012},
    "glm-4.5-air": {"input": 0.0005, "output": 0.0005},
    # GLM-5 系列 (2025年最新)
    "glm-5": {"input": 0.0004, "output": 0.0015},
    "glm-5-plus": {"input": 0.0008, "output": 0.003},
    "glm-5-air": {"input": 0.0005, "output": 0.0005},
    # ==================== Moonshot (Kimi) ====================
    "moonshot-v1-8k": {"input": 0.0006, "output": 0.0006},
    "moonshot-v1-32k": {"input": 0.0006, "output": 0.0006},
    "moonshot-v1-128k": {"input": 0.0006, "output": 0.0006},
    "kimi-k2-0711-preview": {"input": 0.001, "output": 0.002},
    "kimi-for-coding": {"input": 0.0006, "output": 0.0006},
    "kimi-coding": {"input": 0.0006, "output": 0.0006},
    # ==================== MiniMax ====================
    "minimax-text-01": {"input": 0.0001, "output": 0.0001},
    "MiniMax-M2.5": {"input": 0.0001, "output": 0.0001},
    "MiniMax-M2.1": {"input": 0.0001, "output": 0.0001},
    "abab6.5s-chat": {"input": 0.0001, "output": 0.0001},
    # ==================== Ollama (本地模型，免费) ====================
    "ollama": {"input": 0.0, "output": 0.0},
    "qwen2.5:7b": {"input": 0.0, "output": 0.0},
    "llama3:8b": {"input": 0.0, "output": 0.0},
    "mistral:7b": {"input": 0.0, "output": 0.0},
}


def estimate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    use_fallback: bool = True,
) -> tuple[float | None, str]:
    """估算单次 API 调用成本（USD）。

    支持精确匹配和模糊匹配：
    1. 先尝试精确匹配
    2. 再尝试去掉版本后缀（如日期）的匹配
    3. 最后尝试前缀匹配

    Args:
        model: 模型名称
        input_tokens: 输入 token 数量
        output_tokens: 输出 token 数量
        use_fallback: 是否使用兜底价格（默认 True）

    Returns:
        tuple: (成本 USD, 状态信息)
              状态信息包括："exact"(精确匹配), "fuzzy"(模糊匹配), "fallback"(兜底价格), "unknown"(未知)
    """
    if not model or model == "unknown":
        if use_fallback:
            cost = (
                input_tokens * FALLBACK_PRICING["input"]
                + output_tokens * FALLBACK_PRICING["output"]
            ) / 1000
            logger.warning(f"[Cost] 模型名称无效，使用兜底价格: model={model}, cost=${cost:.6f}")
            return cost, "fallback"
        return None, "unknown"

    # 1. 精确匹配
    pricing = _PRICING.get(model)
    if pricing:
        cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1000
        return cost, "exact"

    # 2. 尝试去掉版本日期后缀（如 -20250514）
    import re

    base_model = re.sub(r"-\d{8}$", "", model)
    if base_model != model:
        pricing = _PRICING.get(base_model)
        if pricing:
            cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1000
            logger.debug(f"[Cost] 使用基础模型价格: {model} -> {base_model}, cost=${cost:.6f}")
            return cost, "fuzzy"

    # 3. 尝试前缀匹配（如 glm-4.5-xxx 匹配 glm-4.5）
    for key in sorted(_PRICING.keys(), key=len, reverse=True):  # 长的先匹配
        if model.startswith(key) or key.startswith(model.split("-")[0] if "-" in model else model):
            pricing = _PRICING[key]
            cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1000
            logger.debug(f"[Cost] 使用前缀匹配价格: {model} -> {key}, cost=${cost:.6f}")
            return cost, "fuzzy"

    # 4. 特殊处理 kimi-for-coding 等变体
    model_lower = model.lower()
    for key in _PRICING:
        if key.lower() in model_lower or model_lower in key.lower():
            pricing = _PRICING[key]
            cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1000
            logger.debug(f"[Cost] 使用包含匹配价格: {model} -> {key}, cost=${cost:.6f}")
            return cost, "fuzzy"

    # 5. 使用兜底价格
    if use_fallback:
        cost = (
            input_tokens * FALLBACK_PRICING["input"] + output_tokens * FALLBACK_PRICING["output"]
        ) / 1000
        logger.warning(
            f"[Cost] 模型 '{model}' 无定价配置，使用兜底价格: input=${FALLBACK_PRICING['input']}, output=${FALLBACK_PRICING['output']} per 1K tokens, cost=${cost:.6f}"
        )
        return cost, "fallback"

    logger.warning(f"[Cost] 模型 '{model}' 无定价配置，跳过成本计算")
    return None, "unknown"


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
    _persist_enabled: bool = field(default=True, repr=False)

    def __post_init__(self) -> None:
        """初始化后从磁盘加载历史记录。"""
        if self._persist_enabled:
            self._load_from_disk()

    def _get_cost_file_path(self) -> Path:
        """获取成本记录文件路径。"""
        return settings.sessions_dir / self.session_id / "cost.jsonl"

    def _load_from_disk(self) -> None:
        """从磁盘加载历史成本记录。"""
        cost_file = self._get_cost_file_path()
        if not cost_file.exists():
            return

        try:
            with open(cost_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        rec = UsageRecord(
                            timestamp=data.get("timestamp", time.time()),
                            model=data.get("model", "unknown"),
                            input_tokens=data.get("input_tokens", 0),
                            output_tokens=data.get("output_tokens", 0),
                            cost_usd=data.get("cost_usd"),
                        )
                        self.records.append(rec)
                    except (json.JSONDecodeError, KeyError, TypeError):
                        continue
            logger.debug(f"Loaded {len(self.records)} cost records for session {self.session_id}")
        except Exception as exc:
            logger.warning(f"Failed to load cost history for session {self.session_id}: {exc}")

    def _append_to_disk(self, rec: UsageRecord) -> None:
        """追加单条记录到磁盘。"""
        if not self._persist_enabled:
            return

        try:
            cost_file = self._get_cost_file_path()
            cost_file.parent.mkdir(parents=True, exist_ok=True)

            record_line = json.dumps(
                {
                    "timestamp": rec.timestamp,
                    "model": rec.model,
                    "input_tokens": rec.input_tokens,
                    "output_tokens": rec.output_tokens,
                    "cost_usd": rec.cost_usd,
                },
                ensure_ascii=False,
            )

            with open(cost_file, "a", encoding="utf-8") as f:
                f.write(record_line + "\n")
        except Exception as exc:
            logger.warning(f"Failed to persist cost record for session {self.session_id}: {exc}")

    def record(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> UsageRecord:
        """记录一次 LLM 调用的 token 消耗。"""
        cost, status = estimate_cost(model, input_tokens, output_tokens)
        rec = UsageRecord(
            timestamp=time.time(),
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
        )
        # 如果是兜底价格，在记录中标记
        if status == "fallback":
            rec.model = f"{model} (fallback)"
        self.records.append(rec)
        self._append_to_disk(rec)
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
class TokenRecord:
    """单次 Token 使用记录（兼容新测试）。"""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    model: str

    def estimate_cost(self) -> float:
        """估算本次使用的成本（USD）。"""
        cost, _status = estimate_cost(
            self.model,
            self.prompt_tokens,
            self.completion_tokens,
        )
        return cost or 0.0

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
        self._usage_records: list[TokenRecord] = []

    @property
    def total_tokens(self) -> int:
        return self._total_tokens

    @property
    def total_cost(self) -> float:
        return self._total_cost

    def record_usage(self, usage: TokenRecord) -> None:
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
