"""领域知识加载器，根据对话上下文选择并注入相关知识。

知识文件是 Markdown 格式，头部包含元信息注释：
    <!-- keywords: t检验, 比较, 差异 -->
    <!-- priority: high -->

加载器扫描知识目录，解析关键词和优先级，根据用户消息中的
关键词匹配度选择最相关的知识条目注入到 system prompt 中。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 元信息注释正则
_KEYWORDS_RE = re.compile(r"<!--\s*keywords:\s*(.+?)\s*-->", re.IGNORECASE)
_PRIORITY_RE = re.compile(r"<!--\s*priority:\s*(\w+)\s*-->", re.IGNORECASE)
# HTML 注释（用于从正文中去除元信息）
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

_PRIORITY_WEIGHT = {"high": 2, "normal": 1, "low": 0}


@dataclass
class KnowledgeEntry:
    """一个知识文件的解析结果。"""

    path: Path
    keywords: set[str] = field(default_factory=set)
    priority: str = "normal"
    content: str = ""

    @property
    def priority_weight(self) -> int:
        return _PRIORITY_WEIGHT.get(self.priority, 1)


class KnowledgeLoader:
    """领域知识加载器，根据对话上下文选择并注入相关知识。"""

    def __init__(self, knowledge_dir: Path) -> None:
        self._dir = knowledge_dir
        self._entries: list[KnowledgeEntry] = []
        self._load_entries()

    @property
    def entries(self) -> list[KnowledgeEntry]:
        """所有已加载的知识条目（只读）。"""
        return list(self._entries)

    def reload(self) -> None:
        """重新扫描知识目录。"""
        self._entries.clear()
        self._load_entries()

    def select(
        self,
        user_message: str,
        *,
        dataset_columns: list[str] | None = None,
        max_entries: int = 3,
        max_total_chars: int = 3000,
    ) -> str:
        """根据上下文选择最相关的知识条目，返回拼接后的文本。"""
        text, _ = self.select_with_hits(
            user_message,
            dataset_columns=dataset_columns,
            max_entries=max_entries,
            max_total_chars=max_total_chars,
        )
        return text

    def select_with_hits(
        self,
        user_message: str,
        *,
        dataset_columns: list[str] | None = None,
        max_entries: int = 3,
        max_total_chars: int = 3000,
    ) -> tuple[str, list[dict[str, Any]]]:
        """根据上下文选择最相关的知识条目，返回拼接后的文本。

        匹配逻辑：
        1. 将 user_message 与每个条目的 keywords 做交集
        2. 按匹配关键词数量 × priority_weight 排序
        3. 取前 max_entries 个，总字符数不超过 max_total_chars
        """
        if not self._entries or not user_message:
            return "", []

        msg_lower = user_message.lower()

        scored: list[tuple[float, int, KnowledgeEntry]] = []
        for entry in self._entries:
            hits = sum(1 for kw in entry.keywords if kw in msg_lower)
            if hits == 0:
                continue
            score = hits * entry.priority_weight
            scored.append((score, hits, entry))

        if not scored:
            return "", []

        # 按得分降序排列
        scored.sort(key=lambda t: t[0], reverse=True)

        parts: list[str] = []
        hit_items: list[dict[str, Any]] = []
        total_chars = 0
        for score, hits, entry in scored[:max_entries]:
            chunk = entry.content
            source = entry.path.name
            if total_chars + len(chunk) > max_total_chars:
                # 尝试截断到限制内
                remaining = max_total_chars - total_chars
                if remaining > 200:
                    chunk = chunk[:remaining] + "\n..."
                    parts.append(chunk)
                    hit_items.append(
                        {
                            "source": source,
                            "score": float(score),
                            "hits": int(hits),
                            "snippet": chunk[:300],
                        }
                    )
                break
            parts.append(chunk)
            total_chars += len(chunk)
            hit_items.append(
                {
                    "source": source,
                    "score": float(score),
                    "hits": int(hits),
                    "snippet": chunk[:300],
                }
            )

        return "\n\n".join(parts), hit_items

    # ------ 内部方法 ------

    def _load_entries(self) -> None:
        """扫描知识目录，解析每个 .md 文件的元信息。"""
        if not self._dir.is_dir():
            logger.debug("知识目录不存在: %s", self._dir)
            return

        for md_path in sorted(self._dir.rglob("*.md")):
            # 跳过 README
            if md_path.name.lower() == "readme.md":
                continue
            try:
                entry = self._parse_file(md_path)
                self._entries.append(entry)
                logger.debug(
                    "加载知识: %s (关键词=%d, 优先级=%s)",
                    md_path.name,
                    len(entry.keywords),
                    entry.priority,
                )
            except Exception:
                logger.warning("解析知识文件失败: %s", md_path, exc_info=True)

    @staticmethod
    def _parse_file(path: Path) -> KnowledgeEntry:
        """解析单个知识文件，提取关键词、优先级和正文。"""
        raw = path.read_text(encoding="utf-8")

        # 提取关键词
        keywords: set[str] = set()
        m = _KEYWORDS_RE.search(raw)
        if m:
            keywords = {kw.strip().lower() for kw in m.group(1).split(",") if kw.strip()}

        # 提取优先级
        priority = "normal"
        m = _PRIORITY_RE.search(raw)
        if m:
            p = m.group(1).lower()
            if p in _PRIORITY_WEIGHT:
                priority = p

        # 去除 HTML 注释，得到正文
        content = _COMMENT_RE.sub("", raw).strip()

        return KnowledgeEntry(
            path=path,
            keywords=keywords,
            priority=priority,
            content=content,
        )
