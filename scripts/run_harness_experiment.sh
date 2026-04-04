#!/usr/bin/env bash
# autoresearch harness 实验自动化脚本
#
# 用法：
#   ./scripts/run_harness_experiment.sh <session_id>
#   ./scripts/run_harness_experiment.sh <session_id> <benchmark_set> "描述"
#   ./scripts/run_harness_experiment.sh --auto-run [benchmark_set] [summary]
#   ./scripts/run_harness_experiment.sh --auto-run [benchmark_set] [summary] --provider zhipu --model glm-5
#   ./scripts/run_harness_experiment.sh --auto-run [benchmark_set] [summary] --case-timeout 240
#
# 说明：
#   当前最小版本不会自动触发 benchmark 执行，
#   只会对已存在的 harness session 结果做 pytest 门控 + 聚合评估。
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

AUTO_RUN=0
ROUTE_PROVIDER=""
ROUTE_MODEL=""
CASE_TIMEOUT="240"
if [[ "${1:-}" == "--auto-run" ]]; then
    AUTO_RUN=1
    SESSION_ID=""
    BENCHMARK_SET="${2:-smoke}"
    SUMMARY="${3:-}"
    shift 3 || true
else
    SESSION_ID="${1:-}"
    BENCHMARK_SET="${2:-smoke}"
    SUMMARY="${3:-}"
    shift 3 || true
fi

while [[ $# -gt 0 ]]; do
    case "$1" in
        --provider)
            ROUTE_PROVIDER="${2:-}"
            shift 2
            ;;
        --model)
            ROUTE_MODEL="${2:-}"
            shift 2
            ;;
        --case-timeout)
            CASE_TIMEOUT="${2:-240}"
            shift 2
            ;;
        *)
            echo "未知参数: $1"
            exit 2
            ;;
    esac
done

if [[ -n "$ROUTE_MODEL" && -z "$ROUTE_PROVIDER" ]]; then
    echo "--model 需要与 --provider 一起使用"
    exit 2
fi

if [[ "$AUTO_RUN" -eq 0 && -z "$SESSION_ID" ]]; then
    echo "用法: ./scripts/run_harness_experiment.sh <session_id> [benchmark_set] [summary]"
    echo "或:   ./scripts/run_harness_experiment.sh --auto-run [benchmark_set] [summary] [--provider <id> --model <name>] [--case-timeout <sec>]"
    exit 2
fi

COMMIT=$(git rev-parse --short HEAD)
CHANGED_FILES=$(git diff --name-only HEAD~1 2>/dev/null | paste -sd "," - || echo "-")

if [[ "$AUTO_RUN" -eq 1 ]]; then
    BENCHMARK_CMD=(python scripts/run_harness_benchmarks.py --benchmark-set "$BENCHMARK_SET" --json)
    if [[ -n "$ROUTE_PROVIDER" ]]; then
        BENCHMARK_CMD+=(--provider "$ROUTE_PROVIDER")
    fi
    if [[ -n "$ROUTE_MODEL" ]]; then
        BENCHMARK_CMD+=(--model "$ROUTE_MODEL")
    fi
    BENCHMARK_CMD+=(--case-timeout "$CASE_TIMEOUT")
    AUTO_JSON=$("${BENCHMARK_CMD[@]}")
    SESSION_ID=$(python -c 'import json,sys; print(json.loads(sys.argv[1])["session_id"])' "$AUTO_JSON")
fi

echo "============================================"
echo "  Nini Autoresearch Harness Runner (v1)"
echo "============================================"
echo "commit:        $COMMIT"
echo "session_id:    $SESSION_ID"
echo "benchmark_set: $BENCHMARK_SET"
echo "provider:      ${ROUTE_PROVIDER:--}"
echo "model:         ${ROUTE_MODEL:--}"
echo "case_timeout:  ${CASE_TIMEOUT}s"
echo "changed_files: $CHANGED_FILES"
echo ""

echo ">>> Step 1: pytest 门控"
PYTEST_LOG=$(mktemp)
PYTEST_START=$(date +%s%N)

if python -m pytest -q --tb=short 2>&1 | tee "$PYTEST_LOG"; then
    PYTEST_EXIT=0
else
    PYTEST_EXIT=$?
fi

PYTEST_END=$(date +%s%N)
PYTEST_DURATION=$(echo "scale=1; ($PYTEST_END - $PYTEST_START) / 1000000000" | bc)
TEST_FAILED=$(grep -oP '\d+(?= failed)' "$PYTEST_LOG" | tail -1 || echo "0")

echo ""
echo "pytest: failed=$TEST_FAILED duration=${PYTEST_DURATION}s exit=$PYTEST_EXIT"

if [[ "$PYTEST_EXIT" -ne 0 || "$TEST_FAILED" -gt 0 ]]; then
    echo ""
    echo "⛔ 测试未全部通过，停止 harness 判定。"
    rm -f "$PYTEST_LOG"
    exit 1
fi

echo ""
echo ">>> Step 2: 聚合 harness benchmark 指标并对比"
python scripts/measure_harness_baseline.py \
    --session-id "$SESSION_ID" \
    --benchmark-set "$BENCHMARK_SET" \
    --compare \
    --append \
    --commit "$COMMIT" \
    --changed-files "${CHANGED_FILES:--}" \
    --summary "${SUMMARY:-待填写}" \
    --status "pending"

echo ""
echo "============================================"
echo "  harness 实验完成，请检查结果："
echo "  - 若 pass_rate 不下降且 blocked_rate 不上升，可考虑 keep"
echo "  - 若出现新的 failure tag 或通过率下降，优先 discard"
echo "  - 修改 results/harness_results.tsv 最后一行 status 为 keep 或 discard"
echo "============================================"

rm -f "$PYTEST_LOG"
