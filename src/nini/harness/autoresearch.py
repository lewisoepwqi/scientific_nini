"""第二条 autoresearch 线的 benchmark 聚合与结果账本工具。"""

from __future__ import annotations

import asyncio
import csv
import json
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

import yaml

from nini.agent.model_resolver import (
    BUILTIN_MODE_DEEP,
    BUILTIN_PROVIDER_ID,
    get_model_resolver,
    reload_model_resolver,
)
from nini.agent.runner import AgentRunner
from nini.agent.session import Session
from nini.config import settings
from nini.config_manager import get_active_provider_id, list_user_configured_provider_ids
from nini.harness.models import HarnessRunSummary, HarnessTraceRecord
from nini.harness.runner import HarnessRunner
from nini.harness.store import HarnessTraceStore
from nini.models.database import init_db
from nini.recipe import get_recipe_registry
from nini.tools.registry import create_default_tool_registry

DEFAULT_BENCHMARKS_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "autoresearch" / "harness_benchmarks.yaml"
)
DEFAULT_RESULTS_TSV = Path(__file__).resolve().parents[3] / "results" / "harness_results.tsv"
DEFAULT_PROVIDER_ROUTE_MODELS = {
    "dashscope": "glm-5",
}
DEFAULT_BENCHMARK_CASE_TIMEOUT_SECONDS = 240.0

TSV_COLUMNS = [
    "commit",
    "timestamp",
    "metric_version",
    "benchmark_set",
    "pass_count",
    "blocked_count",
    "failure_count",
    "pass_rate",
    "blocked_rate",
    "median_duration_s",
    "median_cost_usd",
    "median_input_tokens",
    "median_output_tokens",
    "median_tool_calls",
    "prompt_profiles",
    "prompt_truncated_runs",
    "prompt_truncation_rate",
    "median_prompt_tokens_before",
    "median_prompt_tokens_after",
    "median_prompt_token_budget",
    "new_failure_tags",
    "changed_files",
    "change_summary",
    "status",
]


@dataclass(frozen=True)
class BenchmarkCase:
    """单条 benchmark 定义。"""

    benchmark_id: str
    recipe_id: str
    expected_status: str = "completed"
    required: bool = True
    user_request: str = ""
    recipe_inputs: dict[str, Any] | None = None


@dataclass(frozen=True)
class BenchmarkSetDefinition:
    """一组 benchmark 定义。"""

    metric_version: str
    benchmark_set: str
    description: str
    cases: tuple[BenchmarkCase, ...]


def _normalize_row(row: dict[str, Any]) -> dict[str, str]:
    return {str(key): str(value or "") for key, value in row.items()}


def _coerce_int(row: dict[str, str], key: str, default: int = 0) -> int:
    try:
        return int(float(row.get(key, default)))
    except (TypeError, ValueError):
        return default


def _coerce_float(row: dict[str, str], key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, default))
    except (TypeError, ValueError):
        return default


def _format_median(value: float) -> int | float:
    rounded = round(float(value), 6)
    if rounded.is_integer():
        return int(rounded)
    if abs(rounded) >= 1:
        return round(rounded, 2)
    return rounded


def _latest_by_recipe(summaries: list[HarnessRunSummary]) -> dict[str, HarnessRunSummary]:
    latest: dict[str, HarnessRunSummary] = {}
    for item in summaries:
        recipe_id = str(item.recipe_id or "").strip()
        if recipe_id and recipe_id not in latest:
            latest[recipe_id] = item
    return latest


def load_benchmark_set(
    benchmark_set: str,
    *,
    config_path: Path = DEFAULT_BENCHMARKS_PATH,
) -> BenchmarkSetDefinition:
    """读取指定 benchmark 集。"""
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    metric_version = str(payload.get("version", "nini_harness_v1")).strip() or "nini_harness_v1"
    sets = payload.get("sets", {})
    if not isinstance(sets, dict) or benchmark_set not in sets:
        raise KeyError(f"未找到 benchmark_set={benchmark_set}")

    raw_set = sets.get(benchmark_set) or {}
    raw_cases = raw_set.get("cases") or []
    cases: list[BenchmarkCase] = []
    for item in raw_cases:
        if not isinstance(item, dict):
            continue
        recipe_id = str(item.get("recipe_id", "")).strip()
        if not recipe_id:
            continue
        cases.append(
            BenchmarkCase(
                benchmark_id=str(item.get("benchmark_id", recipe_id)).strip() or recipe_id,
                recipe_id=recipe_id,
                expected_status=str(item.get("expected_status", "completed")).strip()
                or "completed",
                required=bool(item.get("required", True)),
                user_request=str(item.get("user_request", "") or "").strip(),
                recipe_inputs=(
                    dict(item.get("recipe_inputs"))
                    if isinstance(item.get("recipe_inputs"), dict)
                    else None
                ),
            )
        )
    if not cases:
        raise ValueError(f"benchmark_set={benchmark_set} 没有可用 cases")

    return BenchmarkSetDefinition(
        metric_version=metric_version,
        benchmark_set=benchmark_set,
        description=str(raw_set.get("description", "")).strip(),
        cases=tuple(cases),
    )


def evaluate_benchmark_set_from_summaries(
    *,
    definition: BenchmarkSetDefinition,
    summaries: list[HarnessRunSummary],
    store: HarnessTraceStore,
    session_id: str,
) -> dict[str, Any]:
    """基于摘要列表计算第二条线主指标。"""
    latest = _latest_by_recipe(summaries)
    durations: list[float] = []
    costs: list[float] = []
    input_tokens: list[float] = []
    output_tokens: list[float] = []
    tool_calls: list[float] = []
    prompt_tokens_before: list[float] = []
    prompt_tokens_after: list[float] = []
    prompt_token_budgets: list[float] = []
    prompt_profiles: set[str] = set()
    failure_counter: Counter[str] = Counter()
    sample_results: list[dict[str, Any]] = []

    pass_count = 0
    blocked_count = 0
    failure_count = 0
    prompt_truncated_runs = 0

    for case in definition.cases:
        matched = latest.get(case.recipe_id)
        actual_status = matched.status if matched is not None else "missing"
        passed = matched is not None and actual_status == case.expected_status
        if passed:
            pass_count += 1
        else:
            failure_count += 1
        if actual_status == "blocked":
            blocked_count += 1

        case_failure_tags: list[str] = []
        tool_call_count = 0
        prompt_audit: dict[str, Any] | None = None
        if matched is not None:
            durations.append(float(matched.duration_ms) / 1000.0)
            costs.append(float(matched.estimated_cost_usd))
            input_tokens.append(float(matched.input_tokens))
            output_tokens.append(float(matched.output_tokens))
            case_failure_tags = list(matched.failure_tags)
            if case_failure_tags:
                failure_counter.update(case_failure_tags)
            elif not passed:
                failure_counter.update([f"benchmark:{actual_status}"])

            record: HarnessTraceRecord | None = None
            try:
                record = store.load_run(matched.run_id, session_id=session_id)
            except FileNotFoundError:
                record = None
            if record is not None and record.task_metrics is not None:
                tool_call_count = int(record.task_metrics.tool_call_count or 0)
            if record is not None and isinstance(record.summary, dict):
                raw_prompt_audit = record.summary.get("prompt_audit")
                if isinstance(raw_prompt_audit, dict):
                    prompt_audit = raw_prompt_audit
                    profile = str(raw_prompt_audit.get("profile", "") or "").strip()
                    if profile:
                        prompt_profiles.add(profile)
                    if bool(raw_prompt_audit.get("truncated")):
                        prompt_truncated_runs += 1
                    if raw_prompt_audit.get("total_tokens_before") is not None:
                        prompt_tokens_before.append(
                            float(raw_prompt_audit.get("total_tokens_before") or 0)
                        )
                    if raw_prompt_audit.get("total_tokens_after") is not None:
                        prompt_tokens_after.append(
                            float(raw_prompt_audit.get("total_tokens_after") or 0)
                        )
                    if raw_prompt_audit.get("token_budget") is not None:
                        prompt_token_budgets.append(
                            float(raw_prompt_audit.get("token_budget") or 0)
                        )
            tool_calls.append(float(tool_call_count))
        else:
            failure_counter.update(["benchmark:missing"])

        sample_results.append(
            {
                "benchmark_id": case.benchmark_id,
                "recipe_id": case.recipe_id,
                "expected_status": case.expected_status,
                "required": case.required,
                "run_id": matched.run_id if matched is not None else None,
                "actual_status": actual_status,
                "failure_tags": case_failure_tags,
                "tool_call_count": tool_call_count,
                "prompt_audit": prompt_audit,
                "passed": passed,
            }
        )

    total_cases = len(definition.cases)
    unique_failure_tags = sorted(failure_counter)
    return {
        "metric_version": definition.metric_version,
        "benchmark_set": definition.benchmark_set,
        "session_id": session_id,
        "description": definition.description,
        "total_cases": total_cases,
        "matched_runs": sum(1 for item in sample_results if item["run_id"]),
        "pass_count": pass_count,
        "blocked_count": blocked_count,
        "failure_count": failure_count,
        "pass_rate": round(pass_count / total_cases, 4) if total_cases else 0.0,
        "blocked_rate": round(blocked_count / total_cases, 4) if total_cases else 0.0,
        "median_duration_s": _format_median(median(durations)) if durations else 0,
        "median_cost_usd": _format_median(median(costs)) if costs else 0,
        "median_input_tokens": _format_median(median(input_tokens)) if input_tokens else 0,
        "median_output_tokens": _format_median(median(output_tokens)) if output_tokens else 0,
        "median_tool_calls": _format_median(median(tool_calls)) if tool_calls else 0,
        "prompt_profiles": sorted(prompt_profiles),
        "prompt_truncated_runs": prompt_truncated_runs,
        "prompt_truncation_rate": (
            round(prompt_truncated_runs / total_cases, 4) if total_cases else 0.0
        ),
        "median_prompt_tokens_before": (
            _format_median(median(prompt_tokens_before)) if prompt_tokens_before else 0
        ),
        "median_prompt_tokens_after": (
            _format_median(median(prompt_tokens_after)) if prompt_tokens_after else 0
        ),
        "median_prompt_token_budget": (
            _format_median(median(prompt_token_budgets)) if prompt_token_budgets else 0
        ),
        "top_failure_tags": failure_counter.most_common(5),
        "failure_tags": unique_failure_tags,
        "sample_results": sample_results,
    }


def _default_recipe_inputs(recipe: Any) -> dict[str, str]:
    """根据 Recipe 输入字段生成可运行的默认输入。"""
    values: dict[str, str] = {}
    for field in getattr(recipe, "input_fields", []):
        key = str(getattr(field, "key", "") or "").strip()
        if not key:
            continue
        example = str(getattr(field, "example", "") or "").strip()
        placeholder = str(getattr(field, "placeholder", "") or "").strip()
        label = str(getattr(field, "label", "") or "").strip()
        candidate = example or placeholder or label or key
        if candidate:
            values[key] = candidate
    return values


def resolve_benchmark_case(
    case: BenchmarkCase, *, recipe_registry: Any | None = None
) -> dict[str, Any]:
    """将 benchmark case 展开为可执行上下文。"""
    registry = recipe_registry or get_recipe_registry()
    recipe = registry.get(case.recipe_id)
    if recipe is None:
        raise KeyError(f"未找到 recipe_id={case.recipe_id}")

    recipe_inputs = _default_recipe_inputs(recipe)
    if case.recipe_inputs:
        for key, value in case.recipe_inputs.items():
            normalized_key = str(key or "").strip()
            normalized_value = str(value or "").strip()
            if normalized_key and normalized_value:
                recipe_inputs[normalized_key] = normalized_value

    user_request = case.user_request or str(getattr(recipe, "example_input", "") or "").strip()
    if not user_request:
        user_request = f"请执行 {recipe.name}"

    return {
        "benchmark_id": case.benchmark_id,
        "recipe": recipe,
        "recipe_inputs": recipe_inputs,
        "user_request": user_request,
        "rendered_prompt": recipe.render_prompt(user_request, recipe_inputs),
    }


async def _auto_answer_questions(
    session: Session,
    tool_call_id: str,
    payload: dict[str, Any],
) -> dict[str, str]:
    """为 benchmark 模式自动补一个最保守的回答。"""
    _ = tool_call_id
    answers: dict[str, str] = {}
    questions = payload.get("questions") if isinstance(payload, dict) else None
    if isinstance(questions, list):
        for item in questions:
            if not isinstance(item, dict):
                continue
            answer_key = ""
            for candidate_key in (
                str(item.get("id", "") or "").strip(),
                str(item.get("header", "") or "").strip(),
                str(item.get("question", "") or "").strip(),
            ):
                if candidate_key:
                    answer_key = candidate_key
                    break
            if not answer_key:
                continue

            fallback = ""
            for candidate_key in (
                str(item.get("id", "") or "").strip(),
                str(item.get("header", "") or "").strip(),
                str(item.get("question", "") or "").strip(),
            ):
                if not candidate_key:
                    continue
                candidate_value = session.recipe_inputs.get(candidate_key)
                if candidate_value is None:
                    continue
                fallback = str(candidate_value).strip()
                if fallback:
                    break

            if not fallback:
                options = item.get("options")
                if isinstance(options, list):
                    selected_labels: list[str] = []
                    for raw_option in options:
                        if not isinstance(raw_option, dict):
                            continue
                        label = str(raw_option.get("label", "") or "").strip()
                        if label:
                            selected_labels.append(label)
                        if selected_labels:
                            break
                    fallback = ", ".join(selected_labels)

            answers[answer_key] = str(fallback or "请基于当前上下文继续。").strip()
    return answers


async def prepare_benchmark_resolver() -> Any:
    """为 benchmark 执行准备显式模型路由。

    优先级：
    1. 当前激活的用户供应商
    2. 已配置供应商列表中的第一个
    3. 系统内置 deep

    特殊规则：
    - `dashscope` 在第二条测试线默认固定到 `glm-5`，避免回退到普通通义模型。
    """
    await reload_model_resolver()
    resolver = get_model_resolver()

    active_provider_id = await get_active_provider_id()
    configured_provider_ids = await list_user_configured_provider_ids()
    route_provider = active_provider_id or (
        configured_provider_ids[0] if configured_provider_ids else None
    )

    if route_provider:
        route_model = DEFAULT_PROVIDER_ROUTE_MODELS.get(route_provider)
        for purpose in ("planning", "chat", "verification"):
            resolver.set_purpose_route(
                purpose=purpose,
                provider_id=route_provider,
                model=route_model,
            )
        return resolver

    for purpose in ("planning", "chat", "verification"):
        resolver.set_purpose_route(
            purpose=purpose,
            provider_id=BUILTIN_PROVIDER_ID,
            model=BUILTIN_MODE_DEEP,
        )
    return resolver


async def prepare_benchmark_resolver_with_override(
    *,
    provider_id: str | None = None,
    model: str | None = None,
) -> Any:
    """为 benchmark 执行准备 resolver，并允许显式覆盖 provider/model。"""
    resolver = await prepare_benchmark_resolver()
    normalized_provider = str(provider_id or "").strip() or None
    normalized_model = str(model or "").strip() or None
    if not normalized_provider:
        return resolver

    for purpose in ("planning", "chat", "verification"):
        resolver.set_purpose_route(
            purpose=purpose,
            provider_id=normalized_provider,
            model=normalized_model,
        )
    return resolver


async def run_benchmark_set_async(
    *,
    benchmark_set: str = "smoke",
    config_path: Path = DEFAULT_BENCHMARKS_PATH,
    session_id: str | None = None,
    store: HarnessTraceStore | None = None,
    tool_registry: Any | None = None,
    agent_runner: Any | None = None,
    route_provider_id: str | None = None,
    route_model: str | None = None,
    case_timeout_seconds: float = DEFAULT_BENCHMARK_CASE_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """执行一组 benchmark，并将 trace 落到同一个 session_id。"""
    settings.ensure_dirs()
    await init_db()

    definition = load_benchmark_set(benchmark_set, config_path=config_path)
    registry = get_recipe_registry()
    actual_store = store or HarnessTraceStore()
    actual_tool_registry = tool_registry or create_default_tool_registry()
    resolver = await prepare_benchmark_resolver_with_override(
        provider_id=route_provider_id,
        model=route_model,
    )
    actual_agent_runner = agent_runner or AgentRunner(
        resolver=resolver,
        tool_registry=actual_tool_registry,
        ask_user_question_handler=_auto_answer_questions,
    )
    harness_runner = HarnessRunner(agent_runner=actual_agent_runner, trace_store=actual_store)
    batch_session_id = session_id or f"autoresearch-harness-{benchmark_set}-{uuid.uuid4().hex[:8]}"

    executed_cases: list[dict[str, Any]] = []
    for case in definition.cases:
        resolved = resolve_benchmark_case(case, recipe_registry=registry)
        recipe = resolved["recipe"]
        recipe_inputs = resolved["recipe_inputs"]
        benchmark_session = Session(id=batch_session_id)
        benchmark_session.bind_recipe_context(
            task_kind="deep_task",
            recipe_id=recipe.recipe_id,
            recipe_inputs=recipe_inputs,
        )
        task_id = uuid.uuid4().hex[:12]
        benchmark_session.set_deep_task_state(
            task_id=task_id,
            status="queued",
            current_step_index=1,
            total_steps=len(recipe.steps),
            current_step_title=recipe.steps[0].title,
            next_hint="基准任务初始化中。",
            retry_count=0,
            current_attempt_id=f"{task_id}:workflow:1",
        )

        async def _collect_events() -> list[Any]:
            return [
                event
                async for event in harness_runner.run(
                    benchmark_session,
                    resolved["rendered_prompt"],
                    stop_event=case_stop_event,
                )
            ]

        timed_out = False
        timeout_seconds = max(float(case_timeout_seconds), 0.1)
        case_stop_event = asyncio.Event()
        events_task = asyncio.create_task(_collect_events())
        try:
            events = await asyncio.wait_for(asyncio.shield(events_task), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            timed_out = True
            case_stop_event.set()
            await asyncio.sleep(0)
            try:
                events = await asyncio.wait_for(
                    events_task,
                    timeout=min(15.0, max(2.0, timeout_seconds * 0.1)),
                )
            except asyncio.TimeoutError:
                events_task.cancel()
                try:
                    await events_task
                except asyncio.CancelledError:
                    pass
                events = []
        executed_cases.append(
            {
                "benchmark_id": case.benchmark_id,
                "recipe_id": case.recipe_id,
                "user_request": resolved["user_request"],
                "event_count": len(events),
                "final_event": (
                    "timeout" if timed_out else (events[-1].type.value if events else None)
                ),
                "timed_out": timed_out,
                "case_timeout_seconds": timeout_seconds,
            }
        )

    return {
        "session_id": batch_session_id,
        "benchmark_set": benchmark_set,
        "metric_version": definition.metric_version,
        "cases": executed_cases,
        "case_count": len(executed_cases),
    }


def run_benchmark_set(
    *,
    benchmark_set: str = "smoke",
    config_path: Path = DEFAULT_BENCHMARKS_PATH,
    session_id: str | None = None,
    store: HarnessTraceStore | None = None,
    tool_registry: Any | None = None,
    agent_runner: Any | None = None,
    route_provider_id: str | None = None,
    route_model: str | None = None,
    case_timeout_seconds: float = DEFAULT_BENCHMARK_CASE_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """同步包装器。"""
    return asyncio.run(
        run_benchmark_set_async(
            benchmark_set=benchmark_set,
            config_path=config_path,
            session_id=session_id,
            store=store,
            tool_registry=tool_registry,
            agent_runner=agent_runner,
            route_provider_id=route_provider_id,
            route_model=route_model,
            case_timeout_seconds=case_timeout_seconds,
        )
    )


async def evaluate_benchmark_set_async(
    *,
    session_id: str,
    benchmark_set: str = "smoke",
    config_path: Path = DEFAULT_BENCHMARKS_PATH,
    limit: int = 500,
    store: HarnessTraceStore | None = None,
) -> dict[str, Any]:
    """异步读取 trace 摘要并计算指标。"""
    settings.ensure_dirs()
    await init_db()
    actual_store = store or HarnessTraceStore()
    definition = load_benchmark_set(benchmark_set, config_path=config_path)
    summaries = await actual_store.list_runs(session_id=session_id, limit=limit)
    return evaluate_benchmark_set_from_summaries(
        definition=definition,
        summaries=summaries,
        store=actual_store,
        session_id=session_id,
    )


def evaluate_benchmark_set(
    *,
    session_id: str,
    benchmark_set: str = "smoke",
    config_path: Path = DEFAULT_BENCHMARKS_PATH,
    limit: int = 500,
    store: HarnessTraceStore | None = None,
) -> dict[str, Any]:
    """同步包装器。"""
    return asyncio.run(
        evaluate_benchmark_set_async(
            session_id=session_id,
            benchmark_set=benchmark_set,
            config_path=config_path,
            limit=limit,
            store=store,
        )
    )


def load_last_keep(
    *,
    results_tsv: Path = DEFAULT_RESULTS_TSV,
    metric_version: str,
    benchmark_set: str,
) -> dict[str, str] | None:
    """读取同版本、同 benchmark_set 的最后一条 keep。"""
    if not results_tsv.exists():
        return None

    with open(results_tsv, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        last_keep: dict[str, str] | None = None
        for row in reader:
            normalized = _normalize_row(row)
            if normalized.get("status") != "keep":
                continue
            if normalized.get("metric_version") != metric_version:
                continue
            if normalized.get("benchmark_set") != benchmark_set:
                continue
            last_keep = normalized
    return last_keep


def compare_against_baseline(metrics: dict[str, Any], baseline: dict[str, str]) -> dict[str, Any]:
    """根据第二条线规则给出 delta 与建议。"""
    delta = {
        "pass_count": int(metrics["pass_count"]) - _coerce_int(baseline, "pass_count"),
        "blocked_count": int(metrics["blocked_count"]) - _coerce_int(baseline, "blocked_count"),
        "failure_count": int(metrics["failure_count"]) - _coerce_int(baseline, "failure_count"),
        "pass_rate": round(float(metrics["pass_rate"]) - _coerce_float(baseline, "pass_rate"), 4),
        "blocked_rate": round(
            float(metrics["blocked_rate"]) - _coerce_float(baseline, "blocked_rate"), 4
        ),
        "median_cost_usd": round(
            float(metrics["median_cost_usd"]) - _coerce_float(baseline, "median_cost_usd"), 6
        ),
        "median_duration_s": round(
            float(metrics["median_duration_s"]) - _coerce_float(baseline, "median_duration_s"), 2
        ),
        "median_input_tokens": round(
            float(metrics["median_input_tokens"]) - _coerce_float(baseline, "median_input_tokens"),
            2,
        ),
        "median_output_tokens": round(
            float(metrics["median_output_tokens"])
            - _coerce_float(baseline, "median_output_tokens"),
            2,
        ),
        "median_tool_calls": round(
            float(metrics["median_tool_calls"]) - _coerce_float(baseline, "median_tool_calls"),
            2,
        ),
        "prompt_truncated_runs": int(metrics["prompt_truncated_runs"])
        - _coerce_int(baseline, "prompt_truncated_runs"),
        "prompt_truncation_rate": round(
            float(metrics["prompt_truncation_rate"])
            - _coerce_float(baseline, "prompt_truncation_rate"),
            4,
        ),
    }
    baseline_raw_tags = str(baseline.get("new_failure_tags", "[]") or "[]")
    try:
        parsed_baseline_tags = json.loads(baseline_raw_tags)
    except json.JSONDecodeError:
        parsed_baseline_tags = []
    baseline_tags = {str(item).strip() for item in parsed_baseline_tags if str(item).strip()}
    current_tags = {str(tag).strip() for tag in metrics.get("failure_tags", []) if str(tag).strip()}
    new_failure_tags = sorted(current_tags - baseline_tags)
    prompt_truncation_mismatch = bool(metrics["prompt_truncated_runs"]) != bool(
        _coerce_int(baseline, "prompt_truncated_runs")
    )

    if delta["pass_rate"] < 0 or delta["blocked_rate"] > 0:
        suggestion = "discard"
    elif delta["pass_count"] > 0 or delta["blocked_count"] < 0 or delta["failure_count"] < 0:
        suggestion = "keep"
    elif (
        delta["median_cost_usd"] < 0
        or delta["median_duration_s"] < 0
        or delta["median_input_tokens"] + delta["median_output_tokens"] < 0
    ):
        suggestion = "keep"
    else:
        suggestion = "review"
    if prompt_truncation_mismatch and suggestion == "keep":
        suggestion = "review"

    return {
        "delta": delta,
        "new_failure_tags": new_failure_tags,
        "prompt_truncation_mismatch": prompt_truncation_mismatch,
        "suggestion": suggestion,
    }


def append_to_tsv(
    *,
    metrics: dict[str, Any],
    commit: str,
    changed_files: str,
    summary: str,
    status: str,
    results_tsv: Path = DEFAULT_RESULTS_TSV,
    new_failure_tags: list[str] | None = None,
) -> None:
    """追加一行到 harness_results.tsv。"""
    row = {
        "commit": commit,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M"),
        "metric_version": metrics["metric_version"],
        "benchmark_set": metrics["benchmark_set"],
        "pass_count": metrics["pass_count"],
        "blocked_count": metrics["blocked_count"],
        "failure_count": metrics["failure_count"],
        "pass_rate": metrics["pass_rate"],
        "blocked_rate": metrics["blocked_rate"],
        "median_duration_s": metrics["median_duration_s"],
        "median_cost_usd": metrics["median_cost_usd"],
        "median_input_tokens": metrics["median_input_tokens"],
        "median_output_tokens": metrics["median_output_tokens"],
        "median_tool_calls": metrics["median_tool_calls"],
        "prompt_profiles": json.dumps(metrics.get("prompt_profiles", []), ensure_ascii=False),
        "prompt_truncated_runs": metrics["prompt_truncated_runs"],
        "prompt_truncation_rate": metrics["prompt_truncation_rate"],
        "median_prompt_tokens_before": metrics["median_prompt_tokens_before"],
        "median_prompt_tokens_after": metrics["median_prompt_tokens_after"],
        "median_prompt_token_budget": metrics["median_prompt_token_budget"],
        "new_failure_tags": json.dumps(new_failure_tags or [], ensure_ascii=False),
        "changed_files": changed_files,
        "change_summary": summary,
        "status": status,
    }
    file_exists = results_tsv.exists() and results_tsv.stat().st_size > 0
    with open(results_tsv, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TSV_COLUMNS, delimiter="\t")
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)
