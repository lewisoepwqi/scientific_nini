#!/usr/bin/env bash
# autoresearch static 实验自动化脚本
#
# 用法：
#   ./scripts/run_static_experiment.sh
#   ./scripts/run_static_experiment.sh "精简 strategy_core"
#
# 流程：pytest 门控 → v2 runtime baseline measure → delta 对比 → 追加 results/static_results.tsv → 建议 keep/discard
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

SUMMARY="${1:-}"
COMMIT=$(git rev-parse --short HEAD)
CHANGED_FILE=$(git diff --name-only HEAD~1 2>/dev/null | head -1 || echo "-")

echo "============================================"
echo "  Nini Autoresearch Static Runner (v2)"
echo "============================================"
echo "commit:       $COMMIT"
echo "changed_file: $CHANGED_FILE"
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

TEST_PASSED=$(grep -oP '\d+(?= passed)' "$PYTEST_LOG" | tail -1 || echo "0")
TEST_FAILED=$(grep -oP '\d+(?= failed)' "$PYTEST_LOG" | tail -1 || echo "0")

echo ""
echo "pytest: passed=$TEST_PASSED failed=$TEST_FAILED duration=${PYTEST_DURATION}s exit=$PYTEST_EXIT"

if [[ "$PYTEST_EXIT" -ne 0 || "$TEST_FAILED" -gt 0 ]]; then
    echo ""
    echo "⛔ 测试未全部通过！"
    echo ""
    echo ">>> 采集 static v2 运行面指标（标记为 discard）..."
    python scripts/measure_static_baseline.py \
        --compare \
        --append \
        --commit "$COMMIT" \
        --changed-file "$CHANGED_FILE" \
        --summary "${SUMMARY:-test_failed=$TEST_FAILED}" \
        --status "discard" \
        --test-passed "$TEST_PASSED" \
        --test-failed "$TEST_FAILED" \
        --test-duration "$PYTEST_DURATION"
    echo ""
    echo "建议: git reset HEAD~1 回退此次 static 实验"
    rm -f "$PYTEST_LOG"
    exit 1
fi

echo ""
echo ">>> Step 2: 采集 static v2 运行面指标并对比"
python scripts/measure_static_baseline.py \
    --compare \
    --append \
    --commit "$COMMIT" \
    --changed-file "$CHANGED_FILE" \
    --summary "${SUMMARY:-待填写}" \
    --status "pending" \
    --test-passed "$TEST_PASSED" \
    --test-failed "$TEST_FAILED" \
    --test-duration "$PYTEST_DURATION"

echo ""
echo "============================================"
echo "  static 实验完成，请检查 delta 结果："
echo "  - 若主基线 total_tokens 改善且测试通过: 编辑 results/static_results.tsv 最后一行 status → keep"
echo "  - 若退步: 编辑 results/static_results.tsv 最后一行 status → discard，然后 git reset HEAD~1"
echo "  - 若提示无同版本 baseline: 先将本次记录作为 static v2 baseline keep"
echo "============================================"

rm -f "$PYTEST_LOG"
