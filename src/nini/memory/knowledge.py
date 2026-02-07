"""Markdown 知识记忆。

每个会话一个 knowledge.md，Agent 可通过 Skill 读写。
用于记录分析发现、数据特征等长期记忆。
"""

from __future__ import annotations

from pathlib import Path

from nini.config import settings


class KnowledgeMemory:
    """基于 Markdown 的会话知识记忆。"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._dir = settings.sessions_dir / session_id
        self._path = self._dir / "knowledge.md"

    def _ensure_dir(self) -> None:
        """确保目录存在（延迟创建）。"""
        if not self._dir.exists():
            self._dir.mkdir(parents=True, exist_ok=True)

    def read(self) -> str:
        """读取知识内容。"""
        if not self._path.exists():
            return ""
        return self._path.read_text(encoding="utf-8")

    def write(self, content: str) -> None:
        """覆盖写入知识内容。"""
        self._ensure_dir()
        self._path.write_text(content, encoding="utf-8")

    def append(self, section: str, content: str) -> None:
        """追加一个章节。"""
        existing = self.read()
        new_content = (
            f"{existing}\n\n## {section}\n\n{content}"
            if existing
            else f"## {section}\n\n{content}"
        )
        self.write(new_content.strip() + "\n")

    def clear(self) -> None:
        """清空知识记忆。"""
        if self._path.exists():
            self._path.unlink()
