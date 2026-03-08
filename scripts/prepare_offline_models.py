"""预下载离线模型到本地缓存，供 Windows 打包脚本复用。

用途：
1. 在打包机上提前拉取语义意图、本地知识检索、重排序模型；
2. 将模型缓存写入指定目录，后续由 PyInstaller 一并打包；
3. 终端输出分阶段进度，方便观察下载状态。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Callable

from nini.config import settings


DEFAULT_SEMANTIC_MODEL = "all-MiniLM-L6-v2"


def _print_step(index: int, total: int, title: str) -> None:
    """输出阶段进度。"""
    print(f"[{index}/{total}] {title}", flush=True)


def _ensure_dir(path: Path) -> Path:
    """确保目录存在并返回规范路径。"""
    resolved = path.expanduser().resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _configure_cache_env(hf_home: Path, sentence_home: Path) -> None:
    """设置当前进程所需的缓存环境变量。"""
    os.environ["HF_HOME"] = str(hf_home)
    os.environ["HUGGINGFACE_HUB_CACHE"] = str(hf_home / "hub")
    os.environ["SENTENCE_TRANSFORMERS_HOME"] = str(sentence_home)
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")


def _is_sentence_transformer_cached(model_name: str, sentence_home: Path) -> bool:
    """检查 sentence-transformers 缓存是否已命中。"""
    try:
        from sentence_transformers import SentenceTransformer

        SentenceTransformer(
            model_name,
            cache_folder=str(sentence_home),
            local_files_only=True,
        )
        return True
    except Exception:
        return False


def _is_cross_encoder_cached(model_name: str, sentence_home: Path) -> bool:
    """检查 CrossEncoder 缓存是否已命中。"""
    try:
        from sentence_transformers import CrossEncoder

        CrossEncoder(
            model_name,
            cache_folder=str(sentence_home),
            local_files_only=True,
        )
        return True
    except Exception:
        return False


def _download_sentence_transformer(model_name: str, sentence_home: Path, label: str) -> None:
    """下载 sentence-transformers 模型。"""
    from sentence_transformers import SentenceTransformer

    print(f"  模型：{label} -> {model_name}", flush=True)
    if _is_sentence_transformer_cached(model_name, sentence_home):
        print("  状态：本地缓存已存在，跳过下载", flush=True)
        return

    print("  状态：开始下载，下面会显示 Hugging Face 进度条", flush=True)
    SentenceTransformer(model_name, cache_folder=str(sentence_home))
    print("  状态：下载完成", flush=True)


def _download_cross_encoder(model_name: str, sentence_home: Path, label: str) -> None:
    """下载 CrossEncoder 模型。"""
    from sentence_transformers import CrossEncoder

    print(f"  模型：{label} -> {model_name}", flush=True)
    if _is_cross_encoder_cached(model_name, sentence_home):
        print("  状态：本地缓存已存在，跳过下载", flush=True)
        return

    print("  状态：开始下载，下面会显示 Hugging Face 进度条", flush=True)
    CrossEncoder(model_name, cache_folder=str(sentence_home))
    print("  状态：下载完成", flush=True)


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="预下载 Nini 离线模型缓存")
    parser.add_argument(
        "--hf-home",
        default=os.environ.get("NINI_HF_HOME") or os.environ.get("HF_HOME") or "",
        help="Hugging Face 缓存根目录",
    )
    parser.add_argument(
        "--sentence-transformers-home",
        default=(
            os.environ.get("NINI_SENTENCE_TRANSFORMERS_HOME")
            or os.environ.get("SENTENCE_TRANSFORMERS_HOME")
            or ""
        ),
        help="sentence-transformers 缓存目录",
    )
    parser.add_argument(
        "--semantic-model",
        default=DEFAULT_SEMANTIC_MODEL,
        help="语义意图识别模型名称",
    )
    parser.add_argument(
        "--knowledge-model",
        default=settings.knowledge_local_embedding_model,
        help="本地知识检索 embedding 模型名称",
    )
    parser.add_argument(
        "--reranker-model",
        default=settings.hierarchical_reranker_model,
        help="层次化重排序模型名称",
    )
    parser.add_argument(
        "--skip-semantic",
        action="store_true",
        help="跳过语义意图模型下载",
    )
    parser.add_argument(
        "--skip-knowledge",
        action="store_true",
        help="跳过知识 embedding 模型下载",
    )
    parser.add_argument(
        "--skip-reranker",
        action="store_true",
        help="跳过重排序模型下载",
    )
    return parser.parse_args()


def main() -> int:
    """执行离线模型预下载。"""
    args = parse_args()

    hf_home_raw = args.hf_home or str(Path.home() / ".cache" / "huggingface")
    sentence_home_raw = args.sentence_transformers_home or str(
        Path.home() / ".cache" / "torch" / "sentence_transformers"
    )

    hf_home = _ensure_dir(Path(hf_home_raw))
    sentence_home = _ensure_dir(Path(sentence_home_raw))
    _configure_cache_env(hf_home, sentence_home)

    print("=== Nini Offline Model Preparation ===", flush=True)
    print(f"HF_HOME={hf_home}", flush=True)
    print(f"SENTENCE_TRANSFORMERS_HOME={sentence_home}", flush=True)
    print("", flush=True)

    tasks: list[tuple[str, Callable[[], None]]] = []
    if not args.skip_semantic:
        tasks.append(
            (
                "预下载语义意图 embedding 模型",
                lambda: _download_sentence_transformer(
                    args.semantic_model,
                    sentence_home,
                    "语义意图 embedding",
                ),
            )
        )
    if not args.skip_knowledge:
        tasks.append(
            (
                "预下载知识检索 embedding 模型",
                lambda: _download_sentence_transformer(
                    args.knowledge_model,
                    sentence_home,
                    "知识检索 embedding",
                ),
            )
        )
    if not args.skip_reranker:
        tasks.append(
            (
                "预下载层次化重排序模型",
                lambda: _download_cross_encoder(
                    args.reranker_model,
                    sentence_home,
                    "层次化重排序",
                ),
            )
        )

    if not tasks:
        print("没有需要下载的模型，已跳过。", flush=True)
        return 0

    for index, (title, action) in enumerate(tasks, start=1):
        _print_step(index, len(tasks), title)
        try:
            action()
        except KeyboardInterrupt:
            print("\n已中断离线模型下载。", file=sys.stderr, flush=True)
            return 130
        except Exception as exc:
            print(f"错误：{title}失败: {exc}", file=sys.stderr, flush=True)
            return 1
        print("", flush=True)

    print("=== 离线模型准备完成 ===", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
