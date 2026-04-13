"""意图评估基线测试。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from nini.capabilities import create_default_capabilities
from nini.intent.base import QueryType
from nini.intent.service import IntentAnalyzer

_DATASET_PATH = Path(__file__).parent / "fixtures" / "intent_eval_dataset.yaml"
_CAPABILITIES = [cap.to_dict() for cap in create_default_capabilities()]


def _load_cases() -> list[dict[str, Any]]:
    """加载 YAML 评估数据集。"""
    with _DATASET_PATH.open(encoding="utf-8") as handle:
        cases = yaml.safe_load(handle) or []
    assert isinstance(cases, list)
    return cases


_CASES = _load_cases()
_DOMAIN_CASES = [case for case in _CASES if case["query_type"] == "domain_task"]
_OOS_CASES = [case for case in _CASES if case["query_type"] == "out_of_scope"]
_domain_results: list[bool] = []
_oos_results: list[bool] = []


@pytest.fixture(scope="module")
def analyzer() -> IntentAnalyzer:
    """提供已初始化的优化版意图分析器。"""
    analyzer = IntentAnalyzer()
    analyzer.initialize(_CAPABILITIES)
    return analyzer


@pytest.fixture(scope="session", autouse=True)
def intent_eval_reporter():
    """在测试结束后打印基线指标。"""
    yield
    if _domain_results:
        print(
            f"intent eval domain top1 accuracy: {sum(_domain_results) / len(_domain_results):.2%}"
        )
    if _oos_results:
        print(f"intent eval oos recall: {sum(_oos_results) / len(_oos_results):.2%}")


@pytest.mark.parametrize("case", _DOMAIN_CASES, ids=lambda case: case["query"][:30])
def test_intent_eval_domain_top1(analyzer: IntentAnalyzer, case: dict[str, Any]) -> None:
    """域内查询应命中标注的 Top-1 能力。"""
    analysis = analyzer.analyze(case["query"])
    top1 = analysis.capability_candidates[0].name if analysis.capability_candidates else None
    _domain_results.append(top1 == case["expected_top1"])
    assert top1 == case["expected_top1"]


@pytest.mark.parametrize("case", _OOS_CASES, ids=lambda case: case["query"][:30])
def test_intent_eval_out_of_scope(analyzer: IntentAnalyzer, case: dict[str, Any]) -> None:
    """OOS 查询应被识别为超出支持范围。"""
    analysis = analyzer.analyze(case["query"])
    matched = analysis.query_type == QueryType.OUT_OF_SCOPE
    _oos_results.append(matched)
    assert analysis.query_type == QueryType.OUT_OF_SCOPE
