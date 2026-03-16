"""Phase 3 意图监控与画像测试。"""

from __future__ import annotations

import json
import logging

import pytest

from nini.capabilities import create_default_capabilities
from nini.intent.base import IntentCandidate
from nini.intent.optimized import OptimizedIntentAnalyzer
from nini.intent.profile_booster import _compute_delta, apply_boost
from nini.models.user_profile import UserProfile

_CAPABILITIES = [cap.to_dict() for cap in create_default_capabilities()]


def _make_profile(preferred_methods: dict[str, float] | None = None) -> UserProfile:
    """构造测试用用户画像。"""
    return UserProfile(user_id="user-1", preferred_methods=preferred_methods or {})


def test_compute_delta_uses_preferred_methods_weight() -> None:
    """5.1 difference_analysis 应从方法偏好中获得正向加权。"""
    profile = _make_profile({"t_test": 0.8})
    assert _compute_delta("difference_analysis", profile) > 0


def test_apply_boost_keeps_order_for_empty_profile() -> None:
    """5.2 空画像不应改变候选顺序和分数。"""
    candidates = [
        IntentCandidate(name="difference_analysis", score=6.0, reason="test"),
        IntentCandidate(name="correlation_analysis", score=4.0, reason="test"),
    ]

    boosted = apply_boost(candidates, _make_profile())

    assert [candidate.name for candidate in boosted] == [candidate.name for candidate in candidates]
    assert [candidate.score for candidate in boosted] == [
        candidate.score for candidate in candidates
    ]


def test_apply_boost_does_not_mutate_original_candidates() -> None:
    """5.3 apply_boost 不应修改原始候选对象。"""
    candidates = [
        IntentCandidate(name="difference_analysis", score=5.0, reason="test"),
        IntentCandidate(name="correlation_analysis", score=4.5, reason="test"),
    ]

    boosted = apply_boost(candidates, _make_profile({"t_test": 0.8}))

    assert candidates[0].score == 5.0
    assert boosted[0] is not candidates[0]
    assert boosted[0].score > candidates[0].score


def test_low_confidence_query_emits_structured_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """5.4 低置信度查询应写入结构化日志。"""
    analyzer = OptimizedIntentAnalyzer()
    analyzer.initialize(_CAPABILITIES)

    with caplog.at_level(logging.INFO, logger="nini.intent.lowconf"):
        analysis = analyzer.analyze("完全陌生的科研描述短语")

    assert analysis.capability_candidates == []
    records = [record for record in caplog.records if record.name == "nini.intent.lowconf"]
    assert records

    payload = json.loads(records[-1].message)
    assert payload["query"] == "完全陌生的科研描述短语"
    assert payload["top_score"] == 0.0
    assert payload["timestamp"]


def test_high_confidence_query_does_not_emit_lowconf_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """5.5 高置信度查询不应写入低置信度日志。"""
    analyzer = OptimizedIntentAnalyzer()
    analyzer.initialize(_CAPABILITIES)

    with caplog.at_level(logging.INFO, logger="nini.intent.lowconf"):
        analysis = analyzer.analyze("帮我做两组样本的t检验")

    assert analysis.capability_candidates
    assert analysis.capability_candidates[0].score >= 3.0
    assert not [record for record in caplog.records if record.name == "nini.intent.lowconf"]
