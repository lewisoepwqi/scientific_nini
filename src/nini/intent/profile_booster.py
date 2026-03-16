"""用户画像意图加权。"""

from __future__ import annotations

from dataclasses import replace

from nini.intent.base import IntentCandidate
from nini.models.user_profile import UserProfile

_MAX_BOOST_DELTA = 3.0
_BOOST_FACTOR = 3.0

_CAPABILITY_METHOD_MAP: dict[str, list[str]] = {
    "difference_analysis": [
        "t_test",
        "anova",
        "mann_whitney",
        "kruskal_wallis",
        "paired_t_test",
        "independent_t_test",
        "one_way_anova",
    ],
    "correlation_analysis": ["pearson", "spearman", "kendall", "correlation"],
    "regression_analysis": [
        "linear_regression",
        "logistic_regression",
        "multiple_regression",
    ],
    "data_exploration": ["data_summary", "preview_data", "data_quality"],
    "data_cleaning": ["clean_data", "dataset_transform"],
    "visualization": ["create_chart", "export_chart"],
    "report_generation": ["generate_report", "export_report"],
    "article_draft": [],
    "citation_management": [],
    "peer_review": [],
    "research_planning": [],
}


def _compute_delta(capability_name: str, user_profile: UserProfile) -> float:
    """计算单个能力的画像加权分数。"""
    methods = _CAPABILITY_METHOD_MAP.get(capability_name, [])
    if not methods:
        return 0.0

    preferred_methods = user_profile.preferred_methods or {}
    weight_sum = sum(preferred_methods.get(method, 0.0) for method in methods)
    return min(weight_sum * _BOOST_FACTOR, _MAX_BOOST_DELTA)


def apply_boost(
    candidates: list[IntentCandidate], user_profile: UserProfile
) -> list[IntentCandidate]:
    """基于用户画像返回新的候选排序，不修改原对象。"""
    boosted = [
        replace(
            candidate,
            score=candidate.score + _compute_delta(candidate.name, user_profile),
        )
        for candidate in candidates
    ]
    return sorted(boosted, key=lambda item: item.score, reverse=True)
