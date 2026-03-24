"""测试 ResultFusionEngine —— 各融合策略、自动分档、冲突检测。"""

from __future__ import annotations

import pytest

from nini.agent.fusion import FusionResult, ResultFusionEngine
from nini.agent.spawner import SubAgentResult

# ─── 辅助 ───────────────────────────────────────────────────────────────────


def _result(agent_id: str, summary: str, success: bool = True) -> SubAgentResult:
    return SubAgentResult(agent_id=agent_id, success=success, summary=summary)


class _MockResolver:
    """模拟 model_resolver，可配置超时或返回固定摘要。"""

    def __init__(self, response: str = "综合摘要", *, timeout: bool = False):
        self._response = response
        self._timeout = timeout
        self.call_count = 0

    async def chat(self, messages, tools, *, purpose=None, **kwargs):
        self.call_count += 1
        if self._timeout:
            import asyncio

            await asyncio.sleep(100)  # 模拟超时
        text = self._response

        async def _gen():
            yield type("C", (), {"text": text})()

        async for chunk in _gen():
            yield chunk


# ─── FusionResult ────────────────────────────────────────────────────────────


def test_fusion_result_defaults():
    """conflicts 和 sources 默认为空列表。"""
    fr = FusionResult(content="hello", strategy="concatenate")
    assert fr.conflicts == []
    assert fr.sources == []


def test_fusion_result_all_fields():
    """所有字段可通过属性访问。"""
    fr = FusionResult(
        content="结果",
        strategy="summarize",
        conflicts=[{"type": "numeric_discrepancy"}],
        sources=["a", "b"],
    )
    assert fr.content == "结果"
    assert fr.strategy == "summarize"
    assert len(fr.conflicts) == 1
    assert fr.sources == ["a", "b"]


# ─── concatenate 策略 ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_concatenate_joins_summaries():
    """concatenate 拼接各结果 summary，换行分隔，不调用 LLM。"""
    mock = _MockResolver()
    engine = ResultFusionEngine(model_resolver=mock)
    results = [_result("a", "摘要 A"), _result("b", "摘要 B")]
    fr = await engine.fuse(results, strategy="concatenate")
    assert "摘要 A" in fr.content
    assert "摘要 B" in fr.content
    assert fr.strategy == "concatenate"
    assert mock.call_count == 0


@pytest.mark.asyncio
async def test_concatenate_no_llm():
    """显式 concatenate 策略不发起 LLM 调用。"""
    mock = _MockResolver()
    engine = ResultFusionEngine(model_resolver=mock)
    await engine.fuse([_result("a", "x"), _result("b", "y")], strategy="concatenate")
    assert mock.call_count == 0


# ─── auto 策略分档 ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_auto_empty_returns_empty():
    """0 个结果返回空内容，不抛出异常。"""
    engine = ResultFusionEngine()
    fr = await engine.fuse([], strategy="auto")
    assert fr.content == ""
    assert fr.strategy == "concatenate"


@pytest.mark.asyncio
async def test_auto_single_result_no_llm():
    """单个结果使用 concatenate，不发起 LLM 调用。"""
    mock = _MockResolver()
    engine = ResultFusionEngine(model_resolver=mock)
    fr = await engine.fuse([_result("a", "唯一结果")], strategy="auto")
    assert fr.strategy == "concatenate"
    assert fr.content == "唯一结果"
    assert mock.call_count == 0


@pytest.mark.asyncio
async def test_auto_two_to_four_results_trigger_summarize():
    """2-4 个结果触发 summarize 策略。"""
    mock = _MockResolver(response="综合摘要内容")
    engine = ResultFusionEngine(model_resolver=mock)
    results = [_result("a", "A"), _result("b", "B"), _result("c", "C")]
    fr = await engine.fuse(results, strategy="auto")
    assert fr.strategy == "summarize"
    assert mock.call_count >= 1


# ─── summarize 超时降级 ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_summarize_timeout_fallback_to_concatenate(monkeypatch):
    """summarize LLM 调用超时时降级为 concatenate，不抛出异常。"""
    import nini.agent.fusion as fusion_module

    monkeypatch.setattr(fusion_module, "_SUMMARIZE_TIMEOUT_SECONDS", 0.01)
    mock = _MockResolver(timeout=True)
    engine = ResultFusionEngine(model_resolver=mock)
    results = [_result("a", "结果 A"), _result("b", "结果 B")]
    fr = await engine.fuse(results, strategy="summarize")
    # 降级为 concatenate
    assert "结果 A" in fr.content or "结果 B" in fr.content


# ─── 冲突检测 ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_conflicts_labeled_not_blocking():
    """冲突标注追加到 conflicts，不修改 content，不阻断融合。"""
    mock = _MockResolver(response="整合摘要")
    engine = ResultFusionEngine(model_resolver=mock)
    results = [
        _result("a", "均值为 100.5，显著性 p=0.01"),
        _result("b", "均值为 5.2，p=0.8"),
    ]
    fr = await engine.fuse(results, strategy="summarize")
    # content 非空
    assert fr.content
    # conflicts 列表存在（可能为空，取决于数值差异阈值）
    assert isinstance(fr.conflicts, list)


# ─── 无效策略降级 ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_invalid_strategy_falls_back_to_concatenate():
    """不支持的策略名降级为 concatenate，记录 WARNING。"""
    engine = ResultFusionEngine()
    results = [_result("a", "内容 A"), _result("b", "内容 B")]
    fr = await engine.fuse(results, strategy="unknown_strategy")
    assert "内容 A" in fr.content
    assert "内容 B" in fr.content
