"""测试 HypothesisContext 和 Hypothesis 数据类。"""

import pytest
from nini.agent.hypothesis_context import Hypothesis, HypothesisContext

# ── Hypothesis 默认值 ──────────────────────────────────────────────────────────


def test_hypothesis_defaults():
    """Hypothesis 创建时默认字段正确。"""
    h = Hypothesis(id="h1", content="测试假设")
    assert h.id == "h1"
    assert h.content == "测试假设"
    assert h.confidence == 0.5
    assert h.status == "pending"
    assert h.evidence_for == []
    assert h.evidence_against == []


def test_hypothesis_mutable_defaults_independent():
    """各实例的列表字段互相独立，不共享可变默认值。"""
    h1 = Hypothesis(id="h1", content="假设1")
    h2 = Hypothesis(id="h2", content="假设2")
    h1.evidence_for.append("证据A")
    assert h2.evidence_for == []


# ── HypothesisContext 默认值 ──────────────────────────────────────────────────


def test_context_defaults():
    """HypothesisContext 初始状态正确。"""
    ctx = HypothesisContext()
    assert ctx.hypotheses == []
    assert ctx.current_phase == "generation"
    assert ctx.iteration_count == 0
    assert ctx.max_iterations == 3
    assert ctx._prev_confidences == []


# ── should_conclude：条件 1 硬上限 ────────────────────────────────────────────


def test_should_conclude_hard_cap():
    """iteration_count >= max_iterations 时收敛（条件 1）。"""
    ctx = HypothesisContext(max_iterations=3)
    ctx.iteration_count = 3
    assert ctx.should_conclude() is True


def test_should_conclude_not_hard_cap():
    """iteration_count < max_iterations 且无其他条件时不收敛。"""
    ctx = HypothesisContext(max_iterations=3)
    ctx.iteration_count = 2
    ctx.hypotheses = [Hypothesis(id="h1", content="待验证")]
    assert ctx.should_conclude() is False


# ── should_conclude：条件 2 所有假设已定论 ────────────────────────────────────


def test_should_conclude_all_concluded_validated():
    """所有假设 status 为 validated 时收敛（条件 2）。"""
    ctx = HypothesisContext(max_iterations=5)
    ctx.iteration_count = 1
    ctx.hypotheses = [
        Hypothesis(id="h1", content="假设1", status="validated"),
        Hypothesis(id="h2", content="假设2", status="validated"),
    ]
    assert ctx.should_conclude() is True


def test_should_conclude_all_concluded_refuted():
    """所有假设 status 为 refuted 时收敛（条件 2）。"""
    ctx = HypothesisContext(max_iterations=5)
    ctx.iteration_count = 1
    ctx.hypotheses = [
        Hypothesis(id="h1", content="假设1", status="refuted"),
    ]
    assert ctx.should_conclude() is True


def test_should_conclude_mixed_concluded():
    """部分 validated + 部分 refuted，全部已定论时收敛（条件 2）。"""
    ctx = HypothesisContext(max_iterations=5)
    ctx.iteration_count = 1
    ctx.hypotheses = [
        Hypothesis(id="h1", content="假设1", status="validated"),
        Hypothesis(id="h2", content="假设2", status="refuted"),
    ]
    assert ctx.should_conclude() is True


def test_should_not_conclude_pending_exists():
    """存在 pending 假设时条件 2 不满足。"""
    ctx = HypothesisContext(max_iterations=5)
    ctx.iteration_count = 1
    ctx.hypotheses = [
        Hypothesis(id="h1", content="假设1", status="validated"),
        Hypothesis(id="h2", content="假设2", status="pending"),
    ]
    assert ctx.should_conclude() is False


def test_should_not_conclude_empty_hypotheses_condition2():
    """空假设列表时条件 2 不触发收敛。"""
    ctx = HypothesisContext(max_iterations=5)
    ctx.iteration_count = 1
    ctx.hypotheses = []
    assert ctx.should_conclude() is False


# ── should_conclude：条件 3 贝叶斯收敛 ────────────────────────────────────────


def test_should_conclude_bayesian_convergence():
    """所有假设置信度变化 < 0.05 时收敛（条件 3）。"""
    ctx = HypothesisContext(max_iterations=5)
    ctx.iteration_count = 1
    ctx.hypotheses = [
        Hypothesis(id="h1", content="假设1", confidence=0.70),
        Hypothesis(id="h2", content="假设2", confidence=0.30),
    ]
    # 变化 < 0.05
    ctx._prev_confidences = [0.68, 0.31]
    assert ctx.should_conclude() is True


def test_should_not_conclude_large_delta():
    """置信度变化 >= 0.05 时条件 3 不满足。"""
    ctx = HypothesisContext(max_iterations=5)
    ctx.iteration_count = 1
    ctx.hypotheses = [
        Hypothesis(id="h1", content="假设1", confidence=0.70),
    ]
    ctx._prev_confidences = [0.50]  # delta = 0.20
    assert ctx.should_conclude() is False


def test_should_not_conclude_mismatched_prev_confidences():
    """_prev_confidences 数量与 hypotheses 不一致时条件 3 不触发。"""
    ctx = HypothesisContext(max_iterations=5)
    ctx.iteration_count = 1
    ctx.hypotheses = [
        Hypothesis(id="h1", content="假设1", confidence=0.70),
        Hypothesis(id="h2", content="假设2", confidence=0.30),
    ]
    ctx._prev_confidences = [0.70]  # 只有 1 个，不匹配
    assert ctx.should_conclude() is False


# ── update_confidence 边界 clamp ──────────────────────────────────────────────


def test_update_confidence_for():
    """支持证据 +0.15。"""
    ctx = HypothesisContext()
    ctx.hypotheses = [Hypothesis(id="h1", content="假设1", confidence=0.5)]
    ctx.update_confidence("h1", "for")
    assert abs(ctx.hypotheses[0].confidence - 0.65) < 1e-9


def test_update_confidence_against():
    """反驳证据 -0.20。"""
    ctx = HypothesisContext()
    ctx.hypotheses = [Hypothesis(id="h1", content="假设1", confidence=0.5)]
    ctx.update_confidence("h1", "against")
    assert abs(ctx.hypotheses[0].confidence - 0.30) < 1e-9


def test_update_confidence_clamp_upper():
    """置信度上限 clamp 为 1.0。"""
    ctx = HypothesisContext()
    ctx.hypotheses = [Hypothesis(id="h1", content="假设1", confidence=0.95)]
    ctx.update_confidence("h1", "for")
    assert ctx.hypotheses[0].confidence == 1.0


def test_update_confidence_clamp_lower():
    """置信度下限 clamp 为 0.0。"""
    ctx = HypothesisContext()
    ctx.hypotheses = [Hypothesis(id="h1", content="假设1", confidence=0.10)]
    ctx.update_confidence("h1", "against")
    assert ctx.hypotheses[0].confidence == 0.0


def test_update_confidence_saves_prev_snapshot():
    """update_confidence 调用前保存 _prev_confidences 快照。"""
    ctx = HypothesisContext()
    ctx.hypotheses = [
        Hypothesis(id="h1", content="假设1", confidence=0.5),
        Hypothesis(id="h2", content="假设2", confidence=0.7),
    ]
    ctx.update_confidence("h1", "for")
    # 快照应是更新前的值
    assert ctx._prev_confidences == [0.5, 0.7]
    # h1 已更新
    assert abs(ctx.hypotheses[0].confidence - 0.65) < 1e-9
    # h2 未变
    assert ctx.hypotheses[1].confidence == 0.7


def test_update_confidence_unknown_id_no_crash(caplog):
    """不存在的 hypothesis_id 不抛异常，发出 WARNING。"""
    ctx = HypothesisContext()
    ctx.hypotheses = [Hypothesis(id="h1", content="假设1", confidence=0.5)]
    import logging

    with caplog.at_level(logging.WARNING, logger="nini.agent.hypothesis_context"):
        ctx.update_confidence("nonexistent", "for")
    assert "nonexistent" in caplog.text


def test_update_confidence_unknown_type_no_crash(caplog):
    """未知 evidence_type 不抛异常，发出 WARNING，置信度不变。"""
    ctx = HypothesisContext()
    ctx.hypotheses = [Hypothesis(id="h1", content="假设1", confidence=0.5)]
    import logging

    with caplog.at_level(logging.WARNING, logger="nini.agent.hypothesis_context"):
        ctx.update_confidence("h1", "unknown_type")
    assert ctx.hypotheses[0].confidence == 0.5
