"""迁移旧 LongTermMemoryStore（JSONL）数据到 SQLite MemoryStore。

扫描 data/sessions/ 目录（或指定的 --data-dir）下每个会话目录中
data/long_term_memory/entries.jsonl 以及顶层 long_term_memory/entries.jsonl，
将每条 LongTermMemoryEntry 写入 SQLite MemoryStore，按 dedup_key 幂等去重。
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _migrate_one_jsonl(jsonl_path: Path, store: "MemoryStore") -> int:  # noqa: F821
    """将单个 entries.jsonl 迁移到 MemoryStore，返回实际写入条数。"""
    count = store.migrate_from_jsonl(jsonl_path)
    if count:
        logger.info("迁移 %s → 写入 %d 条", jsonl_path, count)
    else:
        logger.debug("迁移 %s → 无新条目（已存在或文件为空）", jsonl_path)
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="将 LongTermMemoryStore JSONL 迁移到 SQLite MemoryStore")
    parser.add_argument(
        "--data-dir",
        default="data/sessions",
        help="会话数据根目录（默认：data/sessions）",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="目标 SQLite 数据库路径（默认：data/nini_memory.db）",
    )
    args = parser.parse_args()

    # 动态解析默认 db_path，避免在 import 时触发 settings
    if args.db_path is None:
        try:
            from nini.config import settings

            db_path = settings.sessions_dir.parent / "nini_memory.db"
        except Exception:
            # fallback：相对于当前工作目录
            db_path = Path("data") / "nini_memory.db"
    else:
        db_path = Path(args.db_path)

    # 延迟导入，避免早期 settings 副作用
    from nini.memory.memory_store import MemoryStore

    store = MemoryStore(db_path)
    logger.info("目标数据库：%s", db_path.resolve())

    data_dir = Path(args.data_dir)
    total = 0

    if not data_dir.exists():
        logger.info("数据目录不存在，无需迁移：%s", data_dir.resolve())
        print(f"迁移完成：0 条（目录不存在）")
        store.close()
        return

    # 扫描路径策略：
    # 1. 顶层 data/long_term_memory/entries.jsonl（旧版全局存储）
    global_ltm = data_dir.parent / "long_term_memory" / "entries.jsonl"
    if global_ltm.exists():
        total += _migrate_one_jsonl(global_ltm, store)

    # 2. data/sessions/*/long_term_memory/entries.jsonl（按会话分散存储）
    for session_dir in sorted(data_dir.iterdir()):
        if not session_dir.is_dir():
            continue
        ltm_jsonl = session_dir / "long_term_memory" / "entries.jsonl"
        if ltm_jsonl.exists():
            total += _migrate_one_jsonl(ltm_jsonl, store)

    store.close()
    print(f"迁移完成：共写入 {total} 条记忆")


if __name__ == "__main__":
    main()
