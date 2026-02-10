"""会话标题生成测试。"""

from __future__ import annotations

import pytest

from nini.agent import title_generator


class _DummyResponse:
    """模拟 LLM 响应。"""

    def __init__(self, text: str) -> None:
        self.text = text


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
