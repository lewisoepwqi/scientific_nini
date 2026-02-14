"""领域知识加载器，根据对话上下文选择并注入相关知识。

知识文件是 Markdown 格式，头部包含元信息注释：
    <!-- keywords: t检验, 比较, 差异 -->
    <!-- priority: high -->

加载器扫描知识目录，解析关键词和优先级，根据用户消息中的
关键词匹配度选择最相关的知识条目注入到 system prompt 中。

当向量索引可用时，自动启用向量+关键词混合检索模式，
语义检索结果与关键词结果融合并去重后返回。
"""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 延迟导入，避免循环依赖
_vector_store: Any = None

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
    """领域知识加载器，根据对话上下文选择并注入相关知识。

    当向量索引可用时，自动启用混合检索模式（向量语义 + 关键词匹配），
    否则仅使用关键词匹配。
    """

    def __init__(self, knowledge_dir: Path, *, enable_vector: bool = True) -> None:
        self._dir = knowledge_dir
        self._entries: list[KnowledgeEntry] = []
        self._vector_store: Any = None  # VectorKnowledgeStore
        self._lock = threading.RLock()
        self._load_entries()
        if enable_vector:
            self._init_vector_store()

    @property
    def entries(self) -> list[KnowledgeEntry]:
        """所有已加载的知识条目（只读）。"""
        return list(self._entries)

    @property
    def vector_available(self) -> bool:
        """向量检索是否可用。"""
        return self._vector_store is not None and self._vector_store.is_available

    def reload(self) -> None:
        """重新扫描知识目录（线程安全）。"""
        with self._lock:
            new_entries: list[KnowledgeEntry] = []
            if self._dir.is_dir():
                for md_path in sorted(self._dir.rglob("*.md")):
                    if md_path.name.lower() == "readme.md":
                        continue
                    try:
                        entry = self._parse_file(md_path)
                        new_entries.append(entry)
                    except Exception:
                        logger.warning("解析知识文件失败: %s", md_path, exc_info=True)
            # 原子替换
            self._entries = new_entries
            if self._vector_store is not None:
                self._vector_store.build_or_load()

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

        当向量索引可用时，使用混合检索（向量语义 + 关键词匹配），
        否则仅使用关键词匹配。

        匹配逻辑：
        1. 向量语义检索（如可用）
        2. 关键词匹配（user_message 与 keywords 交集）
        3. 融合去重，按得分排序
        4. 取前 max_entries 个，总字符数不超过 max_total_chars
        """
        if not user_message:
            return "", []

        # 关键词匹配结果
        keyword_text, keyword_hits = self._keyword_search(
            user_message,
            max_entries=max_entries,
            max_total_chars=max_total_chars,
        )

        # 如果向量不可用，直接返回关键词结果
        if not self.vector_available:
            return keyword_text, keyword_hits

        # 向量语义检索
        vector_text, vector_hits = self._vector_store.query(
            user_message,
            top_k=max_entries,
            max_total_chars=max_total_chars,
        )

        # 融合去重：向量结果优先，关键词结果补充
        return self._merge_results(
            vector_hits=vector_hits,
            keyword_hits=keyword_hits,
            max_entries=max_entries,
            max_total_chars=max_total_chars,
        )

    def _keyword_search(
        self,
        user_message: str,
        *,
        max_entries: int = 3,
        max_total_chars: int = 3000,
    ) -> tuple[str, list[dict[str, Any]]]:
        """纯关键词匹配检索（原始逻辑）。"""
        if not self._entries or not user_message:
            return "", []

        msg_lower = user_message.lower()

        scored: list[tuple[float, int, KnowledgeEntry]] = []
        for entry in self._entries:
            hits = sum(1 for kw in entry.keywords if kw in msg_lower)
            if hits == 0:
                continue
            score = float(hits * entry.priority_weight)
            scored.append((score, hits, entry))

        if not scored:
            return "", []

        scored.sort(key=lambda t: t[0], reverse=True)

        parts: list[str] = []
        hit_items: list[dict[str, Any]] = []
        total_chars = 0
        for score, hits, entry in scored[:max_entries]:
            chunk = entry.content
            source = entry.path.name
            if total_chars + len(chunk) > max_total_chars:
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
                            "method": "keyword",
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
                    "method": "keyword",
                }
            )

        return "\n\n".join(parts), hit_items

    @staticmethod
    def _merge_results(
        *,
        vector_hits: list[dict[str, Any]],
        keyword_hits: list[dict[str, Any]],
        max_entries: int,
        max_total_chars: int,
    ) -> tuple[str, list[dict[str, Any]]]:
        """融合向量检索与关键词匹配结果，去重后按得分排序。"""
        seen_keys: set[str] = set()
        merged: list[dict[str, Any]] = []

        def _dedup_key(hit: dict[str, Any]) -> str:
            """生成去重键：source + snippet 前 100 字符。"""
            source = hit.get("source", "")
            snippet = hit.get("snippet", "")[:100]
            return f"{source}:{snippet}"

        # 向量结果优先
        for hit in vector_hits:
            key = _dedup_key(hit)
            if key not in seen_keys:
                seen_keys.add(key)
                merged.append(hit)

        # 关键词结果补充
        for hit in keyword_hits:
            key = _dedup_key(hit)
            if key not in seen_keys:
                seen_keys.add(key)
                merged.append(hit)

        # 按得分排序
        merged.sort(key=lambda h: float(h.get("score", 0)), reverse=True)

        # 截取并拼接
        parts: list[str] = []
        final_hits: list[dict[str, Any]] = []
        total_chars = 0

        for hit in merged[:max_entries]:
            snippet = hit.get("snippet", "")
            if total_chars + len(snippet) > max_total_chars:
                remaining = max_total_chars - total_chars
                if remaining > 200:
                    snippet = snippet[:remaining] + "\n..."
                    parts.append(snippet)
                    final_hits.append(hit)
                break
            parts.append(snippet)
            total_chars += len(snippet)
            final_hits.append(hit)

        return "\n\n".join(parts), final_hits

    # ------ 内部方法 ------

    def _init_vector_store(self) -> None:
        """尝试初始化向量索引。失败时静默回退到关键词模式。"""
        try:
            from nini.knowledge.vector_store import VectorKnowledgeStore, _check_llama_index

            if not _check_llama_index():
                return

            from nini.config import settings

            storage_dir = settings.data_dir / "vector_index"
            self._vector_store = VectorKnowledgeStore(
                knowledge_dir=self._dir,
                storage_dir=storage_dir,
                embed_model=settings.knowledge_openai_embedding_model,
            )
            if self._vector_store.build_or_load():
                logger.info("向量知识索引已就绪，启用混合检索模式")
            else:
                self._vector_store = None
                logger.info("向量索引初始化失败，使用纯关键词检索")
        except Exception:
            self._vector_store = None
            logger.warning("向量检索初始化失败，回退到关键词检索", exc_info=True)

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
