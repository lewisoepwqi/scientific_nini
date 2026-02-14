"""会话标题生成测试。"""

from __future__ import annotations

import pytest

from nini.agent import title_generator


class _DummyResponse:
    """模拟 LLM 响应。"""

    def __init__(
        self,
        text: str,
        *,
        finish_reason: str | None = None,
        finish_reasons: list[str] | None = None,
        usage: dict[str, int] | None = None,
        tool_calls: list[dict[str, object]] | None = None,
    ) -> None:
        self.text = text
        self.finish_reason = finish_reason
        self.finish_reasons = finish_reasons or ([] if finish_reason is None else [finish_reason])
        self.usage = usage or {}
        self.tool_calls = tool_calls or []


@pytest.mark.asyncio
async def test_generate_title_fallback_when_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """当 LLM 为空时应回退到规则标题。"""

    async def _fake_chat_complete(*args, **kwargs):  # type: ignore[no-untyped-def]
        return _DummyResponse("")

    monkeypatch.setattr(title_generator.model_resolver, "chat_complete", _fake_chat_complete)

    messages = [
        {"role": "user", "content": "分析 GDP 数据并画图"},
        {"role": "assistant", "content": "好的，我们开始处理数据。"},
    ]

    title = await title_generator.generate_title(messages)

    assert title == "分析 GDP 数据并画图"


@pytest.mark.asyncio
async def test_generate_title_normalizes_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """应规范化 LLM 输出并返回标题本体。"""

    async def _fake_chat_complete(*args, **kwargs):  # type: ignore[no-untyped-def]
        return _DummyResponse("标题：实验结果分析")

    monkeypatch.setattr(title_generator.model_resolver, "chat_complete", _fake_chat_complete)

    messages = [
        {"role": "user", "content": "请帮我分析实验结果。"},
        {"role": "assistant", "content": "好的。"},
    ]

    title = await title_generator.generate_title(messages)

    assert title == "实验结果分析"


def test_normalize_title_strips_english_prefix_with_dash() -> None:
    """应去掉 title 前缀后的连接符。"""

    title = title_generator._normalize_title("title - 实验结果分析")

    assert title == "实验结果分析"


def test_fallback_title_removes_url() -> None:
    """回退标题应清理 URL。"""

    messages = [{"role": "user", "content": "请分析 https://example.com/demo 数据趋势"}]

    title = title_generator._fallback_title(messages)

    assert title is not None
    assert "http" not in title


@pytest.mark.asyncio
async def test_generate_title_retry_once_when_length_raw_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """raw_empty + length 时应触发一次重试。"""

    call_count = 0
    prompt_lengths: list[int] = []

    async def _fake_chat_complete(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal call_count
        call_count += 1
        req_messages = args[0]
        prompt_lengths.append(len(req_messages[0]["content"]))
        if call_count == 1:
            return _DummyResponse(
                "",
                finish_reason="length",
                usage={"input_tokens": 240, "output_tokens": 50},
            )
        return _DummyResponse(
            "实验结果分析",
            finish_reason="stop",
            usage={"input_tokens": 120, "output_tokens": 12},
        )

    monkeypatch.setattr(title_generator.model_resolver, "chat_complete", _fake_chat_complete)

    messages = [
        {"role": "user", "content": "请对这一组实验样本做完整统计分析并给出图表。"},
        {"role": "assistant", "content": "好的，我先进行数据清洗和描述统计。"},
    ]

    title = await title_generator.generate_title(messages)

    assert title == "实验结果分析"
    assert call_count == 2
    assert prompt_lengths[1] < prompt_lengths[0]


@pytest.mark.asyncio
async def test_generate_title_no_retry_when_not_length(monkeypatch: pytest.MonkeyPatch) -> None:
    """非 length 空返回不应重试。"""

    call_count = 0

    async def _fake_chat_complete(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal call_count
        call_count += 1
        return _DummyResponse(
            "",
            finish_reason="stop",
            usage={"input_tokens": 90, "output_tokens": 0},
        )

    monkeypatch.setattr(title_generator.model_resolver, "chat_complete", _fake_chat_complete)

    messages = [
        {"role": "user", "content": "开始分析数据"},
        {"role": "assistant", "content": "好的，我们开始。"},
    ]

    title = await title_generator.generate_title(messages)

    assert title == "开始分析数据"
    assert call_count == 1
