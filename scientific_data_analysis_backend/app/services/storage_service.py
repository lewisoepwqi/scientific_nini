"""
导出存储辅助方法。
"""
from pathlib import Path

from app.core.config import settings


def get_export_root() -> Path:
    """获取导出目录根路径。"""
    return Path(settings.UPLOAD_DIR) / "exports"


def build_export_path(export_id: str) -> Path:
    """构建分享包文件路径。"""
    return get_export_root() / f"{export_id}.json"


def ensure_export_dir() -> None:
    """确保导出目录存在。"""
    get_export_root().mkdir(parents=True, exist_ok=True)
