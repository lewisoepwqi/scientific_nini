#!/usr/bin/env bash
set -euo pipefail

# 预下载知识库本地 embedding 模型并做可用性验证。
# 默认模型与 Nini 配置保持一致：BAAI/bge-small-zh-v1.5

MODEL_ID="${NINI_KNOWLEDGE_LOCAL_EMBEDDING_MODEL:-BAAI/bge-small-zh-v1.5}"
CACHE_DIR="${HF_HOME:-$HOME/.cache/huggingface}"
LOCAL_DIR=""
REVISION=""
PYTHON_BIN=""

usage() {
  cat <<'EOF'
用法:
  scripts/prefetch_embedding_model.sh [选项]

选项:
  --model <repo_id>       模型仓库 ID（默认: NINI_KNOWLEDGE_LOCAL_EMBEDDING_MODEL 或 BAAI/bge-small-zh-v1.5）
  --cache-dir <path>      HuggingFace 缓存目录（默认: HF_HOME 或 ~/.cache/huggingface）
  --local-dir <path>      固定落盘目录（推荐生产使用）；设置后会把模型下载到该目录
  --revision <rev>        锁定模型版本（tag/branch/commit），默认使用仓库默认分支
  --python <path>         指定 Python 解释器（默认优先 .venv/bin/python）
  -h, --help              显示帮助

示例:
  scripts/prefetch_embedding_model.sh
  scripts/prefetch_embedding_model.sh --local-dir data/models/bge-small-zh-v1.5 --revision main
  scripts/prefetch_embedding_model.sh --model BAAI/bge-base-zh-v1.5
  scripts/prefetch_embedding_model.sh --cache-dir /data/hf-cache
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --model)
      MODEL_ID="${2:-}"
      shift 2
      ;;
    --cache-dir)
      CACHE_DIR="${2:-}"
      shift 2
      ;;
    --local-dir)
      LOCAL_DIR="${2:-}"
      shift 2
      ;;
    --revision)
      REVISION="${2:-}"
      shift 2
      ;;
    --python)
      PYTHON_BIN="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "未知参数: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ -z "$MODEL_ID" ]]; then
  echo "模型 ID 不能为空" >&2
  exit 2
fi

if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x ".venv/bin/python" ]]; then
    PYTHON_BIN=".venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "找不到 Python 解释器: $PYTHON_BIN" >&2
  exit 1
fi

mkdir -p "$CACHE_DIR"

echo "开始预下载 embedding 模型"
echo "MODEL_ID=$MODEL_ID"
echo "CACHE_DIR=$CACHE_DIR"
echo "LOCAL_DIR=${LOCAL_DIR:-<cache-only>}"
echo "REVISION=${REVISION:-<default>}"
echo "PYTHON_BIN=$PYTHON_BIN"

MODEL_ID="$MODEL_ID" HF_HOME="$CACHE_DIR" LOCAL_DIR="$LOCAL_DIR" REVISION="$REVISION" "$PYTHON_BIN" - <<'PY'
from __future__ import annotations

import os
import sys

model_id = os.environ["MODEL_ID"]
cache_dir = os.environ["HF_HOME"]
local_dir = os.environ.get("LOCAL_DIR", "").strip()
revision = os.environ.get("REVISION", "").strip()

print(f"[1/2] 下载模型快照: {model_id}")
try:
    from huggingface_hub import snapshot_download
except Exception as exc:  # noqa: BLE001
    print("缺少 huggingface_hub，请先安装依赖：", file=sys.stderr)
    print("  .venv/bin/pip install llama-index-embeddings-huggingface", file=sys.stderr)
    print(f"详细错误: {exc}", file=sys.stderr)
    raise SystemExit(1) from exc

try:
    kwargs = {
        "repo_id": model_id,
        "cache_dir": cache_dir,
        "resume_download": True,
    }
    if revision:
        kwargs["revision"] = revision
    if local_dir:
        kwargs["local_dir"] = local_dir

    downloaded_path = snapshot_download(**kwargs)
except Exception as exc:  # noqa: BLE001
    print(f"下载失败: {exc}", file=sys.stderr)
    raise SystemExit(1) from exc

print("[2/2] 验证 Nini 运行时可直接调用 HuggingFaceEmbedding")
try:
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
except Exception as exc:  # noqa: BLE001
    print("缺少 llama-index-embeddings-huggingface，请先安装：", file=sys.stderr)
    print("  .venv/bin/pip install llama-index-embeddings-huggingface", file=sys.stderr)
    print(f"详细错误: {exc}", file=sys.stderr)
    raise SystemExit(1) from exc

try:
    model_ref = local_dir if local_dir else model_id
    embedder = HuggingFaceEmbedding(model_name=model_ref)
    vector = embedder.get_text_embedding("Nini embedding warmup")
    print(f"验证成功，向量维度: {len(vector)}")
    if local_dir:
        print(f"模型固定目录: {local_dir}")
    else:
        print(f"模型缓存目录: {downloaded_path}")
except Exception as exc:  # noqa: BLE001
    print(f"模型可用性验证失败: {exc}", file=sys.stderr)
    raise SystemExit(1) from exc
PY

echo
echo "预下载完成。建议设置以下环境变量（如未设置）："
if [[ -n "$LOCAL_DIR" ]]; then
  echo "  export NINI_KNOWLEDGE_LOCAL_EMBEDDING_MODEL=\"$LOCAL_DIR\""
else
  echo "  export NINI_KNOWLEDGE_LOCAL_EMBEDDING_MODEL=\"$MODEL_ID\""
fi
echo "  export HF_HOME=\"$CACHE_DIR\""
echo
echo "然后重启 Nini 服务。"
