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
        record = {
            "id": uuid.uuid4().hex[:12],
            "session_id": self.session_id,
            "name": name,
            "type": artifact_type,
            "format": format_hint,
            "path": str(file_path),
            "download_url": f"/api/artifacts/{self.session_id}/{name}",
            "created_at": _now_iso(),
            "visibility": visibility,
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
                # 统一归一化为“编码一次”的文件名，避免 %25 双重编码。
                try:
                    normalized_suffix = quote(unquote(suffix), safe="")
                except Exception:
                    normalized_suffix = quote(suffix, safe="")
                download_url = f"/api/artifacts/{self.session_id}/{normalized_suffix}"
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
                    item["download_url"] = f"/api/artifacts/{self.session_id}/{quote(safe_name)}"
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
        - 文本类（TXT/CSV/TSV/JSON/MD/PY 等）：返回前 50 行文本
        - HTML：返回完整内容（用于 iframe 渲染）
        - 其他：返回文件基本信息
        """
        kind, record = self._find_record_by_id(file_id)
        if record is None:
            return None

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
            lines = []
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    for i, line in enumerate(f):
                        if i >= 50:
                            break
                        lines.append(line.rstrip("\n"))
            except Exception:
                return {
                    "id": file_id,
                    "kind": kind,
                    "preview_type": "error",
                    "message": "无法读取文件",
                }
            return {
                "id": file_id,
                "kind": kind,
                "preview_type": "text",
                "name": record.get("name", ""),
                "ext": ext,
                "content": "\n".join(lines),
                "total_lines": sum(1 for _ in open(path, "r", encoding="utf-8", errors="replace")),
                "preview_lines": len(lines),
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
