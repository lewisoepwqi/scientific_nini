"""测量第二条 autoresearch-harness 线的 benchmark 指标。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nini.harness.autoresearch import (  # noqa: E402
    DEFAULT_BENCHMARKS_PATH,
    DEFAULT_RESULTS_TSV,
    append_to_tsv,
    compare_against_baseline,
    evaluate_benchmark_set,
    load_last_keep,
)


def _print_metrics(metrics: dict[str, object]) -> None:
    print("--- nini autoresearch harness metrics ---")
    for key in (
        "metric_version",
        "benchmark_set",
        "session_id",
        "total_cases",
        "matched_runs",
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
    ):
        print(f"{key}: {metrics[key]}")

    print("\n--- top failure tags ---")
    for tag, count in metrics.get("top_failure_tags", []):
        print(f"{tag}: {count}")

    print("\n--- benchmark sample results ---")
    for item in metrics.get("sample_results", []):
        print(json.dumps(item, ensure_ascii=False))


def _print_delta(compare_result: dict[str, object]) -> None:
    print("\n--- delta vs last keep ---")
    delta = compare_result["delta"]
    assert isinstance(delta, dict)
    for key in (
        "pass_count",
        "blocked_count",
        "failure_count",
        "pass_rate",
        "blocked_rate",
        "median_cost_usd",
        "median_duration_s",
        "median_input_tokens",
        "median_output_tokens",
        "median_tool_calls",
        "prompt_truncated_runs",
        "prompt_truncation_rate",
    ):
        value = delta[key]
        arrow = "↑" if float(value) > 0 else "↓" if float(value) < 0 else "="
        print(f"  {key}: {arrow} {value}")

    new_failure_tags = compare_result.get("new_failure_tags", [])
    print(f"\nnew_failure_tags: {json.dumps(new_failure_tags, ensure_ascii=False)}")
    print(
        "prompt_truncation_mismatch: "
        f"{json.dumps(bool(compare_result.get('prompt_truncation_mismatch')), ensure_ascii=False)}"
    )
    print(f"suggestion: {compare_result['suggestion']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="测量 Nini autoresearch harness 基线指标")
    parser.add_argument("--session-id", required=True, help="要评估的 harness session_id")
    parser.add_argument("--benchmark-set", default="smoke", help="benchmark 集名称")
    parser.add_argument(
        "--benchmark-config",
        default=str(DEFAULT_BENCHMARKS_PATH),
        help="benchmark YAML 路径",
    )
    parser.add_argument("--limit", type=int, default=500, help="读取的摘要上限")
    parser.add_argument("--compare", action="store_true", help="与同版本 keep 记录对比")
    parser.add_argument("--append", action="store_true", help="追加到 results/harness_results.tsv")
    parser.add_argument("--commit", default="HEAD", help="实验 commit 标识")
    parser.add_argument("--changed-files", default="-", help="本次修改的文件列表")
    parser.add_argument("--summary", default="", help="变更描述")
    parser.add_argument("--status", default="pending", help="keep/discard/pending")
    args = parser.parse_args()

    metrics = evaluate_benchmark_set(
        session_id=args.session_id,
        benchmark_set=args.benchmark_set,
        config_path=Path(args.benchmark_config),
        limit=args.limit,
    )
    _print_metrics(metrics)

    compare_result: dict[str, object] | None = None
    if args.compare:
        baseline = load_last_keep(
            results_tsv=DEFAULT_RESULTS_TSV,
            metric_version=str(metrics["metric_version"]),
            benchmark_set=str(metrics["benchmark_set"]),
        )
        if baseline:
            compare_result = compare_against_baseline(metrics, baseline)
            _print_delta(compare_result)
        else:
            print(
                "\n（无同 metric_version + benchmark_set 的历史 keep 记录可对比，请先建立 baseline）"
            )

    if args.append:
        append_to_tsv(
            metrics=metrics,
            commit=args.commit,
            changed_files=args.changed_files,
            summary=args.summary,
            status=args.status,
            results_tsv=DEFAULT_RESULTS_TSV,
            new_failure_tags=(
                list(compare_result.get("new_failure_tags", [])) if compare_result else []
            ),
        )
        print(f"\n已追加到 {DEFAULT_RESULTS_TSV}")


if __name__ == "__main__":
    main()
