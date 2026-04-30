"""更新状态持久化。"""

from __future__ import annotations

import json
from pathlib import Path

from nini.update.models import UpdateDownloadState


class UpdateStateStore:
    """将更新下载状态保存到本地 JSON 文件。"""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> UpdateDownloadState:
        """读取下载状态；损坏或缺失时返回空状态。"""
        if not self.path.exists():
            return UpdateDownloadState()
        try:
            return UpdateDownloadState.model_validate(
                json.loads(self.path.read_text(encoding="utf-8"))
            )
        except Exception:
            return UpdateDownloadState(error="更新状态文件损坏，已重置")

    def save(self, state: UpdateDownloadState) -> None:
        """保存下载状态。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        temp_path.write_text(
            json.dumps(state.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(self.path)


def build_state_store(updates_dir: Path) -> UpdateStateStore:
    """根据更新目录创建状态存储。"""
    return UpdateStateStore(updates_dir / "state.json")
