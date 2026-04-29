"""LLM Provider Base Classes.

Base classes and data structures for LLM providers.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, TypedDict

logger = logging.getLogger(__name__)


def match_first_model(
    available: list[str],
    keyword_groups: list[tuple[str, ...]],
) -> str | None:
    """按偏好顺序从可用模型列表中匹配第一个命中的模型。"""
    normalized_models = [
        (model, model.strip().lower()) for model in available if str(model).strip()
    ]
    for keywords in keyword_groups:
        for original, normalized in normalized_models:
            if all(keyword in normalized for keyword in keywords):
                return original
    return None


@dataclass
class LLMChunk:
    """LLM 流式输出单元。"""

    text: str = ""
    reasoning: str = ""
    # 保留供应商原始输出文本（可能包含 <think> 标签），用于工具调用上下文回放
    raw_text: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str | None = None
    usage: dict[str, int] | None = None
    # 实际执行模型信息（用于前端展示“当前模型/降级模型”）
    provider_id: str | None = None
    provider_name: str | None = None
    model: str | None = None
    attempt: int | None = None
    # 降级轨迹（当首选模型失败并自动切换时）
    fallback_applied: bool = False
    fallback_from_provider_id: str | None = None
    fallback_from_model: str | None = None
    fallback_reason: str | None = None
    fallback_chain: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class LLMResponse:
    """LLM 完整响应（由流式 chunk 聚合而来）。"""

    text: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    # 记录流式聚合后的终止原因，便于上层诊断空输出/截断等问题
    finish_reason: str | None = None
    finish_reasons: list[str] = field(default_factory=list)


class PurposeRoute(TypedDict):
    """用途路由配置。"""

    provider_id: str | None
    model: str | None
    base_url: str | None


class ReasoningStreamParser:
    """统一解析各供应商"思考内容"输出并处理流式累计片段。"""

    _TAG_PAIRS: tuple[tuple[str, str], ...] = (
        ("<think>", "</think>"),
        ("<thinking>", "</thinking>"),
        ("◁think▷", "◁/think▷"),
    )

    def __init__(self, *, enable_tag_split: bool = False):
        self._enable_tag_split = enable_tag_split
        self._raw_snapshot = ""
        self._text_snapshot = ""
        self._reasoning_snapshot = ""
        self._pending = ""
        self._tag_state: tuple[str, str] | None = None

    @staticmethod
    def _normalize_stream_piece(piece: str, snapshot: str) -> tuple[str, str]:
        """兼容增量流和累计流两种分片格式，防止内容重复。"""
        if not piece:
            return "", snapshot

        # 累计片段：当前值是历史完整前缀，返回增量部分
        if snapshot and piece.startswith(snapshot):
            return piece[len(snapshot) :], piece

        # 检查反向情况：如果 snapshot 以 piece 开头，可能是重复发送
        if snapshot and snapshot.startswith(piece) and len(piece) < len(snapshot):
            # piece 是 snapshot 的前缀，说明是重复内容，返回空
            return "", snapshot

        # 检查 piece 是否完全等于 snapshot 的最后部分（部分重复）
        if snapshot and len(piece) <= len(snapshot):
            # 检查 piece 是否匹配 snapshot 的末尾
            if snapshot.endswith(piece):
                # piece 是 snapshot 的末尾部分，说明是重复
                return "", snapshot

        # 默认按"增量分片"处理
        return piece, snapshot + piece

    @staticmethod
    def _to_text(value: Any) -> str:
        """将 reasoning 相关字段统一转成文本。"""
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, (int, float, bool)):
            return str(value)
        if isinstance(value, dict):
            for key in ("text", "content", "reasoning_content", "reasoning"):
                nested = value.get(key)
                if isinstance(nested, str) and nested:
                    return nested
        return ""

    @staticmethod
    def strip_reasoning_markers(text: str) -> str:
        """去除推理标记（<think> 等）。"""
        import re

        pattern = r"<\/?think>|<\/?thinking>|◁think▷|◁\/think▷"
        return re.sub(pattern, "", text, flags=re.IGNORECASE)

    @staticmethod
    def extract_reasoning_from_delta(delta: Any) -> str:
        """从 OpenAI 兼容 API 的 delta 对象中提取 reasoning 内容。

        支持多种 reasoning 字段命名规范：
        - reasoning_content (DeepSeek 等)
        - reasoning (OpenAI o1 等)
        - thinking (部分国产模型)

        Args:
            delta: OpenAI API 返回的 delta 对象

        Returns:
            reasoning 内容字符串，如果没有则返回空字符串
        """
        if delta is None:
            return ""

        # 尝试各种可能的 reasoning 字段名
        for attr in ("reasoning_content", "reasoning", "thinking"):
            value = getattr(delta, attr, None)
            if value and isinstance(value, str):
                return str(value)

        return ""

    def _pending_prefix_len(self, text: str) -> int:
        """计算需要挂起的后缀长度（不完整的标签前缀）。"""
        for open_tag, _ in self._TAG_PAIRS:
            for i in range(1, min(len(open_tag), len(text) + 1)):
                if text[-i:] == open_tag[:i]:
                    return i
        return 0

    def _split_reasoning_tags(self, text: str) -> tuple[str, str]:
        """从文本中分离 reasoning 标签包裹的内容。"""
        if not text:
            return "", ""

        text_out: list[str] = []
        reasoning_out: list[str] = []
        cursor = self._pending + text
        self._pending = ""

        while cursor:
            if self._tag_state is None:
                # 寻找下一个开启标签
                tag_hit = None
                for open_tag, close_tag in self._TAG_PAIRS:
                    idx = cursor.find(open_tag)
                    if idx >= 0:
                        if tag_hit is None or idx < tag_hit[0]:
                            tag_hit = (idx, (open_tag, close_tag))

                if tag_hit is None:
                    # 没有开启标签
                    hold = self._pending_prefix_len(cursor)
                    if hold > 0:
                        text_out.append(cursor[:-hold])
                        self._pending = cursor[-hold:]
                    else:
                        text_out.append(cursor)
                    break

                open_idx, pair = tag_hit
                if open_idx > 0:
                    text_out.append(cursor[:open_idx])
                cursor = cursor[open_idx + len(pair[0]) :]
                self._tag_state = pair
                continue

            _, close_tag = self._tag_state
            close_idx = cursor.find(close_tag)
            if close_idx < 0:
                hold = self._pending_prefix_len(cursor)
                if hold > 0:
                    reasoning_out.append(cursor[:-hold])
                    self._pending = cursor[-hold:]
                else:
                    reasoning_out.append(cursor)
                break

            if close_idx > 0:
                reasoning_out.append(cursor[:close_idx])
            cursor = cursor[close_idx + len(close_tag) :]
            self._tag_state = None

        return "".join(text_out), "".join(reasoning_out)

    def consume(
        self, *, raw_piece: str, explicit_reasoning_piece: str = ""
    ) -> tuple[str, str, str]:
        """消费一次 chunk，返回（text_delta, reasoning_delta, raw_delta）。"""
        raw_delta, self._raw_snapshot = self._normalize_stream_piece(raw_piece, self._raw_snapshot)
        explicit_reasoning_delta, self._reasoning_snapshot = self._normalize_stream_piece(
            explicit_reasoning_piece,
            self._reasoning_snapshot,
        )

        text_candidate = raw_delta
        tagged_reasoning = ""
        if self._enable_tag_split and raw_delta:
            text_candidate, tagged_reasoning = self._split_reasoning_tags(raw_delta)
            if tagged_reasoning and self._reasoning_snapshot:
                tagged_reasoning = self.strip_reasoning_markers(tagged_reasoning)

        if self._reasoning_snapshot:
            # 当供应商已返回 reasoning 字段时，content 中出现的 think 标记属于冗余噪音
            text_candidate = self.strip_reasoning_markers(text_candidate)

        reasoning_candidate = explicit_reasoning_delta or tagged_reasoning
        text_delta, self._text_snapshot = self._normalize_stream_piece(
            text_candidate,
            self._text_snapshot,
        )
        if explicit_reasoning_delta and tagged_reasoning:
            # 少数模型会同时返回 reasoning_content + 带标签 content，此时避免重复叠加
            tagged_reasoning = ""
        if tagged_reasoning:
            # 将标签解析出的 reasoning 追加到 snapshot，但 delta 只返回新增部分
            prev_len = len(self._reasoning_snapshot)
            combined = self._reasoning_snapshot + tagged_reasoning
            self._reasoning_snapshot = combined
            reasoning_candidate = combined[prev_len:]

        reasoning_delta, _ = self._normalize_stream_piece(
            reasoning_candidate,
            "",
        )
        return text_delta, reasoning_delta, raw_delta


class BaseLLMClient(ABC):
    """LLM 客户端抽象基类。"""

    provider_id: str = ""
    provider_name: str = ""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        reasoning_effort: str | None = None,
    ) -> AsyncGenerator[LLMChunk, None]:
        """流式聊天接口。

        Args:
            reasoning_effort: 推理深度控制（如 "none"/"low"/"medium"/"high"），
                仅对支持 reasoning 控制的 provider 生效。
        """
        ...  # pragma: no cover
        # 确保类型检查器知道这是个 async generator
        yield LLMChunk()  # type: ignore[misc]

    @abstractmethod
    def is_available(self) -> bool:
        """检查客户端是否可用（API Key 是否配置等）。"""
        ...

    def get_model_name(self) -> str:
        """获取当前使用的模型名称。"""
        return getattr(self, "_model", "") or ""

    def pick_model_for_purpose(self, purpose: str) -> str | None:
        """返回指定用途偏好的模型名；None 表示沿用主模型。"""
        return None

    async def aclose(self) -> None:
        """关闭底层 HTTP 客户端，释放连接资源。

        子类应覆盖此方法以关闭各自的 SDK 客户端。
        不调用此方法不会导致功能异常，但可能产生 GC 阶段的
        'AsyncHttpxClientWrapper' 属性缺失警告。
        """
