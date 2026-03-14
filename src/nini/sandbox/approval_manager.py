"""沙盒扩展包永久审批持久化。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterable

from nini.config import settings
from nini.sandbox.policy import REVIEWABLE_IMPORT_ROOTS, normalize_reviewable_import_roots

logger = logging.getLogger(__name__)


class SandboxApprovalManager:
    """管理永久级沙盒扩展包审批。"""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        if self._path is not None:
            return self._path
        return settings.data_dir / "sandbox" / "approved_imports.json"

    def load_approved_imports(self) -> set[str]:
        """读取永久审批集合；异常时按 fail-secure 回退为空集合。"""
        path = self.path
        if not path.exists():
            return set()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("读取永久沙盒审批文件失败，按未授权处理: %s", exc)
            return set()
        if not isinstance(data, dict):
            return set()
        approved = data.get("approved_imports")
        return normalize_reviewable_import_roots(approved if isinstance(approved, list) else [])

    def grant_approved_imports(self, packages: Iterable[str]) -> set[str]:
        """写入永久审批集合，仅接受 reviewable 白名单中的根模块。"""
        approved = self.load_approved_imports()
        normalized = normalize_reviewable_import_roots(packages)
        approved.update(normalized)
        self._write_approved_imports(approved)
        return set(approved)

    def _write_approved_imports(self, packages: Iterable[str]) -> None:
        normalized = sorted(normalize_reviewable_import_roots(packages))
        payload: dict[str, Any] = {
            "approved_imports": normalized,
            "reviewable_import_roots": sorted(REVIEWABLE_IMPORT_ROOTS),
        }
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(path)


approval_manager = SandboxApprovalManager()
