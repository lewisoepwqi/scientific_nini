"""测量当前 Nini autoresearch static 基线指标。

新版指标（metric_version=nini_runtime_v2）遵循两个原则：
1. prompt 使用代表性主场景 + 多场景明细，而不是只测单一硬编码片段。
2. tool schema 使用主 Agent 真实可见工具面，而不是注册表原始暴露全集。

用法：
  python scripts/measure_baseline.py
  python scripts/measure_baseline.py --compare
  python scripts/measure_baseline.py --append
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

RESULTS_TSV = Path(__file__).resolve().parent.parent / "results" / "static_results.tsv"
CURRENT_METRIC_VERSION = "nini_runtime_v2"

# TSV 列顺序（与 results.tsv 表头一致）
TSV_COLUMNS = [
    "commit",
    "timestamp",
    "metric_version",
    "prompt_tokens",
    "tool_schema_tokens",
    "total_tokens",
    "test_passed",
    "test_failed",
    "test_duration_sec",
    "budget_full",
    "budget_standard",
    "budget_compact",
    "changed_file",
    "change_summary",
    "status",
]


@dataclass(frozen=True)
class PromptScenario:
    """代表性 prompt 测量场景。"""

    name: str
    context_window: int | None
    intent_hints: frozenset[str]
    category: str


FULL_SCENARIOS: tuple[PromptScenario, ...] = (
    PromptScenario(
        name="analysis_full",
        context_window=None,
        intent_hints=frozenset({"chart", "stat_test"}),
        category="full",
    ),
    PromptScenario(
        name="report_full",
        context_window=None,
        intent_hints=frozenset({"report", "summary"}),
        category="full",
    ),
    PromptScenario(
        name="literature_full",
        context_window=None,
        intent_hints=frozenset({"literature", "paper"}),
        category="full",
    ),
)

ADDITIONAL_SCENARIOS: tuple[PromptScenario, ...] = (
    PromptScenario(
        name="analysis_standard",
        context_window=32_000,
        intent_hints=frozenset({"chart", "stat_test"}),
        category="profile",
    ),
    PromptScenario(
        name="analysis_compact",
        context_window=8_000,
        intent_hints=frozenset({"chart", "stat_test"}),
        category="profile",
    ),
)

ALL_SCENARIOS = FULL_SCENARIOS + ADDITIONAL_SCENARIOS
SURFACE_STAGES: tuple[str, ...] = ("profile", "analysis", "export")


def _count_tokens(text: str) -> int:
    """用 tiktoken 估算 token 数，不可用时按字符数 / 4 近似。"""
    try:
        import tiktoken

        enc = tiktoken.encoding_for_model("gpt-4")
        return len(enc.encode(text))
    except Exception:
        return len(text) // 4


def _normalize_row(row: dict[str, Any]) -> dict[str, str]:
    return {str(key): str(value or "") for key, value in row.items()}


def _coerce_int(row: dict[str, str], key: str, default: int = 0) -> int:
    try:
        return int(row.get(key, default))
    except (TypeError, ValueError):
        return default


def _is_row_arithmetically_valid(row: dict[str, str]) -> bool:
    prompt_tokens = _coerce_int(row, "prompt_tokens")
    tool_tokens = _coerce_int(row, "tool_schema_tokens")
    total_tokens = _coerce_int(row, "total_tokens")
    return prompt_tokens + tool_tokens == total_tokens


def validate_results_rows() -> list[dict[str, str]]:
    """返回 static_results.tsv 中算术不自洽的记录。"""
    if not RESULTS_TSV.exists():
        return []

    invalid_rows: list[dict[str, str]] = []
    with open(RESULTS_TSV, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            normalized = _normalize_row(row)
            if not normalized:
                continue
            if _is_row_arithmetically_valid(normalized):
                continue
            invalid_rows.append(normalized)
    return invalid_rows


def _refresh_registry() -> Any:
    """构建注册表并刷新技能快照。"""
    from nini.tools.registry import create_default_tool_registry

    return create_default_tool_registry()


def _measure_prompt_scenarios() -> dict[str, dict[str, int]]:
    """测量代表性 prompt 场景。"""
    from nini.agent.prompts.builder import PromptBuilder

    scenario_metrics: dict[str, dict[str, int]] = {}
    for scenario in ALL_SCENARIOS:
        prompt = PromptBuilder(context_window=scenario.context_window).build(
            intent_hints=set(scenario.intent_hints)
        )
        scenario_metrics[scenario.name] = {
            "tokens": _count_tokens(prompt),
            "chars": len(prompt),
        }
    return scenario_metrics


def _filter_visible_tool_definitions(
    *,
    registry: Any,
    stage: str,
) -> list[dict[str, Any]]:
    """按主 Agent 真实可见工具面生成工具定义。"""
    from nini.agent.runner import AgentRunner
    from nini.agent.session import Session
    from nini.agent.tool_exposure_policy import compute_tool_exposure_policy

    session = Session(id=f"autoresearch-{stage}")
    policy = compute_tool_exposure_policy(
        session=session,
        tool_registry=registry,
        stage_override=stage,
    )

    raw_defs = registry.get_tool_definitions()
    raw_by_name = {
        str(item.get("function", {}).get("name", "")).strip(): item
        for item in raw_defs
        if isinstance(item, dict)
    }
    visible_names = [
        str(name).strip() for name in policy.get("visible_tools", []) if str(name).strip()
    ]
    visible_defs = [raw_by_name[name] for name in visible_names if name in raw_by_name]

    # 主 Agent 额外暴露 dispatch_agents 与 ask_user_question。
    dispatch_tool = registry.get("dispatch_agents")
    if dispatch_tool is not None and hasattr(dispatch_tool, "get_tool_definition"):
        visible_defs.append(dispatch_tool.get_tool_definition())

    runner = AgentRunner(tool_registry=registry)
    visible_defs.append(runner._ask_user_question_tool_definition())  # noqa: SLF001
    return visible_defs


def _measure_tool_surfaces(registry: Any) -> dict[str, dict[str, int]]:
    """测量主 Agent 各阶段工具面。"""
    stage_metrics: dict[str, dict[str, int]] = {}
    for stage in SURFACE_STAGES:
        tool_defs = _filter_visible_tool_definitions(registry=registry, stage=stage)
        tool_text = json.dumps(tool_defs, ensure_ascii=False)
        stage_metrics[stage] = {
            "tokens": _count_tokens(tool_text),
            "count": len(tool_defs),
        }
    return stage_metrics


def measure() -> dict[str, Any]:
    """采集新版 autoresearch 指标。"""
    from nini.agent.prompt_policy import get_runtime_context_budget

    registry = _refresh_registry()
    prompt_scenarios = _measure_prompt_scenarios()
    tool_surfaces = _measure_tool_surfaces(registry)

    primary_prompt_tokens = max(
        prompt_scenarios[name]["tokens"]
        for name in ("analysis_full", "report_full", "literature_full")
    )
    primary_tool_tokens = max(tool_surfaces[stage]["tokens"] for stage in SURFACE_STAGES)
    total_tokens = primary_prompt_tokens + primary_tool_tokens

    return {
        "metric_version": CURRENT_METRIC_VERSION,
        "prompt_tokens": primary_prompt_tokens,
        "tool_schema_tokens": primary_tool_tokens,
        "total_tokens": total_tokens,
        "budget_full": get_runtime_context_budget("full"),
        "budget_standard": get_runtime_context_budget("standard"),
        "budget_compact": get_runtime_context_budget("compact"),
        "prompt_scenarios": prompt_scenarios,
        "tool_surfaces": tool_surfaces,
    }


def load_last_keep(metric_version: str = CURRENT_METRIC_VERSION) -> dict[str, str] | None:
    """从 static_results.tsv 读取最后一条同版本且有效的 keep 记录。"""
    if not RESULTS_TSV.exists():
        return None

    with open(RESULTS_TSV, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        last_keep: dict[str, str] | None = None
        for row in reader:
            normalized = _normalize_row(row)
            row_version = normalized.get("metric_version", "legacy_v1") or "legacy_v1"
            if normalized.get("status") != "keep":
                continue
            if row_version != metric_version:
                continue
            if not _is_row_arithmetically_valid(normalized):
                continue
            last_keep = normalized
    return last_keep


def _iter_primary_metric_lines(metrics: dict[str, Any]) -> Iterable[tuple[str, Any]]:
    yield "metric_version", metrics["metric_version"]
    yield "prompt_tokens", metrics["prompt_tokens"]
    yield "tool_schema_tokens", metrics["tool_schema_tokens"]
    yield "total_tokens", metrics["total_tokens"]
    yield "budget_full", metrics["budget_full"]
    yield "budget_standard", metrics["budget_standard"]
    yield "budget_compact", metrics["budget_compact"]


def print_metrics(metrics: dict[str, Any]) -> None:
    """输出主指标与明细。"""
    print("--- nini autoresearch metrics ---")
    for key, value in _iter_primary_metric_lines(metrics):
        print(f"{key}: {value}")

    print("\n--- prompt scenarios ---")
    for scenario in ALL_SCENARIOS:
        item = metrics["prompt_scenarios"][scenario.name]
        print(f"{scenario.name}: tokens={item['tokens']} chars={item['chars']}")

    print("\n--- tool surfaces ---")
    for stage in SURFACE_STAGES:
        item = metrics["tool_surfaces"][stage]
        print(f"{stage}: tokens={item['tokens']} tools={item['count']}")

    invalid_rows = validate_results_rows()
    if invalid_rows:
        print("\n--- static_results.tsv warnings ---")
        for row in invalid_rows:
            commit = row.get("commit", "?")
            total_tokens = row.get("total_tokens", "?")
            expected = _coerce_int(row, "prompt_tokens") + _coerce_int(row, "tool_schema_tokens")
            print(f"invalid_row: commit={commit} total_tokens={total_tokens} expected={expected}")


def print_delta(metrics: dict[str, Any], baseline: dict[str, str]) -> None:
    """对比当前指标与 baseline，输出 delta。"""
    print("\n--- delta vs last keep ---")
    compare_keys = (
        ("prompt_tokens", "prompt_tokens"),
        ("tool_schema_tokens", "tool_schema_tokens"),
        ("total_tokens", "total_tokens"),
    )
    for metric_key, tsv_key in compare_keys:
        current = int(metrics[metric_key])
        previous = _coerce_int(baseline, tsv_key, current)
        delta = current - previous
        pct = (delta / previous * 100) if previous else 0
        arrow = "↑" if delta > 0 else "↓" if delta < 0 else "="
        print(f"  {metric_key}: {previous} → {current}  ({arrow} {abs(delta)}, {pct:+.1f}%)")

    total_delta = int(metrics["total_tokens"]) - _coerce_int(
        baseline, "total_tokens", int(metrics["total_tokens"])
    )
    if total_delta < -10:
        print("\n  建议: 主基线 total_tokens 下降，若测试全通过则 keep")
    elif total_delta > 10:
        print("\n  建议: 主基线 total_tokens 上升，考虑 discard")
    else:
        print("\n  建议: 主基线变化不显著（±10 tokens 内），按质量收益判断")


def append_to_tsv(
    metrics: dict[str, Any],
    commit: str,
    changed_file: str,
    summary: str,
    status: str,
    test_passed: int = 0,
    test_failed: int = 0,
    test_duration: float = 0.0,
) -> None:
    """追加一行到 static_results.tsv。"""
    row = {
        "commit": commit,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M"),
        "metric_version": metrics["metric_version"],
        "prompt_tokens": metrics["prompt_tokens"],
        "tool_schema_tokens": metrics["tool_schema_tokens"],
        "total_tokens": metrics["total_tokens"],
        "test_passed": test_passed,
        "test_failed": test_failed,
        "test_duration_sec": test_duration,
        "budget_full": metrics["budget_full"],
        "budget_standard": metrics["budget_standard"],
        "budget_compact": metrics["budget_compact"],
        "changed_file": changed_file,
        "change_summary": summary,
        "status": status,
    }
    file_exists = RESULTS_TSV.exists() and RESULTS_TSV.stat().st_size > 0
    with open(RESULTS_TSV, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TSV_COLUMNS, delimiter="\t")
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)
    print(f"\n已追加到 {RESULTS_TSV}")


def main() -> None:
    parser = argparse.ArgumentParser(description="测量 Nini autoresearch static 基线指标")
    parser.add_argument("--compare", action="store_true", help="与同版本上次 keep 记录对比")
    parser.add_argument("--append", action="store_true", help="追加到 results/static_results.tsv")
    parser.add_argument("--commit", default="HEAD", help="实验 commit 标识")
    parser.add_argument("--changed-file", default="-", help="本次修改的文件")
    parser.add_argument("--summary", default="", help="变更描述")
    parser.add_argument("--status", default="pending", help="keep/discard/pending")
    parser.add_argument("--test-passed", type=int, default=0, help="pytest 通过数")
    parser.add_argument("--test-failed", type=int, default=0, help="pytest 失败数")
    parser.add_argument("--test-duration", type=float, default=0.0, help="pytest 耗时(秒)")
    args = parser.parse_args()

    metrics = measure()
    print_metrics(metrics)

    if args.compare:
        baseline = load_last_keep()
        if baseline:
            print_delta(metrics, baseline)
        else:
            print("\n（无同 metric_version 的历史 keep 记录可对比，请先建立 v2 baseline）")

    if args.append:
        append_to_tsv(
            metrics,
            commit=args.commit,
            changed_file=args.changed_file,
            summary=args.summary,
            status=args.status,
            test_passed=args.test_passed,
            test_failed=args.test_failed,
            test_duration=args.test_duration,
        )


if __name__ == "__main__":
    main()
