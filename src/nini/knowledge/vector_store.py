"""基于 LlamaIndex 的向量检索引擎。

提供向量+BM25 混合检索能力，替代纯关键词匹配。
支持 MD5 变更检测与自动增量重建索引。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 延迟导入标记：避免未安装 llama-index 时模块加载失败
_LLAMA_INDEX_AVAILABLE: bool | None = None


def _check_llama_index() -> bool:
    """检测 llama-index-core 是否可用。"""
    global _LLAMA_INDEX_AVAILABLE
    if _LLAMA_INDEX_AVAILABLE is not None:
        return _LLAMA_INDEX_AVAILABLE
    try:
        import llama_index.core  # noqa: F401

        _LLAMA_INDEX_AVAILABLE = True
    except ImportError:
        _LLAMA_INDEX_AVAILABLE = False
        logger.info("llama-index-core 未安装，向量检索功能不可用，将回退到关键词匹配")
    return _LLAMA_INDEX_AVAILABLE


class VectorKnowledgeStore:
    """领域知识向量索引，支持语义检索与 BM25 混合排序。

    索引持久化到 ``storage_dir``，通过 MD5 哈希检测文件变更，
    仅在内容变化时重建索引。
    """

    def __init__(
        self,
        knowledge_dir: Path,
        storage_dir: Path,
        *,
        embed_model: str = "text-embedding-3-small",
        chunk_size: int = 256,
        chunk_overlap: int = 32,
    ) -> None:
        self._knowledge_dir = knowledge_dir
        self._storage_dir = storage_dir
        self._embed_model_name = embed_model
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._index: Any = None  # VectorStoreIndex
        self._hash_path = self._storage_dir / "file_hashes.json"

    @property
    def is_available(self) -> bool:
        """向量检索是否可用（llama-index 已安装且索引已构建）。"""
        return _check_llama_index() and self._index is not None

    def build_or_load(self) -> bool:
        """构建或加载索引。返回是否成功。"""
        if not _check_llama_index():
            return False

        try:
            self._storage_dir.mkdir(parents=True, exist_ok=True)

            if self._needs_rebuild():
                logger.info("知识库文件已变更，重建向量索引...")
                return self._build_index()
            else:
                return self._load_index()
        except Exception:
            logger.warning("向量索引构建/加载失败，将回退到关键词匹配", exc_info=True)
            self._index = None
            return False

    def query(
        self,
        query_text: str,
        *,
        top_k: int = 3,
        max_total_chars: int = 3000,
    ) -> tuple[str, list[dict[str, Any]]]:
        """向量语义检索，返回 (拼接文本, 命中详情列表)。"""
        if not self.is_available or not query_text:
            return "", []

        try:
            from llama_index.core import QueryBundle

            retriever = self._index.as_retriever(similarity_top_k=top_k)
            nodes = retriever.retrieve(QueryBundle(query_str=query_text))

            parts: list[str] = []
            hit_items: list[dict[str, Any]] = []
            total_chars = 0

            for node_with_score in nodes:
                node = node_with_score.node
                score = float(node_with_score.score or 0.0)
                text = node.get_content()
                source = node.metadata.get("file_name", "未知来源")

                if total_chars + len(text) > max_total_chars:
                    remaining = max_total_chars - total_chars
                    if remaining > 200:
                        text = text[:remaining] + "\n..."
                        parts.append(text)
                        hit_items.append(
                            {
                                "source": source,
                                "score": score,
                                "hits": 1,
                                "snippet": text[:300],
                                "method": "vector",
                            }
                        )
                    break

                parts.append(text)
                total_chars += len(text)
                hit_items.append(
                    {
                        "source": source,
                        "score": score,
                        "hits": 1,
                        "snippet": text[:300],
                        "method": "vector",
                    }
                )

            return "\n\n".join(parts), hit_items
        except Exception:
            logger.warning("向量检索执行失败", exc_info=True)
            return "", []

    def _needs_rebuild(self) -> bool:
        """通过 MD5 哈希检测知识文件是否变更。"""
        current_hashes = self._compute_file_hashes()
        if not (self._storage_dir / "docstore.json").exists():
            return True
        if not self._hash_path.exists():
            return True

        try:
            saved_hashes = json.loads(self._hash_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return True

        if not isinstance(saved_hashes, dict):
            return True
        normalized_saved = {str(key): str(value) for key, value in saved_hashes.items()}
        return current_hashes != normalized_saved

    def _compute_file_hashes(self) -> dict[str, str]:
        """计算知识目录下所有 .md 文件的 MD5 哈希。"""
        hashes: dict[str, str] = {}
        if not self._knowledge_dir.is_dir():
            return hashes
        for md_path in sorted(self._knowledge_dir.rglob("*.md")):
            if md_path.name.lower() == "readme.md":
                continue
            content = md_path.read_bytes()
            hashes[str(md_path.relative_to(self._knowledge_dir))] = hashlib.sha256(
                content
            ).hexdigest()
        return hashes

    def _build_index(self) -> bool:
        """从知识文件构建向量索引并持久化。"""
        from llama_index.core import Document, Settings, StorageContext, VectorStoreIndex
        from llama_index.core.node_parser import SentenceSplitter

        # 配置 embedding 模型
        embed_model = self._create_embed_model()
        if embed_model is None:
            logger.warning("无法创建 embedding 模型，向量索引构建失败")
            return False

        Settings.embed_model = embed_model
        Settings.chunk_size = self._chunk_size
        Settings.chunk_overlap = self._chunk_overlap

        # 加载知识文档
        documents = self._load_documents()
        if not documents:
            logger.warning("未找到知识文档，跳过索引构建")
            return False

        # 分片
        splitter = SentenceSplitter(
            chunk_size=self._chunk_size,
            chunk_overlap=self._chunk_overlap,
        )
        nodes = splitter.get_nodes_from_documents(documents)
        logger.info("知识文档分片完成: %d 个文档 → %d 个节点", len(documents), len(nodes))

        # 构建索引
        storage_context = StorageContext.from_defaults()
        self._index = VectorStoreIndex(
            nodes,
            storage_context=storage_context,
        )

        # 持久化
        self._index.storage_context.persist(persist_dir=str(self._storage_dir))

        # 保存文件哈希
        hashes = self._compute_file_hashes()
        self._hash_path.write_text(
            json.dumps(hashes, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info("向量索引构建并持久化完成: %s", self._storage_dir)
        return True

    def _load_index(self) -> bool:
        """从磁盘加载已有索引。"""
        from llama_index.core import Settings, StorageContext, load_index_from_storage

        embed_model = self._create_embed_model()
        if embed_model is None:
            return False

        Settings.embed_model = embed_model

        try:
            storage_context = StorageContext.from_defaults(persist_dir=str(self._storage_dir))
            self._index = load_index_from_storage(storage_context)
            logger.info("从磁盘加载向量索引成功: %s", self._storage_dir)
            return True
        except Exception:
            logger.warning("加载向量索引失败，将尝试重建", exc_info=True)
            return self._build_index()

    def _load_documents(self) -> list[Any]:
        """将知识 Markdown 文件加载为 LlamaIndex Document 对象。"""
        import re

        from llama_index.core import Document

        comment_re = re.compile(r"<!--.*?-->", re.DOTALL)
        documents: list[Document] = []

        if not self._knowledge_dir.is_dir():
            return documents

        for md_path in sorted(self._knowledge_dir.rglob("*.md")):
            if md_path.name.lower() == "readme.md":
                continue
            try:
                raw = md_path.read_text(encoding="utf-8")
                # 去除 HTML 注释（元信息），保留正文
                content = comment_re.sub("", raw).strip()
                if not content:
                    continue
                documents.append(
                    Document(
                        text=content,
                        metadata={
                            "file_name": md_path.name,
                            "file_path": str(md_path.relative_to(self._knowledge_dir)),
                        },
                    )
                )
            except Exception:
                logger.warning("加载知识文件失败: %s", md_path, exc_info=True)

        return documents

    def _create_embed_model(self) -> Any | None:
        """创建 embedding 模型实例。优先使用 OpenAI，回退到本地。"""
        from nini.config import settings

        # 尝试使用 OpenAI embedding
        api_key = settings.openai_api_key
        if api_key:
            try:
                from llama_index.embeddings.openai import OpenAIEmbedding

                return OpenAIEmbedding(
                    model=self._embed_model_name,
                    api_key=api_key,
                )
            except ImportError:
                logger.info("llama-index-embeddings-openai 未安装")
            except Exception:
                logger.warning("创建 OpenAI embedding 模型失败", exc_info=True)

        # 回退: 尝试使用 HuggingFace 本地模型
        if importlib.util.find_spec("llama_index.embeddings.huggingface") is None:
            logger.info(
                "未安装 llama-index-embeddings-huggingface，跳过本地 embedding，"
                "将回退到关键词检索"
            )
            return None

        try:
            from llama_index.embeddings.huggingface import HuggingFaceEmbedding

            return HuggingFaceEmbedding(model_name=settings.knowledge_local_embedding_model)
        except ImportError:
            logger.info("本地 embedding 依赖加载失败，已回退到关键词检索")
        except ValueError as exc:
            logger.warning(
                "本地 embedding 模型配置无效（model=%s）: %s",
                settings.knowledge_local_embedding_model,
                exc,
            )
        except Exception:
            logger.warning("无法创建本地 embedding 模型，已回退到关键词检索")

        return None

    async def initialize(self) -> None:
        """初始化向量存储（异步包装）.

        实际调用 build_or_load 构建或加载索引。
        """
        self.build_or_load()

    async def add_document(
        self,
        doc_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """添加文档到向量存储.

        注意：当前实现仅将文档保存到知识目录，
        需要调用 build_or_load 重建索引才能检索。

        Args:
            doc_id: 文档 ID
            content: 文档内容
            metadata: 元数据

        Returns:
            是否成功
        """
        try:
            doc_path = self._knowledge_dir / f"{doc_id}.txt"
            doc_path.write_text(content, encoding="utf-8")

            # 保存元数据
            if metadata:
                meta_path = self._storage_dir / f"{doc_id}_meta.json"
                meta_path.write_text(
                    json.dumps(metadata, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

            return True
        except Exception as e:
            logger.error(f"添加文档失败: {e}")
            return False

    async def remove_document(self, doc_id: str) -> bool:
        """从向量存储中移除文档.

        Args:
            doc_id: 文档 ID

        Returns:
            是否成功
        """
        try:
            doc_path = self._knowledge_dir / f"{doc_id}.txt"
            meta_path = self._storage_dir / f"{doc_id}_meta.json"

            if doc_path.exists():
                doc_path.unlink()
            if meta_path.exists():
                meta_path.unlink()

            return True
        except Exception as e:
            logger.error(f"移除文档失败: {e}")
            return False

    async def search(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[tuple[str, float]]:
        """搜索文档.

        Args:
            query: 查询文本
            top_k: 返回结果数量

        Returns:
            (文档ID, 分数) 列表
        """
        _, hit_items = self.query(query, top_k=top_k)
        return [(item.get("source", "unknown"), item.get("score", 0.0)) for item in hit_items]

    async def get_document(self, doc_id: str) -> dict[str, Any] | None:
        """获取文档信息.

        Args:
            doc_id: 文档 ID

        Returns:
            文档信息字典，不存在返回 None
        """
        try:
            doc_path = self._knowledge_dir / f"{doc_id}.txt"
            meta_path = self._storage_dir / f"{doc_id}_meta.json"

            if not doc_path.exists():
                return None

            content = doc_path.read_text(encoding="utf-8")
            metadata = {}
            if meta_path.exists():
                metadata = json.loads(meta_path.read_text(encoding="utf-8"))

            return {
                "id": doc_id,
                "content": content,
                "metadata": metadata,
            }
        except Exception as e:
            logger.error(f"获取文档失败: {e}")
            return None

    @property
    def _initialized(self) -> bool:
        """内部属性：检查是否已初始化."""
        return self.is_available
