"""第二条 autoresearch-harness 线的聚合与账本测试。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from nini.config import settings
from nini.harness.autoresearch import (
    _auto_answer_questions,
    append_to_tsv,
    compare_against_baseline,
    compute_tool_call_quality,
    evaluate_benchmark_set_from_summaries,
    load_benchmark_set,
    load_last_keep,
    prepare_benchmark_resolver,
    prepare_benchmark_resolver_with_override,
    resolve_benchmark_case,
    run_benchmark_set_async,
)
from nini.harness.models import (
    HarnessRunContext,
    HarnessTaskMetrics,
    HarnessTraceRecord,
    ToolCallEntry,
)
from nini.harness.store import HarnessTraceStore
from nini.models.database import init_db
from nini.agent import event_builders as eb


@pytest.mark.asyncio
async def test_evaluate_benchmark_set_from_summaries_collects_latest_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()
    await init_db()

    benchmark_path = tmp_path / "benchmarks.yaml"
    benchmark_path.write_text(
        """
version: nini_harness_v1
sets:
  smoke:
    description: 测试集
    cases:
      - benchmark_id: literature_review_success
        recipe_id: literature_review
        expected_status: completed
        required: true
      - benchmark_id: experiment_plan_success
        recipe_id: experiment_plan
        expected_status: completed
        required: true
      - benchmark_id: results_interpretation_success
        recipe_id: results_interpretation
        expected_status: completed
        required: true
""".strip(),
        encoding="utf-8",
    )
    definition = load_benchmark_set("smoke", config_path=benchmark_path)
    store = HarnessTraceStore()

    record_old = HarnessTraceRecord(
        run_id="run_old_lit",
        session_id="session_demo",
        turn_id="turn_old_lit",
        user_message="请执行文献综述",
        run_context=HarnessRunContext(turn_id="turn_old_lit", recipe_id="literature_review"),
        recipe_id="literature_review",
        status="blocked",
        failure_tags=["tool_loop"],
        summary={"input_tokens": 100, "output_tokens": 30, "estimated_cost_usd": 0.2},
        task_metrics=HarnessTaskMetrics(tool_call_count=7),
        started_at="2026-04-03T00:00:00+00:00",
        finished_at="2026-04-03T00:00:05+00:00",
    )
    record_new = HarnessTraceRecord(
        run_id="run_new_lit",
        session_id="session_demo",
        turn_id="turn_new_lit",
        user_message="请执行文献综述",
        run_context=HarnessRunContext(turn_id="turn_new_lit", recipe_id="literature_review"),
        recipe_id="literature_review",
        status="completed",
        summary={
            "input_tokens": 120,
            "output_tokens": 40,
            "estimated_cost_usd": 0.1,
            "prompt_audit": {
                "profile": "standard",
                "truncated": True,
                "total_tokens_before": 6593,
                "total_tokens_after": 2988,
                "token_budget": 3000,
            },
        },
        task_metrics=HarnessTaskMetrics(tool_call_count=5),
        started_at="2026-04-03T00:00:10+00:00",
        finished_at="2026-04-03T00:00:20+00:00",
    )
    record_exp = HarnessTraceRecord(
        run_id="run_exp",
        session_id="session_demo",
        turn_id="turn_exp",
        user_message="请制定实验计划",
        run_context=HarnessRunContext(turn_id="turn_exp", recipe_id="experiment_plan"),
        recipe_id="experiment_plan",
        status="blocked",
        failure_tags=["artifact_missing"],
        summary={
            "input_tokens": 90,
            "output_tokens": 20,
            "estimated_cost_usd": 0.15,
            "prompt_audit": {
                "profile": "standard",
                "truncated": True,
                "total_tokens_before": 6593,
                "total_tokens_after": 2988,
                "token_budget": 3000,
            },
        },
        task_metrics=HarnessTaskMetrics(tool_call_count=4),
        started_at="2026-04-03T00:00:30+00:00",
        finished_at="2026-04-03T00:00:36+00:00",
    )

    await store.save_run(record_old)
    await store.save_run(record_new)
    await store.save_run(record_exp)

    summaries = await store.list_runs(session_id="session_demo", limit=10)
    metrics = evaluate_benchmark_set_from_summaries(
        definition=definition,
        summaries=summaries,
        store=store,
        session_id="session_demo",
    )

    assert metrics["pass_count"] == 1
    assert metrics["blocked_count"] == 1
    assert metrics["failure_count"] == 2
    assert metrics["pass_rate"] == 0.3333
    assert metrics["blocked_rate"] == 0.3333
    assert metrics["median_tool_calls"] == 4.5
    assert metrics["prompt_profiles"] == ["standard"]
    assert metrics["prompt_truncated_runs"] == 2
    assert metrics["prompt_truncation_rate"] == 0.6667
    assert metrics["median_prompt_tokens_before"] == 6593
    assert metrics["median_prompt_tokens_after"] == 2988
    assert metrics["median_prompt_token_budget"] == 3000
    assert metrics["failure_tags"] == ["artifact_missing", "benchmark:missing"]
    latest_literature = next(
        item for item in metrics["sample_results"] if item["recipe_id"] == "literature_review"
    )
    assert latest_literature["run_id"] == "run_new_lit"


def test_compare_against_baseline_marks_regression_and_new_tags() -> None:
    metrics = {
        "pass_count": 1,
        "blocked_count": 1,
        "failure_count": 2,
        "pass_rate": 0.3333,
        "blocked_rate": 0.3333,
        "median_cost_usd": 0.12,
        "median_duration_s": 8.0,
        "median_input_tokens": 120,
        "median_output_tokens": 40,
        "median_tool_calls": 5,
        "prompt_truncated_runs": 1,
        "prompt_truncation_rate": 0.3333,
        "failure_tags": ["artifact_missing", "benchmark:missing"],
    }
    baseline = {
        "pass_count": "2",
        "blocked_count": "0",
        "failure_count": "1",
        "pass_rate": "0.6667",
        "blocked_rate": "0.0",
        "median_cost_usd": "0.10",
        "median_duration_s": "7",
        "median_input_tokens": "100",
        "median_output_tokens": "30",
        "median_tool_calls": "4",
        "prompt_truncated_runs": "0",
        "prompt_truncation_rate": "0.0",
        "new_failure_tags": json.dumps(["artifact_missing"], ensure_ascii=False),
    }

    result = compare_against_baseline(metrics, baseline)

    assert result["suggestion"] == "discard"
    assert result["new_failure_tags"] == ["benchmark:missing"]
    assert result["prompt_truncation_mismatch"] is True


def test_compare_against_baseline_avoids_keep_on_prompt_truncation_mismatch() -> None:
    metrics = {
        "pass_count": 2,
        "blocked_count": 0,
        "failure_count": 1,
        "pass_rate": 0.6667,
        "blocked_rate": 0.0,
        "median_cost_usd": 0.09,
        "median_duration_s": 6.0,
        "median_input_tokens": 90,
        "median_output_tokens": 25,
        "median_tool_calls": 4,
        "prompt_truncated_runs": 3,
        "prompt_truncation_rate": 1.0,
        "failure_tags": ["artifact_missing"],
    }
    baseline = {
        "pass_count": "2",
        "blocked_count": "0",
        "failure_count": "1",
        "pass_rate": "0.6667",
        "blocked_rate": "0.0",
        "median_cost_usd": "0.10",
        "median_duration_s": "7",
        "median_input_tokens": "100",
        "median_output_tokens": "30",
        "median_tool_calls": "4",
        "prompt_truncated_runs": "0",
        "prompt_truncation_rate": "0.0",
        "new_failure_tags": json.dumps(["artifact_missing"], ensure_ascii=False),
    }

    result = compare_against_baseline(metrics, baseline)

    assert result["prompt_truncation_mismatch"] is True
    assert result["suggestion"] == "review"


def test_harness_results_append_and_load_keep(tmp_path: Path) -> None:
    results_path = tmp_path / "harness_results.tsv"
    metrics = {
        "metric_version": "nini_harness_v1",
        "benchmark_set": "smoke",
        "pass_count": 2,
        "blocked_count": 0,
        "failure_count": 1,
        "pass_rate": 0.6667,
        "blocked_rate": 0.0,
        "median_duration_s": 7,
        "median_cost_usd": 0.1,
        "median_input_tokens": 100,
        "median_output_tokens": 30,
        "median_tool_calls": 4,
        "prompt_profiles": ["standard"],
        "prompt_truncated_runs": 3,
        "prompt_truncation_rate": 1.0,
        "median_prompt_tokens_before": 6593,
        "median_prompt_tokens_after": 2988,
        "median_prompt_token_budget": 3000,
    }

    append_to_tsv(
        metrics=metrics,
        commit="abc123",
        changed_files="src/nini/agent/prompt_policy.py",
        summary="测试",
        status="keep",
        results_tsv=results_path,
        new_failure_tags=["artifact_missing"],
    )

    loaded = load_last_keep(
        results_tsv=results_path,
        metric_version="nini_harness_v1",
        benchmark_set="smoke",
    )

    assert loaded is not None
    assert loaded["commit"] == "abc123"
    assert loaded["benchmark_set"] == "smoke"
    assert loaded["prompt_truncated_runs"] == "3"
    assert loaded["new_failure_tags"] == json.dumps(["artifact_missing"], ensure_ascii=False)


def test_resolve_benchmark_case_uses_explicit_inputs() -> None:
    definition = load_benchmark_set("smoke")
    case = definition.cases[0]

    resolved = resolve_benchmark_case(case)

    assert resolved["recipe"].recipe_id == case.recipe_id
    assert resolved["user_request"]
    assert resolved["recipe_inputs"]["topic"] == "肠道菌群与抑郁症"
    assert "Recipe 模式" in resolved["rendered_prompt"]


@pytest.mark.asyncio
async def test_prepare_benchmark_resolver_prefers_active_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeResolver:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None, str | None]] = []

        def set_purpose_route(
            self,
            *,
            purpose: str,
            provider_id: str | None = None,
            model: str | None = None,
            base_url: str | None = None,
        ) -> None:
            _ = base_url
            self.calls.append((purpose, provider_id, model))

    async def _fake_reload() -> None:
        return None

    async def _fake_active() -> str | None:
        return "openai"

    async def _fake_configured() -> list[str]:
        return ["openai", "anthropic"]

    resolver = _FakeResolver()
    monkeypatch.setattr("nini.harness.autoresearch.reload_model_resolver", _fake_reload)
    monkeypatch.setattr("nini.harness.autoresearch.get_model_resolver", lambda: resolver)
    monkeypatch.setattr("nini.harness.autoresearch.get_active_provider_id", _fake_active)
    monkeypatch.setattr(
        "nini.harness.autoresearch.list_user_configured_provider_ids",
        _fake_configured,
    )

    prepared = await prepare_benchmark_resolver()

    assert prepared is resolver
    assert resolver.calls == [
        ("planning", "openai", None),
        ("chat", "openai", None),
        ("verification", "openai", None),
    ]


@pytest.mark.asyncio
async def test_prepare_benchmark_resolver_uses_glm5_for_dashscope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeResolver:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None, str | None]] = []

        def set_purpose_route(
            self,
            *,
            purpose: str,
            provider_id: str | None = None,
            model: str | None = None,
            base_url: str | None = None,
        ) -> None:
            _ = base_url
            self.calls.append((purpose, provider_id, model))

    async def _fake_reload() -> None:
        return None

    async def _fake_active() -> str | None:
        return "dashscope"

    async def _fake_configured() -> list[str]:
        return ["dashscope", "zhipu"]

    resolver = _FakeResolver()
    monkeypatch.setattr("nini.harness.autoresearch.reload_model_resolver", _fake_reload)
    monkeypatch.setattr("nini.harness.autoresearch.get_model_resolver", lambda: resolver)
    monkeypatch.setattr("nini.harness.autoresearch.get_active_provider_id", _fake_active)
    monkeypatch.setattr(
        "nini.harness.autoresearch.list_user_configured_provider_ids",
        _fake_configured,
    )

    prepared = await prepare_benchmark_resolver()

    assert prepared is resolver
    assert resolver.calls == [
        ("planning", "dashscope", "glm-5"),
        ("chat", "dashscope", "glm-5"),
        ("verification", "dashscope", "glm-5"),
    ]


@pytest.mark.asyncio
async def test_prepare_benchmark_resolver_falls_back_to_builtin_deep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeResolver:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None, str | None]] = []

        def set_purpose_route(
            self,
            *,
            purpose: str,
            provider_id: str | None = None,
            model: str | None = None,
            base_url: str | None = None,
        ) -> None:
            _ = base_url
            self.calls.append((purpose, provider_id, model))

    async def _fake_reload() -> None:
        return None

    async def _fake_active() -> str | None:
        return None

    async def _fake_configured() -> list[str]:
        return []

    resolver = _FakeResolver()
    monkeypatch.setattr("nini.harness.autoresearch.reload_model_resolver", _fake_reload)
    monkeypatch.setattr("nini.harness.autoresearch.get_model_resolver", lambda: resolver)
    monkeypatch.setattr("nini.harness.autoresearch.get_active_provider_id", _fake_active)
    monkeypatch.setattr(
        "nini.harness.autoresearch.list_user_configured_provider_ids",
        _fake_configured,
    )

    prepared = await prepare_benchmark_resolver()

    assert prepared is resolver
    assert resolver.calls == [
        ("planning", "builtin", "deep"),
        ("chat", "builtin", "deep"),
        ("verification", "builtin", "deep"),
    ]


@pytest.mark.asyncio
async def test_prepare_benchmark_resolver_with_override_applies_glm5(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeResolver:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None, str | None]] = []

        def set_purpose_route(
            self,
            *,
            purpose: str,
            provider_id: str | None = None,
            model: str | None = None,
            base_url: str | None = None,
        ) -> None:
            _ = base_url
            self.calls.append((purpose, provider_id, model))

    async def _fake_prepare() -> _FakeResolver:
        return resolver

    resolver = _FakeResolver()
    monkeypatch.setattr(
        "nini.harness.autoresearch.prepare_benchmark_resolver",
        _fake_prepare,
    )

    prepared = await prepare_benchmark_resolver_with_override(
        provider_id="zhipu",
        model="glm-5",
    )

    assert prepared is resolver
    assert resolver.calls == [
        ("planning", "zhipu", "glm-5"),
        ("chat", "zhipu", "glm-5"),
        ("verification", "zhipu", "glm-5"),
    ]


class _HappyPathRunner:
    async def run(
        self,
        session,
        user_message: str,
        *,
        append_user_message: bool = True,
        stop_event=None,
        turn_id: str | None = None,
        stage_override: str | None = None,
    ):
        _ = user_message, stop_event, stage_override
        assert turn_id is not None
        if append_user_message:
            session.add_message("user", "执行 benchmark", turn_id=turn_id)
        yield eb.build_iteration_start_event(iteration=0, turn_id=turn_id)
        yield eb.build_token_usage_event(
            input_tokens=80,
            output_tokens=20,
            model="demo-model",
            cost_usd=0.08,
            turn_id=turn_id,
        )
        session.add_message("assistant", "benchmark 已完成。", turn_id=turn_id)
        yield eb.build_text_event("benchmark 已完成。", turn_id=turn_id)
        yield eb.build_done_event(turn_id=turn_id)


class _TimeoutThenSuccessRunner:
    async def run(
        self,
        session,
        user_message: str,
        *,
        append_user_message: bool = True,
        stop_event=None,
        turn_id: str | None = None,
        stage_override: str | None = None,
    ):
        _ = user_message, append_user_message, stop_event, stage_override
        assert turn_id is not None
        if session.recipe_id == "literature_review":
            await asyncio.sleep(0.05)
            return
        yield eb.build_iteration_start_event(iteration=0, turn_id=turn_id)
        session.add_message("assistant", "benchmark 已完成。", turn_id=turn_id)
        yield eb.build_done_event(turn_id=turn_id)


@pytest.mark.asyncio
async def test_auto_answer_questions_uses_header_and_first_option_without_id() -> None:
    from nini.agent.session import Session

    session = Session()
    session.bind_recipe_context(
        task_kind="deep_task",
        recipe_id="experiment_plan",
        recipe_inputs={"research_question": "睡眠干预是否能改善焦虑症状"},
    )

    answers = await _auto_answer_questions(
        session,
        "tool-demo",
        {
            "questions": [
                {
                    "header": "干预方式",
                    "question": "睡眠干预的具体方式是什么？",
                    "multiSelect": False,
                    "options": [
                        {"label": "睡眠剥夺模型", "description": "desc"},
                        {"label": "睡眠改善干预", "description": "desc"},
                    ],
                },
                {
                    "header": "终点指标",
                    "question": "除了炎症指标，是否还测量其他终点？",
                    "multiSelect": True,
                    "options": [
                        {"label": "行为学测试", "description": "desc"},
                        {"label": "睡眠质量指标", "description": "desc"},
                    ],
                },
            ]
        },
    )

    assert answers == {
        "干预方式": "睡眠剥夺模型",
        "终点指标": "行为学测试",
    }


@pytest.mark.asyncio
async def test_run_benchmark_set_async_persists_grouped_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()
    await init_db()

    benchmark_path = tmp_path / "benchmarks.yaml"
    benchmark_path.write_text(
        """
version: nini_harness_v1
sets:
  smoke:
    description: 测试集
    cases:
      - benchmark_id: literature_review_success
        recipe_id: literature_review
        expected_status: completed
        required: true
        user_request: 请做文献综述
        recipe_inputs:
          topic: 肠道菌群与抑郁症
      - benchmark_id: experiment_plan_success
        recipe_id: experiment_plan
        expected_status: completed
        required: true
        user_request: 请做实验计划
        recipe_inputs:
          research_question: 睡眠干预是否能改善焦虑症状
""".strip(),
        encoding="utf-8",
    )

    result = await run_benchmark_set_async(
        benchmark_set="smoke",
        config_path=benchmark_path,
        session_id="batch_demo",
        agent_runner=_HappyPathRunner(),
    )

    assert result["session_id"] == "batch_demo"
    assert result["case_count"] == 2


@pytest.mark.asyncio
async def test_run_benchmark_set_async_continues_after_case_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()
    await init_db()

    benchmark_path = tmp_path / "benchmarks.yaml"
    benchmark_path.write_text(
        """
version: nini_harness_v1
sets:
  smoke:
    description: 测试集
    cases:
      - benchmark_id: literature_review_success
        recipe_id: literature_review
        expected_status: completed
        required: true
        user_request: 请做文献综述
      - benchmark_id: experiment_plan_success
        recipe_id: experiment_plan
        expected_status: completed
        required: true
        user_request: 请做实验计划
""".strip(),
        encoding="utf-8",
    )

    result = await run_benchmark_set_async(
        benchmark_set="smoke",
        config_path=benchmark_path,
        session_id="batch_timeout_demo",
        agent_runner=_TimeoutThenSuccessRunner(),
        case_timeout_seconds=0.01,
    )

    assert result["case_count"] == 2
    assert result["cases"][0]["timed_out"] is True
    assert result["cases"][0]["final_event"] == "timeout"
    assert result["cases"][1]["timed_out"] is False
    assert result["cases"][1]["final_event"] == "done"

    store = HarnessTraceStore()
    summaries = await store.list_runs(session_id="batch_timeout_demo", limit=10)
    assert len(summaries) == 2
    assert {item.recipe_id for item in summaries} == {"literature_review", "experiment_plan"}
    status_by_recipe = {item.recipe_id: item.status for item in summaries}
    assert status_by_recipe["literature_review"] in {"blocked", "stopped"}
    assert status_by_recipe["literature_review"] != "error"
    assert status_by_recipe["experiment_plan"] == "completed"


# ---------------------------------------------------------------------------
# 工具调用质量指标测试
# ---------------------------------------------------------------------------


def test_compute_tool_call_quality_perfect_match() -> None:
    """所有期望工具都被调用，无冗余。"""
    sequence = [
        ToolCallEntry(tool_name="search_literature", arguments_hash="aaa"),
        ToolCallEntry(tool_name="task_state", arguments_hash="bbb"),
        ToolCallEntry(tool_name="collect_artifacts", arguments_hash="ccc"),
    ]
    result = compute_tool_call_quality(
        sequence,
        expected_tools=("search_literature", "task_state", "collect_artifacts"),
        mode="subset",
    )
    assert result["tool_precision"] == 1.0
    assert result["tool_recall"] == 1.0
    assert result["tool_f1"] == 1.0
    assert result["redundant_call_rate"] == 0.0
    assert result["first_tool_accuracy"] == 1.0


def test_compute_tool_call_quality_partial_recall() -> None:
    """只调用了部分期望工具。"""
    sequence = [
        ToolCallEntry(tool_name="search_literature", arguments_hash="aaa"),
        ToolCallEntry(tool_name="task_state", arguments_hash="bbb"),
    ]
    result = compute_tool_call_quality(
        sequence,
        expected_tools=("search_literature", "task_state", "collect_artifacts"),
        mode="subset",
    )
    assert result["tool_precision"] == 1.0
    assert result["tool_recall"] == pytest.approx(0.6667, abs=0.001)
    assert result["redundant_call_rate"] == 0.0


def test_compute_tool_call_quality_with_extra_tools() -> None:
    """调用了额外的非期望工具，precision 下降。"""
    sequence = [
        ToolCallEntry(tool_name="search_literature", arguments_hash="aaa"),
        ToolCallEntry(tool_name="stat_test", arguments_hash="bbb"),
        ToolCallEntry(tool_name="task_state", arguments_hash="ccc"),
    ]
    result = compute_tool_call_quality(
        sequence,
        expected_tools=("search_literature", "task_state"),
        mode="subset",
    )
    assert result["tool_precision"] == pytest.approx(0.6667, abs=0.001)
    assert result["tool_recall"] == 1.0


def test_compute_tool_call_quality_with_redundancy() -> None:
    """同工具同参数重复调用。"""
    sequence = [
        ToolCallEntry(tool_name="search_literature", arguments_hash="aaa"),
        ToolCallEntry(tool_name="search_literature", arguments_hash="aaa"),
        ToolCallEntry(tool_name="task_state", arguments_hash="bbb"),
    ]
    result = compute_tool_call_quality(
        sequence,
        expected_tools=("search_literature", "task_state"),
        mode="subset",
    )
    assert result["redundant_call_rate"] == pytest.approx(0.3333, abs=0.001)


def test_compute_tool_call_quality_no_expected_tools() -> None:
    """未定义 expected_tools 时返回 -1 标记。"""
    sequence = [
        ToolCallEntry(tool_name="stat_test", arguments_hash="aaa"),
    ]
    result = compute_tool_call_quality(sequence, expected_tools=(), mode="subset")
    assert result["tool_precision"] == -1.0
    assert result["tool_recall"] == -1.0
    assert result["tool_f1"] == -1.0


def test_compute_tool_call_quality_first_tool_miss() -> None:
    """首次工具选择不在期望集中。"""
    sequence = [
        ToolCallEntry(tool_name="stat_test", arguments_hash="aaa"),
        ToolCallEntry(tool_name="search_literature", arguments_hash="bbb"),
    ]
    result = compute_tool_call_quality(
        sequence,
        expected_tools=("search_literature",),
        mode="subset",
    )
    assert result["first_tool_accuracy"] == 0.0


def test_load_benchmark_set_parses_expected_tools() -> None:
    """确认 YAML 中的 expected_tools 被正确解析。"""
    definition = load_benchmark_set("smoke")
    lit_case = next(c for c in definition.cases if c.recipe_id == "literature_review")
    assert "search_literature" in lit_case.expected_tools
    assert "task_state" in lit_case.expected_tools
    assert lit_case.expected_tools_mode == "subset"


@pytest.mark.asyncio
async def test_evaluate_includes_tool_quality_metrics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """验证聚合评估结果包含工具调用质量指标。"""
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()
    await init_db()

    benchmark_path = tmp_path / "benchmarks.yaml"
    benchmark_path.write_text(
        """
version: nini_harness_v1
sets:
  smoke:
    description: 测试集
    cases:
      - benchmark_id: lit_success
        recipe_id: literature_review
        expected_status: completed
        required: true
        expected_tools:
          - search_literature
          - task_state
        expected_tools_mode: subset
""".strip(),
        encoding="utf-8",
    )
    definition = load_benchmark_set("smoke", config_path=benchmark_path)
    store = HarnessTraceStore()

    record = HarnessTraceRecord(
        run_id="run_quality_test",
        session_id="session_quality",
        turn_id="turn_q",
        user_message="请做文献综述",
        run_context=HarnessRunContext(turn_id="turn_q", recipe_id="literature_review"),
        recipe_id="literature_review",
        status="completed",
        summary={"input_tokens": 100, "output_tokens": 30, "estimated_cost_usd": 0.1},
        task_metrics=HarnessTaskMetrics(
            tool_call_count=3,
            tool_call_sequence=[
                ToolCallEntry(tool_name="search_literature", arguments_hash="a1"),
                ToolCallEntry(tool_name="task_state", arguments_hash="b1"),
                ToolCallEntry(tool_name="collect_artifacts", arguments_hash="c1"),
            ],
        ),
        started_at="2026-04-03T00:00:00+00:00",
        finished_at="2026-04-03T00:00:10+00:00",
    )
    await store.save_run(record)

    summaries = await store.list_runs(session_id="session_quality", limit=10)
    metrics = evaluate_benchmark_set_from_summaries(
        definition=definition,
        summaries=summaries,
        store=store,
        session_id="session_quality",
    )

    assert metrics["median_tool_precision"] == pytest.approx(0.6667, abs=0.001)
    assert metrics["median_tool_recall"] == 1.0
    assert metrics["median_tool_f1"] > 0
    assert metrics["median_redundant_call_rate"] == 0
    assert metrics["first_tool_accuracy"] == 1.0

    # sample_results 中包含 tool_quality
    lit_result = next(r for r in metrics["sample_results"] if r["recipe_id"] == "literature_review")
    assert lit_result["tool_quality"] is not None
    assert lit_result["tool_quality"]["tool_recall"] == 1.0


def test_compare_baseline_includes_tool_f1_delta() -> None:
    """验证 compare_against_baseline 包含 tool_f1 delta。"""
    metrics = {
        "pass_count": 2,
        "blocked_count": 0,
        "failure_count": 1,
        "pass_rate": 0.6667,
        "blocked_rate": 0.0,
        "median_cost_usd": 0.1,
        "median_duration_s": 7.0,
        "median_input_tokens": 100,
        "median_output_tokens": 30,
        "median_tool_calls": 4,
        "median_tool_f1": 0.85,
        "median_tool_precision": 0.8,
        "median_tool_recall": 0.9,
        "median_redundant_call_rate": 0.1,
        "prompt_truncated_runs": 0,
        "prompt_truncation_rate": 0.0,
        "failure_tags": [],
    }
    baseline = {
        "pass_count": "2",
        "blocked_count": "0",
        "failure_count": "1",
        "pass_rate": "0.6667",
        "blocked_rate": "0.0",
        "median_cost_usd": "0.12",
        "median_duration_s": "8",
        "median_input_tokens": "110",
        "median_output_tokens": "35",
        "median_tool_calls": "5",
        "median_tool_f1": "0.7",
        "median_tool_precision": "0.65",
        "median_tool_recall": "0.8",
        "median_redundant_call_rate": "0.2",
        "prompt_truncated_runs": "0",
        "prompt_truncation_rate": "0.0",
        "new_failure_tags": "[]",
    }

    result = compare_against_baseline(metrics, baseline)

    assert result["delta"]["median_tool_f1"] == pytest.approx(0.15, abs=0.001)
    assert result["delta"]["median_tool_precision"] == pytest.approx(0.15, abs=0.001)
    assert result["delta"]["median_tool_recall"] == pytest.approx(0.1, abs=0.001)
    assert result["delta"]["median_redundant_call_rate"] == pytest.approx(-0.1, abs=0.001)
    # tool_f1 改善应触发 keep
    assert result["suggestion"] == "keep"


def test_compare_baseline_tool_f1_regression_blocks_keep() -> None:
    """tool_f1 显著退化时不应 keep。"""
    metrics = {
        "pass_count": 2,
        "blocked_count": 0,
        "failure_count": 1,
        "pass_rate": 0.6667,
        "blocked_rate": 0.0,
        "median_cost_usd": 0.08,
        "median_duration_s": 6.0,
        "median_input_tokens": 90,
        "median_output_tokens": 25,
        "median_tool_calls": 3,
        "median_tool_f1": 0.5,
        "median_tool_precision": 0.5,
        "median_tool_recall": 0.5,
        "median_redundant_call_rate": 0.0,
        "prompt_truncated_runs": 0,
        "prompt_truncation_rate": 0.0,
        "failure_tags": [],
    }
    baseline = {
        "pass_count": "2",
        "blocked_count": "0",
        "failure_count": "1",
        "pass_rate": "0.6667",
        "blocked_rate": "0.0",
        "median_cost_usd": "0.10",
        "median_duration_s": "7",
        "median_input_tokens": "100",
        "median_output_tokens": "30",
        "median_tool_calls": "4",
        "median_tool_f1": "0.9",
        "median_tool_precision": "0.85",
        "median_tool_recall": "0.95",
        "median_redundant_call_rate": "0.0",
        "prompt_truncated_runs": "0",
        "prompt_truncation_rate": "0.0",
        "new_failure_tags": "[]",
    }

    result = compare_against_baseline(metrics, baseline)

    # 虽然成本/耗时降低会触发 keep，但 tool_f1 退化 > 0.05 应阻止
    assert result["suggestion"] == "review"
