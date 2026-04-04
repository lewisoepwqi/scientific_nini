"""执行第二条 autoresearch-harness 线的 benchmark 集。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nini.harness.autoresearch import DEFAULT_BENCHMARKS_PATH, run_benchmark_set  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="执行 Nini autoresearch harness benchmark")
    parser.add_argument("--benchmark-set", default="smoke", help="benchmark 集名称")
    parser.add_argument(
        "--benchmark-config",
        default=str(DEFAULT_BENCHMARKS_PATH),
        help="benchmark YAML 路径",
    )
    parser.add_argument("--session-id", default=None, help="可选，指定输出 session_id")
    parser.add_argument("--provider", default=None, help="可选，显式指定 benchmark provider")
    parser.add_argument("--model", default=None, help="可选，显式指定 benchmark model")
    parser.add_argument("--case-timeout", type=float, default=240.0, help="单个 case 超时秒数")
    parser.add_argument("--json", action="store_true", help="仅输出 JSON 结果")
    args = parser.parse_args()

    result = run_benchmark_set(
        benchmark_set=args.benchmark_set,
        config_path=Path(args.benchmark_config),
        session_id=args.session_id,
        route_provider_id=args.provider,
        route_model=args.model,
        case_timeout_seconds=args.case_timeout,
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
        return

    print("--- harness benchmark batch ---")
    print(f"session_id: {result['session_id']}")
    print(f"benchmark_set: {result['benchmark_set']}")
    print(f"case_count: {result['case_count']}")
    print("\n--- cases ---")
    for item in result["cases"]:
        print(json.dumps(item, ensure_ascii=False))


if __name__ == "__main__":
    main()
