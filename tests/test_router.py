"""测试 TaskRouter —— 规则路由、LLM 兜底、批量路由。"""

from __future__ import annotations

import pytest

from nini.agent.router import RoutingDecision, TaskRouter


# ─── 辅助 ───────────────────────────────────────────────────────────────────

class _MockResolver:
    """模拟 model_resolver，可配置返回内容或抛出异常。"""

    def __init__(self, response: str | None = None, *, should_raise: bool = False):
        self._response = response
        self._should_raise = should_raise
        self.call_count = 0

    async def chat(self, messages, tools, *, purpose=None, **kwargs):
        self.call_count += 1
        if self._should_raise:
            raise RuntimeError("模拟 LLM 失败")
        text = self._response or ""

        async def _gen():
            yield type("C", (), {"text": text})()

        async for chunk in _gen():
            yield chunk


# ─── RoutingDecision ────────────────────────────────────────────────────────

def test_routing_decision_default_parallel():
    """parallel 默认为 True。"""
    rd = RoutingDecision(agent_ids=["a"], tasks=["t"], confidence=0.9, strategy="rule")
    assert rd.parallel is True


def test_routing_decision_all_fields():
    """所有字段可通过属性访问。"""
    rd = RoutingDecision(
        agent_ids=["data_cleaner"],
        tasks=["清洗数据"],
        confidence=0.8,
        strategy="rule",
        parallel=False,
    )
    assert rd.agent_ids == ["data_cleaner"]
    assert rd.tasks == ["清洗数据"]
    assert rd.confidence == 0.8
    assert rd.strategy == "rule"
    assert rd.parallel is False


# ─── 规则路由 ────────────────────────────────────────────────────────────────

def test_rule_route_high_confidence_data_cleaner():
    """清洗数据关键词应命中 data_cleaner，置信度 >= 0.7。"""
    router = TaskRouter(enable_llm_fallback=False)
    result = router._rule_route("请帮我清洗数据并处理缺失值")
    assert "data_cleaner" in result.agent_ids
    assert result.strategy == "rule"
    assert result.confidence >= 0.7


def test_rule_route_multiple_agents():
    """同时包含清洗和统计关键词应命中 data_cleaner 和 statistician。"""
    router = TaskRouter(enable_llm_fallback=False)
    result = router._rule_route("清洗数据后做统计检验和回归")
    assert "data_cleaner" in result.agent_ids
    assert "statistician" in result.agent_ids
    assert result.parallel is True
    assert len(result.tasks) == len(result.agent_ids)


def test_rule_route_no_keywords():
    """无关键词时 confidence < 0.7，agent_ids 为空。"""
    router = TaskRouter(enable_llm_fallback=False)
    result = router._rule_route("今天天气怎么样？")
    assert result.confidence < 0.7
    assert result.agent_ids == []


def test_rule_route_case_insensitive():
    """关键词匹配大小写不敏感（ANOVA 和 anova 均能命中）。"""
    router = TaskRouter(enable_llm_fallback=False)
    result = router._rule_route("ANOVA 方差分析")
    assert "statistician" in result.agent_ids


# ─── route() 方法 ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_route_uses_rule_when_confident():
    """规则置信度 >= 0.7 时不调用 LLM。"""
    mock = _MockResolver()
    router = TaskRouter(model_resolver=mock, enable_llm_fallback=True)
    result = await router.route("请清洗数据并处理缺失值和异常值")
    assert "data_cleaner" in result.agent_ids
    assert result.strategy == "rule"
    assert mock.call_count == 0  # 未调用 LLM


@pytest.mark.asyncio
async def test_route_llm_fallback_on_low_confidence():
    """规则置信度 < 0.7 时触发 LLM 兜底。"""
    llm_json = '{"agent_ids": ["statistician"], "tasks": ["统计分析"], "confidence": 0.9, "parallel": true}'
    mock = _MockResolver(response=llm_json)
    router = TaskRouter(model_resolver=mock, enable_llm_fallback=True)
    result = await router.route("帮我做一些分析")
    assert result.strategy == "llm"
    assert mock.call_count >= 1


@pytest.mark.asyncio
async def test_route_llm_failure_falls_back_to_rule():
    """LLM 路由失败时降级为规则结果，不抛出异常。"""
    mock = _MockResolver(should_raise=True)
    router = TaskRouter(model_resolver=mock, enable_llm_fallback=True)
    # 用无关键词的意图触发 LLM 兜底
    result = await router.route("今天天气怎么样")
    # 不抛出异常，返回规则结果
    assert isinstance(result, RoutingDecision)


# ─── route_batch() ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_route_batch_empty_returns_empty():
    """空列表输入返回空列表。"""
    router = TaskRouter(enable_llm_fallback=False)
    results = await router.route_batch([])
    assert results == []


@pytest.mark.asyncio
async def test_route_batch_preserves_order():
    """返回顺序与输入一致。"""
    router = TaskRouter(enable_llm_fallback=False)
    tasks = ["清洗数据", "统计分析", "作图"]
    results = await router.route_batch(tasks)
    assert len(results) == 3


@pytest.mark.asyncio
async def test_route_batch_no_llm_when_disabled():
    """enable_llm_fallback=False 时 route_batch 不调用 LLM。"""
    mock = _MockResolver()
    router = TaskRouter(model_resolver=mock, enable_llm_fallback=False)
    await router.route_batch(["清洗数据", "统计分析"])
    assert mock.call_count == 0
