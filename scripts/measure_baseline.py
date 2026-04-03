"""测量当前 Nini 配置下的 prompt/tool token 开销。

用法：
  python scripts/measure_baseline.py              # 仅测量，输出指标
  python scripts/measure_baseline.py --append      # 测量并追加到 results.tsv
  python scripts/measure_baseline.py --compare     # 测量并与 results.tsv 最后一条 keep 对比

退出码：
  0 = 正常
  1 = 导入或配置错误
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

RESULTS_TSV = Path(__file__).resolve().parent.parent / "results.tsv"

# TSV 列顺序（与 results.tsv 表头一致）
TSV_COLUMNS = [
    "commit",
    "timestamp",
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


def _count_tokens(text: str) -> int:
    """用 tiktoken 估算 token 数，不可用时按字符数 / 4 近似。"""
    try:
        import tiktoken

        enc = tiktoken.encoding_for_model("gpt-4")
        return len(enc.encode(text))
    except Exception:
        return len(text) // 4


def measure() -> dict:
    """采集所有指标，返回字典。"""
    from nini.agent.prompt_policy import get_runtime_context_budget
    from nini.agent.prompts.builder import PromptBuilder

    # ---- 1. System Prompt Token 开销 ----
    builder = PromptBuilder(context_window=None)  # full profile
    prompt = builder.build(intent_hints={"chart", "stat_test"})
    prompt_tokens = _count_tokens(prompt)

    # ---- 2. 工具 Schema Token 开销 ----
    tool_tokens = 0
    tool_count = 0
    try:
        from nini.tools.registry import create_default_tool_registry

        registry = create_default_tool_registry()
        tool_defs = registry.get_tool_definitions()
        tool_text = json.dumps(tool_defs, ensure_ascii=False)
        tool_tokens = _count_tokens(tool_text)
        tool_count = len(tool_defs)
    except Exception as e:
        print(f"警告: 工具 schema 测量失败: {e}", file=sys.stderr)

    # ---- 3. 运行时上下文预算 ----
    budget_full = get_runtime_context_budget("full")
    budget_standard = get_runtime_context_budget("standard")
    budget_compact = get_runtime_context_budget("compact")

    # ---- 4. 复合指标 ----
    total_tokens = prompt_tokens + tool_tokens

    return {
        "prompt_tokens": prompt_tokens,
        "prompt_chars": len(prompt),
        "tool_schema_tokens": tool_tokens,
        "tool_count": tool_count,
        "total_tokens": total_tokens,
        "budget_full": budget_full,
        "budget_standard": budget_standard,
        "budget_compact": budget_compact,
    }


def load_last_keep() -> dict | None:
    """从 results.tsv 读取最后一条 status=keep 的记录。"""
    if not RESULTS_TSV.exists():
        return None
    with open(RESULTS_TSV, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        last_keep = None
        for row in reader:
            if row.get("status") == "keep":
                last_keep = row
    return last_keep


def print_metrics(metrics: dict) -> None:
    """输出指标（供日志 grep 使用）。"""
    print("--- nini autoresearch metrics ---")
    for key in [
        "prompt_tokens",
        "prompt_chars",
        "tool_schema_tokens",
        "tool_count",
        "total_tokens",
        "budget_full",
        "budget_standard",
        "budget_compact",
    ]:
        print(f"{key}: {metrics[key]}")


def print_delta(metrics: dict, baseline: dict) -> None:
    """对比当前指标与 baseline，输出 delta。"""
    print("\n--- delta vs last keep ---")
    compare_keys = [
        ("prompt_tokens", "prompt_tokens"),
        ("tool_schema_tokens", "tool_schema_tokens"),
        ("total_tokens", "total_tokens"),
    ]
    for metric_key, tsv_key in compare_keys:
        current = metrics[metric_key]
        previous = int(baseline.get(tsv_key, current))
        delta = current - previous
        pct = (delta / previous * 100) if previous else 0
        arrow = "↑" if delta > 0 else "↓" if delta < 0 else "="
        print(f"  {metric_key}: {previous} → {current}  ({arrow} {abs(delta)}, {pct:+.1f}%)")

    # 建议
    total_delta = metrics["total_tokens"] - int(baseline.get("total_tokens", metrics["total_tokens"]))
    if total_delta < -10:
        print("\n  💡 建议: total_tokens 下降，若测试全通过则 keep")
    elif total_delta > 10:
        print("\n  ⚠️  建议: total_tokens 上升，考虑 discard")
    else:
        print("\n  ℹ️  建议: 变化不显著（±10 tokens 内），按其他收益判断")


def append_to_tsv(metrics: dict, commit: str, changed_file: str, summary: str, status: str,
                  test_passed: int = 0, test_failed: int = 0, test_duration: float = 0.0) -> None:
    """追加一行到 results.tsv。"""
    row = {
        "commit": commit,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M"),
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
    parser = argparse.ArgumentParser(description="测量 Nini prompt/tool token 开销")
    parser.add_argument("--compare", action="store_true", help="与上次 keep 记录对比")
    parser.add_argument("--append", action="store_true", help="追加到 results.tsv")
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
            print("\n（无历史 keep 记录可对比）")

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
