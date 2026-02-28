"""会话工作空间管理器。

每个会话对应一个独立工作空间目录：
- workspace/uploads: 用户上传的数据文件
- workspace/artifacts: Agent 产物（图表/报告等）
- workspace/notes: 用户或助手保存的文本
- workspace/index.json: 文件索引
"""

from __future__ import annotations

import base64
import io
import json
import mimetypes
import re
import shutil
from copy import deepcopy
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote, unquote

import pandas as pd

from nini.config import settings
from nini.utils.dataframe_io import read_dataframe

_SAFE_FILENAME_PATTERN = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff._ -]")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkspaceManager:
    """管理单个会话的工作空间。"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.base_dir = settings.sessions_dir / session_id / "workspace"
        self.workspace_dir = self.base_dir
        self.uploads_dir = self.base_dir / "uploads"
        self.artifacts_dir = self.base_dir / "artifacts"
        self.notes_dir = self.base_dir / "notes"
        self.executions_dir = self.base_dir / "executions"
        self.index_path = self.base_dir / "index.json"

    def ensure_dirs(self) -> None:
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.notes_dir.mkdir(parents=True, exist_ok=True)
        self.executions_dir.mkdir(parents=True, exist_ok=True)

    def sanitize_filename(self, name: str, *, default_name: str = "file") -> str:
        raw = Path(name).name.strip()
        if not raw:
            raw = default_name
        cleaned = _SAFE_FILENAME_PATTERN.sub("_", raw).strip(" .")
        return cleaned or default_name

    def resolve_workspace_path(
        self,
        relative_path: str,
        *,
        allow_root: bool = False,
        allow_missing: bool = True,
    ) -> Path:
        """将工作空间相对路径解析为安全绝对路径。"""
        self.ensure_dirs()
        raw = relative_path.strip().replace("\\", "/")
        if not raw:
            if allow_root:
                return self.workspace_dir.resolve()
            raise ValueError("path 不能为空")

        rel = Path(raw)
        if rel.is_absolute():
            raise ValueError("path 不能为绝对路径")
        if any(part in ("", ".", "..") for part in rel.parts):
            raise ValueError("path 非法")

        target = (self.workspace_dir / rel).resolve()
        if not target.is_relative_to(self.workspace_dir.resolve()):
            raise ValueError("path 超出工作空间目录")
        if not allow_missing and not target.exists():
            raise FileNotFoundError(relative_path)
        return target

    def build_artifact_download_url(self, filename: str) -> str:
        """构建产物下载 URL（文件名统一做单次编码）。"""
        try:
            normalized = quote(unquote(filename), safe="")
        except Exception:
            normalized = quote(filename, safe="")
        return f"/api/artifacts/{self.session_id}/{normalized}"

    def _iter_index_records(
        self,
        index: dict[str, Any],
    ) -> list[tuple[str, dict[str, Any], str]]:
        """遍历索引中的文件记录，返回 (kind, record, path_key)。"""
        records: list[tuple[str, dict[str, Any], str]] = []
        for kind, path_key in (("dataset", "file_path"), ("artifact", "path"), ("note", "path")):
            bucket = {
                "dataset": "datasets",
                "artifact": "artifacts",
                "note": "notes",
            }[kind]
            items = index.get(bucket, [])
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict):
                    records.append((kind, item, path_key))
        return records

    def _find_record_by_path(
        self,
        target: Path,
        *,
        index: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any] | None, str | None]:
        """按磁盘路径定位索引记录。"""
        active_index = index or self._load_index()
        resolved_target = target.resolve()
        for kind, item, path_key in self._iter_index_records(active_index):
            raw = str(item.get(path_key, "")).strip()
            if not raw:
                continue
            try:
                item_path = Path(raw).resolve()
            except Exception:
                continue
            if item_path == resolved_target:
                return kind, item, path_key
        return "", None, None

    def _remove_records_under_path(
        self,
        index: dict[str, Any],
        target: Path,
    ) -> list[tuple[str, dict[str, Any]]]:
        """删除索引中位于指定路径下的记录。"""
        removed: list[tuple[str, dict[str, Any]]] = []
        resolved_target = target.resolve()
        bucket_map = {
            "dataset": "datasets",
            "artifact": "artifacts",
            "note": "notes",
        }
        kept: dict[str, list[dict[str, Any]]] = {bucket: [] for bucket in bucket_map.values()}

        for kind, item, path_key in self._iter_index_records(index):
            raw = str(item.get(path_key, "")).strip()
            if not raw:
                kept[bucket_map[kind]].append(item)
                continue
            try:
                item_path = Path(raw).resolve()
            except Exception:
                kept[bucket_map[kind]].append(item)
                continue
            if item_path == resolved_target or resolved_target in item_path.parents:
                removed.append((kind, item))
            else:
                kept[bucket_map[kind]].append(item)

        for bucket, items in kept.items():
            index[bucket] = items
        return removed

    def _sync_record_after_path_change(
        self,
        kind: str,
        item: dict[str, Any],
        path_key: str,
        new_path: Path,
    ) -> None:
        """路径变更后同步索引记录中的名称和下载地址。"""
        item[path_key] = str(new_path)
        item["name"] = new_path.name

        if kind == "dataset":
            item["file_type"] = new_path.suffix.lstrip(".").lower()
            item["download_url"] = (
                f"/api/workspace/{self.session_id}/uploads/{quote(new_path.name, safe='')}"
            )
        elif kind == "artifact":
            item["download_url"] = self.build_artifact_download_url(new_path.name)
        elif kind == "note":
            item["download_url"] = (
                f"/api/workspace/{self.session_id}/notes/{quote(new_path.name, safe='')}"
            )

    def _upsert_note_record_for_path(self, path: Path) -> dict[str, Any] | None:
        """仅为 notes 根目录下的文件维护 note 记录。"""
        if path.parent != self.notes_dir:
            return None

        index = self._load_index()
        _, existing, path_key = self._find_record_by_path(path, index=index)
        if existing is not None and path_key is not None:
            self._sync_record_after_path_change("note", existing, path_key, path)
            self._save_index(index)
            return existing

        note_record = {
            "id": uuid.uuid4().hex[:12],
            "session_id": self.session_id,
            "name": path.name,
            "type": "note",
            "path": str(path),
            "download_url": f"/api/workspace/{self.session_id}/notes/{quote(path.name, safe='')}",
            "created_at": _now_iso(),
        }
        notes = index.get("notes", [])
        if not isinstance(notes, list):
            notes = []
        notes.append(note_record)
        index["notes"] = notes
        self._save_index(index)
        return note_record

    def get_tree(self) -> dict[str, Any]:
        """返回工作空间目录树。"""
        self.ensure_dirs()

        def build_node(path: Path) -> dict[str, Any]:
            relative = (
                ""
                if path == self.workspace_dir
                else path.relative_to(self.workspace_dir).as_posix()
            )
            if path.is_dir():
                children = [
                    build_node(child)
                    for child in sorted(
                        path.iterdir(),
                        key=lambda item: (not item.is_dir(), item.name.lower()),
                    )
                    if child.name != "index.json"
                ]
                return {
                    "name": path.name if relative else "workspace",
                    "path": relative,
                    "type": "dir",
                    "children": children,
                }

            stat = path.stat()
            return {
                "name": path.name,
                "path": relative,
                "type": "file",
                "size": stat.st_size,
                "updated_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            }

        return build_node(self.workspace_dir)

    def read_file(self, relative_path: str) -> str:
        """读取工作空间中的文本文件。"""
        target = self.resolve_workspace_path(relative_path, allow_missing=False)
        if target.is_dir():
            raise IsADirectoryError(relative_path)
        return target.read_text(encoding="utf-8", errors="replace")

    def save_text_file(self, relative_path: str, content: str) -> Path:
        """按路径保存文本文件。"""
        target = self.resolve_workspace_path(relative_path, allow_missing=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        self._upsert_note_record_for_path(target)
        return target

    def delete_path(self, relative_path: str) -> dict[str, Any]:
        """按路径删除工作空间中的文件或目录，并同步索引。"""
        target = self.resolve_workspace_path(relative_path, allow_missing=False)
        if target == self.workspace_dir:
            raise ValueError("不能删除工作空间根目录")

        index = self._load_index()
        removed_records = self._remove_records_under_path(index, target)

        if target.is_dir():
            shutil.rmtree(target, ignore_errors=False)
        else:
            target.unlink(missing_ok=False)

        self._save_index(index)
        return {
            "path": relative_path,
            "deleted_records": [
                {"kind": kind, "record": record}
                for kind, record in removed_records
            ],
        }

    def rename_path(self, relative_path: str, new_name: str) -> dict[str, Any]:
        """按路径重命名工作空间中的文件，并同步索引。"""
        target = self.resolve_workspace_path(relative_path, allow_missing=False)
        if target == self.workspace_dir:
            raise ValueError("不能重命名工作空间根目录")
        if target.is_dir():
            raise IsADirectoryError(relative_path)
        if not new_name.strip():
            raise ValueError("文件名不能为空")

        safe_name = self.sanitize_filename(new_name, default_name=target.name)
        new_path = target.with_name(safe_name)
        if new_path == target:
            return {
                "old_path": relative_path,
                "new_path": target.relative_to(self.workspace_dir).as_posix(),
                "updated_records": [],
            }
        if new_path.exists():
            raise FileExistsError(new_path.name)

        target.rename(new_path)

        index = self._load_index()
        kind, record, path_key = self._find_record_by_path(new_path, index=index)
        updated_records: list[dict[str, Any]] = []
        if record is None or path_key is None:
            kind, record, path_key = self._find_record_by_path(target, index=index)
        if record is not None and path_key is not None:
            old_record = deepcopy(record)
            self._sync_record_after_path_change(kind, record, path_key, new_path)
            updated_records.append({"kind": kind, "old_record": old_record, "record": record})
            self._save_index(index)

        return {
            "old_path": relative_path,
            "new_path": new_path.relative_to(self.workspace_dir).as_posix(),
            "updated_records": updated_records,
        }

    def batch_download_paths(self, paths: list[str]) -> bytes:
        """按相对路径将工作空间文件打包为 ZIP。"""
        self.ensure_dirs()
        buf = io.BytesIO()
        added = 0
        used_names: set[str] = set()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for raw_path in paths:
                target = self.resolve_workspace_path(raw_path, allow_missing=False)
                if target.is_dir():
                    for child in sorted(target.rglob("*")):
                        if not child.is_file():
                            continue
                        arcname = child.relative_to(self.workspace_dir).as_posix()
                        zf.write(child, arcname)
                        added += 1
                    continue
                base_name = self.sanitize_filename(target.name, default_name=target.name)
                arcname = base_name
                if arcname in used_names:
                    stem = Path(base_name).stem
                    suffix = Path(base_name).suffix
                    index = 2
                    while True:
                        candidate = f"{stem} ({index}){suffix}"
                        if candidate not in used_names:
                            arcname = candidate
                            break
                        index += 1
                used_names.add(arcname)
                zf.write(target, arcname)
                added += 1
        if added == 0:
            return b""
        return buf.getvalue()

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
            "folders": [],
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
            data.setdefault("folders", [])
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
        df = read_dataframe(path, ext)
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
        visibility: str = "deliverable",
    ) -> dict[str, Any]:
        index = self._load_index()
        artifacts = index.get("artifacts", [])
        if not isinstance(artifacts, list):
            artifacts = []
        normalized_path = str(file_path)
        now = _now_iso()
        record: dict[str, Any] = {
            "id": uuid.uuid4().hex[:12],
            "session_id": self.session_id,
            "name": name,
            "type": artifact_type,
            "format": format_hint,
            "path": normalized_path,
            "download_url": self.build_artifact_download_url(name),
            "created_at": now,
            "visibility": visibility,
        }

        # 同一路径（或同名同类型同格式）重复写入时执行 upsert，避免工作区出现重复条目。
        matched = False
        for item in artifacts:
            if not isinstance(item, dict):
                continue
            same_path = str(item.get("path", "")) == normalized_path
            same_identity = (
                str(item.get("name", "")) == name
                and str(item.get("type", "")) == artifact_type
                and str(item.get("format", "")) == str(format_hint)
            )
            if not same_path and not same_identity:
                continue
            item["name"] = name
            item["type"] = artifact_type
            item["format"] = format_hint
            item["path"] = normalized_path
            item["download_url"] = self.build_artifact_download_url(name)
            item["created_at"] = now
            item["visibility"] = visibility
            record = item
            matched = True
            break

        if not matched:
            artifacts.append(record)

        artifacts = self._deduplicate_artifacts(artifacts)
        index["artifacts"] = artifacts
        self._save_index(index)
        return record

    def _artifact_dedup_key(self, item: dict[str, Any]) -> str:
        path_key = str(item.get("path", "")).strip()
        if path_key:
            return f"path:{path_key}"
        name_key = str(item.get("name", "")).strip()
        type_key = str(item.get("type", "")).strip()
        fmt_key = str(item.get("format", "")).strip()
        return f"identity:{name_key}|{type_key}|{fmt_key}"

    def _deduplicate_artifacts(self, artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        unique: dict[str, dict[str, Any]] = {}
        for item in artifacts:
            if not isinstance(item, dict):
                continue
            key = self._artifact_dedup_key(item)
            current = unique.get(key)
            if current is None:
                unique[key] = item
                continue
            old_ts = str(current.get("created_at", ""))
            new_ts = str(item.get("created_at", ""))
            if new_ts >= old_ts:
                unique[key] = item
        return list(unique.values())

    def list_artifacts(self) -> list[dict[str, Any]]:
        index = self._load_index()
        artifacts = index.get("artifacts", [])
        if not isinstance(artifacts, list):
            return []
        result: list[dict[str, Any]] = []
        for item in artifacts:
            if isinstance(item, dict):
                result.append(item)
        result = self._deduplicate_artifacts(result)
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
                    "folder": item.get("folder"),
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
                download_url = self.build_artifact_download_url(suffix)
            files.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "kind": "artifact",
                    "size": size,
                    "created_at": item.get("created_at"),
                    "folder": item.get("folder"),
                    "download_url": download_url,
                    "meta": {
                        "type": item.get("type"),
                        "format": item.get("format"),
                        "versions": item.get("versions", []),
                        "version": item.get("version"),
                        "visibility": item.get("visibility", "deliverable"),
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
                    "folder": item.get("folder"),
                    "download_url": f"/api/workspace/{self.session_id}/notes/{quote(str(item.get('name', '')))}",
                    "meta": {},
                }
            )

        files.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
        return files

    def list_workspace_files_with_paths(self) -> list[dict[str, Any]]:
        """列出工作空间文件，并补充相对路径信息供新版路径式 API 使用。"""
        files = self.list_workspace_files()
        index = self._load_index()
        path_by_id: dict[str, str] = {}

        for _kind, item, path_key in self._iter_index_records(index):
            file_id = str(item.get("id", "")).strip()
            raw_path = str(item.get(path_key, "")).strip()
            if not file_id or not raw_path:
                continue
            try:
                rel_path = Path(raw_path).resolve().relative_to(self.workspace_dir.resolve()).as_posix()
            except Exception:
                continue
            path_by_id[file_id] = rel_path

        enriched: list[dict[str, Any]] = []
        for item in files:
            copied = dict(item)
            file_id = str(copied.get("id", "")).strip()
            if file_id and file_id in path_by_id:
                copied["path"] = path_by_id[file_id]
            enriched.append(copied)
        return enriched

    def search_files_with_paths(self, query: str) -> list[dict[str, Any]]:
        """根据文件名搜索工作空间文件，并补充相对路径。"""
        if not query or not query.strip():
            return self.list_workspace_files_with_paths()

        query_lower = query.strip().lower()
        results = []
        for item in self.list_workspace_files_with_paths():
            name = str(item.get("name", "")).lower()
            if query_lower in name:
                results.append(item)
        return results

    # ---- 文件操作扩展（工作区面板用） ----

    def _find_record_by_id(self, file_id: str) -> tuple[str, dict[str, Any] | None]:
        """根据文件 ID 查找记录，返回 (kind, record) 或 (kind, None)。"""
        index = self._load_index()
        for kind in ("datasets", "artifacts", "notes"):
            for item in index.get(kind, []):
                if isinstance(item, dict) and item.get("id") == file_id:
                    kind_singular = {
                        "datasets": "dataset",
                        "artifacts": "artifact",
                        "notes": "note",
                    }[kind]
                    return kind_singular, item
        return "", None

    def delete_file(self, file_id: str) -> dict[str, Any] | None:
        """删除文件：从索引移除并删除磁盘文件。返回被删除的记录，或 None。"""
        index = self._load_index()
        deleted: dict[str, Any] | None = None

        for kind in ("datasets", "artifacts", "notes"):
            items = index.get(kind, [])
            new_items = []
            for item in items:
                if isinstance(item, dict) and item.get("id") == file_id:
                    deleted = item
                else:
                    new_items.append(item)
            if deleted:
                index[kind] = new_items
                break

        if deleted is None:
            return None

        # 删除磁盘文件
        file_path_str = deleted.get("file_path") or deleted.get("path") or ""
        if file_path_str:
            path = Path(file_path_str)
            if path.exists() and path.is_file():
                path.unlink(missing_ok=True)

        self._save_index(index)
        return deleted

    def rename_file(self, file_id: str, new_name: str) -> dict[str, Any] | None:
        """重命名文件：更新索引中的名称和磁盘文件名。返回更新后的记录。"""
        safe_name = self.sanitize_filename(new_name)
        index = self._load_index()

        for kind in ("datasets", "artifacts", "notes"):
            for item in index.get(kind, []):
                if not isinstance(item, dict) or item.get("id") != file_id:
                    continue

                old_name = item.get("name", "")
                item["name"] = safe_name

                # 移动磁盘文件
                path_key = "file_path" if "file_path" in item else "path"
                old_path_str = item.get(path_key, "")
                if old_path_str:
                    old_path = Path(old_path_str)
                    if old_path.exists() and old_path.is_file():
                        # 保持 ID 前缀（如 dataset_001_xxx.csv → dataset_001_new_name.csv）
                        parent = old_path.parent
                        old_stem = old_path.name
                        # 数据集文件以 id_ 为前缀
                        if kind == "datasets" and old_stem.startswith(file_id + "_"):
                            new_filename = f"{file_id}_{safe_name}"
                        else:
                            new_filename = safe_name
                        new_path = parent / new_filename
                        if new_path != old_path:
                            old_path.rename(new_path)
                            item[path_key] = str(new_path)

                # 更新 download_url
                if kind == "datasets":
                    fname = Path(item.get(path_key, "")).name
                    item["download_url"] = (
                        f"/api/workspace/{self.session_id}/uploads/{quote(fname)}"
                    )
                elif kind == "artifacts":
                    item["download_url"] = self.build_artifact_download_url(safe_name)
                elif kind == "notes":
                    item["download_url"] = (
                        f"/api/workspace/{self.session_id}/notes/{quote(safe_name)}"
                    )

                self._save_index(index)
                return item

        return None

    def get_file_preview(self, file_id: str) -> dict[str, Any] | None:
        """获取文件预览内容。

        - 图片（PNG/JPEG/SVG/GIF）：返回 base64 编码
        - 文本类（TXT/CSV/TSV/JSON/MD/PY 等）：返回完整文本
        - HTML：返回完整内容（用于 iframe 渲染）
        - 其他：返回文件基本信息
        """
        kind, record = self._find_record_by_id(file_id)
        if record is None:
            return None

        return self._build_preview_payload(
            file_id=file_id,
            kind=kind,
            record=record,
        )

    def _build_preview_payload(
        self,
        *,
        file_id: str,
        kind: str,
        record: dict[str, Any],
    ) -> dict[str, Any]:
        """根据索引记录构建统一预览载荷。"""
        path_str = record.get("file_path") or record.get("path") or ""
        if not path_str:
            return {
                "id": file_id,
                "kind": kind,
                "preview_type": "unavailable",
                "message": "文件路径不存在",
            }

        path = Path(path_str)
        if not path.exists() or not path.is_file():
            return {
                "id": file_id,
                "kind": kind,
                "preview_type": "unavailable",
                "message": "文件不存在",
            }

        ext = path.suffix.lower().lstrip(".")
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        file_size = path.stat().st_size

        # 图片类型
        if ext in ("png", "jpg", "jpeg", "gif", "svg", "webp"):
            # 大图片限制（超过 5MB 不做 base64）
            if file_size > 5 * 1024 * 1024:
                return {
                    "id": file_id,
                    "kind": kind,
                    "preview_type": "image_too_large",
                    "name": record.get("name", ""),
                    "size": file_size,
                    "mime_type": mime_type,
                }
            data = base64.b64encode(path.read_bytes()).decode("ascii")
            return {
                "id": file_id,
                "kind": kind,
                "preview_type": "image",
                "name": record.get("name", ""),
                "mime_type": mime_type,
                "data": f"data:{mime_type};base64,{data}",
            }

        # HTML 类型（Plotly 图表等）
        if ext in ("html", "htm"):
            content = path.read_text(encoding="utf-8", errors="replace")
            return {
                "id": file_id,
                "kind": kind,
                "preview_type": "html",
                "name": record.get("name", ""),
                "content": content,
            }

        # Plotly 图表 JSON（.plotly.json）—— 返回 download_url 供前端直接渲染
        if path.name.endswith(".plotly.json"):
            return {
                "id": file_id,
                "kind": kind,
                "preview_type": "plotly_chart",
                "name": record.get("name", ""),
                "download_url": record.get("download_url", ""),
            }

        # 文本类型
        text_exts = {
            "txt",
            "csv",
            "tsv",
            "json",
            "md",
            "py",
            "r",
            "log",
            "yaml",
            "yml",
            "toml",
            "ini",
            "cfg",
        }
        if ext in text_exts:
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                return {
                    "id": file_id,
                    "kind": kind,
                    "preview_type": "error",
                    "message": "无法读取文件",
                }
            total_lines = len(content.splitlines())
            return {
                "id": file_id,
                "kind": kind,
                "preview_type": "text",
                "name": record.get("name", ""),
                "ext": ext,
                "content": content,
                "total_lines": total_lines,
                "preview_lines": total_lines,
            }

        # PDF 类型
        if ext == "pdf":
            return {
                "id": file_id,
                "kind": kind,
                "preview_type": "pdf",
                "name": record.get("name", ""),
                "size": file_size,
                "download_url": record.get("download_url", ""),
            }

        # 其他类型
        return {
            "id": file_id,
            "kind": kind,
            "preview_type": "unsupported",
            "name": record.get("name", ""),
            "ext": ext,
            "size": file_size,
            "mime_type": mime_type,
        }

    def get_file_preview_by_path(self, relative_path: str) -> dict[str, Any]:
        """按路径获取文件预览。"""
        target = self.resolve_workspace_path(relative_path, allow_missing=False)
        if target.is_dir():
            raise IsADirectoryError(relative_path)

        kind, record, _path_key = self._find_record_by_path(target)
        if record is None:
            kind = "file"
            record = {
                "id": relative_path,
                "name": target.name,
                "path": str(target),
                "download_url": (
                    f"/api/workspace/{self.session_id}/download/{quote(relative_path, safe='')}"
                ),
            }
        file_id = str(record.get("id", relative_path))
        return self._build_preview_payload(file_id=file_id, kind=kind, record=record)

    def search_files(self, query: str) -> list[dict[str, Any]]:
        """根据文件名模糊搜索工作空间文件。"""
        if not query or not query.strip():
            return self.list_workspace_files()

        query_lower = query.strip().lower()
        results = []
        for f in self.list_workspace_files():
            name = str(f.get("name", "")).lower()
            if query_lower in name:
                results.append(f)
        return results

    # ---- 代码执行历史持久化 ----

    def save_code_execution(
        self,
        *,
        code: str,
        output: str,
        status: str = "success",
        language: str = "python",
        tool_name: str | None = None,
        tool_args: dict[str, Any] | None = None,
        context_token_count: int | None = None,
        intent: str | None = None,
    ) -> dict[str, Any]:
        """将代码执行记录持久化到 workspace/executions/ 目录。"""
        self.ensure_dirs()
        exec_id = uuid.uuid4().hex[:12]
        record: dict[str, Any] = {
            "id": exec_id,
            "session_id": self.session_id,
            "code": code,
            "output": output,
            "status": status,
            "language": language,
            "created_at": _now_iso(),
        }
        if tool_name is not None:
            record["tool_name"] = tool_name
        if tool_args is not None:
            record["tool_args"] = tool_args
        if context_token_count is not None:
            record["context_token_count"] = context_token_count
        if intent:
            record["intent"] = intent
        exec_path = self.executions_dir / f"{exec_id}.json"
        exec_path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return record

    def list_code_executions(self, limit: int = 50) -> list[dict[str, Any]]:
        """从磁盘加载执行历史，按时间倒序返回。"""
        self.ensure_dirs()
        records: list[dict[str, Any]] = []
        for path in self.executions_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    records.append(data)
            except Exception:
                continue
        records.sort(key=lambda r: str(r.get("created_at", "")), reverse=True)
        return records[:limit]

    def move_path_to_folder(
        self,
        relative_path: str,
        folder_id: str | None,
    ) -> dict[str, Any]:
        """按路径将索引中的文件移动到指定文件夹。"""
        target = self.resolve_workspace_path(relative_path, allow_missing=False)
        kind, record, _path_key = self._find_record_by_path(target)
        if record is None:
            raise FileNotFoundError(relative_path)

        index = self._load_index()
        _, stored_record, _ = self._find_record_by_path(target, index=index)
        if stored_record is None:
            raise FileNotFoundError(relative_path)

        stored_record["folder"] = folder_id
        self._save_index(index)
        return {
            "kind": kind,
            "record": stored_record,
        }

    # ---- 批量下载 ----

    def batch_download(self, file_ids: list[str]) -> bytes:
        """将选中文件打包为 ZIP，返回 ZIP 文件的字节内容。"""
        buf = io.BytesIO()
        used_names: set[str] = set()
        added = 0
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for fid in file_ids:
                _, record = self._find_record_by_id(fid)
                if record is None:
                    continue
                path_str = record.get("file_path") or record.get("path") or ""
                if not path_str:
                    continue
                path = Path(path_str)
                if path.exists() and path.is_file():
                    base_name = self.sanitize_filename(
                        str(record.get("name", path.name)), default_name=path.name
                    )
                    arcname = base_name
                    if arcname in used_names:
                        stem = Path(base_name).stem
                        suffix = Path(base_name).suffix
                        idx = 2
                        while True:
                            candidate = f"{stem} ({idx}){suffix}"
                            if candidate not in used_names:
                                arcname = candidate
                                break
                            idx += 1
                    used_names.add(arcname)
                    zf.write(path, arcname)
                    added += 1
        if added == 0:
            return b""
        return buf.getvalue()

    # ---- 文件版本控制 ----

    def add_version(self, file_id: str, new_path: Path) -> dict[str, Any] | None:
        """为已有产物添加新版本。旧版本保留在 versions 列表中。"""
        index = self._load_index()
        max_versions = 10

        for kind in ("artifacts",):
            for item in index.get(kind, []):
                if not isinstance(item, dict) or item.get("id") != file_id:
                    continue

                # 初始化 versions 数组
                versions = item.setdefault("versions", [])

                # 将当前版本加入历史
                current_path = item.get("path", "")
                if current_path:
                    versions.append(
                        {
                            "path": current_path,
                            "created_at": item.get("created_at", _now_iso()),
                            "version": len(versions) + 1,
                        }
                    )

                # 更新为新版本
                item["path"] = str(new_path)
                item["created_at"] = _now_iso()
                item["version"] = len(versions) + 1

                # 限制版本数量
                if len(versions) > max_versions:
                    # 删除最旧的版本文件
                    for old in versions[: len(versions) - max_versions]:
                        old_path = Path(old.get("path", ""))
                        if old_path.exists():
                            old_path.unlink(missing_ok=True)
                    item["versions"] = versions[-max_versions:]

                self._save_index(index)
                return item

        return None

    def get_file_versions(self, file_id: str) -> list[dict[str, Any]]:
        """获取文件的版本历史。"""
        index = self._load_index()
        for kind in ("artifacts",):
            for item in index.get(kind, []):
                if isinstance(item, dict) and item.get("id") == file_id:
                    versions = item.get("versions", [])
                    return (
                        cast(list[dict[str, Any]], versions) if isinstance(versions, list) else []
                    )
        return []

    # ---- Agent 自定义文件夹 ----

    def create_folder(self, name: str, parent: str | None = None) -> dict[str, Any]:
        """创建自定义文件夹。"""
        index = self._load_index()
        folders = index.setdefault("folders", [])

        folder_id = uuid.uuid4().hex[:12]
        folder = {
            "id": folder_id,
            "name": name,
            "parent": parent,
            "created_at": _now_iso(),
        }
        folders.append(folder)
        self._save_index(index)
        return folder

    def list_folders(self) -> list[dict[str, Any]]:
        """列出所有自定义文件夹。"""
        index = self._load_index()
        folders = index.get("folders", [])
        return [f for f in folders if isinstance(f, dict)]

    def move_file(self, file_id: str, folder_id: str | None) -> dict[str, Any] | None:
        """将文件移动到指定文件夹（folder_id=None 移到根目录）。"""
        index = self._load_index()
        for kind in ("datasets", "artifacts", "notes"):
            for item in index.get(kind, []):
                if isinstance(item, dict) and item.get("id") == file_id:
                    item["folder"] = folder_id
                    self._save_index(index)
                    return item
        return None
