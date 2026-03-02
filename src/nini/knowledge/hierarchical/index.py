"""层次化索引管理器。

支持三级索引：L0 (文档级)、L1 (章节级)、L2 (段落级)
"""

from __future__ import annotations

import hashlib
import json
import logging
import pickle
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from nini.config import settings
from nini.knowledge.hierarchical.parser import ChunkNode, DocumentNode, MarkdownParser, SectionNode

logger = logging.getLogger(__name__)


@dataclass
class IndexMetadata:
    """索引元数据。"""

    version: str = "1.0"
    created_at: str = ""
    updated_at: str = ""
    file_hashes: dict[str, str] = field(default_factory=dict)


class HierarchicalIndex:
    """层次化知识索引管理器。

    管理三级索引：
    - L0: 文档级索引（文档摘要和元信息）
    - L1: 章节级索引（章节标题和内容）
    - L2: 段落级索引（段落内容和向量）

    Attributes:
        knowledge_dir: 知识库目录
        storage_dir: 索引存储目录
        parser: Markdown 解析器
    """

    def __init__(
        self,
        knowledge_dir: Path | None = None,
        storage_dir: Path | None = None,
    ) -> None:
        """初始化层次化索引。

        Args:
            knowledge_dir: 知识库目录，默认使用 settings.knowledge_dir
            storage_dir: 索引存储目录，默认使用 data_dir/hierarchical_index
        """
        self.knowledge_dir = knowledge_dir or settings.knowledge_dir
        self.storage_dir = storage_dir or (settings.data_dir / "hierarchical_index")
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.parser = MarkdownParser(
            chunk_size=settings.hierarchical_chunk_size,
            chunk_overlap=settings.hierarchical_chunk_overlap,
        )

        # 三级索引存储
        self.l0_index: dict[str, DocumentNode] = {}  # doc_id -> DocumentNode
        self.l1_index: dict[str, SectionNode] = {}   # section_id -> SectionNode
        self.l2_index: dict[str, ChunkNode] = {}     # chunk_id -> ChunkNode

        # 父子关系映射
        self.parent_map: dict[str, str] = {}  # child_id -> parent_id

        # 元数据
        self.metadata = IndexMetadata()

    def build_index(self) -> bool:
        """构建层次化索引。

        Returns:
            是否成功构建
        """
        try:
            logger.info("开始构建层次化索引...")

            # 扫描所有 Markdown 文件
            md_files = list(self.knowledge_dir.rglob("*.md"))
            logger.info(f"发现 {len(md_files)} 个 Markdown 文件")

            for md_path in md_files:
                if md_path.name.lower() == "readme.md":
                    continue

                try:
                    self._index_document(md_path)
                except Exception as e:
                    logger.warning(f"索引文档失败: {md_path} - {e}")

            # 保存索引
            self._save_index()

            logger.info(
                f"层次化索引构建完成: "
                f"L0={len(self.l0_index)}, L1={len(self.l1_index)}, L2={len(self.l2_index)}"
            )
            return True

        except Exception as e:
            logger.error(f"构建层次化索引失败: {e}")
            return False

    def load_index(self) -> bool:
        """从磁盘加载索引。

        Returns:
            是否成功加载
        """
        try:
            l0_path = self.storage_dir / "l0_index.pkl"
            l1_path = self.storage_dir / "l1_index.pkl"
            l2_path = self.storage_dir / "l2_index.pkl"
            meta_path = self.storage_dir / "metadata.json"

            if not all(p.exists() for p in [l0_path, l1_path, l2_path, meta_path]):
                logger.info("索引文件不存在，需要重新构建")
                return False

            with open(l0_path, "rb") as f:
                self.l0_index = pickle.load(f)
            with open(l1_path, "rb") as f:
                self.l1_index = pickle.load(f)
            with open(l2_path, "rb") as f:
                self.l2_index = pickle.load(f)

            with open(meta_path, "r", encoding="utf-8") as f:
                meta_dict = json.load(f)
                self.metadata = IndexMetadata(**meta_dict)

            logger.info(
                f"层次化索引加载完成: "
                f"L0={len(self.l0_index)}, L1={len(self.l1_index)}, L2={len(self.l2_index)}"
            )
            return True

        except Exception as e:
            logger.warning(f"加载层次化索引失败: {e}")
            return False

    def build_or_load(self) -> bool:
        """构建或加载索引。

        如果索引已存在且未过期，则加载；否则重新构建。

        Returns:
            是否成功
        """
        if self.load_index():
            if not self._is_index_stale():
                return True
            logger.info("索引已过期，需要重建")

        return self.build_index()

    def _index_document(self, file_path: Path) -> None:
        """索引单个文档。"""
        doc = self.parser.parse_file(file_path)

        # 添加到 L0 索引
        self.l0_index[doc.id] = doc

        # 添加章节到 L1 索引
        for section in doc.sections:
            self.l1_index[section.id] = section
            self.parent_map[section.id] = doc.id

            # 添加段落块到 L2 索引
            for chunk in section.chunks:
                self.l2_index[chunk.id] = chunk
                self.parent_map[chunk.id] = section.id

    def _save_index(self) -> None:
        """保存索引到磁盘。"""
        # 更新元数据
        from datetime import datetime, timezone

        self.metadata.updated_at = datetime.now(timezone.utc).isoformat()
        self.metadata.file_hashes = self._compute_file_hashes()

        # 保存索引文件
        with open(self.storage_dir / "l0_index.pkl", "wb") as f:
            pickle.dump(self.l0_index, f)
        with open(self.storage_dir / "l1_index.pkl", "wb") as f:
            pickle.dump(self.l1_index, f)
        with open(self.storage_dir / "l2_index.pkl", "wb") as f:
            pickle.dump(self.l2_index, f)

        # 保存元数据
        with open(self.storage_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(asdict(self.metadata), f, ensure_ascii=False, indent=2)

        logger.info(f"索引已保存到: {self.storage_dir}")

    def _is_index_stale(self) -> bool:
        """检查索引是否过期（源文件是否有变更）。"""
        current_hashes = self._compute_file_hashes()
        return current_hashes != self.metadata.file_hashes

    def _compute_file_hashes(self) -> dict[str, str]:
        """计算所有知识文件的哈希值。"""
        hashes: dict[str, str] = {}

        for md_path in sorted(self.knowledge_dir.rglob("*.md")):
            if md_path.name.lower() == "readme.md":
                continue

            try:
                content = md_path.read_bytes()
                relative_path = str(md_path.relative_to(self.knowledge_dir))
                hashes[relative_path] = hashlib.sha256(content).hexdigest()
            except Exception:
                pass

        return hashes

    def get_document(self, doc_id: str) -> DocumentNode | None:
        """获取文档节点。"""
        return self.l0_index.get(doc_id)

    def get_section(self, section_id: str) -> SectionNode | None:
        """获取章节节点。"""
        return self.l1_index.get(section_id)

    def get_chunk(self, chunk_id: str) -> ChunkNode | None:
        """获取段落节点。"""
        return self.l2_index.get(chunk_id)

    def get_parent(self, node_id: str) -> str | None:
        """获取父节点 ID。"""
        return self.parent_map.get(node_id)

    def get_document_sections(self, doc_id: str) -> list[SectionNode]:
        """获取文档的所有章节。"""
        return [s for s in self.l1_index.values() if s.parent_doc_id == doc_id]

    def get_section_chunks(self, section_id: str) -> list[ChunkNode]:
        """获取章节的所有段落。"""
        return [c for c in self.l2_index.values() if c.parent_section_id == section_id]

    def get_stats(self) -> dict[str, Any]:
        """获取索引统计信息。"""
        return {
            "l0_count": len(self.l0_index),
            "l1_count": len(self.l1_index),
            "l2_count": len(self.l2_index),
            "storage_dir": str(self.storage_dir),
            "last_updated": self.metadata.updated_at,
        }
