"""本地 BM25 知识检索器 — 零外部依赖实现。

使用 BM25 算法和 jieba 中文分词实现高效本地检索，
无需向量模型或外部 API。
- 延迟：~10ms（1000 文档以内）
- 内存：~30MB（索引结构）
- 依赖：jieba, rank_bm25（纯 Python）
"""

from __future__ import annotations

import json
import logging
import pickle
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 延迟导入（避免未安装时导入失败）
_jieba = None
_BM25Okapi = None


def _get_jieba():
    """获取 jieba 分词器（延迟导入）。"""
    global _jieba
    if _jieba is None:
        try:
            import jieba

            _jieba = jieba
            # 禁用 jieba 日志
            _jieba.setLogLevel(logging.INFO)
        except ImportError:
            logger.warning("jieba 未安装，将使用简单分词")
            _jieba = False
    return _jieba


def _get_bm25():
    """获取 BM25 类（延迟导入）。"""
    global _BM25Okapi
    if _BM25Okapi is None:
        try:
            from rank_bm25 import BM25Okapi

            _BM25Okapi = BM25Okapi
        except ImportError:
            logger.warning("rank_bm25 未安装，BM25 检索不可用")
            _BM25Okapi = False
    return _BM25Okapi


@dataclass
class Document:
    """知识文档。"""

    id: str
    title: str
    content: str
    path: Path | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    """搜索结果。"""

    document: Document
    score: float
    rank: int


class LocalBM25Retriever:
    """本地 BM25 知识检索器。

    基于 BM25 算法和中文分词实现高效的本地知识检索，
    无需外部向量模型或 API 服务。

    Attributes:
        knowledge_dir: 知识库目录
        cache_dir: 索引缓存目录
        _documents: 文档列表
        _bm25: BM25 索引
        _tokenized_docs: 分词后的文档
    """

    def __init__(
        self,
        knowledge_dir: Path,
        cache_dir: Path | None = None,
    ) -> None:
        """初始化 BM25 检索器。

        Args:
            knowledge_dir: 知识库 Markdown 文件目录
            cache_dir: 索引缓存目录，默认为 knowledge_dir/.bm25_cache
        """
        self.knowledge_dir = Path(knowledge_dir)
        self.cache_dir = cache_dir or self.knowledge_dir / ".bm25_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self._documents: list[Document] = []
        self._bm25: Any = None
        self._tokenized_docs: list[list[str]] = []
        self._initialized = False

        # 检查依赖
        self._jieba_available = _get_jieba() is not False
        self._bm25_available = _get_bm25() is not False

        if not self._bm25_available:
            logger.warning("rank_bm25 未安装，BM25 检索功能不可用")
        if not self._jieba_available:
            logger.warning("jieba 未安装，将使用简单分词")

    @property
    def is_available(self) -> bool:
        """检索器是否可用。"""
        return self._bm25_available and self._initialized

    def initialize(self) -> bool:
        """初始化检索器（加载或构建索引）。

        Returns:
            是否成功初始化
        """
        if self._initialized:
            return True

        if not self._bm25_available:
            logger.error("BM25 依赖未安装，无法初始化")
            return False

        # 尝试加载缓存
        if self._load_cache():
            self._initialized = True
            logger.info("BM25 索引从缓存加载完成: %d 文档", len(self._documents))
            return True

        # 构建新索引
        if self._build_index():
            self._save_cache()
            self._initialized = True
            logger.info("BM25 索引构建完成: %d 文档", len(self._documents))
            return True

        return False

    def _tokenize(self, text: str) -> list[str]:
        """分词。

        优先使用 jieba 中文分词，同时生成字符 n-gram 以提高中文召回率。
        对于中文，使用 bi-gram（2字组合）可以匹配部分重叠的词，如：
        - "相关性" 生成 bi-gram: ["相关", "关性"]
        - "相关" 匹配 "相关性" 的一部分
        """
        if not text:
            return []

        text = text.lower().strip()
        tokens: list[str] = []

        # 使用 jieba 分词作为基础
        if self._jieba_available:
            jieba = _get_jieba()
            words = list(jieba.cut(text))
            tokens = [t.strip() for t in words if len(t.strip()) > 1]

            # 对长中文词生成 bi-gram，提高部分匹配能力
            for word in words:
                word = word.strip()
                # 中文长词（3字以上）生成 bi-gram
                if len(word) >= 3 and all('\u4e00' <= c <= '\u9fff' for c in word):
                    for i in range(len(word) - 1):
                        bigram = word[i:i + 2]
                        tokens.append(bigram)
        else:
            # 简单分词（回退）
            tokens = re.findall(r"[a-z][a-z0-9_-]*", text)
            tokens.extend(re.findall(r"[\u4e00-\u9fff]{2,}", text))

        return tokens

    def _build_index(self) -> bool:
        """构建 BM25 索引。"""
        BM25Okapi = _get_bm25()
        if BM25Okapi is False:
            return False

        documents = []
        tokenized_docs = []

        if not self.knowledge_dir.exists():
            logger.warning("知识库目录不存在: %s", self.knowledge_dir)
            return False

        # 遍历所有 Markdown 文件
        md_files = list(self.knowledge_dir.rglob("*.md"))
        logger.info("发现 %d 个知识文件", len(md_files))

        for md_path in md_files:
            if md_path.name.lower() == "readme.md":
                continue

            try:
                content = md_path.read_text(encoding="utf-8")

                # 解析元信息
                metadata = self._parse_metadata(content)
                title = metadata.get("title", md_path.stem)
                clean_content = self._clean_content(content)

                # 创建文档
                doc_id = str(md_path.relative_to(self.knowledge_dir))
                doc = Document(
                    id=doc_id,
                    title=title,
                    content=clean_content,
                    path=md_path,
                    metadata=metadata,
                )
                documents.append(doc)

                # 分词（标题 + 内容）
                text_to_index = f"{title} {clean_content}"
                tokens = self._tokenize(text_to_index)
                tokenized_docs.append(tokens)

            except Exception as e:
                logger.warning("加载知识文件失败: %s - %s", md_path, e)

        if not documents:
            logger.warning("没有加载到任何知识文档")
            return False

        self._documents = documents
        self._tokenized_docs = tokenized_docs
        self._bm25 = BM25Okapi(tokenized_docs)

        return True

    def _parse_metadata(self, content: str) -> dict[str, Any]:
        """解析 Markdown 元信息。"""
        metadata = {}

        # 匹配 HTML 注释格式的元信息
        # <!-- keywords: x, y, z -->
        # <!-- priority: high -->
        keywords_match = re.search(r"<!--\s*keywords:\s*(.+?)\s*-->", content, re.IGNORECASE)
        if keywords_match:
            keywords = [k.strip() for k in keywords_match.group(1).split(",")]
            metadata["keywords"] = keywords

        priority_match = re.search(r"<!--\s*priority:\s*(\w+)\s*-->", content, re.IGNORECASE)
        if priority_match:
            metadata["priority"] = priority_match.group(1).lower()

        # 提取标题（第一个 # 开头行）
        title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if title_match:
            metadata["title"] = title_match.group(1).strip()

        return metadata

    def _clean_content(self, content: str) -> str:
        """清理内容（去除元信息）。"""
        # 去除 HTML 注释
        content = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
        # 去除 Markdown 链接
        content = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", content)
        # 去除代码块
        content = re.sub(r"```[\s\S]*?```", "", content)
        # 去除特殊字符
        content = re.sub(r"[#*`_|\-\[\]]", " ", content)

        return content.strip()

    def search(
        self,
        query: str,
        top_k: int = 3,
        min_score: float = 0.0,
        max_total_chars: int = 3000,
    ) -> tuple[str, list[dict[str, Any]]]:
        """搜索知识库。

        Args:
            query: 查询文本
            top_k: 返回结果数量
            min_score: 最低分数阈值（文档至少有一个匹配词才能达到正分）
            max_total_chars: 返回文本的最大字符数

        Returns:
            (拼接的文本, 详细结果列表)
        """
        if not self.is_available:
            logger.warning("BM25 检索器未初始化")
            return "", []

        if not query:
            return "", []

        # 分词查询
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return "", []

        # BM25 检索
        scores = self._bm25.get_scores(query_tokens)

        # 获取 Top-K
        top_indices = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True,
        )[:top_k]

        # 检查是否有有效结果
        if not top_indices:
            return "", []

        # 检查是否有任何匹配（基于 token 交集）
        # 并计算基于关键词的分数（用于 BM25 失效时的回退）
        keyword_scores: dict[int, int] = {}
        has_matches = False
        query_token_set = set(query_tokens)
        for idx in range(len(self._documents)):
            doc_tokens = set(self._tokenized_docs[idx])
            common = doc_tokens & query_token_set
            keyword_scores[idx] = len(common)
            if common:
                has_matches = True

        # 如果 BM25 所有分数都为 0 但有匹配，使用关键词分数
        if all(scores[i] == 0 for i in top_indices) and has_matches:
            # 使用关键词匹配数量作为排序依据
            top_indices = sorted(
                range(len(scores)),
                key=lambda i: (keyword_scores[i], scores[i]),
                reverse=True,
            )[:top_k]

        results: list[dict[str, Any]] = []
        parts: list[str] = []
        total_chars = 0

        for rank, idx in enumerate(top_indices):
            score = float(scores[idx])
            # 如果 BM25 分数为 0 但有匹配，使用关键词分数作为替代
            if score == 0 and keyword_scores[idx] > 0:
                score = float(keyword_scores[idx])
            # 如果没有匹配且分数太低，跳过
            if score <= min_score and keyword_scores[idx] == 0:
                continue

            doc = self._documents[idx]

            # 构建结果
            result = {
                "id": doc.id,
                "title": doc.title,
                "source": doc.path.name if doc.path else doc.id,
                "score": score,
                "rank": rank + 1,
                "snippet": doc.content[:300] + "..." if len(doc.content) > 300 else doc.content,
            }
            results.append(result)

            # 添加到文本（控制长度）
            content_chunk = f"# {doc.title}\n{doc.content[:1000]}"
            if total_chars + len(content_chunk) > max_total_chars:
                remaining = max_total_chars - total_chars
                if remaining > 100:
                    parts.append(content_chunk[:remaining] + "\n...")
                break

            parts.append(content_chunk)
            total_chars += len(content_chunk)

        return "\n\n".join(parts), results

    def reload(self) -> bool:
        """重新加载索引（知识文件变更后调用）。

        Returns:
            是否成功
        """
        self._initialized = False
        self._documents = []
        self._bm25 = None
        self._tokenized_docs = []

        # 清除缓存
        cache_file = self.cache_dir / "bm25_index.pkl"
        if cache_file.exists():
            cache_file.unlink()

        return self.initialize()

    def _load_cache(self) -> bool:
        """从缓存加载索引。"""
        cache_file = self.cache_dir / "bm25_index.pkl"
        meta_file = self.cache_dir / "bm25_meta.json"

        if not cache_file.exists() or not meta_file.exists():
            return False

        # 检查知识文件是否有变更
        if self._is_cache_stale(meta_file):
            logger.info("BM25 缓存已过期，需要重建")
            return False

        try:
            with open(cache_file, "rb") as f:
                cache_data = pickle.load(f)

            self._documents = cache_data["documents"]
            self._tokenized_docs = cache_data["tokenized_docs"]

            BM25Okapi = _get_bm25()
            self._bm25 = BM25Okapi(self._tokenized_docs)

            return True

        except Exception as e:
            logger.warning("加载 BM25 缓存失败: %s", e)
            return False

    def _save_cache(self) -> None:
        """保存索引到缓存。"""
        cache_file = self.cache_dir / "bm25_index.pkl"
        meta_file = self.cache_dir / "bm25_meta.json"

        try:
            # 保存索引数据
            cache_data = {
                "documents": self._documents,
                "tokenized_docs": self._tokenized_docs,
            }
            with open(cache_file, "wb") as f:
                pickle.dump(cache_data, f)

            # 保存元信息（文件哈希）
            file_hashes = self._compute_file_hashes()
            meta = {
                "file_hashes": file_hashes,
                "doc_count": len(self._documents),
            }
            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.warning("保存 BM25 缓存失败: %s", e)

    def _is_cache_stale(self, meta_file: Path) -> bool:
        """检查缓存是否过期。"""
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)

            saved_hashes = meta.get("file_hashes", {})
            current_hashes = self._compute_file_hashes()

            return saved_hashes != current_hashes

        except Exception:
            return True

    def _compute_file_hashes(self) -> dict[str, str]:
        """计算知识文件哈希。"""
        import hashlib

        hashes = {}
        if not self.knowledge_dir.exists():
            return hashes

        for md_path in sorted(self.knowledge_dir.rglob("*.md")):
            if md_path.name.lower() == "readme.md":
                continue
            try:
                content = md_path.read_bytes()
                file_id = str(md_path.relative_to(self.knowledge_dir))
                hashes[file_id] = hashlib.sha256(content).hexdigest()
            except Exception:
                pass

        return hashes

    def get_stats(self) -> dict[str, Any]:
        """获取检索器统计信息。"""
        return {
            "initialized": self._initialized,
            "document_count": len(self._documents),
            "jieba_available": self._jieba_available,
            "bm25_available": self._bm25_available,
            "cache_dir": str(self.cache_dir),
        }
