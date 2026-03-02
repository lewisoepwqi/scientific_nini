"""Markdown 文档结构解析器。

支持提取层次化结构：文档 → 章节 → 段落
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ChunkNode:
    """段落级节点（L2）。"""

    id: str
    content: str
    token_count: int = 0
    parent_section_id: str = ""


@dataclass
class SectionNode:
    """章节级节点（L1）。"""

    id: str
    title: str
    level: int  # 1=H1, 2=H2, 3=H3
    content: str = ""
    chunks: list[ChunkNode] = field(default_factory=list)
    parent_doc_id: str = ""
    parent_section_id: str | None = None  # 上级章节（如果是子章节）


@dataclass
class DocumentNode:
    """文档级节点（L0）。"""

    id: str
    title: str
    file_path: Path
    content: str = ""
    summary: str = ""  # 文档摘要
    sections: list[SectionNode] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class MarkdownParser:
    """Markdown 文档结构解析器。

    提取文档的层次化结构，支持标题层级识别和语义分块。
    """

    # 标题正则：匹配 # ## ### 开头的行
    HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
    # HTML 注释（元信息）
    COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
    # 代码块
    CODE_BLOCK_RE = re.compile(r"```[\s\S]*?```")

    def __init__(self, chunk_size: int = 256, chunk_overlap: int = 32) -> None:
        """初始化解析器。

        Args:
            chunk_size: 目标段落大小（字符数）
            chunk_overlap: 段落重叠大小
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def parse(self, content: str, file_path: Path | None = None) -> DocumentNode:
        """解析 Markdown 内容，返回文档树。

        Args:
            content: Markdown 文件内容
            file_path: 文件路径（用于生成 ID）

        Returns:
            DocumentNode: 文档树根节点
        """
        file_path = file_path or Path("unknown.md")
        doc_id = self._generate_doc_id(file_path)

        # 清理内容（去除元信息注释）
        clean_content = self._clean_content(content)

        # 提取文档标题（第一个 H1 或文件名）
        title = self._extract_title(clean_content, file_path)

        # 提取元信息
        metadata = self._extract_metadata(content)

        # 创建文档节点
        doc = DocumentNode(
            id=doc_id,
            title=title,
            file_path=file_path,
            content=clean_content,
            metadata=metadata,
        )

        # 提取章节结构
        sections = self._extract_sections(clean_content, doc_id)
        doc.sections = sections

        # 为每个章节生成段落分块
        for section in sections:
            section.chunks = self._chunk_section(section)

        return doc

    def parse_file(self, file_path: Path) -> DocumentNode:
        """解析 Markdown 文件。

        Args:
            file_path: Markdown 文件路径

        Returns:
            DocumentNode: 文档树根节点
        """
        content = file_path.read_text(encoding="utf-8")
        return self.parse(content, file_path)

    def _clean_content(self, content: str) -> str:
        """清理内容，去除元信息注释但保留其他内容。"""
        # 只去除 HTML 注释（通常用于元信息）
        return self.COMMENT_RE.sub("", content).strip()

    def _extract_title(self, content: str, file_path: Path) -> str:
        """提取文档标题。"""
        # 查找第一个 H1 标题
        match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if match:
            return match.group(1).strip()
        # 回退到文件名
        return file_path.stem

    def _extract_metadata(self, content: str) -> dict[str, Any]:
        """提取 HTML 注释格式的元信息。"""
        metadata: dict[str, Any] = {}

        # keywords
        kw_match = re.search(r"<!--\s*keywords:\s*(.+?)\s*-->", content, re.IGNORECASE)
        if kw_match:
            keywords = [k.strip() for k in kw_match.group(1).split(",")]
            metadata["keywords"] = keywords

        # priority
        prio_match = re.search(r"<!--\s*priority:\s*(\w+)\s*-->", content, re.IGNORECASE)
        if prio_match:
            metadata["priority"] = prio_match.group(1).lower()

        return metadata

    def _extract_sections(
        self,
        content: str,
        doc_id: str,
    ) -> list[SectionNode]:
        """提取章节结构。

        基于标题层级构建章节树。
        只提取 H2 作为主要章节（H1 是文档标题，H3+ 是子章节）。
        """
        # 查找所有标题
        all_headings = list(self.HEADING_RE.finditer(content))
        # 过滤出 H2 作为主要章节
        headings = [h for h in all_headings if len(h.group(1)) == 2]

        if not headings:
            # 没有标题，将整个文档作为一个章节
            return [
                SectionNode(
                    id=f"{doc_id}#sec0",
                    title="正文",
                    level=1,
                    content=content.strip(),
                    parent_doc_id=doc_id,
                )
            ]

        sections: list[SectionNode] = []
        section_stack: list[SectionNode] = []

        for i, match in enumerate(headings):
            hashes, title = match.groups()
            level = len(hashes)
            start_pos = match.end()
            end_pos = headings[i + 1].start() if i + 1 < len(headings) else len(content)

            section_content = content[start_pos:end_pos].strip()

            section = SectionNode(
                id=f"{doc_id}#sec{i}",
                title=title.strip(),
                level=level,
                content=section_content,
                parent_doc_id=doc_id,
            )

            # 维护章节层级关系
            while section_stack and section_stack[-1].level >= level:
                section_stack.pop()

            if section_stack:
                section.parent_section_id = section_stack[-1].id

            section_stack.append(section)
            sections.append(section)

        return sections

    def _chunk_section(self, section: SectionNode) -> list[ChunkNode]:
        """将章节内容分块。

        优先在段落边界分割，保持语义连贯性。
        """
        content = section.content
        if not content:
            return []

        chunks: list[ChunkNode] = []

        # 按段落分割
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]

        if not paragraphs:
            return []

        current_chunk = ""
        chunk_index = 0

        for para in paragraphs:
            # 如果当前段落加上已有内容超过 chunk_size，先保存当前块
            if current_chunk and len(current_chunk) + len(para) > self.chunk_size:
                chunks.append(
                    ChunkNode(
                        id=f"{section.id}#chunk{chunk_index}",
                        content=current_chunk.strip(),
                        token_count=len(current_chunk) // 4,  # 粗略估计
                        parent_section_id=section.id,
                    )
                )
                # 保留重叠部分
                if len(current_chunk) > self.chunk_overlap:
                    current_chunk = current_chunk[-self.chunk_overlap :]
                else:
                    current_chunk = ""
                chunk_index += 1

            current_chunk += "\n\n" + para if current_chunk else para

        # 保存最后一个块
        if current_chunk:
            chunks.append(
                ChunkNode(
                    id=f"{section.id}#chunk{chunk_index}",
                    content=current_chunk.strip(),
                    token_count=len(current_chunk) // 4,
                    parent_section_id=section.id,
                )
            )

        return chunks

    def _generate_doc_id(self, file_path: Path) -> str:
        """生成文档 ID。"""
        # 使用相对路径作为 ID 基础
        return str(file_path.with_suffix("")).replace("/", "#").replace("\\", "#")
