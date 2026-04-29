"""会话标题生成测试。"""

from __future__ import annotations

import pytest

from nini.agent import title_generator


class _DummyResponse:
    """模拟 LLM 响应。"""

    def __init__(
        self,
        text: str | None,
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
async def test_generate_title_fallback_when_chat_complete_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """当 optional 调用全链失败返回 None 时应走规则兜底。"""

    async def _fake_chat_complete(*args, **kwargs):  # type: ignore[no-untyped-def]
        return None

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


def test_trim_title_length_prefers_prefix_boundary() -> None:
    """本地截断应优先按分隔符保留前半段标题。"""

    title = title_generator._trim_title_length("实验结果分析：方差检验与回归建模")

    assert title == "实验结果分析"


def test_fallback_title_removes_url() -> None:
    """回退标题应清理 URL。"""

    messages = [{"role": "user", "content": "请分析 https://example.com/demo 数据趋势"}]

    title = title_generator._fallback_title(messages)

    assert title is not None
    assert "http" not in title


def test_fallback_title_skips_generic_greeting() -> None:
    """回退标题应跳过寒暄，提取后续真实意图。"""

    messages = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好，我在。"},
        {"role": "user", "content": "请帮我分析 GDP 数据并画图"},
    ]

    title = title_generator._fallback_title(messages)

    assert title == "分析 GDP 数据并画图"


@pytest.mark.asyncio
async def test_generate_title_calls_optional_once_when_length_raw_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """raw_empty + length 时不再重试，而是直接走规则兜底。"""

    call_count = 0
    captured_kwargs: dict[str, object] = {}

    async def _fake_chat_complete(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal call_count
        call_count += 1
        captured_kwargs.update(kwargs)
        if call_count == 1:
            return _DummyResponse(
                "",
                finish_reason="length",
                usage={"input_tokens": 240, "output_tokens": 50},
            )
        return _DummyResponse("不应发生")

    monkeypatch.setattr(title_generator.model_resolver, "chat_complete", _fake_chat_complete)

    messages = [
        {
            "role": "user",
            "content": "请对这一组实验样本做完整统计分析并给出图表。"
            + "这是一段很长的补充说明文字用于测试截断逻辑。" * 10,
        },
        {
            "role": "assistant",
            "content": "好的，我先进行数据清洗和描述统计。"
            + "接下来我会逐步分析每一列数据的分布特征。" * 10,
        },
    ]

    title = await title_generator.generate_title(messages)

    assert title == title_generator._fallback_title(messages)
    assert call_count == 1
    assert captured_kwargs["purpose"] == "title_generation"
    assert captured_kwargs["optional"] is True


@pytest.mark.asyncio
async def test_generate_title_trims_long_model_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """模型返回超长标题时应优先本地裁剪，而不是依赖重试。"""

    async def _fake_chat_complete(*args, **kwargs):  # type: ignore[no-untyped-def]
        return _DummyResponse("实验结果分析：方差检验与回归建模")

    monkeypatch.setattr(title_generator.model_resolver, "chat_complete", _fake_chat_complete)

    messages = [
        {"role": "user", "content": "请帮我分析实验结果并总结统计结论"},
    ]

    title = await title_generator.generate_title(messages)

    assert title == "实验结果分析"


@pytest.mark.asyncio
async def test_generate_title_prompt_uses_shorter_user_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """标题提示词应优先使用少量用户消息并缩短上下文。"""

    captured_prompt = ""

    async def _fake_chat_complete(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal captured_prompt
        captured_prompt = args[0][0]["content"]
        return _DummyResponse("实验结果分析")

    monkeypatch.setattr(title_generator.model_resolver, "chat_complete", _fake_chat_complete)

    messages = [
        {"role": "user", "content": "第一条用户问题。" + "补充说明" * 40},
        {"role": "assistant", "content": "第一条助手回复。" + "回复细节" * 40},
        {"role": "user", "content": "第二条用户问题。" + "更多背景" * 40},
        {"role": "assistant", "content": "第二条助手回复。" + "更多结果" * 40},
    ]

    title = await title_generator.generate_title(messages)

    assert title == "实验结果分析"
    assert "用户:" in captured_prompt
    assert captured_prompt.count("用户:") == 2
    assert "助手:" not in captured_prompt
    assert "回复细节回复细节回复细节回复细节回复细节回复细节" not in captured_prompt


@pytest.mark.asyncio
async def test_generate_title_does_not_retry_when_not_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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


@pytest.mark.asyncio
async def test_generate_title_returns_none_when_messages_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """无可用消息时应直接返回 None。"""

    async def _fake_chat_complete(*args, **kwargs):  # type: ignore[no-untyped-def]
        return _DummyResponse("不应调用")

    monkeypatch.setattr(title_generator.model_resolver, "chat_complete", _fake_chat_complete)

    assert await title_generator.generate_title([]) is None


@pytest.mark.asyncio
async def test_generate_title_returns_none_when_only_generic_greeting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """只有寒暄时不应生成空泛标题。"""

    async def _fake_chat_complete(*args, **kwargs):  # type: ignore[no-untyped-def]
        return _DummyResponse("", finish_reason="stop")

    monkeypatch.setattr(title_generator.model_resolver, "chat_complete", _fake_chat_complete)

    messages = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好，请问有什么可以帮你？"},
    ]

    title = await title_generator.generate_title(messages)

    assert title is None
