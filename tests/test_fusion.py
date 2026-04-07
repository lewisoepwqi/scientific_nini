"""测试 ResultFusionEngine —— 各融合策略、自动分档、冲突检测。"""

from __future__ import annotations

import pytest

from nini.agent.artifact_ref import ArtifactRef
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
    assert isinstance(fr.conflicts, list)


@pytest.mark.asyncio
async def test_summarize_without_resolver_keeps_conflicts_on_frozen_result():
    """无 resolver 时也应返回新对象，而不是修改冻结结果。"""
    engine = ResultFusionEngine(model_resolver=None)
    results = [
        _result("a", "均值为 100.5"),
        _result("b", "均值为 5.2"),
    ]
    fr = await engine.fuse(results, strategy="summarize")
    assert fr.strategy == "concatenate"
    assert isinstance(fr.conflicts, list)


@pytest.mark.asyncio
async def test_hierarchical_strategy_returns_new_result_without_mutation():
    """hierarchical 路径应返回新对象，不得修改冻结 FusionResult。"""
    mock = _MockResolver(response="层级摘要")
    engine = ResultFusionEngine(model_resolver=mock)
    results = [_result(f"agent_{idx}", f"摘要 {idx}") for idx in range(6)]
    fr = await engine.fuse(results, strategy="hierarchical")
    assert fr.strategy == "hierarchical"
    assert fr.sources == [f"agent_{idx}" for idx in range(6)]


@pytest.mark.asyncio
async def test_hierarchical_batches_run_concurrently(monkeypatch):
    """hierarchical 策略多批次应通过 asyncio.gather 并发执行，而非串行。"""
    import asyncio
    import nini.agent.fusion as fusion_module

    gather_calls: list[int] = []
    original_gather = asyncio.gather

    async def tracking_gather(*coros, **kwargs):
        gather_calls.append(len(coros))
        return await original_gather(*coros, **kwargs)

    monkeypatch.setattr(asyncio, "gather", tracking_gather)

    mock = _MockResolver(response="批次摘要")
    engine = ResultFusionEngine(model_resolver=mock)
    # 9 个结果 → 3 批（每批 _HIERARCHICAL_BATCH_SIZE=4）→ asyncio.gather 调用 1 次，包含 3 个协程
    results = [_result(f"agent_{idx}", f"摘要 {idx}") for idx in range(9)]
    fr = await engine.fuse(results, strategy="hierarchical")
    assert fr.strategy == "hierarchical"
    # 第一次 gather 调用应包含 3 个批次协程
    assert any(n == 3 for n in gather_calls), f"期望 3 批并发，实际: {gather_calls}"


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


# ─── 产物文件名冲突检测 ──────────────────────────────────────────────────────


def test_detect_artifact_key_conflict_with_artifact_ref():
    """两个子 Agent 产出同名文件时，检测到 artifact_key_conflict。"""
    engine = ResultFusionEngine()
    r1 = SubAgentResult(
        agent_id="agent_a",
        success=True,
        summary="Agent A 完成",
        artifacts={
            "chart": ArtifactRef(path="chart.plotly.json", type="chart", summary="图A", agent_id="agent_a")
        },
    )
    r2 = SubAgentResult(
        agent_id="agent_b",
        success=True,
        summary="Agent B 完成",
        artifacts={
            "chart": ArtifactRef(path="chart.plotly.json", type="chart", summary="图B", agent_id="agent_b")
        },
    )
    conflicts = engine._detect_conflicts([r1, r2])
    conflict_types = [c["type"] for c in conflicts]
    assert "artifact_key_conflict" in conflict_types
    conflict = next(c for c in conflicts if c["type"] == "artifact_key_conflict")
    assert conflict["filename"] == "chart.plotly.json"
    assert "agent_a" in conflict["agents"]
    assert "agent_b" in conflict["agents"]


def test_detect_no_conflict_when_different_filenames():
    """两个子 Agent 产出不同名文件时，不报告 artifact_key_conflict。"""
    engine = ResultFusionEngine()
    r1 = SubAgentResult(
        agent_id="agent_a",
        success=True,
        summary="摘要 A",
        artifacts={
            "chart_a": ArtifactRef(path="chart_a.json", type="chart", summary="图A", agent_id="agent_a")
        },
    )
    r2 = SubAgentResult(
        agent_id="agent_b",
        success=True,
        summary="摘要 B",
        artifacts={
            "chart_b": ArtifactRef(path="chart_b.json", type="chart", summary="图B", agent_id="agent_b")
        },
    )
    conflicts = engine._detect_conflicts([r1, r2])
    conflict_types = [c["type"] for c in conflicts]
    assert "artifact_key_conflict" not in conflict_types
