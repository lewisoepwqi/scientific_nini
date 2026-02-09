"""会话工作空间管理器。

每个会话对应一个独立工作空间目录：
- workspace/uploads: 用户上传的数据文件
- workspace/artifacts: Agent 产物（图表/报告等）
- workspace/notes: 用户或助手保存的文本
- workspace/index.json: 文件索引
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pandas as pd

from nini.config import settings

_SAFE_FILENAME_PATTERN = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff._ -]")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkspaceManager:
    """管理单个会话的工作空间。"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.base_dir = settings.sessions_dir / session_id / "workspace"
        self.uploads_dir = self.base_dir / "uploads"
        self.artifacts_dir = self.base_dir / "artifacts"
        self.notes_dir = self.base_dir / "notes"
        self.index_path = self.base_dir / "index.json"

    def ensure_dirs(self) -> None:
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.notes_dir.mkdir(parents=True, exist_ok=True)

    def sanitize_filename(self, name: str, *, default_name: str = "file") -> str:
        raw = Path(name).name.strip()
        if not raw:
            raw = default_name
        cleaned = _SAFE_FILENAME_PATTERN.sub("_", raw).strip(" .")
        return cleaned or default_name

    def unique_dataset_name(self, preferred_name: str) -> str:
        entries = self.list_datasets()
        existing = {str(item.get("name", "")) for item in entries}
        if preferred_name not in existing:
            return preferred_name
        stem = preferred_name
        ext = ""
        if "." in preferred_name:
            stem, ext = preferred_name.rsplit(".", 1)
            ext = "." + ext
        index = 2
        while True:
            candidate = f"{stem} ({index}){ext}"
            if candidate not in existing:
                return candidate
            index += 1

    def _default_index(self) -> dict[str, Any]:
        return {
            "version": 1,
            "session_id": self.session_id,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "datasets": [],
            "artifacts": [],
            "notes": [],
        }

    def _load_index(self) -> dict[str, Any]:
        self.ensure_dirs()
        if not self.index_path.exists():
            index = self._default_index()
            self._save_index(index)
            return index
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("工作空间索引格式不正确")
            data.setdefault("datasets", [])
            data.setdefault("artifacts", [])
            data.setdefault("notes", [])
            data.setdefault("session_id", self.session_id)
            data.setdefault("version", 1)
            return data
        except Exception:
            index = self._default_index()
            self._save_index(index)
            return index

    def _save_index(self, data: dict[str, Any]) -> None:
        data["updated_at"] = _now_iso()
        self.index_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def add_dataset_record(
        self,
        *,
        dataset_id: str,
        name: str,
        file_path: Path,
        file_type: str,
        file_size: int,
        row_count: int,
        column_count: int,
    ) -> dict[str, Any]:
        index = self._load_index()
        record = {
            "id": dataset_id,
            "session_id": self.session_id,
            "name": name,
            "file_path": str(file_path),
            "file_type": file_type,
            "file_size": file_size,
            "row_count": row_count,
            "column_count": column_count,
            "created_at": _now_iso(),
        }
        datasets = [
            item
            for item in index.get("datasets", [])
            if isinstance(item, dict) and item.get("name") != name
        ]
        datasets.append(record)
        index["datasets"] = datasets
        self._save_index(index)
        return record

    def list_datasets(self) -> list[dict[str, Any]]:
        index = self._load_index()
        datasets = index.get("datasets", [])
        if not isinstance(datasets, list):
            return []
        result: list[dict[str, Any]] = []
        for item in datasets:
            if isinstance(item, dict):
                result.append(item)
        return sorted(
            result,
            key=lambda item: str(item.get("created_at", "")),
            reverse=True,
        )

    def get_dataset_by_id(self, dataset_id: str) -> dict[str, Any] | None:
        for item in self.list_datasets():
            if item.get("id") == dataset_id:
                return item
        return None

    def get_dataset_by_name(self, name: str) -> dict[str, Any] | None:
        for item in self.list_datasets():
            if item.get("name") == name:
                return item
        return None

    def load_dataset_by_id(self, dataset_id: str) -> tuple[dict[str, Any], pd.DataFrame]:
        record = self.get_dataset_by_id(dataset_id)
        if record is None:
            raise ValueError(f"数据集 '{dataset_id}' 不存在")
        path = Path(str(record.get("file_path", "")))
        if not path.exists():
            raise ValueError(f"数据集文件不存在: {path}")
        ext = str(record.get("file_type", "")).lower()
        if ext in ("xlsx", "xls"):
            df = pd.read_excel(path)
        elif ext == "csv":
            df = pd.read_csv(path)
        elif ext in ("tsv", "txt"):
            df = pd.read_csv(path, sep="\t")
        else:
            raise ValueError(f"不支持的数据集扩展名: {ext}")
        return record, df

    def hydrate_session_datasets(self, session: Any) -> int:
        loaded = 0
        for item in self.list_datasets():
            name = str(item.get("name", "")).strip()
            if not name or name in session.datasets:
                continue
            dataset_id = str(item.get("id", "")).strip()
            if not dataset_id:
                continue
            try:
                _, df = self.load_dataset_by_id(dataset_id)
            except Exception:
                continue
            session.datasets[name] = df
            loaded += 1
        return loaded

    def add_artifact_record(
        self,
        *,
        name: str,
        artifact_type: str,
        file_path: Path,
        format_hint: str | None = None,
    ) -> dict[str, Any]:
        index = self._load_index()
        record = {
            "id": uuid.uuid4().hex[:12],
            "session_id": self.session_id,
            "name": name,
            "type": artifact_type,
            "format": format_hint,
            "path": str(file_path),
            "download_url": f"/api/artifacts/{self.session_id}/{name}",
            "created_at": _now_iso(),
        }
        artifacts = index.get("artifacts", [])
        if not isinstance(artifacts, list):
            artifacts = []
        artifacts.append(record)
        index["artifacts"] = artifacts
        self._save_index(index)
        return record

    def list_artifacts(self) -> list[dict[str, Any]]:
        index = self._load_index()
        artifacts = index.get("artifacts", [])
        if not isinstance(artifacts, list):
            return []
        result: list[dict[str, Any]] = []
        for item in artifacts:
            if isinstance(item, dict):
                result.append(item)
        return sorted(
            result,
            key=lambda item: str(item.get("created_at", "")),
            reverse=True,
        )

    def save_text_note(self, content: str, filename: str | None = None) -> dict[str, Any]:
        self.ensure_dirs()
        raw_name = filename or f"note_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.md"
        safe_name = self.sanitize_filename(raw_name, default_name="note.md")
        if "." not in safe_name:
            safe_name = f"{safe_name}.md"
        path = self.notes_dir / safe_name
        path.write_text(content, encoding="utf-8")

        index = self._load_index()
        note_record = {
            "id": uuid.uuid4().hex[:12],
            "session_id": self.session_id,
            "name": safe_name,
            "type": "note",
            "path": str(path),
            "download_url": f"/api/workspace/{self.session_id}/notes/{safe_name}",
            "created_at": _now_iso(),
        }
        notes = index.get("notes", [])
        if not isinstance(notes, list):
            notes = []
        notes.append(note_record)
        index["notes"] = notes
        self._save_index(index)
        return note_record

    def list_notes(self) -> list[dict[str, Any]]:
        index = self._load_index()
        notes = index.get("notes", [])
        if not isinstance(notes, list):
            return []
        result: list[dict[str, Any]] = []
        for item in notes:
            if isinstance(item, dict):
                result.append(item)
        return sorted(
            result,
            key=lambda item: str(item.get("created_at", "")),
            reverse=True,
        )

    def list_workspace_files(self) -> list[dict[str, Any]]:
        files: list[dict[str, Any]] = []

        for item in self.list_datasets():
            files.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "kind": "dataset",
                    "size": item.get("file_size", 0),
                    "created_at": item.get("created_at"),
                    "download_url": (
                        f"/api/workspace/{self.session_id}/uploads/"
                        f"{quote(Path(str(item.get('file_path', ''))).name)}"
                    ),
                    "meta": {
                        "row_count": item.get("row_count"),
                        "column_count": item.get("column_count"),
                        "file_type": item.get("file_type"),
                    },
                }
            )

        for item in self.list_artifacts():
            path = Path(str(item.get("path", "")))
            size = 0
            if path.exists() and path.is_file():
                size = path.stat().st_size
            raw_url = str(item.get("download_url", "")).strip()
            download_url = raw_url
            if raw_url.startswith(f"/api/artifacts/{self.session_id}/"):
                suffix = raw_url.split(f"/api/artifacts/{self.session_id}/", 1)[-1]
                download_url = f"/api/artifacts/{self.session_id}/{quote(suffix)}"
            files.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "kind": "artifact",
                    "size": size,
                    "created_at": item.get("created_at"),
                    "download_url": download_url,
                    "meta": {
                        "type": item.get("type"),
                        "format": item.get("format"),
                    },
                }
            )

        for item in self.list_notes():
            path = Path(str(item.get("path", "")))
            size = 0
            if path.exists() and path.is_file():
                size = path.stat().st_size
            files.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "kind": "note",
                    "size": size,
                    "created_at": item.get("created_at"),
                    "download_url": f"/api/workspace/{self.session_id}/notes/{quote(str(item.get('name', '')))}",
                    "meta": {},
                }
            )

        files.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
        return files
