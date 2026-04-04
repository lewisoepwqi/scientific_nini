#!/usr/bin/env bash
# static 线兼容入口，转发到 run_static_experiment.sh。
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
exec ./scripts/run_static_experiment.sh "$@"
