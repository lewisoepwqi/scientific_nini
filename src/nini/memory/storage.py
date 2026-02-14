"""文件和产物存储。"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

from nini.config import settings


class ArtifactStorage:
    """会话产物存储（图表、导出文件等）。"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._dir = settings.sessions_dir / session_id / "workspace" / "artifacts"
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, data: bytes, filename: str) -> Path:
        """保存产物，返回路径。"""
        path = self._dir / filename
        path.write_bytes(data)
        return path

    def save_text(self, text: str, filename: str) -> Path:
        """保存文本产物。"""
        path = self._dir / filename
        path.write_text(text, encoding="utf-8")
        return path

    def get_path(self, filename: str) -> Path:
        """获取产物路径。"""
        return self._dir / filename

    def list_artifacts(self) -> list[dict[str, Any]]:
        """列出所有产物。"""
        result: list[dict[str, Any]] = []
        if self._dir.exists():
            for p in sorted(self._dir.iterdir()):
                if p.is_file():
                    stat = p.stat()
                    result.append(
                        {
                            "name": p.name,
                            "size": stat.st_size,
                            "path": str(p),
                        }
                    )

        # 兼容旧目录
        legacy_dir = settings.sessions_dir / self.session_id / "artifacts"
        if legacy_dir.exists():
            for p in sorted(legacy_dir.iterdir()):
                if p.is_file() and not any(item["name"] == p.name for item in result):
                    stat = p.stat()
                    result.append(
                        {
                            "name": p.name,
                            "size": stat.st_size,
                            "path": str(p),
                        }
                    )
        return result

    def cleanup(self) -> None:
        """清理所有产物。"""
        if self._dir.exists():
            shutil.rmtree(self._dir)
            self._dir.mkdir(parents=True, exist_ok=True)
