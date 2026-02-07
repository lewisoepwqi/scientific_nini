"""JSONL 会话记忆。

每个会话一个 .jsonl 文件，append-only 追加写入。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nini.config import settings

logger = logging.getLogger(__name__)


class ConversationMemory:
    """基于 JSONL 的持久化会话记忆。"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._dir = settings.sessions_dir / session_id
        self._path = self._dir / "memory.jsonl"

    def _ensure_dir(self) -> None:
        """确保目录存在（延迟创建）。"""
        if not self._dir.exists():
            self._dir.mkdir(parents=True, exist_ok=True)

    def append(self, entry: dict[str, Any]) -> None:
        """追加一条记录。"""
        self._ensure_dir()
        entry["_ts"] = datetime.now(timezone.utc).isoformat()
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")

    def load_all(self) -> list[dict[str, Any]]:
        """加载所有记录。"""
        if not self._path.exists():
            return []
        entries: list[dict[str, Any]] = []
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.warning("跳过损坏的 JSONL 行: %s", line[:100])
        return entries

    def load_messages(self) -> list[dict[str, Any]]:
        """加载所有消息（过滤出 role 字段的记录）。"""
        return [e for e in self.load_all() if "role" in e]

    def clear(self) -> None:
        """清空会话记忆。"""
        if self._path.exists():
            self._path.unlink()
