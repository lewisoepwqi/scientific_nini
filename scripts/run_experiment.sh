#!/usr/bin/env bash
# autoresearch 实验自动化脚本
#
# 用法：
#   ./scripts/run_experiment.sh                    # 交互式（自动检测改动文件）
#   ./scripts/run_experiment.sh "精简 strategy_core"  # 指定描述
#
# 流程：pytest 门控 → measure → delta 对比 → 追加 results.tsv → 建议 keep/discard
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

SUMMARY="${1:-}"
COMMIT=$(git rev-parse --short HEAD)
CHANGED_FILE=$(git diff --name-only HEAD~1 2>/dev/null | head -1 || echo "-")

echo "============================================"
echo "  Nini Autoresearch Experiment Runner"
echo "============================================"
echo "commit:       $COMMIT"
echo "changed_file: $CHANGED_FILE"
echo ""

# ---- Step 1: pytest 门控 ----
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

# 解析测试结果
TEST_PASSED=$(grep -oP '\d+(?= passed)' "$PYTEST_LOG" | tail -1 || echo "0")
TEST_FAILED=$(grep -oP '\d+(?= failed)' "$PYTEST_LOG" | tail -1 || echo "0")

echo ""
echo "pytest: passed=$TEST_PASSED failed=$TEST_FAILED duration=${PYTEST_DURATION}s exit=$PYTEST_EXIT"

if [[ "$PYTEST_EXIT" -ne 0 || "$TEST_FAILED" -gt 0 ]]; then
    echo ""
    echo "⛔ 测试未全部通过！"
    echo ""
    # 仍然采集指标但标记 discard
    echo ">>> 采集指标（标记为 discard）..."
    python scripts/measure_baseline.py \
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
    echo "建议: git reset HEAD~1 回退此次实验"
    rm -f "$PYTEST_LOG"
    exit 1
fi

# ---- Step 2: 采集指标并对比 ----
echo ""
echo ">>> Step 2: 采集指标并对比"
python scripts/measure_baseline.py \
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
echo "  实验完成！请检查 delta 结果："
echo "  - 若改善: 编辑 results.tsv 最后一行 status → keep"
echo "  - 若退步: 编辑 results.tsv 最后一行 status → discard，然后 git reset HEAD~1"
echo "============================================"

rm -f "$PYTEST_LOG"
